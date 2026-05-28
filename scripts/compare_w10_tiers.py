"""Compare W8 baseline (isotropic) vs W10 Tier 1 (sr=3.0) vs W10 Tier 2 (sr=12.0).
对比 W8 baseline (各向同性) vs W10 Tier1/Tier2 surrogate-only。

Produces:
- reports/pipeline/w10_tier_comparison.png  : target | H | θ | composite | powder for each tier
- reports/pipeline/w10_tier_trajectory.png  : enrichment curve across steps for all three runs
- reports/w10_tier_comparison.json          : numeric summary
"""
from __future__ import annotations  # / Type hints

import json  # / JSON
import sys  # / System
from pathlib import Path  # / Paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # / Root
if str(PROJECT_ROOT) not in sys.path:  # / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # / Add

import matplotlib.pyplot as plt  # / Pyplot
import numpy as np  # / NumPy

from src.config import load_config  # / Config
from src.physics.plate_loss_adapter import load_target_binary  # / Target
from src.scoring.recognisability_score import chladni_powder_density  # / Powder
from src.scoring.recognisability_score import coverage_recall  # / Recall


def _load_summary(path: Path) -> dict:  # / Load summary
    return json.loads(Path(path).read_text(encoding="utf-8"))  # / Parse


def _safe_load_numpy(p: Path) -> np.ndarray | None:  # / Safe load
    try:
        return np.load(p)  # / Load
    except Exception:
        return None  # / None


def _compute_metrics(amp_grid: np.ndarray, target_binary_full: np.ndarray, sigma_rel: float = 0.05) -> dict:  # / Metrics
    from src.scoring.geometry_helpers import resize_binary_nearest  # / Lazy
    N = int(amp_grid.shape[0])  # / N
    tgt_n = resize_binary_nearest(target_binary_full.astype(bool), N)  # / Resize
    density = chladni_powder_density(amp_grid, sigma_rel=float(sigma_rel))  # / Powder
    mass_target = float(density[tgt_n].sum())  # / On-target mass
    mass_total = float(density.sum())  # / Total mass
    p_target = mass_target / max(mass_total, 1.0e-12)  # / P(on target)
    p_uniform = float(tgt_n.sum()) / float(N * N)  # / P(uniform)
    enrichment = p_target / max(p_uniform, 1.0e-12)  # / Enrichment
    recall = coverage_recall(amp_grid, tgt_n, percentile=20.0)  # / Recall (lowest 20% amplitude valley)
    return {"enrichment": float(enrichment), "recall": float(recall), "density_peak": float(density.max()), "p_target": float(p_target)}  # / Return


def main() -> int:  # / Main
    config = load_config("config.yaml")  # / Config
    target = load_target_binary(config).astype(bool)  # / Target binary

    runs = [
        {"label": "W8 baseline\n(isotropic, sr=1.0)", "dir": Path("candidates/w8_ic_v1"), "summary_name": "w8_optimization_summary.json", "sr": 1.0, "tier": "baseline"},
        {"label": "W10 Tier 1\nCF-PETG (sr=3.0)", "dir": Path("candidates/w10_ic_tier1_sr3"), "summary_name": "w10_optimization_summary.json", "sr": 3.0, "tier": "tier1"},
        {"label": "W10 Tier 2\nContinuous CF (sr=12.0)", "dir": Path("candidates/w10_ic_tier2_sr12"), "summary_name": "w10_optimization_summary.json", "sr": 12.0, "tier": "tier2"},
    ]  # 三组对比 / Three groups

    data = []  # 收集 / Collect
    for r in runs:  # 每组 / Per run
        summary_path = r["dir"] / r["summary_name"]  # / Path
        if not summary_path.exists():  # 缺失 / Missing
            print(f"[warn] missing {summary_path}; skip"); continue  # / Warn
        summary = _load_summary(summary_path)  # / Load
        amp = _safe_load_numpy(r["dir"] / "composite_amplitude.npy")  # / Composite
        H = _safe_load_numpy(r["dir"] / "H_continuous.csv") if (r["dir"] / "H_continuous.csv").exists() else None  # / H
        if H is None:  # CSV / CSV
            try:
                H = np.loadtxt(str(r["dir"] / "H_continuous.csv"), delimiter=",")
            except Exception:
                H = None
        theta = None  # / θ
        theta_csv = r["dir"] / "theta_continuous_rad.csv"  # / Path
        if theta_csv.exists():  # θ / θ
            theta = np.loadtxt(str(theta_csv), delimiter=",")  # / Load
        metrics = _compute_metrics(amp, target, sigma_rel=0.05) if amp is not None else {"enrichment": float("nan"), "recall": float("nan"), "density_peak": float("nan"), "p_target": float("nan")}  # / Metrics
        data.append({"run": r, "summary": summary, "amp": amp, "H": H, "theta": theta, "metrics": metrics})  # / Append

    # === Figure 1: Tier comparison grid ===
    fig, axes = plt.subplots(len(data), 5, figsize=(16, 4.0 * len(data)), squeeze=False)  # / 5 cols
    for i, d in enumerate(data):  # 每行 / Per row
        r = d["run"]; s = d["summary"]; m = d["metrics"]; amp = d["amp"]; H = d["H"]; theta = d["theta"]  # / Unpack
        # Col 0: target
        ax = axes[i, 0]; ax.imshow(target, cmap="gray_r"); ax.set_title("Target (IC)" if i == 0 else "")  # / Target
        ax.set_ylabel(r["label"], fontsize=10); ax.set_xticks([]); ax.set_yticks([])  # / Label
        # Col 1: H
        ax = axes[i, 1]
        if H is not None:
            im = ax.imshow(H, cmap="viridis"); plt.colorbar(im, ax=ax, fraction=0.046)
        ax.set_title("H (mm)" if i == 0 else ""); ax.set_xticks([]); ax.set_yticks([])  # / H
        # Col 2: θ (Tier 1 / Tier 2 only)
        ax = axes[i, 2]
        if theta is not None:
            theta_deg = (np.rad2deg(theta) % 180.0)  # / mod 180
            im = ax.imshow(theta_deg, cmap="twilight", vmin=0, vmax=180); plt.colorbar(im, ax=ax, fraction=0.046)
            # 用箭头叠加方向场 / Overlay director arrows
            ny, nx = theta.shape
            X, Y = np.meshgrid(np.arange(nx), np.arange(ny))
            U = np.cos(theta); V = -np.sin(theta)  # screen y inverted
            step_arr = max(1, ny // 8)
            ax.quiver(X[::step_arr, ::step_arr], Y[::step_arr, ::step_arr], U[::step_arr, ::step_arr], V[::step_arr, ::step_arr], color="white", scale=20, headlength=0, headwidth=1, pivot="middle", alpha=0.8)
        else:
            ax.text(0.5, 0.5, "(isotropic\nno θ)", ha="center", va="center", transform=ax.transAxes, fontsize=11, color="gray")
        ax.set_title(f"θ (deg, mod π)" if i == 0 else ""); ax.set_xticks([]); ax.set_yticks([])  # / θ
        # Col 3: composite amplitude (proxy grid)
        ax = axes[i, 3]
        if amp is not None:
            im = ax.imshow(np.abs(amp), cmap="magma"); plt.colorbar(im, ax=ax, fraction=0.046)
        ax.set_title("Composite |U|" if i == 0 else ""); ax.set_xticks([]); ax.set_yticks([])  # / U
        # Col 4: powder density overlay
        ax = axes[i, 4]
        if amp is not None:
            N = amp.shape[0]
            density = chladni_powder_density(amp, sigma_rel=0.05)
            ax.imshow(density, cmap="magma")
            from src.scoring.geometry_helpers import resize_binary_nearest
            tgt_n = resize_binary_nearest(target.astype(bool), N)
            ax.contour(tgt_n.astype(float), levels=[0.5], colors="cyan", linewidths=1.2)
        ax.set_title(f"Powder + target contour\nenrichment {m['enrichment']:.2f}x  recall {m['recall']*100:.1f}%" if i == 0 else f"enrichment {m['enrichment']:.2f}x  recall {m['recall']*100:.1f}%")
        ax.set_xticks([]); ax.set_yticks([])

    fig.suptitle("W10 Anisotropy: Material Tier Comparison (surrogate-only, IC target)", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out1 = Path("reports/pipeline/w10_tier_comparison.png"); out1.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out1, dpi=110)
    print(f"saved: {out1}")
    plt.close(fig)

    # === Figure 2: Enrichment trajectory ===
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for d in data:  # 每条曲线 / Per curve
        r = d["run"]; s = d["summary"]
        enr_curve = s.get("trace", {}).get("enrichment", [])
        if enr_curve:
            axes[0].plot(enr_curve, label=r["label"].replace("\n", " "), linewidth=1.8)
    axes[0].set_xlabel("step"); axes[0].set_ylabel("surrogate enrichment (×)")
    axes[0].set_title("Enrichment vs step (surrogate)")
    axes[0].grid(alpha=0.3); axes[0].legend(loc="lower right", fontsize=9)

    bar_labels = [d["run"]["label"].replace("\n", " ") for d in data]
    bar_values = [d["metrics"]["enrichment"] for d in data]
    bar_colors = ["#888888", "#3a8dde", "#dc3545"]
    axes[1].barh(bar_labels, bar_values, color=bar_colors[: len(bar_values)])
    for i, v in enumerate(bar_values):
        axes[1].text(v + 0.1, i, f" {v:.2f}×", va="center", fontsize=10)
    axes[1].set_xlabel("surrogate enrichment (×)")
    axes[1].set_title("Final surrogate enrichment")
    axes[1].grid(axis="x", alpha=0.3)

    fig.suptitle("W10 tier comparison — surrogate enrichment progression", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out2 = Path("reports/pipeline/w10_tier_trajectory.png")
    fig.savefig(out2, dpi=110)
    print(f"saved: {out2}")
    plt.close(fig)

    # === JSON summary ===
    summary_out = {
        "runs": [
            {
                "tier": d["run"]["tier"],
                "label": d["run"]["label"].replace("\n", " "),
                "stiffness_ratio": d["run"]["sr"],
                "surrogate_enrichment": d["metrics"]["enrichment"],
                "surrogate_recall": d["metrics"]["recall"],
                "p_target": d["metrics"]["p_target"],
                "frequencies_hz": d["summary"].get("frequencies_hz"),
                "weights": d["summary"].get("weights"),
                "best_step": d["summary"].get("best_step"),
                "executed_steps": d["summary"].get("executed_steps"),
                "theta_rms_deg_final": d["summary"].get("trace", {}).get("theta_rms_deg", [None])[-1] if d["summary"].get("trace", {}).get("theta_rms_deg") else None,
            }
            for d in data
        ],
        "target": "IC (configured default)",
        "loss": "enrichment+contrast+recall (surrogate)",
        "sigma_rel": 0.05,
    }
    out3 = Path("reports/w10_tier_comparison.json")
    out3.write_text(json.dumps(summary_out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out3}")
    print()
    print("=== summary ===")
    for r in summary_out["runs"]:
        print(f"  {r['tier']:>8s}  sr={r['stiffness_ratio']:6.2f}  surrogate_enrichment={r['surrogate_enrichment']:6.3f}×  recall={r['surrogate_recall']*100:5.1f}%  θ_RMS_final={r['theta_rms_deg_final']}")
    return 0


if __name__ == "__main__":  # / Direct
    raise SystemExit(main())  # / Exit
