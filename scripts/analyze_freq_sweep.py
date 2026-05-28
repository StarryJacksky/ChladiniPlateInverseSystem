"""Analyse per-frequency response of an orthotropic sweep and find best frequencies."""
from __future__ import annotations
import os, sys, json
from pathlib import Path
Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from src.scoring.recognisability_score import (
    chladni_powder_density,
    recognisability_score_grid,
)
from scipy.ndimage import binary_dilation


def load_csv(path, image_size, plate_length_mm):
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
    for _ in range(6):
        if mask.all(): break
        expanded = binary_dilation(mask)
        new = expanded & ~mask
        if not new.any(): break
        # Fill new cells with mean of immediate neighbors
        from scipy.ndimage import grey_dilation
        gr = grey_dilation(grid.real, size=3)
        gi = grey_dilation(grid.imag, size=3)
        grid = np.where(new, gr + 1j*gi, grid)
        mask = mask | new
    return grid


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", default="w10_ic_tier2_sr12")
    p.add_argument("--freqs", default="240,300,360,400,440,480,520,580,640,700,760,840")
    p.add_argument("--output-base", default="reports/w10_comsol_validation/orthotropic_sweep")
    args = p.parse_args()
    sweep_freqs = [float(x) for x in args.freqs.split(",")]
    candidate = args.candidate
    image_size = 256
    plate_length_mm = 150.0

    target = np.load("data/processed_targets/target_binary.npy").astype(bool)
    tgt_img = Image.fromarray((target.astype(np.uint8) * 255))
    tgt_img = tgt_img.resize((image_size, image_size), resample=Image.NEAREST)
    target_grid = (np.array(tgt_img) > 127).astype(bool)

    rows = []
    fields = []
    for f in sweep_freqs:
        variant_id = f"{candidate}_comsol_f{f:.1f}Hz".replace(".", "p")
        csv_path = Path(f"data/comsol_exports/{variant_id}/forced_response/forced_response.csv")
        if not csv_path.exists():
            print(f"missing {csv_path}")
            continue
        amp_complex = load_csv(csv_path, image_size, plate_length_mm)
        amp = np.abs(amp_complex)
        scores = recognisability_score_grid(amp, target_grid, sigma_rel=0.05, percentile=20.0)
        rows.append({
            "frequency_hz": f,
            "enrichment": float(scores["enrichment_factor"]),
            "recall": float(scores["coverage_recall"]),
            "contrast": float(scores["gaussian_contrast"]),
            "max_amp": float(amp.max()),
            "mean_amp": float(amp.mean()),
            "rms_amp": float(np.sqrt((amp**2).mean())),
        })
        fields.append((f, amp_complex, amp))

    # Sort by enrichment to find best frequencies
    rows_by_enrich = sorted(rows, key=lambda r: -r["enrichment"])
    print("=== Per-frequency results (sorted by enrichment desc) ===")
    print(f"{'freq Hz':>10} {'enrich':>8} {'recall':>8} {'contrast':>10} {'max_amp':>12} {'rms_amp':>12}")
    for r in rows_by_enrich:
        print(f"{r['frequency_hz']:>10.1f} {r['enrichment']:>8.3f} {r['recall']:>8.3f} {r['contrast']:>10.3f} {r['max_amp']:>12.3e} {r['rms_amp']:>12.3e}")

    # Take top 3
    top3 = rows_by_enrich[:3]
    top3_freqs = set(r["frequency_hz"] for r in top3)
    
    # Composite using top-3 by enrichment, weighted by enrichment
    sel_fields = []
    sel_weights = []
    sel_freqs = []
    for f, amp_complex, _amp in fields:
        if f in top3_freqs:
            sel_fields.append(amp_complex)
            for r in top3:
                if r["frequency_hz"] == f:
                    sel_weights.append(r["enrichment"])
                    break
            sel_freqs.append(f)
    sel_weights = np.array(sel_weights)
    sel_weights = sel_weights / sel_weights.sum()
    composite = np.sqrt(sum(w * (np.abs(F)**2) for w, F in zip(sel_weights, sel_fields)))
    comp_scores = recognisability_score_grid(composite, target_grid, sigma_rel=0.05, percentile=20.0)
    print(f"\n=== Composite (top-3 enrichment-weighted) ===")
    print(f"freqs={sel_freqs} weights={sel_weights}")
    print(f"enrichment={comp_scores['enrichment_factor']:.3f} recall={comp_scores['coverage_recall']:.3f} contrast={comp_scores['gaussian_contrast']:.3f}")

    # Visualisation: per-freq powder + composite
    output_dir = Path(args.output_base) / candidate
    output_dir.mkdir(parents=True, exist_ok=True)
    np.save(output_dir / "composite_top3enrich.npy", composite)

    n_plots = len(rows) + 1
    n_cols = 5
    n_rows = (n_plots + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4 * n_cols, 3.2 * n_rows))
    if n_rows == 1: axes = axes.reshape(1, -1)
    sweep_sorted = sorted(rows, key=lambda r: r["frequency_hz"])
    for idx, r in enumerate(sweep_sorted):
        ax = axes[idx // n_cols, idx % n_cols]
        for f, _ac, amp in fields:
            if f == r["frequency_hz"]:
                powder = chladni_powder_density(amp, sigma_rel=0.05)
                ax.imshow(powder, cmap="hot", origin="upper")
                tag = "[TOP3]" if f in top3_freqs else ""
                ax.set_title(f"{r['frequency_hz']:.0f}Hz {tag}\nenrich={r['enrichment']:.2f} recall={r['recall']:.2f}", fontsize=9)
                ax.axis("off")
                break
    comp_idx = len(sweep_sorted)
    ax = axes[comp_idx // n_cols, comp_idx % n_cols]
    powder = chladni_powder_density(composite, sigma_rel=0.05)
    ax.imshow(powder, cmap="hot", origin="upper")
    ax.set_title(f"Composite top-3\nenrich={comp_scores['enrichment_factor']:.2f} recall={comp_scores['coverage_recall']:.2f}", fontsize=9)
    ax.axis("off")
    for k in range(comp_idx + 1, n_rows * n_cols):
        axes[k // n_cols, k % n_cols].axis("off")
    fig.suptitle(f"COMSOL orthotropic sweep — {candidate} (E1/E2=12, G/G_iso=1.5)\n12 single-freq runs (top-3 by enrich + composite shown)", fontsize=11)
    plt.tight_layout()
    fig.savefig(output_dir / "orthotropic_sweep_per_freq.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {output_dir / 'orthotropic_sweep_per_freq.png'}")

    # Write summary
    summary = {
        "sweep_freqs_hz": sweep_freqs,
        "rows": rows,
        "top3_by_enrichment": top3,
        "composite_freqs": list(sel_freqs),
        "composite_weights": list(map(float, sel_weights)),
        "composite_metrics": {k: float(v) for k, v in comp_scores.items()},
    }
    (output_dir / "sweep_analysis.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
