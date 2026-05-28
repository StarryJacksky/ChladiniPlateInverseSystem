"""Final visualisation contrasting W10 surrogate predictions with COMSOL isotropic-equivalent measurements.

Reads the surrogate composite_amplitude.npy from each W10 candidate dir, the COMSOL
composite_<id>.npy from reports/w10_comsol_validation/final_compare/, computes
matched metrics, and produces a 3×4 figure with:

Row 1: surrogate composite | COMSOL composite | surrogate powder | COMSOL powder
... one row per candidate (baseline / tier1 / tier2)

Plus a bar chart that shows surrogate-predicted enrichment vs COMSOL-measured
enrichment side by side with the achievement-rate ratio.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np

from src.scoring.recognisability_score import (
    chladni_powder_density,
    coverage_recall,
    recognisability_score_grid,
)

CANDIDATES = [
    {
        "id": "baseline_w8",
        "label": "W8 baseline",
        "surrogate_path": None,
        "surrogate_enrich": None,
        "surrogate_recall": None,
        "comsol_npy": "reports/w10_comsol_validation/final_compare/composite_baseline_w8.npy",
    },
    {
        "id": "w10_tier1_sr3",
        "label": "W10 tier1 (CF-PETG sr=3.0)",
        "surrogate_path": "candidates/w10_ic_tier1_sr3/composite_amplitude.npy",
        "surrogate_summary": "candidates/w10_ic_tier1_sr3/w10_optimization_summary.json",
        "comsol_npy": "reports/w10_comsol_validation/final_compare/composite_w10_tier1_sr3.npy",
    },
    {
        "id": "w10_tier2_sr12",
        "label": "W10 tier2 (Continuous CF sr=12.0)",
        "surrogate_path": "candidates/w10_ic_tier2_sr12/composite_amplitude.npy",
        "surrogate_summary": "candidates/w10_ic_tier2_sr12/w10_optimization_summary.json",
        "comsol_npy": "reports/w10_comsol_validation/final_compare/composite_w10_tier2_sr12.npy",
    },
]


def evaluate_amp(amp: np.ndarray, target_at_size: np.ndarray) -> dict[str, float]:
    powder = chladni_powder_density(amp, sigma_rel=0.05)
    scores = recognisability_score_grid(amp, target_at_size, sigma_rel=0.05, percentile=20.0)
    return {
        "enrichment_factor": float(scores["enrichment_factor"]),
        "coverage_recall": float(scores["coverage_recall"]),
        "gaussian_contrast": float(scores["gaussian_contrast"]),
        "powder_density": powder,
    }


def resize_target_to(target: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    from PIL import Image
    tgt = Image.fromarray((target.astype(np.uint8) * 255))
    tgt = tgt.resize(target_shape[::-1], resample=Image.NEAREST)
    return (np.array(tgt) > 127).astype(bool)


def main() -> None:
    import matplotlib.pyplot as plt

    target_path = Path("data/processed_targets/target_binary.npy")
    target = np.load(target_path).astype(bool)
    output_dir = Path("reports/w10_comsol_validation/final_compare")
    output_dir.mkdir(parents=True, exist_ok=True)

    enriched_summary: dict[str, dict] = {"target_pixels_native": int(target.sum()), "target_shape": list(target.shape), "rows": []}

    fig, axes = plt.subplots(len(CANDIDATES), 4, figsize=(16, 4 * len(CANDIDATES)))
    if len(CANDIDATES) == 1:
        axes = axes.reshape(1, -1)
    column_titles = ["Surrogate amplitude (orthotropic+θ)", "COMSOL amplitude (isotropic, no θ)", "Surrogate powder", "COMSOL powder"]
    for col, title in enumerate(column_titles):
        axes[0, col].set_title(title, fontsize=11)

    metrics_rows: list[dict] = []

    for r, cdef in enumerate(CANDIDATES):
        comsol_amp = np.load(cdef["comsol_npy"])
        target_c = resize_target_to(target, comsol_amp.shape)
        comsol_metrics = evaluate_amp(comsol_amp, target_c)

        if cdef["surrogate_path"]:
            surrogate_amp = np.load(cdef["surrogate_path"])
            target_s = resize_target_to(target, surrogate_amp.shape)
            surrogate_metrics = evaluate_amp(surrogate_amp, target_s)
        else:
            surrogate_amp = None
            surrogate_metrics = None

        if surrogate_amp is not None:
            axes[r, 0].imshow(np.abs(surrogate_amp), cmap="viridis", origin="upper")
            axes[r, 0].set_title(f"{cdef['label']}\nenrich={surrogate_metrics['enrichment_factor']:.2f}× recall={surrogate_metrics['coverage_recall']:.2f}", fontsize=10)
            axes[r, 0].axis("off")
            axes[r, 2].imshow(surrogate_metrics["powder_density"], cmap="hot", origin="upper")
            axes[r, 2].axis("off")
        else:
            axes[r, 0].axis("off")
            axes[r, 0].text(0.5, 0.5, f"{cdef['label']}\n(no surrogate composite —\n W8 baseline)", ha="center", va="center", transform=axes[r, 0].transAxes)
            axes[r, 2].axis("off")

        axes[r, 1].imshow(comsol_amp, cmap="viridis", origin="upper")
        axes[r, 1].set_title(f"enrich={comsol_metrics['enrichment_factor']:.2f}× recall={comsol_metrics['coverage_recall']:.2f}", fontsize=10)
        axes[r, 1].axis("off")
        axes[r, 3].imshow(comsol_metrics["powder_density"], cmap="hot", origin="upper")
        axes[r, 3].axis("off")

        metrics_rows.append({
            "id": cdef["id"],
            "label": cdef["label"],
            "surrogate_enrichment": float(surrogate_metrics["enrichment_factor"]) if surrogate_metrics else None,
            "surrogate_recall": float(surrogate_metrics["coverage_recall"]) if surrogate_metrics else None,
            "comsol_enrichment": float(comsol_metrics["enrichment_factor"]),
            "comsol_recall": float(comsol_metrics["coverage_recall"]),
            "achievement_enrich": (float(comsol_metrics["enrichment_factor"]) / float(surrogate_metrics["enrichment_factor"]) if surrogate_metrics and surrogate_metrics["enrichment_factor"] > 0 else None),
            "achievement_recall": (float(comsol_metrics["coverage_recall"]) / float(surrogate_metrics["coverage_recall"]) if surrogate_metrics and surrogate_metrics["coverage_recall"] > 0 else None),
        })

    fig.suptitle("W10 final results: surrogate (orthotropic+θ) vs COMSOL (isotropic, no θ)\nθ-induced D4 breaking not captured in COMSOL pipeline — Sprint 2 §3 required for full Shell-orthotropic", fontsize=11)
    plt.tight_layout()
    fig.savefig(output_dir / "final_compare_full.png", dpi=120, bbox_inches="tight")
    plt.close(fig)

    # Achievement-rate bar chart
    valid_rows = [r for r in metrics_rows if r.get("surrogate_enrichment") is not None]
    fig2, (ax2a, ax2b) = plt.subplots(1, 2, figsize=(13, 5))
    labels = [r["id"] for r in metrics_rows]
    enrich_comsol = [r["comsol_enrichment"] for r in metrics_rows]
    enrich_surrogate = [r["surrogate_enrichment"] if r["surrogate_enrichment"] is not None else r["comsol_enrichment"] for r in metrics_rows]
    x_pos = np.arange(len(labels))
    width = 0.35
    ax2a.bar(x_pos - width / 2, enrich_surrogate, width, label="Surrogate (orthotropic+θ)", color="#4C72B0")
    ax2a.bar(x_pos + width / 2, enrich_comsol, width, label="COMSOL (isotropic-equiv)", color="#DD8452")
    ax2a.set_xticks(x_pos)
    ax2a.set_xticklabels(labels, rotation=15)
    ax2a.set_ylabel("Enrichment factor")
    ax2a.set_title("Enrichment: surrogate prediction vs COMSOL measured")
    ax2a.axhline(1.0, color="gray", linestyle="--", alpha=0.5, label="random (enrich=1)")
    ax2a.legend(loc="upper left", fontsize=9)
    # achievement rates
    achievement = [r["achievement_enrich"] if r["achievement_enrich"] is not None else 1.0 for r in metrics_rows]
    bars = ax2b.bar(x_pos, achievement, color=["gray", "#DD8452", "#DD8452"])
    ax2b.set_xticks(x_pos)
    ax2b.set_xticklabels(labels, rotation=15)
    ax2b.set_ylabel("COMSOL/Surrogate ratio")
    ax2b.set_title("Achievement rate (COMSOL / surrogate)")
    ax2b.axhline(1.0, color="gray", linestyle="--", alpha=0.5)
    for x, v in zip(x_pos, achievement):
        ax2b.text(x, v + 0.02, f"{v*100:.0f}%", ha="center", fontsize=9)
    plt.tight_layout()
    fig2.savefig(output_dir / "final_compare_achievement.png", dpi=120, bbox_inches="tight")
    plt.close(fig2)

    enriched_summary["rows"] = metrics_rows
    (output_dir / "final_metrics.json").write_text(json.dumps(enriched_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Visualisations:")
    print("  ", output_dir / "final_compare_full.png")
    print("  ", output_dir / "final_compare_achievement.png")
    print("Metrics:")
    for r in metrics_rows:
        if r["surrogate_enrichment"] is not None:
            print(f"  {r['id']}: surrogate={r['surrogate_enrichment']:.2f}× COMSOL={r['comsol_enrichment']:.2f}× (achievement={r['achievement_enrich']*100:.0f}%)")
        else:
            print(f"  {r['id']}: surrogate=N/A COMSOL={r['comsol_enrichment']:.2f}×")


if __name__ == "__main__":
    main()
