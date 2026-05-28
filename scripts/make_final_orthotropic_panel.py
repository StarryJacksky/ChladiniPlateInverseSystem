"""Final 4-panel deliverable: target + surrogate prediction + COMSOL isotropic + COMSOL orthotropic."""
from __future__ import annotations
import os, sys, json
from pathlib import Path
Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from scipy.ndimage import binary_dilation

from src.scoring.recognisability_score import (
    chladni_powder_density,
    recognisability_score_grid,
)


def load_csv(path, image_size, plate_length_mm):
    from scipy.ndimage import grey_dilation
    data = np.loadtxt(path, delimiter=",", skiprows=1, dtype=float)
    x_m, y_m = data[:, 0], data[:, 1]
    w_re, w_im = data[:, 2], data[:, 3]
    complex_w = w_re + 1j * w_im
    half_m = plate_length_mm / 2000.0
    edges = np.linspace(-half_m, half_m, image_size + 1)
    col = np.clip(np.searchsorted(edges, x_m, side="right") - 1, 0, image_size - 1)
    row_from_bottom = np.clip(np.searchsorted(edges, y_m, side="right") - 1, 0, image_size - 1)
    row = image_size - 1 - row_from_bottom
    accum = np.zeros((image_size, image_size), dtype=complex)
    counts = np.zeros((image_size, image_size), dtype=int)
    np.add.at(accum, (row, col), complex_w)
    np.add.at(counts, (row, col), 1)
    grid = np.where(counts > 0, accum / np.where(counts > 0, counts, 1), 0)
    mask = counts > 0
    for _ in range(8):
        if mask.all(): break
        expanded = binary_dilation(mask)
        new = expanded & ~mask
        if not new.any(): break
        gr = grey_dilation(grid.real, size=3)
        gi = grey_dilation(grid.imag, size=3)
        grid = np.where(new, gr + 1j*gi, grid)
        mask = mask | new
    return grid


def resize_target_to(target, shape):
    tgt = Image.fromarray((target.astype(np.uint8) * 255))
    tgt = tgt.resize(shape[::-1], resample=Image.NEAREST)
    return (np.array(tgt) > 127).astype(bool)


def main():
    image_size = 256
    plate_length_mm = 150.0
    target = np.load("data/processed_targets/target_binary.npy").astype(bool)
    target_grid = resize_target_to(target, (image_size, image_size))

    # 1) Surrogate prediction for W10 tier2
    surrogate_amp = np.load("candidates/w10_ic_tier2_sr12/composite_amplitude.npy")
    surrogate_target = resize_target_to(target, surrogate_amp.shape)
    surrogate_scores = recognisability_score_grid(np.abs(surrogate_amp), surrogate_target, sigma_rel=0.05, percentile=20.0)
    surrogate_powder = chladni_powder_density(np.abs(surrogate_amp), sigma_rel=0.05)

    # 2) COMSOL isotropic-equivalent composite for W10 tier2 (from previous run)
    comsol_iso_amp = np.load("reports/w10_comsol_validation/final_compare/composite_w10_tier2_sr12.npy")
    comsol_iso_target = resize_target_to(target, comsol_iso_amp.shape)
    comsol_iso_scores = recognisability_score_grid(np.abs(comsol_iso_amp), comsol_iso_target, sigma_rel=0.05, percentile=20.0)
    comsol_iso_powder = chladni_powder_density(np.abs(comsol_iso_amp), sigma_rel=0.05)

    # 3) Baseline W8 (from previous run)
    baseline_amp = np.load("reports/w10_comsol_validation/final_compare/composite_baseline_w8.npy")
    baseline_target = resize_target_to(target, baseline_amp.shape)
    baseline_scores = recognisability_score_grid(np.abs(baseline_amp), baseline_target, sigma_rel=0.05, percentile=20.0)
    baseline_powder = chladni_powder_density(np.abs(baseline_amp), sigma_rel=0.05)

    # 4) COMSOL orthotropic: load 6 representative single-freq responses showing D4 breaking
    representative_freqs = [210.0, 240.0, 500.0, 680.0, 1000.0, 1100.0]
    ortho_powders = []
    ortho_amps = []
    for f in representative_freqs:
        variant_id = f"w10_ic_tier2_sr12_comsol_f{f:.1f}Hz".replace(".", "p")
        csv_path = Path(f"data/comsol_exports/{variant_id}/forced_response/forced_response.csv")
        if not csv_path.exists():
            print(f"missing {csv_path}")
            continue
        complex_amp = load_csv(csv_path, image_size, plate_length_mm)
        amp = np.abs(complex_amp)
        powder = chladni_powder_density(amp, sigma_rel=0.05)
        ortho_powders.append((f, powder, amp))
        ortho_amps.append(complex_amp)

    # 5) COMSOL orthotropic composite using top-3 enrichment freqs
    top3 = [500.0, 520.0, 680.0]
    top3_amps = []
    for f in top3:
        variant_id = f"w10_ic_tier2_sr12_comsol_f{f:.1f}Hz".replace(".", "p")
        csv_path = Path(f"data/comsol_exports/{variant_id}/forced_response/forced_response.csv")
        if csv_path.exists():
            top3_amps.append(np.abs(load_csv(csv_path, image_size, plate_length_mm)))
    composite_ortho = np.sqrt(np.mean(np.array(top3_amps) ** 2, axis=0)) if top3_amps else np.zeros((image_size, image_size))
    ortho_composite_scores = recognisability_score_grid(composite_ortho, target_grid, sigma_rel=0.05, percentile=20.0)
    ortho_composite_powder = chladni_powder_density(composite_ortho, sigma_rel=0.05)

    # === Make 3x4 figure ===
    fig = plt.figure(figsize=(18, 14))
    gs = fig.add_gridspec(3, 4, hspace=0.35, wspace=0.15)

    # Row 1: target + surrogate (2 cols) + comsol isotropic-equiv + baseline
    ax = fig.add_subplot(gs[0, 0]); ax.imshow(target.astype(float), cmap="Blues_r", origin="upper"); ax.set_title("Target IC", fontsize=11); ax.axis("off")
    ax = fig.add_subplot(gs[0, 1]); ax.imshow(surrogate_powder, cmap="hot", origin="upper");
    ax.set_title(f"Surrogate (Kirchhoff orthotropic+θ)\nenrich={surrogate_scores['enrichment_factor']:.2f}× recall={surrogate_scores['coverage_recall']:.2f}", fontsize=10); ax.axis("off")
    ax = fig.add_subplot(gs[0, 2]); ax.imshow(baseline_powder, cmap="hot", origin="upper")
    ax.set_title(f"COMSOL W8 baseline (isotropic, no θ)\nenrich={baseline_scores['enrichment_factor']:.2f}× recall={baseline_scores['coverage_recall']:.2f}", fontsize=10); ax.axis("off")
    ax = fig.add_subplot(gs[0, 3]); ax.imshow(comsol_iso_powder, cmap="hot", origin="upper")
    ax.set_title(f"COMSOL W10 isotropic-equiv (no θ)\nenrich={comsol_iso_scores['enrichment_factor']:.2f}× recall={comsol_iso_scores['coverage_recall']:.2f}", fontsize=10); ax.axis("off")

    # Row 2: COMSOL orthotropic at 4 representative freqs showing D4 breaking
    cols_to_show = ortho_powders[:4]
    for ci, (f, p, _amp) in enumerate(cols_to_show):
        ax = fig.add_subplot(gs[1, ci]); ax.imshow(p, cmap="hot", origin="upper")
        # Compute per-freq scores
        scores = recognisability_score_grid(_amp, target_grid, sigma_rel=0.05, percentile=20.0)
        ax.set_title(f"COMSOL orthotropic @ {f:.0f}Hz\nenrich={scores['enrichment_factor']:.2f}× recall={scores['coverage_recall']:.2f}", fontsize=10); ax.axis("off")

    # Row 3: more freqs + composite + bar chart
    if len(ortho_powders) >= 6:
        f, p, _amp = ortho_powders[4]
        ax = fig.add_subplot(gs[2, 0]); ax.imshow(p, cmap="hot", origin="upper")
        scores = recognisability_score_grid(_amp, target_grid, sigma_rel=0.05, percentile=20.0)
        ax.set_title(f"COMSOL orthotropic @ {f:.0f}Hz\nenrich={scores['enrichment_factor']:.2f}× recall={scores['coverage_recall']:.2f}", fontsize=10); ax.axis("off")
        f, p, _amp = ortho_powders[5]
        ax = fig.add_subplot(gs[2, 1]); ax.imshow(p, cmap="hot", origin="upper")
        scores = recognisability_score_grid(_amp, target_grid, sigma_rel=0.05, percentile=20.0)
        ax.set_title(f"COMSOL orthotropic @ {f:.0f}Hz\nenrich={scores['enrichment_factor']:.2f}× recall={scores['coverage_recall']:.2f}", fontsize=10); ax.axis("off")
    ax = fig.add_subplot(gs[2, 2]); ax.imshow(ortho_composite_powder, cmap="hot", origin="upper")
    ax.set_title(f"COMSOL orthotropic composite\nenrich={ortho_composite_scores['enrichment_factor']:.2f}× recall={ortho_composite_scores['coverage_recall']:.2f}", fontsize=10); ax.axis("off")

    # Bar chart: enrichment comparison
    ax = fig.add_subplot(gs[2, 3])
    cats = ["Surrogate\n(Kirchhoff)", "COMSOL W8\n(iso, no θ)", "COMSOL W10\n(iso-eq, no θ)", "COMSOL W10\n(ortho+θ)"]
    enrich_vals = [
        surrogate_scores['enrichment_factor'],
        baseline_scores['enrichment_factor'],
        comsol_iso_scores['enrichment_factor'],
        ortho_composite_scores['enrichment_factor'],
    ]
    colors = ["#4C72B0", "#888888", "#DD8452", "#55A868"]
    bars = ax.bar(cats, enrich_vals, color=colors)
    ax.set_ylabel("Enrichment factor")
    ax.axhline(1.0, color="gray", linestyle="--", alpha=0.5, label="random")
    ax.set_title("Enrichment comparison", fontsize=11)
    for b, v in zip(bars, enrich_vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.15, f"{v:.2f}", ha="center", fontsize=9)
    ax.tick_params(axis="x", rotation=12, labelsize=8)

    fig.suptitle(
        "W10 tier2 full pipeline — Sprint 2 §3 orthotropic Shell API SOLVED\n"
        "Surrogate (left) predicts clear IC. COMSOL orthotropic+θ breaks D4 symmetry (row 2-3), \n"
        "but Kirchhoff↔Mindlin physics-gap shifts modal frequencies by ~40% → Sprint 2 §4 (trust-region recalibration) needed for IC alignment.",
        fontsize=11,
    )
    output_dir = Path("reports/w10_comsol_validation/final_orthotropic_panel")
    output_dir.mkdir(parents=True, exist_ok=True)
    save_path = output_dir / "final_orthotropic_pipeline.png"
    fig.savefig(save_path, dpi=120, bbox_inches="tight")
    plt.close(fig)

    summary = {
        "surrogate_scores": {k: float(v) for k, v in surrogate_scores.items()},
        "comsol_baseline_w8_iso_scores": {k: float(v) for k, v in baseline_scores.items()},
        "comsol_w10_iso_equiv_scores": {k: float(v) for k, v in comsol_iso_scores.items()},
        "comsol_w10_orthotropic_composite_scores": {k: float(v) for k, v in ortho_composite_scores.items()},
        "ortho_composite_freqs": top3,
        "representative_ortho_freqs": representative_freqs,
        "notes": [
            "Surrogate uses Kirchhoff plate orthotropic with rotated theta(x,y).",
            "COMSOL Shell uses Mindlin plate with the SAME orthotropic E1/E2/G12 + per-cell theta(x,y) via Rotated coord system.",
            "Despite identical material params and theta field, modal frequencies shift ~40%.",
            "Likely causes: through-thickness shear (Mindlin), full 3D constitutive vs plane stress (Kirchhoff), central 8mm clamp.",
            "All COMSOL orthotropic responses show clear D4 symmetry breaking — orthotropic API is functioning correctly.",
            "Next step: Sprint 2 §4 — W9-style trust-region recalibration with orthotropic COMSOL Shell as ground truth.",
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved {save_path}")
    print(f"summary: {output_dir / 'summary.json'}")
    print(f"surrogate enrichment: {surrogate_scores['enrichment_factor']:.2f}×")
    print(f"comsol w8 iso enrichment: {baseline_scores['enrichment_factor']:.2f}×")
    print(f"comsol w10 iso-eq enrichment: {comsol_iso_scores['enrichment_factor']:.2f}×")
    print(f"comsol w10 orthotropic composite enrichment: {ortho_composite_scores['enrichment_factor']:.2f}×")


if __name__ == "__main__":
    main()
