from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # JSON / JSON
import sys  # 系统 / System
from pathlib import Path  # 路径 / Paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 根 / Root
if str(PROJECT_ROOT) not in sys.path:  # 检查 / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加 / Add

import matplotlib  # matplotlib / matplotlib
matplotlib.use("Agg")  # Agg / Agg
import matplotlib.pyplot as plt  # pyplot / pyplot
import numpy as np  # NumPy / NumPy

from src.comsol.import_results import interpolate_to_grid  # 插值 / Interpolate
from src.forced_response.score_comsol_response import load_forced_response_csv  # CSV / CSV
from src.scoring.recognisability_score import chladni_powder_density  # 撒粉 / Powder
from src.scoring.recognisability_score import recognisability_score_grid  # 评分 / Score


def rms_compose(amps: list[np.ndarray], weights: list[float]) -> np.ndarray:  # 加权 RMS / RMS
    w = np.asarray(weights, dtype=np.float64) / max(sum(weights), 1.0e-12)  # 归一 / Normalise
    stack = np.stack([a ** 2 for a in amps], axis=0)  # 平方 / Squares
    return np.sqrt(np.clip((w[:, None, None] * stack).sum(axis=0), 0.0, None))  # sqrt / sqrt


def load_composite(candidate_dir_pattern: str, freqs: list[float], weights: list[float]) -> np.ndarray | None:  # 加载并 RMS / Load and RMS
    amps: list[np.ndarray] = []  # 振幅 / Amplitudes
    matched_weights: list[float] = []  # 匹配权重 / Matched weights
    for f, wgt in zip(freqs, weights):  # 遍历 / Iterate
        for fmt in [f'{f:.1f}', f'{f:.2f}']:  # 两种精度 / Two precisions
            label = f'f{fmt}'.replace('.', 'p')  # 标签 / Label
            csv_path = Path(f'data/comsol_exports/{candidate_dir_pattern}_sweep_{label}/forced_response/forced_response.csv')  # 路径 / Path
            if csv_path.exists():  # 找到 / Found
                x, y, _, _, w_abs = load_forced_response_csv(csv_path)  # CSV / Load
                field = interpolate_to_grid(x, y, w_abs, grid_size=256)  # 插值 / Interp
                amps.append(field)  # 追加 / Append
                matched_weights.append(wgt)  # 追加 / Append
                break  # 找到一个就行 / Break
    if not amps:  # 没找到 / Empty
        return None  # 返回 / Return
    return rms_compose(amps, matched_weights)  # RMS / RMS


def main() -> int:  # 主 / Main
    cases = [
        ("X-form", "w8_xform_v1", "target_xform.npy"),  # X / X
        ("IC letters", "w8_ic_v1", "target_binary.npy"),  # IC / IC
        ("+ Cross", "w8_cross_v1", "target_cross.npy"),  # Cross / Cross
        ("Diagonal", "w8_diagonal_v1", "target_diagonal.npy"),  # Diag / Diag
        ("Sprint1 baseline (IC)", "w8_ic_sprint1_baseline", "target_binary.npy", "sprint1_baseline_ic"),  # baseline / baseline
        ("Sprint1 +SBS (IC)", "w8_ic_sprint1_sbs", "target_binary.npy", "sprint1_sbs_ic"),  # SBS / SBS
    ]  # 案例 / Cases

    fig, axes = plt.subplots(len(cases), 3, figsize=(12, 4 * len(cases)))  # 子图 / Subplots
    for row, case in enumerate(cases):  # 遍历 / Iterate
        if len(case) == 3:  # 历史 / Historical
            label, cid, target_name = case  # 解构 / Unpack
            export_prefix = cid  # 历史 / Historical
        else:  # Sprint1 / Sprint1
            label, cid, target_name, export_prefix = case  # 解构 / Unpack
        target = np.load(f'data/processed_targets/{target_name}').astype(bool)  # 目标 / Target
        meta = json.load(open(f'candidates/{cid}/w8_optimization_summary.json'))  # 摘要 / Meta
        composite = load_composite(export_prefix, meta['frequencies_hz'], meta['weights'])  # 合成 / Composite
        if composite is None:  # 缺数据 / Missing
            for ax in axes[row]:  # 关掉 / Hide
                ax.axis('off')  # 关 / Off
                ax.text(0.5, 0.5, f'{label}: no COMSOL data', ha='center', va='center', transform=ax.transAxes)  # 提示 / Text
            continue  # 跳过 / Skip
        m = recognisability_score_grid(composite, target, sigma_rel=0.05, percentile=20.0)  # 评分 / Score
        powder = chladni_powder_density(composite, sigma_rel=0.05)  # 撒粉 / Powder

        ax = axes[row, 0]  # 左 / Left
        ax.imshow(target, cmap='gray_r')  # 目标 / Target
        ax.set_title(f'{label}\ntarget', fontsize=10)  # 标题 / Title
        ax.axis('off')  # 关 / Off

        ax = axes[row, 1]  # 中 / Middle
        ax.imshow(composite, cmap='inferno')  # 振幅 / Amplitude
        ax.set_title(f'COMSOL RMS amplitude\nmax={composite.max():.2e} m', fontsize=10)  # 标题 / Title
        ax.axis('off')  # 关 / Off

        ax = axes[row, 2]  # 右 / Right
        ax.imshow(powder, cmap='gray', vmin=0, vmax=1)  # 撒粉 / Powder
        ax.contour(target, levels=[0.5], colors='red', linewidths=0.5)  # 目标轮廓 / Target outline
        ax.set_title(f'simulated powder\nenrichment={m["enrichment_factor"]:.2f}x  recall={m["coverage_recall"]*100:.0f}%', fontsize=10)  # 标题 / Title
        ax.axis('off')  # 关 / Off

    plt.suptitle("Sprint 1 COMSOL validation: bug-fix-corrected enrichment\n(Chladni powder = exp(-(|u|/peak)²/σ²), red = target outline)", fontsize=12)  # 总标 / Suptitle
    plt.tight_layout()  # 紧凑 / Tight
    out = Path('reports/pipeline/sprint1_comsol_status.png')  # 输出 / Output
    out.parent.mkdir(parents=True, exist_ok=True)  # 建目录 / Mkdir
    plt.savefig(out, dpi=110, bbox_inches='tight')  # 保存 / Save
    plt.close(fig)  # 关 / Close
    print(f"Saved: {out}")  # 提示 / Print
    return 0  # 返回 / Return


if __name__ == "__main__":  # 直接 / Direct
    raise SystemExit(main())  # 退出 / Exit
