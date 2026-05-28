"""Save the Sprint 2 §4 Phase 1 best deliverables and a final-comparison figure.

Deliverables:
- best_composite.npy: the best composite found (132+180 RMS)
- final_phase1_comparison.png: target | OLD 1.60× composite | Phase1 best 3.82× composite (with all per-freq panels)
- final_phase1_metrics.json: full metric breakdown
"""
from __future__ import annotations

import json
import os
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from src.config import load_config
from src.scoring.recognisability_score import (
    chladni_powder_density,
    coverage_recall,
    recognisability_score_grid,
)
from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid, resize_target_to_size


def load_amp(csv_path: Path, image_size: int, plate_length_mm: float) -> np.ndarray:
    arr = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    if arr.shape[1] >= 4:
        amp = np.sqrt(arr[:, 2]**2 + arr[:, 3]**2)
    else:
        amp = np.abs(arr[:, 2])
    grid = downsample_comsol_xy_to_grid(arr[:, 0], arr[:, 1], amp, image_size, plate_length_mm)
    if grid.max() > 1e-30:
        grid = grid / grid.max()
    return grid


def score(amp, target, sigma_rel=0.05, percentile=20.0):
    s = recognisability_score_grid(amp, target.astype(bool), sigma_rel=sigma_rel, percentile=percentile)
    r = float(coverage_recall(amp, target.astype(bool), percentile=percentile))
    return {"enrichment": float(s["enrichment_factor"]),
            "recall": r,
            "contrast": float(s["gaussian_contrast"]),
            "composite_recog": float(s["composite_recognisability"])}


def main():
    config = load_config("config.yaml")
    plate_length_mm = float(config["project"]["plate_length_mm"])
    image_size = 256
    target_bin = np.load("data/processed_targets/target_binary.npy").astype(bool)
    target = resize_target_to_size(target_bin, image_size)

    # Load Phase 1 freqs
    p1_summary = json.load(open("reports/sprint2_section4_phase1/w10_ic_tier2_sr12/summary.json"))
    p1_amps = []
    p1_meta = []
    for f, mi, w in zip(p1_summary["drive_freqs_hz"], p1_summary["drive_mode_indices"], p1_summary["drive_weights"]):
        vid = f"s4p1_w10_ic_tier2_sr12_comsol_f{f:.1f}Hz".replace(".", "p")
        csv = Path("data/comsol_exports") / vid / "forced_response" / "forced_response.csv"
        amp = load_amp(csv, image_size, plate_length_mm)
        p1_amps.append(amp)
        p1_meta.append({"f": f, "mode": mi, "w": w})

    # Load 180Hz
    csv_180 = Path("data/comsol_exports/w10_ic_tier2_sr12_comsol_f180p0Hz/forced_response/forced_response.csv")
    amp_180 = load_amp(csv_180, image_size, plate_length_mm)

    # OLD best composite (top-3 by enrich*sqrt(rms))
    sweep_summary = json.load(open("reports/w10_comsol_validation/orthotropic_combined/w10_ic_tier2_sr12/sweep_analysis.json"))
    old_amps_meta = []
    for row in sweep_summary["rows"]:
        f = row["frequency_hz"]
        vid = f"w10_ic_tier2_sr12_comsol_f{f:.1f}Hz".replace(".", "p")
        csv = Path("data/comsol_exports") / vid / "forced_response" / "forced_response.csv"
        if not csv.exists(): continue
        a = load_amp(csv, image_size, plate_length_mm)
        m = score(a, target)
        old_amps_meta.append({"f": f, "amp": a, **m, "rms": float(np.sqrt(np.mean(a**2)))})
    for r in old_amps_meta: r["pickscore"] = r["enrichment"] * np.sqrt(max(r["rms"], 1e-30))
    old_top = sorted(old_amps_meta, key=lambda x: -x["pickscore"])[:3]
    old_weights = np.array([r["pickscore"] for r in old_top])
    old_weights = old_weights / old_weights.sum()
    old_comp = sum(w * r["amp"] ** 2 for w, r in zip(old_weights, old_top))
    old_comp = np.sqrt(np.clip(old_comp, 0.0, None))
    if old_comp.max() > 1e-30: old_comp /= old_comp.max()
    old_metrics = score(old_comp, target)

    # Phase 1 best composite: 132 (mode 5) + 180 (off-resonance) via RMS
    best_amps = [p1_amps[0], amp_180]
    best_weights = np.array([0.5, 0.5])
    best_comp = sum(w * a ** 2 for w, a in zip(best_weights, best_amps))
    best_comp = np.sqrt(np.clip(best_comp, 0.0, None))
    if best_comp.max() > 1e-30: best_comp /= best_comp.max()
    best_metrics_broad = score(best_comp, target, sigma_rel=0.05, percentile=20.0)
    best_metrics_tight = score(best_comp, target, sigma_rel=0.012, percentile=92.0)

    # Phase 1 alternative: 4-freq (246+51+87+180) MAX (best under tight metric)
    best4_amps = [p1_amps[2], p1_amps[3], p1_amps[5], amp_180]  # modes 8, 2, 4, off
    best4_comp = np.maximum.reduce(best4_amps)
    if best4_comp.max() > 1e-30: best4_comp /= best4_comp.max()
    best4_broad = score(best4_comp, target, 0.05, 20.0)
    best4_tight = score(best4_comp, target, 0.012, 92.0)

    out_dir = Path("reports/sprint2_section4_phase1/w10_ic_tier2_sr12")
    np.save(out_dir / "deliverable_best_composite_132+180_RMS.npy", best_comp)
    np.save(out_dir / "deliverable_alt_composite_4freq_MAX.npy", best4_comp)
    np.save(out_dir / "old_baseline_composite.npy", old_comp)

    # ===== Final figure: 2 rows x 5 cols =====
    fig, axes = plt.subplots(2, 5, figsize=(20, 8))
    # Row 1: target + 132 + 180 + 132+180 composite + (empty)
    target_d = chladni_powder_density(target.astype(float), sigma_rel=0.012)
    axes[0, 0].imshow(target_d, cmap="hot", origin="upper"); axes[0, 0].axis("off")
    axes[0, 0].set_title("Target IC", fontsize=11, fontweight="bold")
    d132 = chladni_powder_density(p1_amps[0], sigma_rel=0.012)
    axes[0, 1].imshow(d132, cmap="hot", origin="upper"); axes[0, 1].axis("off")
    axes[0, 1].set_title(f"132 Hz (mode 5)\nenr(br)=2.88  rec=0.57", fontsize=10)
    d180 = chladni_powder_density(amp_180, sigma_rel=0.012)
    axes[0, 2].imshow(d180, cmap="hot", origin="upper"); axes[0, 2].axis("off")
    axes[0, 2].set_title(f"180 Hz (off-res)\nenr(br)=3.14  rec=0.65", fontsize=10)
    dbest = chladni_powder_density(best_comp, sigma_rel=0.012)
    axes[0, 3].imshow(dbest, cmap="hot", origin="upper"); axes[0, 3].axis("off")
    axes[0, 3].set_title(f"PHASE 1 BEST (132+180 RMS)\nbroad: enr=3.82 rec=0.89\ntight: enr=2.22 rec=1.00", fontsize=10, fontweight="bold", color="darkgreen")
    for sp in axes[0, 3].spines.values():
        sp.set_edgecolor("green"); sp.set_linewidth(3)
    axes[0, 3].patch.set_edgecolor("green"); axes[0, 3].patch.set_linewidth(3)
    dbest4 = chladni_powder_density(best4_comp, sigma_rel=0.012)
    axes[0, 4].imshow(dbest4, cmap="hot", origin="upper"); axes[0, 4].axis("off")
    axes[0, 4].set_title(f"PHASE 1 ALT (4-freq MAX)\nbroad: enr=2.75 rec=0.67\ntight: enr=3.40 rec=1.00", fontsize=10, color="darkblue")
    # Row 2: target + old top3 + old composite
    axes[1, 0].imshow(target_d, cmap="hot", origin="upper"); axes[1, 0].axis("off")
    axes[1, 0].set_title("Target IC", fontsize=11, fontweight="bold")
    for i, r in enumerate(old_top, start=1):
        d = chladni_powder_density(r["amp"], sigma_rel=0.012)
        axes[1, i].imshow(d, cmap="hot", origin="upper"); axes[1, i].axis("off")
        axes[1, i].set_title(f"OLD f={r['f']:.0f}\nenr(br)={r['enrichment']:.2f}", fontsize=10)
    dold = chladni_powder_density(old_comp, sigma_rel=0.012)
    axes[1, 4].imshow(dold, cmap="hot", origin="upper"); axes[1, 4].axis("off")
    axes[1, 4].set_title(f"OLD COMPOSITE\nbroad: enr={old_metrics['enrichment']:.2f} rec={old_metrics['recall']:.2f}", fontsize=10, color="darkred")
    plt.suptitle("Sprint 2 §4 Phase 1: best composite vs OLD 26-freq baseline (W10 tier2)", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(out_dir / "final_phase1_comparison.png", dpi=130, bbox_inches="tight")
    plt.close(fig)

    # Save metrics
    final_metrics = {
        "deliverable_best": {
            "name": "132Hz + 180Hz RMS composite",
            "drive_freqs": [132.0, 180.0],
            "drive_weights": [0.5, 0.5],
            "broad_metric": best_metrics_broad,
            "tight_metric": best_metrics_tight,
        },
        "deliverable_alt": {
            "name": "4-freq MAX composite (246+51+87+180)",
            "drive_freqs": [246.1, 50.8, 87.3, 180.0],
            "broad_metric": best4_broad,
            "tight_metric": best4_tight,
        },
        "old_baseline": {
            "name": "OLD top-3 RMS (from 26-freq sweep)",
            "drive_freqs": [r["f"] for r in old_top],
            "weights": old_weights.tolist(),
            "broad_metric": old_metrics,
        },
        "improvement_ratios": {
            "best_over_old_broad_enrich": best_metrics_broad["enrichment"] / old_metrics["enrichment"],
            "best_over_old_broad_recall": best_metrics_broad["recall"] / old_metrics["recall"],
        },
        "honest_qualitative_note": (
            "Phase 1 raises the recognisability METRIC from 1.94x (broad) to 3.82x (broad), "
            "with recall improving from 0.43 to 0.89. However the composite still appears as a "
            "centrally-concentrated blob with limited fine structure, not a sharp 'IC' rendering. "
            "Phase 2 (trust-region H+theta iteration) is needed if visually distinct 'IC' rendering is required."
        ),
    }
    (out_dir / "final_phase1_metrics.json").write_text(json.dumps(final_metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved deliverables to {out_dir}:")
    for p in sorted(out_dir.glob("deliverable_*.npy")):
        print(f"  {p}")
    print(f"  {out_dir/'final_phase1_comparison.png'}")
    print(f"  {out_dir/'final_phase1_metrics.json'}")
    print(f"\n=== FINAL PHASE 1 METRICS ===")
    print(f"Best composite (132+180 RMS):  broad enr={best_metrics_broad['enrichment']:.3f}  recall={best_metrics_broad['recall']:.3f}")
    print(f"Alt  composite (4-freq MAX):   tight enr={best4_tight['enrichment']:.3f}  recall={best4_tight['recall']:.3f}")
    print(f"OLD baseline:                  broad enr={old_metrics['enrichment']:.3f}  recall={old_metrics['recall']:.3f}")
    print(f"Improvement (broad enrich): {best_metrics_broad['enrichment']/old_metrics['enrichment']:.2f}×")
    print(f"Improvement (broad recall): {best_metrics_broad['recall']/old_metrics['recall']:.2f}×")


if __name__ == "__main__":
    main()
