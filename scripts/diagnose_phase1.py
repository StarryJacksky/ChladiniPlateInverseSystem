"""Diagnose Sprint 2 §4 Phase 1 results vs the existing 26-freq sweep composite.

Goals:
1. Compute per-frequency forced-response enrichment for Phase 1's 6 drives (apples-to-apples).
2. Recompute the OLD 26-freq sweep composite with the SAME scoring params used here.
3. Visualise: target | each per-freq powder | Phase 1 composite | OLD composite.
4. Report whether Phase 1 is genuinely worse, or just measured under different scoring.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation
import matplotlib.pyplot as plt

from src.config import load_config
from src.scoring.recognisability_score import (
    chladni_powder_density,
    coverage_recall,
    recognisability_score_grid,
)
from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid, resize_target_to_size


SIGMA_REL = 0.05
PERCENTILE = 20.0


def score(amp_grid: np.ndarray, target: np.ndarray) -> dict:
    s = recognisability_score_grid(amp_grid, target.astype(bool), sigma_rel=SIGMA_REL, percentile=PERCENTILE)
    return {"enrich": float(s["enrichment_factor"]), "contrast": float(s["gaussian_contrast"]),
            "recall": float(coverage_recall(amp_grid, target.astype(bool), percentile=PERCENTILE))}


def load_amp(csv_path: Path, image_size: int, plate_length_mm: float) -> np.ndarray:
    arr = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    # Detect columns
    if arr.shape[1] >= 4:
        amp = np.sqrt(arr[:, 2]**2 + arr[:, 3]**2)
    else:
        amp = np.abs(arr[:, 2])
    grid = downsample_comsol_xy_to_grid(arr[:, 0], arr[:, 1], amp, image_size, plate_length_mm)
    if grid.max() > 1e-30:
        grid = grid / grid.max()
    return grid


def main():
    config = load_config("config.yaml")
    plate_length_mm = float(config["project"]["plate_length_mm"])
    image_size = 256
    target_bin = np.load("data/processed_targets/target_binary.npy").astype(bool)
    target = resize_target_to_size(target_bin, image_size)

    # ===== Phase 1: per-freq forced response =====
    summary = json.load(open("reports/sprint2_section4_phase1/w10_ic_tier2_sr12/summary.json"))
    candidates = []
    print("=== Phase 1: per-frequency forced response enrichment ===")
    for f, mi, w in zip(summary["drive_freqs_hz"], summary["drive_mode_indices"], summary["drive_weights"]):
        vid = f"s4p1_w10_ic_tier2_sr12_comsol_f{f:.1f}Hz".replace(".", "p")
        csv = Path("data/comsol_exports") / vid / "forced_response" / "forced_response.csv"
        if not csv.exists():
            print(f"  MISSING: {csv}")
            continue
        amp = load_amp(csv, image_size, plate_length_mm)
        m = score(amp, target)
        candidates.append({"f": f, "mode": mi, "w": w, "amp": amp, **m})
        print(f"  f={f:7.2f}Hz mode={mi} w={w:.3f}  enrich={m['enrich']:6.3f}  recall={m['recall']:6.3f}  rms={float(np.sqrt(np.mean(amp**2))):.3e}")

    p1_comp = np.zeros_like(target, dtype=float)
    for c in candidates:
        p1_comp += float(c["w"]) * c["amp"] ** 2
    p1_comp = np.sqrt(np.clip(p1_comp, 0.0, None))
    if p1_comp.max() > 1e-30: p1_comp /= p1_comp.max()
    p1_metrics = score(p1_comp, target)
    print(f"\nPhase 1 composite (s4p1, IC-weighted): enrich={p1_metrics['enrich']:.3f}  recall={p1_metrics['recall']:.3f}")

    # ===== OLD 26-freq sweep composite =====
    sweep_dir = Path("data/comsol_exports")
    # Find candidate dirs from old sweep
    print(f"\n=== OLD 26-freq sweep: per-freq enrichments under same scoring ===")
    sweep_results = []
    old_summary = json.load(open("reports/w10_comsol_validation/orthotropic_combined/w10_ic_tier2_sr12/sweep_analysis.json"))
    for row in old_summary["rows"]:
        f = row["frequency_hz"]
        # try multiple naming
        for variant_template in [
            f"w10_ic_tier2_sr12_comsol_f{f:.1f}Hz",
            f"sweep_w10_ic_tier2_sr12_comsol_f{f:.1f}Hz",
        ]:
            vid = variant_template.replace(".", "p")
            csv = sweep_dir / vid / "forced_response" / "forced_response.csv"
            if csv.exists(): break
        else:
            continue
        amp = load_amp(csv, image_size, plate_length_mm)
        m = score(amp, target)
        rms = float(np.sqrt(np.mean(amp**2)))
        sweep_results.append({"f": f, "amp": amp, "rms": rms, **m})
        print(f"  f={f:6.1f}Hz  enrich={m['enrich']:6.3f}  recall={m['recall']:6.3f}  rms={rms:.3e}")

    # Reproduce composite with old-style weighting: top-3 by enrich × rms
    if sweep_results:
        # Pick top-3 by score = enrich * sqrt(rms)
        for r in sweep_results: r["score"] = r["enrich"] * np.sqrt(max(r["rms"], 1e-30))
        sweep_top = sorted(sweep_results, key=lambda x: -x["score"])[:3]
        weights = np.array([r["score"] for r in sweep_top])
        weights = weights / weights.sum()
        old_comp = np.zeros_like(target, dtype=float)
        for w, r in zip(weights, sweep_top):
            old_comp += w * r["amp"] ** 2
        old_comp = np.sqrt(np.clip(old_comp, 0.0, None))
        if old_comp.max() > 1e-30: old_comp /= old_comp.max()
        old_metrics = score(old_comp, target)
        print(f"\nOLD 26-freq composite (top-3 by score=enrich*sqrt(rms)):")
        for r, w in zip(sweep_top, weights):
            print(f"  f={r['f']:.1f}Hz  enrich={r['enrich']:.3f}  weight={w:.3f}")
        print(f"  composite: enrich={old_metrics['enrich']:.3f}  recall={old_metrics['recall']:.3f}")

    # ===== Visualisation =====
    fig, axes = plt.subplots(2, max(4, len(candidates) + 2), figsize=(4*max(4, len(candidates)+2), 8))
    if axes.ndim == 1: axes = axes.reshape(1, -1)
    # Top row: target + per-freq Phase 1
    target_density = chladni_powder_density(target.astype(float), sigma_rel=SIGMA_REL)
    axes[0, 0].imshow(target_density, cmap="hot", origin="upper")
    axes[0, 0].set_title("Target IC")
    axes[0, 0].axis("off")
    for i, c in enumerate(candidates, start=1):
        d = chladni_powder_density(c["amp"], sigma_rel=SIGMA_REL)
        axes[0, i].imshow(d, cmap="hot", origin="upper")
        axes[0, i].set_title(f"#{c['mode']} f={c['f']:.0f}\nenr={c['enrich']:.2f} r={c['recall']:.2f}", fontsize=9)
        axes[0, i].axis("off")
    # Phase 1 composite
    d = chladni_powder_density(p1_comp, sigma_rel=SIGMA_REL)
    pos = len(candidates) + 1
    axes[0, pos].imshow(d, cmap="hot", origin="upper")
    axes[0, pos].set_title(f"Phase1 composite\nenr={p1_metrics['enrich']:.2f} r={p1_metrics['recall']:.2f}", fontsize=9)
    axes[0, pos].axis("off")
    for j in range(pos+1, axes.shape[1]):
        axes[0, j].axis("off")

    # Bottom row: old composite + top-3 from old sweep
    axes[1, 0].imshow(target_density, cmap="hot", origin="upper")
    axes[1, 0].set_title("Target IC")
    axes[1, 0].axis("off")
    if sweep_results:
        for i, r in enumerate(sweep_top, start=1):
            d = chladni_powder_density(r["amp"], sigma_rel=SIGMA_REL)
            axes[1, i].imshow(d, cmap="hot", origin="upper")
            axes[1, i].set_title(f"old top f={r['f']:.0f}\nenr={r['enrich']:.2f}", fontsize=9)
            axes[1, i].axis("off")
        d = chladni_powder_density(old_comp, sigma_rel=SIGMA_REL)
        axes[1, 4].imshow(d, cmap="hot", origin="upper")
        axes[1, 4].set_title(f"OLD composite\nenr={old_metrics['enrich']:.2f} r={old_metrics['recall']:.2f}", fontsize=9)
        axes[1, 4].axis("off")
    for j in range(5, axes.shape[1]):
        axes[1, j].axis("off")

    plt.suptitle(f"Sprint 2 §4 Phase 1 diagnosis (sigma_rel={SIGMA_REL}, pct={PERCENTILE})", fontsize=12)
    plt.tight_layout()
    out_dir = Path("reports/sprint2_section4_phase1/w10_ic_tier2_sr12")
    fig.savefig(out_dir / "phase1_diagnosis.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\nWrote: {out_dir/'phase1_diagnosis.png'}")

    # Final report
    diag = {
        "scoring": {"sigma_rel": SIGMA_REL, "percentile": PERCENTILE},
        "phase1_per_freq": [{"f": c["f"], "mode": c["mode"], "weight": c["w"], "enrich": c["enrich"], "recall": c["recall"]} for c in candidates],
        "phase1_composite": p1_metrics,
        "sweep_per_freq": [{"f": r["f"], "enrich": r["enrich"], "recall": r["recall"], "rms": r["rms"]} for r in sweep_results] if sweep_results else [],
    }
    if sweep_results:
        diag["sweep_top3"] = [{"f": r["f"], "enrich": r["enrich"], "weight": float(w)} for r, w in zip(sweep_top, weights)]
        diag["sweep_composite"] = old_metrics
    (out_dir / "phase1_diagnosis.json").write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
