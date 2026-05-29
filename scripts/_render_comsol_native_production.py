"""Render COMSOL-native (jet rainbow, 3D tilted) sand maps for production runs.

Loads the COMSOL mesh nodes from forced_response.csv directly (no downsample),
builds the RMS composite from the run's best subset, and produces a panel
that mimics COMSOL's GUI screenshot style: jet colormap, tilted axonometric
view, axes in metres.

Usage:
    .venv/bin/python scripts/_render_comsol_native_production.py
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri

ROOT = Path(__file__).resolve().parents[1]


def load_csv(p: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """forced_response.csv columns: x, y, w_real, w_imag, w_abs."""
    arr = np.loadtxt(p, delimiter=",", skiprows=1)
    x, y = arr[:, 0], arr[:, 1]
    amp = arr[:, 4] if arr.shape[1] >= 5 else np.sqrt(arr[:, 2] ** 2 + arr[:, 3] ** 2)
    return x, y, amp


def freq_label_to_csv_path(prefix: str, candidate_id: str, freq_str: str,
                            drive_freqs: list[float]) -> Path:
    """Resolve 'fLABEL' (rounded int Hz) → matching exact-freq CSV path."""
    target_int = int(freq_str)
    nearest = min(drive_freqs, key=lambda f: abs(int(round(f)) - target_int))
    freq_tag = f"f{nearest:.1f}Hz".replace(".", "p")
    vid = f"{prefix}_{candidate_id}_comsol_{freq_tag}"
    return ROOT / "data" / "comsol_exports" / vid / "forced_response" / "forced_response.csv"


def build_composite(summary: dict, candidate_id: str, stage_prefix: str
                     ) -> tuple[np.ndarray, np.ndarray, np.ndarray, str, list[float]]:
    """Build RMS composite on COMSOL mesh from best subset."""
    bc = summary["phase1"]["best_composite"]
    subset, method = bc["subset"], bc["method"]
    drive_freqs = list(summary["phase1"]["drive_freqs"])
    amps = []
    x0 = y0 = None
    used_freqs = []
    for fl in subset:
        csv = freq_label_to_csv_path(stage_prefix, candidate_id, fl, drive_freqs)
        if not csv.exists():
            raise FileNotFoundError(f"missing: {csv}")
        x, y, a = load_csv(csv)
        if x0 is None:
            x0, y0 = x, y
        peak = float(np.max(np.abs(a)))
        if peak > 0:
            a = a / peak
        amps.append(a)
        nearest = min(drive_freqs, key=lambda f: abs(int(round(f)) - int(fl)))
        used_freqs.append(nearest)
    stack = np.stack(amps, axis=0)
    if method == "RMS":
        comp = np.sqrt(np.mean(stack ** 2, axis=0))
    elif method == "MAX":
        comp = np.max(stack, axis=0)
    else:
        comp = np.sum(stack, axis=0)
    if comp.max() > 1e-30:
        comp = comp / comp.max()
    return x0, y0, comp, "+".join(subset), used_freqs


def powder_from_amp(amp: np.ndarray, sigma_rel: float = 0.025) -> np.ndarray:
    """Powder density = exp(-(|w|/σ)²): bright at nodes (low displacement)."""
    peak = float(np.max(np.abs(amp)))
    if peak <= 0:
        return np.ones_like(amp)
    norm = np.abs(amp) / peak
    return np.exp(-((norm / sigma_rel) ** 2))


def add_jet_2d(ax, x_m, y_m, values, title: str, plate_mm: float = 150.0, vmax=1.0):
    triang = mtri.Triangulation(x_m, y_m)
    cs = ax.tricontourf(triang, values, levels=200, cmap="jet", vmin=0, vmax=vmax)
    ax.set_aspect("equal")
    ax.set_xlim(-plate_mm/2/1000, plate_mm/2/1000)
    ax.set_ylim(-plate_mm/2/1000, plate_mm/2/1000)
    ax.set_xlabel("x [m]", fontsize=9)
    ax.set_ylabel("y [m]", fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.tick_params(labelsize=8)
    return cs


def add_jet_3d(fig, gs, x_m, y_m, values, title: str, plate_mm: float = 150.0, vmax=1.0):
    ax = fig.add_subplot(gs, projection="3d")
    triang = mtri.Triangulation(x_m, y_m)
    surf = ax.plot_trisurf(triang, values, cmap="jet", linewidth=0, antialiased=True,
                            vmin=0, vmax=vmax, edgecolor="none")
    ax.view_init(elev=45, azim=-60)
    ax.set_xlim(-plate_mm/2/1000, plate_mm/2/1000)
    ax.set_ylim(-plate_mm/2/1000, plate_mm/2/1000)
    ax.set_zlim(0, vmax)
    ax.set_xlabel("x [m]", fontsize=9, labelpad=4)
    ax.set_ylabel("y [m]", fontsize=9, labelpad=4)
    ax.set_zticks([])
    ax.set_title(title, fontsize=10, pad=8)
    ax.tick_params(labelsize=8)
    return surf


def render_run(label: str, summary_path: Path, prefix_p1: str, prefix_p2: str,
                fig, gs_row, sigma_rel: float = 0.025):
    """Render one row: |w| 2D | |w| 3D | powder 2D | powder 3D."""
    summary = json.loads(summary_path.read_text())
    cand = summary["candidate_id"]
    bc = summary["phase1"]["best_composite"]
    p2 = summary.get("phase2") or {}
    use_p1 = (p2.get("best_iter", 0) == 0)
    prefix = prefix_p1 if use_p1 else prefix_p2
    stage_tag = "Phase 1" if use_p1 else f"Phase 2 iter {p2['best_iter']}"

    x, y, amp, subset_str, used_freqs = build_composite(summary, cand, prefix)
    powder = powder_from_amp(amp, sigma_rel=sigma_rel)
    fhz = ", ".join(f"{f:.1f}" for f in used_freqs)
    sr = summary.get("stiffness_ratio")

    head = (f"{label}  (sr={sr})\n"
            f"{stage_tag} · COMSOL @ {fhz} Hz · {bc['method']}({subset_str})\n"
            f"broad enr={bc['broad']['enrich']:.2f}× rec={bc['broad']['recall']:.2f}  |  "
            f"tight enr={bc['tight']['enrich']:.2f}× rec={bc['tight']['recall']:.2f}")

    ax_amp_2d = fig.add_subplot(gs_row[0])
    add_jet_2d(ax_amp_2d, x, y, amp, f"|w| amplitude (top-down)\n{head}")
    add_jet_3d(fig, gs_row[1], x, y, amp, "|w| amplitude (3D tilted)")

    ax_pow_2d = fig.add_subplot(gs_row[2])
    add_jet_2d(ax_pow_2d, x, y, powder, f"Chladni powder σ={sigma_rel}\n(bright = nodal lines = sand)")
    add_jet_3d(fig, gs_row[3], x, y, powder, "Powder (3D tilted)")


def main() -> int:
    cfp = ROOT / "reports/production/production_design/production_summary.json"
    pla = ROOT / "reports/production_pla/production_design/production_summary.json"

    fig = plt.figure(figsize=(22, 11))
    outer = fig.add_gridspec(2, 1, hspace=0.45)
    row0 = outer[0].subgridspec(1, 4, wspace=0.30)
    row1 = outer[1].subgridspec(1, 4, wspace=0.30)

    render_run("CF-PETG anisotropic", cfp, "prodp1", "prodp2it1", fig, row0)
    render_run("PLA isotropic (school FDM)", pla, "prodp1", "prodp2it1", fig, row1)

    fig.suptitle("COMSOL-native rendering: CF-PETG (sr=3) vs school FDM PLA (sr=1, no θ)\n"
                  "Same target, same pipeline, raw COMSOL mesh — jet colormap matches COMSOL GUI default",
                  fontsize=13, fontweight="bold", y=0.995)

    out = ROOT / "reports/_material_comparison/comsol_native_pla_vs_cfpetg.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    print(f"[wrote] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
