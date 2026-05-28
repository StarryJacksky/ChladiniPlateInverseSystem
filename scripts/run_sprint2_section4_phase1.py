"""Sprint 2 §4 Phase 1 — Modal-calibrated COMSOL drive.

Algorithm:
1. Load a W10 candidate design (H, theta) and its COMSOL eigenfrequency data.
2. Compute each COMSOL eigenmode's "IC-likeness" — i.e. how well a Gaussian-blurred
   |mode_shape| matches the IC target.
3. Pick the top-K most-IC-like COMSOL modes and drive COMSOL forced response at
   those eigenfrequencies with weights ∝ IC-likeness score.
4. Compute composite enrichment vs the 26-freq sweep baseline and the original
   surrogate-frequency drive.

This Phase 1 does NOT re-optimise H+θ. It only changes the COMSOL drive frequency
list. Speed: ~5 minutes (K≤6 COMSOL forced-response runs at 30s each).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import time
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, gaussian_filter

from src.config import load_config
from src.scoring.recognisability_score import (
    chladni_powder_density,
    coverage_recall,
    recognisability_score_grid,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sprint 2 §4 Phase 1: modal-calibrated COMSOL drive.")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--candidate", default="w10_ic_tier2_sr12", help="W10 candidate directory.")
    p.add_argument("--eigfreq-export", default="data/comsol_exports/modal_calibration_w10_tier2/eigenfrequency", help="Existing COMSOL eigenfrequency export dir for this design.")
    p.add_argument("--top-k", type=int, default=6, help="Number of best-MAC-to-IC modes to drive.")
    p.add_argument("--off-resonance-hz", type=float, default=1.5, help="Drive slightly off-resonance to avoid singular direct solver (default +1.5 Hz).")
    p.add_argument("--ic-likeness-power", type=float, default=2.0, help="Weight = IC_score^power; >1 emphasises top modes.")
    p.add_argument("--mode-shape-sigma-rel", type=float, default=0.05, help="Gaussian blur applied to |mode shape| when computing IC-likeness.")
    p.add_argument("--target-binary", default="data/processed_targets/target_binary.npy")
    p.add_argument("--stiffness-ratio", type=float, default=12.0)
    p.add_argument("--shear-ratio", type=float, default=1.5)
    p.add_argument("--image-size", type=int, default=256)
    p.add_argument("--n-modes", type=int, default=30)
    p.add_argument("--output-dir", default="reports/sprint2_section4_phase1")
    p.add_argument("--skip-comsol", action="store_true", help="Skip COMSOL run; just compute selection + reuse existing exports.")
    p.add_argument("--clean", action="store_true", help="Remove existing variant dirs before re-running.")
    p.add_argument("--variant-prefix", default="s4p1", help="Variant directory prefix to avoid collisions across material tiers.")
    return p.parse_args()


def downsample_comsol_xy_to_grid(x_m: np.ndarray, y_m: np.ndarray, values: np.ndarray, image_size: int, plate_length_mm: float) -> np.ndarray:
    """Bin irregular COMSOL samples onto image_size grid, with dilation hole-fill."""
    half_m = float(plate_length_mm) / 2000.0
    edges = np.linspace(-half_m, half_m, image_size + 1)
    col = np.clip(np.searchsorted(edges, x_m, side="right") - 1, 0, image_size - 1)
    row_from_bottom = np.clip(np.searchsorted(edges, y_m, side="right") - 1, 0, image_size - 1)
    row = image_size - 1 - row_from_bottom
    accum = np.zeros((image_size, image_size), dtype=np.float64)
    counts = np.zeros((image_size, image_size), dtype=np.int64)
    np.add.at(accum, (row, col), values)
    np.add.at(counts, (row, col), 1)
    safe = np.where(counts > 0, counts, 1)
    grid = accum / safe
    mask = counts > 0
    for _ in range(8):
        if mask.all(): break
        expanded = binary_dilation(mask)
        new = expanded & ~mask
        if not new.any(): break
        for r, c in zip(*np.where(new)):
            rmin, rmax = max(r - 1, 0), min(r + 2, image_size)
            cmin, cmax = max(c - 1, 0), min(c + 2, image_size)
            nb = grid[rmin:rmax, cmin:cmax]
            nbm = mask[rmin:rmax, cmin:cmax]
            if nbm.any():
                grid[r, c] = nb[nbm].mean()
        mask = mask | new
    return grid


def load_comsol_eigenmodes(eig_dir: Path, n_modes: int, image_size: int, plate_length_mm: float) -> tuple[np.ndarray, list[np.ndarray]]:
    """Returns (freqs[n], modes[n] as image_size grids)."""
    eig_csv = eig_dir / "eigenfrequencies.csv"
    arr = np.loadtxt(eig_csv, delimiter=",", skiprows=1)
    if arr.ndim == 1: arr = arr.reshape(-1, 2)
    n_modes = min(n_modes, len(arr))
    freqs = arr[:n_modes, 1].astype(float)
    xy = np.loadtxt(eig_dir / "mode_xy.csv", delimiter=",", skiprows=1)
    x, y = xy[:, 0], xy[:, 1]
    modes: list[np.ndarray] = []
    for k in range(1, n_modes + 1):
        m = np.loadtxt(eig_dir / f"mode_{k:03d}.csv", delimiter=",", skiprows=1)
        if m.ndim == 1: m = m.reshape(-1, 2)
        # Take |w| as the powder driver (real eigenmodes for undamped; sign ambiguous, |·| is the right invariant for nodal-line patterns)
        amp = np.sqrt(m[:, 0] ** 2 + m[:, 1] ** 2)
        modes.append(downsample_comsol_xy_to_grid(x, y, amp, image_size, plate_length_mm))
    return freqs, modes


def resize_target_to_size(target_binary: np.ndarray, image_size: int) -> np.ndarray:
    if target_binary.shape == (image_size, image_size):
        return target_binary.astype(bool)
    img = Image.fromarray((target_binary.astype(np.uint8) * 255))
    img = img.resize((image_size, image_size), resample=Image.NEAREST)
    return (np.array(img) > 127).astype(bool)


def compute_ic_likeness(mode_grid: np.ndarray, target_binary: np.ndarray, sigma_rel: float = 0.05) -> dict[str, float]:
    """How well does a Gaussian-blurred |mode| match the IC target?
    Returns enrichment, recall, contrast, and a combined "ic_likeness" score."""
    amp = np.abs(mode_grid).astype(np.float64)
    amp = amp / max(float(np.max(amp)), 1e-30)
    scores = recognisability_score_grid(amp, target_binary.astype(bool), sigma_rel=float(sigma_rel), percentile=20.0)
    recall = coverage_recall(amp, target_binary.astype(bool), percentile=20.0)
    enrich = float(scores["enrichment_factor"])
    contrast = float(scores["gaussian_contrast"])
    # Combined: log enrichment + recall (recall is bounded; log enrich is unbounded)
    ic_likeness = float(np.log(max(enrich, 0.01))) + 0.5 * float(recall)
    return {
        "enrichment": enrich,
        "recall": float(recall),
        "contrast": contrast,
        "ic_likeness": ic_likeness,
    }


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    plate_length_mm = float(config["project"]["plate_length_mm"])
    image_size = int(args.image_size)

    output_dir = Path(args.output_dir) / args.candidate
    output_dir.mkdir(parents=True, exist_ok=True)

    # === Load IC target + downsample to image_size ===
    target_binary = np.load(args.target_binary).astype(bool)
    target_at_image = resize_target_to_size(target_binary, image_size)

    # === Load COMSOL eigenmodes ===
    eig_dir = Path(args.eigfreq_export)
    print(f"Loading COMSOL eigenmodes from {eig_dir}")
    comsol_freqs, comsol_modes = load_comsol_eigenmodes(eig_dir, args.n_modes, image_size, plate_length_mm)
    print(f"  loaded {len(comsol_freqs)} modes; freq range {comsol_freqs.min():.1f}–{comsol_freqs.max():.1f} Hz")

    # === Compute IC-likeness for each COMSOL eigenmode ===
    print(f"\nIC-likeness ranking (top {min(15, len(comsol_freqs))}):")
    rankings = []
    for k, (f, m) in enumerate(zip(comsol_freqs, comsol_modes)):
        scores = compute_ic_likeness(m, target_at_image, sigma_rel=float(args.mode_shape_sigma_rel))
        rankings.append({"mode_index": k + 1, "frequency_hz": float(f), **scores})
    ranked = sorted(rankings, key=lambda r: -r["ic_likeness"])
    print(f"{'rank':>4} {'mode':>5} {'freq_hz':>8} {'enrich':>7} {'recall':>7} {'ic_score':>9}")
    for i, r in enumerate(ranked[:15]):
        print(f"{i+1:>4} {r['mode_index']:>5} {r['frequency_hz']:>8.2f} {r['enrichment']:>7.3f} {r['recall']:>7.3f} {r['ic_likeness']:>9.3f}")

    # === Pick top-K and build drive list ===
    K = max(1, int(args.top_k))
    top = ranked[:K]
    enrichments = np.array([t["enrichment"] for t in top], dtype=np.float64)
    weights_raw = enrichments ** float(args.ic_likeness_power)
    weights_raw = np.where(np.isfinite(weights_raw) & (weights_raw > 0), weights_raw, 1e-6)
    weights = weights_raw / weights_raw.sum()
    eig_freqs_selected = [float(t["frequency_hz"]) for t in top]
    drive_freqs = [f + float(args.off_resonance_hz) for f in eig_freqs_selected]
    drive_modes = [int(t["mode_index"]) for t in top]
    print(f"\nSelected top-{K} drive (eig_freq | drive_freq=eig+{args.off_resonance_hz:.1f}Hz, mode, weight):")
    for ef, df, mi, w in zip(eig_freqs_selected, drive_freqs, drive_modes, weights):
        print(f"  eig={ef:7.2f}  drive={df:7.2f} Hz  mode={mi}  weight={w:.4f}")

    # === Run COMSOL forced response at calibrated freqs (delegate to run_w10_comsol_validation) ===
    variant_prefix = str(args.variant_prefix)
    if not args.skip_comsol:
        print(f"\nLaunching COMSOL forced response at {len(drive_freqs)} calibrated freqs...")
        from subprocess import run as sub_run
        cmd_args = [
            ".venv/bin/python", "scripts/run_w10_comsol_validation.py",
            "--candidate", args.candidate,
            "--material-mode", "orthotropic_shell",
            "--use-uniform-actuator",
            "--stiffness-ratio", str(args.stiffness_ratio),
            "--shear-ratio", str(args.shear_ratio),
            "--frequencies", ",".join(f"{f:.4f}" for f in drive_freqs),
            "--variant-prefix", variant_prefix,
            "--image-size", str(image_size),
            "--output-dir", str(Path(args.output_dir).resolve()),
        ]
        if args.clean:
            # Remove old variant dirs
            candidates_root = Path(config["paths"]["candidates_dir"])
            for f in drive_freqs:
                vid = f"{variant_prefix}_{args.candidate}_comsol_f{f:.1f}Hz".replace(".", "p")
                vd = candidates_root / vid
                if vd.exists():
                    shutil.rmtree(vd)
        # NOTE: run_w10_comsol_validation will compute its own composite using the
        # SURROGATE weights (read from W10 summary) when --frequencies is provided.
        # We want to use our OWN weights, so do composite re-calculation below.
        t0 = time.time()
        proc = sub_run(cmd_args, check=False)
        print(f"COMSOL run finished in {time.time()-t0:.1f}s with rc={proc.returncode}")
        if proc.returncode != 0:
            raise RuntimeError("run_w10_comsol_validation.py failed; see logs.")

    # === Re-compute composite with OUR calibrated weights ===
    from src.comsol.discovery import config_with_runtime_discovery
    runtime_config, _, _ = config_with_runtime_discovery(config)
    comsol_exports_dir = Path(runtime_config["paths"]["comsol_exports_dir"])
    complex_fields: list[np.ndarray] = []
    for f in drive_freqs:
        vid = f"{variant_prefix}_{args.candidate}_comsol_f{f:.1f}Hz".replace(".", "p")
        export_dir = comsol_exports_dir / vid / "forced_response"
        response_csv = export_dir / "forced_response.csv"
        if not response_csv.exists():
            raise FileNotFoundError(f"Missing {response_csv}")
        # Reuse the loader from run_w10_comsol_validation
        from scripts.run_w10_comsol_validation import load_forced_response_csv
        amp = load_forced_response_csv(response_csv, image_size, plate_length_mm)
        complex_fields.append(amp)

    composite_amp = np.zeros_like(np.abs(complex_fields[0]))
    for w, field in zip(weights, complex_fields):
        composite_amp += float(w) * np.abs(field) ** 2
    composite_amp = np.sqrt(np.clip(composite_amp, 0.0, None))

    # === Score the composite ===
    s = recognisability_score_grid(composite_amp, target_at_image, sigma_rel=0.05, percentile=20.0)
    recall = float(coverage_recall(composite_amp, target_at_image, percentile=20.0))
    metrics = {
        "enrichment_factor": float(s["enrichment_factor"]),
        "coverage_recall": recall,
        "gaussian_contrast": float(s["gaussian_contrast"]),
        "directional_alignment": float(s["directional_alignment"]),
        "composite_recognisability": float(s["composite_recognisability"]),
    }
    print(f"\n=== §4 PHASE 1 COMPOSITE METRICS (modal-calibrated drive) ===")
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}")

    # === Save artefacts ===
    np.save(output_dir / "composite_s4p1.npy", composite_amp)
    np.save(output_dir / "target_at_image.npy", target_at_image.astype(np.uint8))
    summary = {
        "version": "sprint2_section4_phase1",
        "candidate": args.candidate,
        "drive_freqs_hz": drive_freqs,
        "drive_mode_indices": drive_modes,
        "drive_weights": weights.tolist(),
        "all_comsol_ic_rankings": ranked,
        "metrics": metrics,
        "comparison": {
            "baseline_w8_comsol_enrichment": 1.75,
            "w10_tier2_isotropic_comsol_enrichment": 2.41,
            "w10_tier2_orthotropic_sweep_composite": 1.60,
            "s4p1_modal_calibrated_enrichment": metrics["enrichment_factor"],
        },
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nArtefacts:")
    print(f"  {output_dir/'composite_s4p1.npy'}")
    print(f"  {output_dir/'summary.json'}")


if __name__ == "__main__":
    main()
