"""End-to-end COMSOL comparison for W10 validation.

Runs baseline (W8 calibrated_six_v1) and W10 tier1/tier2 candidates through the
SAME COMSOL pipeline (isotropic E_iso, uniform single-actuator wide-Gaussian load
to mimic the W10 surrogate's base acceleration), then aggregates a composite RMS
amplitude per candidate from each candidate's design frequencies (weighted).

Note: this is the *isotropic* COMSOL test. Without true orthotropic shell, the
θ-induced D4 breaking is NOT captured in COMSOL. The orthotropic shell injection
attempt is preserved in comsol_templates/apply_orthotropic_shell.m for Sprint 2 §3.

Outputs reports/w10_comsol_validation/final_compare/:
  - composites.npy (3 × 256 × 256 stack)
  - summary.json
  - final_compare.png  (target + 3 powders side-by-side)
  - final_compare_trajectory.png  (bar metrics chart)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np

from src.comsol.credentials import ensure_comsol_credentials
from src.comsol.discovery import config_with_runtime_discovery
from src.comsol.export_parameters import export_candidate_for_comsol
from src.comsol.run_livelink import (
    DEFAULT_FORCED_RUNNER_PATH,
    DEFAULT_MATLAB_PATH,
    apply_comsol_server_environment,
    matlab_path_from_comsol_command,
    matlab_quote,
    run_command_streamed,
)
from src.comsol.server import ensure_comsol_server
from src.config import load_config
from src.scoring.recognisability_score import (
    chladni_powder_density,
    coverage_recall,
    recognisability_score_grid,
)


CANDIDATE_DEFS = {
    "baseline_w8": {
        "label": "W8 baseline (isotropic optim, calibrated 6-actuator)",
        "source_dir": "candidates/mosaic_z_candidate_151_calibrated_six_v1",
        "frequencies_hz": [796.96],
        "weights": [1.0],
        "stiffness_ratio": 1.0,
        "shear_ratio": 1.0,
        "theta_csv": None,
    },
    "w10_tier1_sr3": {
        "label": "W10 tier1 (CF-PETG sr=3.0)",
        "source_dir": "candidates/w10_ic_tier1_sr3",
        "frequencies_hz": None,
        "weights": None,
        "stiffness_ratio": 3.0,
        "shear_ratio": 0.85,
        "theta_csv": "theta_continuous_rad.csv",
    },
    "w10_tier2_sr12": {
        "label": "W10 tier2 (Continuous CF sr=12.0)",
        "source_dir": "candidates/w10_ic_tier2_sr12",
        "frequencies_hz": None,
        "weights": None,
        "stiffness_ratio": 12.0,
        "shear_ratio": 0.55,
        "theta_csv": "theta_continuous_rad.csv",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="W10 COMSOL comparison (baseline vs tier1 vs tier2).")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output-dir", default="reports/w10_comsol_validation/final_compare")
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--damping-ratio", type=float, default=0.02)
    parser.add_argument("--force-sigma-mm", type=float, default=200.0, help="Wide Gaussian to approximate uniform pressure.")
    parser.add_argument("--top-n", type=int, default=3, help="Top-N weighted W10 frequencies to actually run.")
    parser.add_argument("--baseline-w8-id", default="mosaic_z_candidate_151_calibrated_six_v1")
    parser.add_argument("--skip-comsol", action="store_true", help="Re-aggregate only.")
    parser.add_argument("--force-run", action="store_true")
    return parser.parse_args()


def write_uniform_actuator_csv(output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as f:
        f.write("id,x_mm,y_mm,amplitude,phase_deg\n")
        f.write("1,0.0,0.0,1.0,0.0\n")


def write_frequency_csv(path: Path, drive_frequency_hz: float, damping_ratio: float, force_sigma_mm: float) -> None:
    import csv
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["drive_frequency_hz", "damping_ratio", "force_sigma_mm"])
        writer.writeheader()
        writer.writerow({
            "drive_frequency_hz": float(drive_frequency_hz),
            "damping_ratio": float(damping_ratio),
            "force_sigma_mm": float(force_sigma_mm),
        })


def write_baseline_material_csv(material: dict, output_path: Path) -> None:
    E_iso = float(material["youngs_modulus_pa"])
    rows = [
        ("mat_density", float(material["density_kg_m3"]), "kg/m^3"),
        ("mat_poisson_ratio", float(material["poisson_ratio"]), "1"),
        ("mat_youngs_modulus", E_iso, "Pa"),
        ("mat_thermal_conductivity", float(material.get("thermal_conductivity_w_mk", 0.2)), "W/(m*K)"),
        ("mat_heat_capacity", float(material.get("heat_capacity_j_kgk", 1500.0)), "J/(kg*K)"),
        ("mat_thermal_expansion", float(material.get("thermal_expansion_1_k", 8.0e-5)), "1/K"),
    ]
    with output_path.open("w", encoding="utf-8") as f:
        f.write("name,value,unit\n")
        for name, value, unit in rows:
            f.write(f"{name},{float(value):.12g},{unit}\n")


def prepare_variant_dir(
    candidate_id: str,
    candidate_def: dict,
    drive_frequency_hz: float,
    output_candidate_dir: Path,
    config_paths: dict,
    material: dict,
    damping_ratio: float,
    force_sigma_mm: float,
) -> None:
    if output_candidate_dir.exists():
        shutil.rmtree(output_candidate_dir)
    output_candidate_dir.mkdir(parents=True)
    source_dir = Path(candidate_def["source_dir"])
    shutil.copy(source_dir / "H.csv", output_candidate_dir / "H.csv")
    baseline_dir = config_paths["candidates"] / "mosaic_z_candidate_151_calibrated_six_v1"
    for filename in ["support_parameters.csv", "topology_primitives.csv", "design_variable_parameters.csv"]:
        src = baseline_dir / filename
        if src.exists():
            shutil.copy(src, output_candidate_dir / filename)
    write_uniform_actuator_csv(output_candidate_dir / "actuator_parameters.csv")
    export_candidate_for_comsol(output_candidate_dir, material)
    write_baseline_material_csv(material, output_candidate_dir / "material_parameters.csv")
    write_frequency_csv(output_candidate_dir / "frequency_parameters.csv", drive_frequency_hz, damping_ratio, force_sigma_mm)
    metadata = {
        "candidate_kind": candidate_id,
        "label": candidate_def["label"],
        "drive_frequency_hz": float(drive_frequency_hz),
        "stiffness_ratio_design": float(candidate_def["stiffness_ratio"]),
        "shear_ratio_design": float(candidate_def["shear_ratio"]),
        "actuator_pattern": "single_center_uniform",
        "material_mode": "isotropic_baseline",
    }
    (output_candidate_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def run_matlab(runtime_config: dict, candidate_dir: Path, export_dir: Path) -> int:
    comsol_config = runtime_config.get("comsol", {})
    matlab = str(comsol_config.get("matlab_path", DEFAULT_MATLAB_PATH))
    model = Path(comsol_config.get("model_path", "comsol_templates/Chladni_15x15_bound.mph"))
    runner = Path(comsol_config.get("forced_response_runner_path", DEFAULT_FORCED_RUNNER_PATH))
    runner_dir = runner.parent.resolve()
    mli_path = matlab_path_from_comsol_command(comsol_config.get("comsol_command_path", ""))
    parts: list[str] = []
    if mli_path is not None:
        parts.append(f"setenv('COMSOL_MLI_PATH',{matlab_quote(mli_path)})")
        parts.append(f"addpath({matlab_quote(mli_path)})")
    parts.append(f"addpath({matlab_quote(runner_dir)})")
    parts.append(
        f"run_chladni_forced_response({matlab_quote(model.resolve())},{matlab_quote(candidate_dir.resolve())},{matlab_quote(export_dir.resolve())})"
    )
    command = [matlab, "-nosplash", "-noFigureWindows", "-sd", str(Path.cwd()), "-batch", "; ".join(parts)]
    log_path = export_dir / "livelink_forced_response.log"
    timeout_s = float(comsol_config.get("livelink_timeout_s", 7200))
    rc, _ = run_command_streamed(command, log_path, timeout_s=timeout_s)
    return rc


def downsample_to_grid(samples_x: np.ndarray, samples_y: np.ndarray, values: np.ndarray, image_size: int, plate_length_mm: float) -> np.ndarray:
    half_m = float(plate_length_mm) / 2000.0
    edges = np.linspace(-half_m, half_m, image_size + 1)
    col_idx = np.clip(np.searchsorted(edges, samples_x, side="right") - 1, 0, image_size - 1)
    row_idx_from_bottom = np.clip(np.searchsorted(edges, samples_y, side="right") - 1, 0, image_size - 1)
    row_idx = image_size - 1 - row_idx_from_bottom
    accum = np.zeros((image_size, image_size), dtype=np.complex128)
    counts = np.zeros((image_size, image_size), dtype=np.int64)
    np.add.at(accum, (row_idx, col_idx), values)
    np.add.at(counts, (row_idx, col_idx), 1)
    safe_counts = np.where(counts > 0, counts, 1)
    grid = accum / safe_counts
    if (counts == 0).any():
        mask = counts > 0
        filled = grid.copy()
        for _ in range(8):
            new_cells = ~mask
            if not new_cells.any():
                break
            for r, c in zip(*np.where(new_cells)):
                rmin, rmax = max(r - 1, 0), min(r + 2, image_size)
                cmin, cmax = max(c - 1, 0), min(c + 2, image_size)
                neighborhood_mask = mask[rmin:rmax, cmin:cmax]
                if neighborhood_mask.any():
                    filled[r, c] = filled[rmin:rmax, cmin:cmax][neighborhood_mask].mean()
                    mask[r, c] = True
            grid = filled
        grid = filled
    return grid


def load_forced_response_csv(response_csv: Path, image_size: int, plate_length_mm: float) -> np.ndarray:
    import csv
    rows = []
    with response_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            x = float(row.get("x", "0"))
            y = float(row.get("y", "0"))
            wr = float(row.get("w_real", "0"))
            wi = float(row.get("w_imag", "0"))
            rows.append((x, y, complex(wr, wi)))
    if not rows:
        raise RuntimeError(f"Empty forced response CSV: {response_csv}")
    xs = np.array([r[0] for r in rows], dtype=np.float64)
    ys = np.array([r[1] for r in rows], dtype=np.float64)
    ws = np.array([r[2] for r in rows], dtype=np.complex128)
    return downsample_to_grid(xs, ys, ws, image_size, plate_length_mm)


def composite_rms(fields: list[np.ndarray], weights: np.ndarray) -> np.ndarray:
    weights = np.asarray(weights, dtype=np.float64)
    weights = weights / max(float(np.sum(weights)), 1.0e-30)
    sq = np.zeros_like(fields[0], dtype=np.float64)
    for fld, w in zip(fields, weights):
        sq += float(w) * np.abs(fld).astype(np.float64) ** 2
    return np.sqrt(np.clip(sq, 0.0, None))


def get_top_n_frequencies(source_dir: Path, top_n: int) -> tuple[list[float], list[float]]:
    summary_path = source_dir / "w10_optimization_summary.json"
    if summary_path.exists():
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        freqs = list(data["frequencies_hz"])
        weights = list(data["weights"])
    else:
        freqs_arr = np.loadtxt(source_dir / "frequencies_hz.csv", delimiter=",", skiprows=1)
        weights_arr = np.loadtxt(source_dir / "weights.csv", delimiter=",", skiprows=1)
        freqs = freqs_arr.tolist()
        weights = weights_arr.tolist()
    order = np.argsort(np.array(weights))[::-1]
    top_idx = sorted(order[: max(1, top_n)])
    return [float(freqs[i]) for i in top_idx], [float(weights[i]) for i in top_idx]


def evaluate_metrics(target_binary: np.ndarray, composite_amp: np.ndarray, image_size: int) -> dict[str, float]:
    image_target = target_binary
    if image_target.shape != composite_amp.shape:
        from PIL import Image
        tgt = Image.fromarray((image_target.astype(np.uint8) * 255))
        tgt = tgt.resize((image_size, image_size), resample=Image.NEAREST)
        image_target = (np.array(tgt) > 127).astype(bool)
    powder = chladni_powder_density(composite_amp, sigma_rel=0.05)
    scores = recognisability_score_grid(composite_amp, image_target, sigma_rel=0.05, percentile=20.0)
    return {
        "enrichment_factor": float(scores["enrichment_factor"]),
        "coverage_recall": float(scores["coverage_recall"]),
        "gaussian_contrast": float(scores["gaussian_contrast"]),
        "directional_alignment": float(scores["directional_alignment"]),
        "composite_recognisability": float(scores["composite_recognisability"]),
        "powder_max": float(np.max(powder)),
        "powder_mean": float(np.mean(powder)),
        "target_pixels": int(image_target.sum()),
    }


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)
    config_paths = {
        "candidates": Path(runtime_config["paths"]["candidates_dir"]),
        "comsol_exports": Path(runtime_config["paths"]["comsol_exports_dir"]),
        "processed_targets": Path(runtime_config["paths"]["processed_targets_dir"]),
    }
    plate_length_mm = float(runtime_config["project"]["plate_length_mm"])
    image_size = int(args.image_size)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = np.load(config_paths["processed_targets"] / "target_binary.npy").astype(bool)

    if not args.skip_comsol:
        ensure_comsol_credentials(runtime_config)
        apply_comsol_server_environment(runtime_config)
        if not ensure_comsol_server(runtime_config, wait_s=60.0):
            raise RuntimeError("COMSOL server not reachable.")
        time.sleep(1.0)

    material = runtime_config.get("material", {})

    results: dict[str, dict] = {}
    for candidate_id, candidate_def in CANDIDATE_DEFS.items():
        print(f"\n=== {candidate_id}: {candidate_def['label']} ===")
        source_dir = Path(candidate_def["source_dir"])
        if candidate_def["frequencies_hz"] is None:
            freqs, weights = get_top_n_frequencies(source_dir, args.top_n)
        else:
            freqs = list(candidate_def["frequencies_hz"])
            weights = list(candidate_def["weights"]) if candidate_def["weights"] else [1.0] * len(freqs)
        print(f"  frequencies={freqs}\n  weights={weights}")

        fields: list[np.ndarray] = []
        per_freq: list[dict] = []
        for freq, weight in zip(freqs, weights):
            variant_id = f"final_compare_{candidate_id}_f{freq:.1f}Hz".replace(".", "p")
            candidate_dir = config_paths["candidates"] / variant_id
            export_dir = config_paths["comsol_exports"] / variant_id / "forced_response"
            export_dir.mkdir(parents=True, exist_ok=True)
            response_csv = export_dir / "forced_response.csv"
            need_run = (args.force_run or not response_csv.exists()) and not args.skip_comsol
            if need_run:
                prepare_variant_dir(
                    candidate_id=candidate_id,
                    candidate_def=candidate_def,
                    drive_frequency_hz=freq,
                    output_candidate_dir=candidate_dir,
                    config_paths=config_paths,
                    material=material,
                    damping_ratio=args.damping_ratio,
                    force_sigma_mm=args.force_sigma_mm,
                )
                t0 = time.time()
                rc = run_matlab(runtime_config, candidate_dir, export_dir)
                if rc != 0:
                    raise RuntimeError(f"MATLAB failed for {variant_id} (rc={rc}); see {export_dir/'livelink_forced_response.log'}")
                print(f"  freq={freq:.1f}Hz weight={weight:.3f} done in {time.time()-t0:.1f}s")
            if not response_csv.exists():
                raise FileNotFoundError(f"Missing forced_response.csv: {response_csv}")
            amp = load_forced_response_csv(response_csv, image_size, plate_length_mm)
            fields.append(amp)
            per_freq.append({
                "variant_id": variant_id,
                "frequency_hz": float(freq),
                "weight": float(weight),
                "field_max_abs": float(np.max(np.abs(amp))),
                "response_csv": str(response_csv),
            })

        composite = composite_rms(fields, np.array(weights))
        metrics = evaluate_metrics(target, composite, image_size)
        results[candidate_id] = {
            "label": candidate_def["label"],
            "frequencies_hz": freqs,
            "weights": weights,
            "stiffness_ratio_design": float(candidate_def["stiffness_ratio"]),
            "shear_ratio_design": float(candidate_def["shear_ratio"]),
            "per_freq": per_freq,
            "metrics": metrics,
        }
        np.save(output_dir / f"composite_{candidate_id}.npy", composite)
        print(f"  metrics: enrichment={metrics['enrichment_factor']:.3f} recall={metrics['coverage_recall']:.3f}")

    summary = {
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "image_size": image_size,
        "material_mode": "isotropic_baseline (E=2e9 Pa)",
        "actuator_pattern": "single_center_uniform (wide Gaussian)",
        "note": "orthotropic_shell_attempt_logged_in_comsol_templates/apply_orthotropic_shell.m; full Shell-physics orthotropic is Sprint 2 §3.",
        "results": results,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSummary written to {summary_path}")

    # Visualization
    try:
        import matplotlib.pyplot as plt
        candidates = list(results.keys())
        fig, axes = plt.subplots(2, len(candidates) + 1, figsize=(5 * (len(candidates) + 1), 9))
        # Top row: target + composites
        axes[0, 0].imshow(target, cmap="gray", origin="upper")
        axes[0, 0].set_title("Target (IC)")
        axes[0, 0].axis("off")
        for i, cid in enumerate(candidates, start=1):
            comp = np.load(output_dir / f"composite_{cid}.npy")
            axes[0, i].imshow(comp, cmap="viridis", origin="upper")
            axes[0, i].set_title(f"{cid}\nCOMSOL composite")
            axes[0, i].axis("off")
        # Bottom row: empty + powder densities
        axes[1, 0].axis("off")
        axes[1, 0].text(0.05, 0.5, "Powder density\n(low amp = high powder)", ha="left", va="center", transform=axes[1, 0].transAxes)
        for i, cid in enumerate(candidates, start=1):
            comp = np.load(output_dir / f"composite_{cid}.npy")
            powder = chladni_powder_density(comp, sigma_rel=0.05)
            axes[1, i].imshow(powder, cmap="hot", origin="upper")
            axes[1, i].set_title(f"enrich={results[cid]['metrics']['enrichment_factor']:.2f}×\nrecall={results[cid]['metrics']['coverage_recall']:.2f}")
            axes[1, i].axis("off")
        fig.suptitle("W10 COMSOL Comparison (isotropic, uniform actuator)\nθ-induced D4 breaking not captured — Sprint 2 §3 required for full orthotropic", fontsize=11)
        plt.tight_layout()
        fig.savefig(output_dir / "final_compare.png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        # Bar chart of metrics
        fig2, ax2 = plt.subplots(figsize=(8, 5))
        x_pos = np.arange(len(candidates))
        enrich = [results[c]["metrics"]["enrichment_factor"] for c in candidates]
        recall = [results[c]["metrics"]["coverage_recall"] for c in candidates]
        width = 0.35
        ax2.bar(x_pos - width / 2, enrich, width, label="Enrichment factor")
        ax2.bar(x_pos + width / 2, recall, width, label="Coverage recall")
        ax2.set_xticks(x_pos)
        ax2.set_xticklabels(candidates, rotation=15)
        ax2.set_ylabel("Metric")
        ax2.set_title("COMSOL isotropic-equivalent comparison")
        ax2.legend()
        ax2.axhline(1.0, color="gray", linestyle="--", alpha=0.5, label="Random baseline (enrichment=1)")
        plt.tight_layout()
        fig2.savefig(output_dir / "final_compare_trajectory.png", dpi=120, bbox_inches="tight")
        plt.close(fig2)
        print(f"Visualizations: {output_dir/'final_compare.png'}, {output_dir/'final_compare_trajectory.png'}")
    except Exception as exc:
        print(f"Visualization failed: {exc}")

    print("\n=== Final metrics summary ===")
    for cid in results:
        m = results[cid]["metrics"]
        print(f"  {cid}: enrichment={m['enrichment_factor']:.3f}  recall={m['coverage_recall']:.3f}  contrast={m['gaussian_contrast']:.3f}")


if __name__ == "__main__":
    main()
