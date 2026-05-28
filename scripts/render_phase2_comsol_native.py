"""COMSOL-native rendering for Phase 2 results.

Mimics how COMSOL itself displays the displacement field and Chladni powder pattern,
using the original COMSOL mesh nodes via matplotlib triangulation (no downsampling).
"""
import json
import os
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image


def load_comsol_mesh(csv_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load (x_m, y_m, |w|) from COMSOL forced_response.csv."""
    arr = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    x = arr[:, 0]
    y = arr[:, 1]
    if arr.shape[1] >= 5:
        amp = arr[:, 4]  # use w_abs column directly
    elif arr.shape[1] >= 4:
        amp = np.sqrt(arr[:, 2] ** 2 + arr[:, 3] ** 2)
    else:
        amp = np.abs(arr[:, 2])
    return x, y, amp


def render_field_comsol_style(ax, x_m: np.ndarray, y_m: np.ndarray, values: np.ndarray, title: str,
                                 cmap: str = "RdBu_r", title_fs: int = 11, plate_length_mm: float = 150.0,
                                 normalize: bool = True, log_scale: bool = False):
    """Render a single COMSOL field using triangulation, matching COMSOL's native rendering style."""
    triang = mtri.Triangulation(x_m * 1000, y_m * 1000)  # convert to mm
    z = values.copy()
    if normalize and np.max(np.abs(z)) > 1e-30:
        z = z / np.max(np.abs(z))
    if log_scale:
        z = np.log10(np.maximum(z, 1e-6))
    cs = ax.tricontourf(triang, z, levels=200, cmap=cmap)
    ax.set_aspect("equal")
    ax.set_xlim(-plate_length_mm / 2, plate_length_mm / 2)
    ax.set_ylim(-plate_length_mm / 2, plate_length_mm / 2)
    ax.set_title(title, fontsize=title_fs)
    ax.tick_params(labelsize=8)
    return cs


def render_powder_comsol_style(ax, x_m: np.ndarray, y_m: np.ndarray, amplitude: np.ndarray, title: str,
                                  sigma_rel: float = 0.025, plate_length_mm: float = 150.0,
                                  title_fs: int = 11):
    """Render Chladni powder accumulation in a realistic style: bright = powder gathers (nodal lines)."""
    peak = float(np.max(np.abs(amplitude)))
    if peak <= 0:
        powder = np.ones_like(amplitude)
    else:
        norm = np.abs(amplitude) / peak
        powder = np.exp(-((norm / sigma_rel) ** 2))
    triang = mtri.Triangulation(x_m * 1000, y_m * 1000)
    # Use a powder-like colormap: dark plate background, light powder lines
    powder_cmap = LinearSegmentedColormap.from_list("powder", ["#1a1a1a", "#444444", "#a8a06a", "#e8d896", "#ffffff"])
    cs = ax.tricontourf(triang, powder, levels=200, cmap=powder_cmap, vmin=0, vmax=1)
    ax.set_aspect("equal")
    ax.set_xlim(-plate_length_mm / 2, plate_length_mm / 2)
    ax.set_ylim(-plate_length_mm / 2, plate_length_mm / 2)
    ax.set_facecolor("#000000")
    ax.set_title(title, fontsize=title_fs)
    ax.tick_params(labelsize=8)
    return cs


def get_per_freq_csv(record: dict, freq_label: str) -> Path:
    """Get the COMSOL CSV path for a given iter record + freq label."""
    cand = record["candidate_id"]
    iter_n = record["iter"]
    prefix = f"p2it{iter_n}"
    nearest = None
    for df in record["drive_freqs"]:
        if f"{int(round(df))}" == freq_label:
            nearest = df
            break
    if nearest is None:
        nearest = float(freq_label)
    vid = f"{prefix}_{cand}_comsol_f{nearest:.1f}Hz".replace(".", "p")
    return Path("data/comsol_exports") / vid / "forced_response" / "forced_response.csv"


def build_composite_mesh(record: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    """Build composite amplitude on the COMSOL mesh (no downsampling).
    Returns (x, y, composite_values, subset_str).
    """
    bc = record["best_composite"]
    subset = bc["subset"]
    method = bc["method"]
    all_x = None
    all_y = None
    amps_list = []
    for f_label in subset:
        csv = get_per_freq_csv(record, f_label)
        x, y, amp = load_comsol_mesh(csv)
        if all_x is None:
            all_x = x
            all_y = y
        # Normalize each per-frequency field to its own max
        peak = float(np.max(np.abs(amp)))
        if peak > 0:
            amp = amp / peak
        amps_list.append(amp)
    stack = np.stack(amps_list, axis=0)
    if method == "RMS":
        comp = np.sqrt(np.mean(stack ** 2, axis=0))
    elif method == "MAX":
        comp = np.max(stack, axis=0)
    else:
        comp = np.sum(stack, axis=0)
    if comp.max() > 1e-30:
        comp = comp / comp.max()
    return all_x, all_y, comp, "+".join(subset)


def main():
    summary = json.load(open("reports/sprint2_section4_phase2/phase2_summary.json"))
    plate_length_mm = 150.0
    history = summary["history"]
    recs = {h["iter"]: h for h in history}

    # === FIG 1: iter 1 (best) — full COMSOL-native breakdown ===
    iter1 = recs[1]
    bc = iter1["best_composite"]
    sub_freqs = bc["subset"]
    method = bc["method"]

    n_panels = len(sub_freqs) + 1  # individual freqs + composite
    fig, axes = plt.subplots(2, n_panels, figsize=(5 * n_panels, 10))
    if axes.ndim == 1:
        axes = axes.reshape(2, -1)

    # Row 0: displacement amplitude (rainbow, like COMSOL default)
    # Row 1: simulated powder (dark = displaced, light = powder gathers at nodes)
    for ci, fl in enumerate(sub_freqs):
        csv = get_per_freq_csv(iter1, fl)
        x, y, amp = load_comsol_mesh(csv)
        nearest = None
        for df in iter1["drive_freqs"]:
            if f"{int(round(df))}" == fl:
                nearest = df
                break
        title_freq = f"COMSOL @ {nearest:.1f} Hz" if nearest else f"COMSOL @ ~{fl} Hz"
        render_field_comsol_style(axes[0, ci], x, y, amp,
                                    title=f"{title_freq}\n|w| displacement amplitude",
                                    cmap="rainbow")
        render_powder_comsol_style(axes[1, ci], x, y, amp,
                                     title=f"{title_freq}\nsimulated Chladni powder (σ=0.025)",
                                     sigma_rel=0.025)

    # Last column: composite
    x, y, comp, sub_str = build_composite_mesh(iter1)
    render_field_comsol_style(axes[0, -1], x, y, comp,
                                title=f"{method}({sub_str}) composite\n|w| equivalent",
                                cmap="rainbow")
    render_powder_comsol_style(axes[1, -1], x, y, comp,
                                 title=f"{method}({sub_str}) composite\nfinal Chladni powder",
                                 sigma_rel=0.025)

    fig.suptitle(
        f"Phase 2 iter 1 (BEST) — COMSOL-native mesh rendering · tier1 CF-PETG sr=3\n"
        f"broad enr={bc['broad']['enrich']:.2f}× rec={bc['broad']['recall']:.2f} | "
        f"tight enr={bc['tight']['enrich']:.2f}× rec={bc['tight']['recall']:.2f}",
        fontsize=14, fontweight="bold",
    )
    plt.tight_layout()
    out1 = Path("reports/sprint2_section4_phase2/comsol_native_iter1.png")
    fig.savefig(out1, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out1}")

    # === FIG 2: headline — target | iter 0 | iter 1 | iter 3 final powder (COMSOL native) ===
    iter0 = recs[0]
    iter3 = recs[3]

    fig2, axes2 = plt.subplots(1, 4, figsize=(22, 6))

    target_bin = np.load("data/processed_targets/target_binary.npy").astype(bool)
    target_disp = np.array(Image.fromarray(target_bin.astype(np.uint8) * 255).resize((400, 400), Image.NEAREST))
    axes2[0].imshow(target_disp, cmap="Greys", origin="lower",
                     extent=[-plate_length_mm/2, plate_length_mm/2, -plate_length_mm/2, plate_length_mm/2])
    axes2[0].set_title("Target IC pattern\n(150 × 150 mm)", fontsize=12)
    axes2[0].set_aspect("equal")
    axes2[0].tick_params(labelsize=8)

    for col, (rec, lbl) in enumerate([
        (iter0, "Phase 1 baseline (iter 0)"),
        (iter1, "Phase 2 iter 1 (best broad)"),
        (iter3, "Phase 2 iter 3 (best recall)"),
    ], start=1):
        x, y, comp, sub_str = build_composite_mesh(rec)
        bc_r = rec["best_composite"]
        render_powder_comsol_style(axes2[col], x, y, comp,
                                     title=f"{lbl}\n{bc_r['method']}({sub_str})\n"
                                           f"broad enr={bc_r['broad']['enrich']:.2f}×  rec={bc_r['broad']['recall']:.2f} | "
                                           f"tight enr={bc_r['tight']['enrich']:.2f}×  rec={bc_r['tight']['recall']:.2f}",
                                     sigma_rel=0.025, title_fs=11)
        axes2[col].set_xlabel("x [mm]")
        axes2[col].set_ylabel("y [mm]")

    axes2[0].set_xlabel("x [mm]")
    axes2[0].set_ylabel("y [mm]")

    fig2.suptitle("COMSOL-native Chladni powder rendering — Phase 2 final comparison",
                   fontsize=14, fontweight="bold")
    plt.tight_layout()
    out2 = Path("reports/sprint2_section4_phase2/comsol_native_headline.png")
    fig2.savefig(out2, dpi=160, bbox_inches="tight")
    plt.close(fig2)
    print(f"Saved: {out2}")

    # === FIG 3: ONLY iter 1 powder, large, side-by-side with target ===
    fig3, axes3 = plt.subplots(1, 2, figsize=(14, 7))

    axes3[0].imshow(target_disp, cmap="Greys", origin="lower",
                     extent=[-plate_length_mm/2, plate_length_mm/2, -plate_length_mm/2, plate_length_mm/2])
    axes3[0].set_title("Target IC", fontsize=14)
    axes3[0].set_aspect("equal")
    axes3[0].set_xlabel("x [mm]")
    axes3[0].set_ylabel("y [mm]")

    x, y, comp, sub_str = build_composite_mesh(iter1)
    bc1 = iter1["best_composite"]
    render_powder_comsol_style(axes3[1], x, y, comp,
                                 title=f"Phase 2 best: {bc1['method']}({sub_str})\n"
                                       f"broad enr={bc1['broad']['enrich']:.2f}× rec={bc1['broad']['recall']:.2f} | "
                                       f"tight enr={bc1['tight']['enrich']:.2f}× rec={bc1['tight']['recall']:.2f}",
                                 sigma_rel=0.025, title_fs=12)
    axes3[1].set_xlabel("x [mm]")

    fig3.suptitle("COMSOL-rendered final Chladni pattern — tier1 CF-PETG sr=3 (Phase 2 iter 1)",
                   fontsize=14, fontweight="bold")
    plt.tight_layout()
    out3 = Path("reports/sprint2_section4_phase2/comsol_native_iter1_focused.png")
    fig3.savefig(out3, dpi=180, bbox_inches="tight")
    plt.close(fig3)
    print(f"Saved: {out3}")

    # === FIG 4: Multi-sigma sweep — show how powder σ choice affects visual ===
    fig4, axes4 = plt.subplots(1, 4, figsize=(22, 6))
    sigmas = [0.05, 0.025, 0.012, 0.008]
    sigma_names = ["broad σ=0.05", "medium σ=0.025", "sharp σ=0.012", "very sharp σ=0.008"]
    x, y, comp, sub_str = build_composite_mesh(iter1)
    for i, (sig, name) in enumerate(zip(sigmas, sigma_names)):
        render_powder_comsol_style(axes4[i], x, y, comp,
                                     title=f"{name}\nPhase 2 iter 1 ({bc1['method']}({sub_str}))",
                                     sigma_rel=sig, title_fs=11)
        axes4[i].set_xlabel("x [mm]")
        if i == 0:
            axes4[i].set_ylabel("y [mm]")

    fig4.suptitle("Effect of powder σ on visualization — Phase 2 iter 1 best composite",
                   fontsize=14, fontweight="bold")
    plt.tight_layout()
    out4 = Path("reports/sprint2_section4_phase2/comsol_native_iter1_sigma_sweep.png")
    fig4.savefig(out4, dpi=150, bbox_inches="tight")
    plt.close(fig4)
    print(f"Saved: {out4}")


if __name__ == "__main__":
    main()
