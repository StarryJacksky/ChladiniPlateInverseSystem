from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # JSON / JSON
import sys  # 系统 / System
from pathlib import Path  # 路径 / Paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 根 / Root
if str(PROJECT_ROOT) not in sys.path:  # 检查 / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加 / Add

import argparse  # argparse / argparse
import matplotlib  # matplotlib / matplotlib
matplotlib.use("Agg")  # Agg / Agg
import matplotlib.pyplot as plt  # pyplot / pyplot
import numpy as np  # NumPy / NumPy

from src.comsol.import_results import interpolate_to_grid  # 插值 / Interpolate
from src.forced_response.score_comsol_response import load_forced_response_csv  # CSV / CSV
from src.scoring.recognisability_score import chladni_powder_density  # 撒粉 / Powder


def rms_compose(amps: list[np.ndarray], weights: list[float]) -> np.ndarray:  # RMS / RMS
    w = np.asarray(weights, dtype=np.float64) / max(sum(weights), 1e-12)  # 归一 / Normalise
    stack = np.stack([a ** 2 for a in amps], axis=0)  # 平方 / Squares
    return np.sqrt(np.clip((w[:, None, None] * stack).sum(axis=0), 0.0, None))  # sqrt / sqrt


def main() -> int:  # 主 / Main
    parser = argparse.ArgumentParser()  # 解析 / Parse
    parser.add_argument("--run-name", type=str, required=True, help="W9 run name (e.g. ic_v1).")  # 运行 / Run
    parser.add_argument("--target", type=str, required=True, help="Target NPY path.")  # 目标 / Target
    args = parser.parse_args()  # 解析 / Parse

    target = np.load(args.target).astype(bool)  # 目标 / Target
    run_root = PROJECT_ROOT / "candidates" / "w9_runs" / args.run_name  # 根 / Root
    history = json.loads((run_root / "w9_history.json").read_text(encoding="utf-8"))  # 历史 / History
    iters = history["history"]  # 迭代 / Iters
    n_iter = len(iters)  # 数 / Count
    print(f"Loaded {n_iter} outer iters from {run_root}")  # 提示 / Print

    fig, axes = plt.subplots(n_iter, 3, figsize=(12, 4 * n_iter))  # 子图 / Subplots
    if n_iter == 1:  # 单行 / Single row
        axes = axes.reshape(1, -1)  # 重整 / Reshape
    for i, h in enumerate(iters):  # 遍历 / Iterate
        freqs = h["frequencies_hz"]  # 频率 / Freqs
        weights = h["weights"]  # 权重 / Weights
        prefix = f"w9_{args.run_name}_iter{i}"  # 前缀 / Prefix
        amps: list[np.ndarray] = []  # 振幅 / Amplitudes
        for f in freqs:  # 遍历 / Iterate
            found = None  # 占位 / Placeholder
            for fmt in [f"{f:.1f}", f"{f:.2f}"]:  # 两种 / Two
                label = f"f{fmt}".replace(".", "p")  # 标签 / Label
                csv_path = PROJECT_ROOT / "data" / "comsol_exports" / f"{prefix}_sweep_{label}" / "forced_response" / "forced_response.csv"  # 路径 / Path
                if csv_path.exists():  # 找到 / Found
                    x, y, _, _, w_abs = load_forced_response_csv(csv_path)  # CSV / Load
                    field = interpolate_to_grid(x, y, w_abs, grid_size=256)  # 插值 / Interp
                    found = field  # 找到 / Found
                    break  # 退 / Break
            if found is not None:  # 有 / Yes
                amps.append(found)  # 加 / Append
        if not amps:  # 空 / Empty
            for ax in axes[i]:  # 关 / Hide
                ax.axis("off")  # 关 / Off
            continue  # 跳过 / Skip
        composite = rms_compose(amps, weights[: len(amps)])  # RMS / RMS
        powder = chladni_powder_density(composite, sigma_rel=0.05)  # 撒粉 / Powder
        H_path = run_root / f"H_iter{i}.npy"  # H / H
        H = np.load(H_path) if H_path.exists() else np.zeros((15, 15))  # 加载 / Load

        ax = axes[i, 0]  # H / H
        ax.imshow(H, cmap="viridis", vmin=0.6, vmax=1.8)  # H 图 / H plot
        ax.set_title(f"iter {i}: H (15×15)\ntrust={h['trust_radius_mm']:.2f} mm", fontsize=10)  # 标题 / Title
        ax.axis("off")  # 关 / Off

        ax = axes[i, 1]  # COMSOL / COMSOL
        ax.imshow(composite, cmap="inferno")  # 振幅 / Amplitude
        ax.set_title(f"COMSOL RMS amplitude\nmax={composite.max():.2e} m", fontsize=10)  # 标题 / Title
        ax.axis("off")  # 关 / Off

        ax = axes[i, 2]  # 撒粉 / Powder
        ax.imshow(powder, cmap="gray", vmin=0, vmax=1)  # 撒粉 / Powder
        ax.contour(target, levels=[0.5], colors="red", linewidths=0.5)  # 目标 / Target outline
        title = (f"powder (target=red)\nCOMSOL enrich={h['comsol_enrichment']:.2f}x  "
                 f"surr={h['surrogate_enrichment']:.2f}x\nratio decision: {h['trust_decision']}")  # 标题 / Title
        ax.set_title(title, fontsize=9)  # 标题 / Title
        ax.axis("off")  # 关 / Off

    plt.suptitle(f"W9 trust-region: {args.run_name}\n"
                 f"Best COMSOL enrichment: {history['best_comsol_enrichment']:.3f}x at iter {history['best_iteration']}", fontsize=11)  # 总标 / Suptitle
    plt.tight_layout()  # 紧凑 / Tight
    out = PROJECT_ROOT / "reports" / "pipeline" / f"w9_{args.run_name}_progression.png"  # 输出 / Output
    out.parent.mkdir(parents=True, exist_ok=True)  # 建 / Mkdir
    plt.savefig(out, dpi=110, bbox_inches="tight")  # 保存 / Save
    plt.close(fig)  # 关 / Close
    print(f"Saved: {out}")  # 提示 / Print

    # Enrichment trajectory plot
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))  # 子图 / Subplots
    iter_x = list(range(n_iter))  # x / X
    surr_y = [h["surrogate_enrichment"] for h in iters]  # 代理 / Surrogate
    comsol_y = [h["comsol_enrichment"] for h in iters]  # COMSOL / COMSOL
    radius_y = [h["trust_radius_mm"] for h in iters]  # 半径 / Radius
    axes[0].plot(iter_x, surr_y, "o-", label="surrogate enrichment", color="C0")  # 代理 / Surrogate
    axes[0].plot(iter_x, comsol_y, "s-", label="COMSOL enrichment", color="C1")  # COMSOL / COMSOL
    axes[0].axhline(1.97, color="gray", linestyle="--", label="Sprint1 baseline COMSOL = 1.97x")  # 基线 / Baseline
    axes[0].set_xlabel("outer iter")  # x / X label
    axes[0].set_ylabel("enrichment (×)")  # y / Y label
    axes[0].set_title("Enrichment trajectory")  # 标题 / Title
    axes[0].grid(True, alpha=0.3)  # 网格 / Grid
    axes[0].legend()  # 图例 / Legend

    axes[1].plot(iter_x, radius_y, "o-", color="C2")  # 半径 / Radius
    axes[1].set_xlabel("outer iter")  # x / X label
    axes[1].set_ylabel("trust radius (mm)")  # y / Y label
    axes[1].set_title("Trust radius evolution")  # 标题 / Title
    axes[1].grid(True, alpha=0.3)  # 网格 / Grid

    plt.tight_layout()  # 紧凑 / Tight
    out2 = PROJECT_ROOT / "reports" / "pipeline" / f"w9_{args.run_name}_trajectory.png"  # 输出 / Output
    plt.savefig(out2, dpi=120, bbox_inches="tight")  # 保存 / Save
    plt.close(fig)  # 关 / Close
    print(f"Saved: {out2}")  # 提示 / Print

    return 0  # 返回 / Return


if __name__ == "__main__":  # 直接 / Direct
    raise SystemExit(main())  # 退出 / Exit
