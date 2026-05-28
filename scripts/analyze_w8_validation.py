from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # JSON / JSON
import sys  # 系统 / System
from pathlib import Path  # 路径 / Paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 根 / Root
if str(PROJECT_ROOT) not in sys.path:  # 检查 / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加 / Add

import numpy as np  # NumPy / NumPy

from src.frequency_domain.load_frequency_response import load_frequency_response  # 加载 / Loader
from src.scoring.recognisability_score import chladni_powder_density  # 粉 / Powder
from src.scoring.recognisability_score import recognisability_score_grid  # 评分 / Score


def rms_compose(per_freq_amps: list[np.ndarray], weights: list[float]) -> np.ndarray:  # 加权 RMS / Weighted RMS
    w = np.asarray(weights, dtype=np.float64)  # 权重 / Weights
    w = w / max(float(w.sum()), 1.0e-12)  # 归一化 / Normalise
    stack = np.stack([a ** 2 for a in per_freq_amps], axis=0)  # 平方 / Squares
    composite_sq = (w[:, None, None] * stack).sum(axis=0)  # 加权和 / Weighted sum
    return np.sqrt(np.clip(composite_sq, 0.0, None))  # sqrt（不加固定 epsilon，避免 COMSOL 1e-23 量级被 epsilon 压平） / sqrt without additive epsilon


CANDIDATES = [
    ("w8_diagonal_v1", "target_diagonal.npy", "pipeline_w8_diag_validation_w8_diagonal_v1"),
    ("w8_xform_v1", "target_xform.npy", "pipeline_w8_xform_validation_w8_xform_v1"),
    ("w8_cross_v1", "target_cross.npy", "pipeline_w8_cross_validation_w8_cross_v1"),
    ("w8_ic_v1", "target_binary.npy", "pipeline_w8_ic_validation_w8_ic_v1"),
]  # 候选 / Candidates


def main() -> int:  # 主 / Main
    report: dict[str, dict] = {}  # 报告 / Report
    for cid, target_name, export_dir in CANDIDATES:  # 遍历 / Iterate
        target_path = Path("data/processed_targets") / target_name  # 目标 / Target
        target = np.load(target_path).astype(bool)  # 加载 / Load
        sweep_csv = Path("data/comsol_frequency_exports") / export_dir / "frequency_response.csv"  # CSV / CSV
        if not sweep_csv.exists():  # 跳过 / Skip
            print(f"  SKIP {cid}: missing {sweep_csv}")  # 提示 / Hint
            continue  # 跳过 / Skip
        summary_path = Path("candidates") / cid / "w8_optimization_summary.json"  # 摘要 / Summary
        meta = json.loads(summary_path.read_text(encoding="utf-8"))  # 加载 / Load
        freqs = list(meta["frequencies_hz"])  # 频率 / Freqs
        weights = list(meta["weights"])  # 权重 / Weights
        surrogate = meta.get("best_surrogate_metrics") or {}  # 代理 / Surrogate
        responses, _ = load_frequency_response(str(sweep_csv), 256)  # 加载 / Load
        available_freqs = sorted(responses.keys())  # 频率 / Freqs
        amps = []  # 振幅 / Amplitudes
        for f in freqs:  # 遍历 / Iterate
            best_match = min(available_freqs, key=lambda x: abs(x - f))  # 最近 / Nearest
            if abs(best_match - f) > 1.0:  # 过远 / Too far
                print(f"  WARN {cid}: freq {f:.2f} Hz not found, nearest {best_match:.2f}")  # 提示 / Warn
            amps.append(responses[best_match])  # 加入 / Append
        composite_amp = rms_compose(amps, weights)  # RMS / RMS
        comsol_metrics = recognisability_score_grid(composite_amp, target, sigma_rel=0.05, percentile=20.0)  # 综合分 / Score
        per_freq_metrics = {}  # 每频 / Per freq
        for f, a in zip(freqs, amps):  # 遍历 / Iterate
            m = recognisability_score_grid(a, target, sigma_rel=0.05, percentile=20.0)  # 评分 / Score
            per_freq_metrics[f] = m  # 收集 / Collect
        best_single = max(per_freq_metrics.items(), key=lambda kv: kv[1]["composite_recognisability"])  # 最佳单频 / Best single
        print(f"\n=== {cid} (target: {target_name}) ===")  # 头 / Header
        print(f"  Surrogate predicted: enrichment={surrogate.get('enrichment', 0.0):.2f}x  contrast={surrogate.get('contrast', 0.0):.2f}  recall={surrogate.get('recall', 0.0)*100:.1f}%")  # 代理 / Surrogate
        print(f"  COMSOL RMS-composite: enrichment={comsol_metrics['enrichment_factor']:.2f}x  contrast={comsol_metrics['gaussian_contrast']:.2f}  recall={comsol_metrics['coverage_recall']*100:.1f}%  direction={comsol_metrics['directional_alignment']:.2f}  composite={comsol_metrics['composite_recognisability']:.4f}")  # COMSOL / COMSOL
        print(f"  COMSOL best single freq @ {best_single[0]:.1f} Hz: enrichment={best_single[1]['enrichment_factor']:.2f}x  recall={best_single[1]['coverage_recall']*100:.1f}%  composite={best_single[1]['composite_recognisability']:.4f}")  # 最佳单频 / Best single
        np.save(Path("candidates") / cid / "composite_amplitude_comsol.npy", composite_amp)  # 保存 / Save
        report[cid] = {"target": target_name, "frequencies_hz": freqs, "weights": weights, "surrogate": surrogate, "comsol_rms_composite": comsol_metrics, "comsol_best_single_freq": {"frequency_hz": float(best_single[0]), "metrics": best_single[1]}, "per_freq_metrics": {f"{f:.2f}": per_freq_metrics[f] for f in freqs}}  # 报告 / Report
    out_path = Path("reports/w8_comsol_validation.json")  # 输出 / Output
    out_path.parent.mkdir(parents=True, exist_ok=True)  # 建目录 / Mkdir
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 / Write
    print(f"\nReport saved: {out_path}")  # 打印 / Print
    return 0  # 返回 / Return


if __name__ == "__main__":  # 直接 / Direct
    raise SystemExit(main())  # 退出 / Exit
