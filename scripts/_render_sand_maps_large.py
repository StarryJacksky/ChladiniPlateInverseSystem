"""Render high-resolution sand-map comparison: CF-PETG vs PLA.

Single target, 5 rows = (target / Phase1 broad / Phase1 sharp / Phase2 broad / Phase2 sharp),
2 columns = (CF-PETG, PLA). Sized for actual visual inspection.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "reports" / "production" / "production_design"
P = ROOT / "reports" / "production_pla" / "production_design"
OUT = ROOT / "reports" / "_material_comparison" / "sand_maps_large.png"


def load(dir_: Path, name: str):
    p = dir_ / name
    return np.load(p) if p.exists() else None


def main():
    target = load(B, "target_resized.npy")
    fields = [
        ("target", target, "gray_r"),
        ("Phase 1 powder broad", "phase1_best_powder_broad.npy", "afmhot"),
        ("Phase 1 powder sharp", "phase1_best_powder_sharp.npy", "afmhot"),
        ("Phase 2 powder broad", "phase2_best_powder_broad.npy", "afmhot"),
        ("Phase 2 powder sharp", "phase2_best_powder_sharp.npy", "afmhot"),
    ]
    fig, axes = plt.subplots(5, 3, figsize=(13, 21), gridspec_kw=dict(wspace=0.02, hspace=0.18))
    for r, (label, fname, cmap) in enumerate(fields):
        if r == 0:
            arr_b = arr_p = target
        else:
            arr_b = load(B, fname)
            arr_p = load(P, fname)

        ax_target = axes[r, 0]
        if r == 0:
            ax_target.imshow(target, cmap="gray_r")
            ax_target.set_title("Target (binary)", fontsize=13, pad=8)
        else:
            ax_target.imshow(target, cmap="gray_r")
            ax_target.set_title("Target", fontsize=11, pad=4, color="gray")
        ax_target.axis("off")

        ax_b = axes[r, 1]
        if arr_b is not None:
            a = arr_b.astype(np.float64)
            vmax = float(np.percentile(a, 99.5))
            ax_b.imshow(a, cmap=cmap, vmin=0, vmax=max(vmax, 1e-12))
        ax_b.set_title(f"CF-PETG (sr=3.0)\n{label}", fontsize=12, pad=6)
        ax_b.axis("off")

        ax_p = axes[r, 2]
        if arr_p is not None:
            a = arr_p.astype(np.float64)
            vmax = float(np.percentile(a, 99.5))
            ax_p.imshow(a, cmap=cmap, vmin=0, vmax=max(vmax, 1e-12))
        ax_p.set_title(f"PLA iso (sr=1.0, no θ)\n{label}", fontsize=12, pad=6)
        ax_p.axis("off")

    fig.suptitle(
        "Sand-map comparison: CF-PETG anisotropic vs school FDM PLA isotropic\n"
        "Same target, same pipeline, same H optimisation budget (300 steps)",
        fontsize=15, y=0.995,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=130, bbox_inches="tight")
    print(f"[wrote] {OUT}")


if __name__ == "__main__":
    main()
