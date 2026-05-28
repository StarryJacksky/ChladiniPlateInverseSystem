from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # JSON / JSON
import sys  # 系统 / System
from pathlib import Path  # 路径 / Paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 根 / Root
if str(PROJECT_ROOT) not in sys.path:  # 检查 / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加 / Add

import numpy as np  # NumPy / NumPy

from src.comsol.import_results import interpolate_to_grid  # 插值 / Interpolate
from src.forced_response.score_comsol_response import load_forced_response_csv  # CSV / CSV
from src.scoring.recognisability_score import recognisability_score_grid  # 评分 / Score


def rms_compose(per_freq_amps: list[np.ndarray], weights: list[float]) -> np.ndarray:  # 加权 RMS / Weighted RMS
    w = np.asarray(weights, dtype=np.float64)  # 权重 / Weights
    w = w / max(float(w.sum()), 1.0e-12)  # 归一化 / Normalise
    stack = np.stack([a ** 2 for a in per_freq_amps], axis=0)  # 平方 / Squares
    composite_sq = (w[:, None, None] * stack).sum(axis=0)  # 加权和 / Weighted sum
    return np.sqrt(np.clip(composite_sq, 0.0, None))  # sqrt（不加固定 epsilon，避免 COMSOL 1e-23 量级被 1e-18 epsilon 压平） / sqrt without additive epsilon (COMSOL composite_sq ~1e-23)


def load_field(candidate_dir: Path, grid_size: int = 256) -> np.ndarray:  # 加载单频场 / Load single-freq field
    csv_path = candidate_dir / "forced_response" / "forced_response.csv"  # 路径 / Path
    if not csv_path.exists():  # 不存在 / Missing
        raise FileNotFoundError(f"Missing forced response CSV: {csv_path}")  # 抛错 / Raise
    x, y, _, _, w_abs = load_forced_response_csv(csv_path)  # 读 CSV / Load
    field = interpolate_to_grid(x, y, w_abs, grid_size=grid_size)  # 插值 / Interp
    return field  # 返回 / Return


def analyze_one(tag: str, target_path: Path, exports_root: Path, surrogate_summary_path: Path) -> dict:  # 分析单个配置 / Analyse one config
    target = np.load(target_path).astype(bool)  # 目标 / Target
    meta = json.loads(surrogate_summary_path.read_text(encoding="utf-8"))  # 摘要 / Summary
    freqs = list(meta["frequencies_hz"])  # 频率 / Freqs
    weights = list(meta["weights"])  # 权重 / Weights
    surrogate = meta.get("best_surrogate_metrics") or {}  # 代理 / Surrogate

    amps: list[np.ndarray] = []  # 振幅 / Amplitudes
    per_freq_metrics: dict[float, dict] = {}  # 每频 / Per freq
    for f in freqs:  # 遍历 / Iterate
        f_label = f"f{f:.1f}".replace(".", "p")  # 频率标签 / Freq tag
        cand_dir = exports_root / f"{tag}_sweep_{f_label}"  # 目录 / Dir
        if not cand_dir.exists():  # 不存在 / Missing
            print(f"  [warn] missing exports for {f_label}: {cand_dir}")  # 提示 / Warn
            continue  # 跳过 / Skip
        field = load_field(cand_dir, grid_size=256)  # 加载 / Load
        amps.append(field)  # 追加 / Append
        m = recognisability_score_grid(field, target, sigma_rel=0.05, percentile=20.0)  # 评分 / Score
        per_freq_metrics[float(f)] = m  # 保存 / Save

    if len(amps) != len(freqs):  # 数量不一致 / Mismatch
        print(f"  [warn] only {len(amps)}/{len(freqs)} frequencies available; aborting RMS")  # 提示 / Warn
        return {"surrogate": surrogate, "comsol_rms_composite": None, "per_freq_metrics": per_freq_metrics}  # 返回部分 / Partial
    composite_amp = rms_compose(amps, weights)  # RMS / RMS
    comsol_metrics = recognisability_score_grid(composite_amp, target, sigma_rel=0.05, percentile=20.0)  # 综合 / Composite
    best_single = max(per_freq_metrics.items(), key=lambda kv: kv[1]["composite_recognisability"])  # 最佳单频 / Best single
    return {"freqs_hz": freqs, "weights": weights, "surrogate": surrogate, "comsol_rms_composite": comsol_metrics, "comsol_best_single": {"freq_hz": float(best_single[0]), "metrics": best_single[1]}, "per_freq_metrics": {f"{f:.2f}": per_freq_metrics[f] for f in sorted(per_freq_metrics.keys())}}  # 返回 / Return


def main() -> int:  # 主 / Main
    target_path = Path("data/processed_targets/target_binary.npy")  # IC / IC
    exports_root = Path("data/comsol_exports")  # COMSOL 导出 / COMSOL exports
    configs = [
        ("baseline", "candidates/w8_ic_sprint1_baseline/w8_optimization_summary.json", "sprint1_baseline_ic"),  # baseline / baseline
        ("+SBS",     "candidates/w8_ic_sprint1_sbs/w8_optimization_summary.json",      "sprint1_sbs_ic"),       # SBS / SBS
        ("+Sinkhorn(A1)", "candidates/w8_ic_sprint1_sinkhorn/w8_optimization_summary.json", "sprint1_sinkhorn_ic"),  # Sinkhorn / Sinkhorn
        ("+SBS+Sinkhorn", "candidates/w8_ic_sprint1_both/w8_optimization_summary.json", "sprint1_both_ic"),     # Both / Both
    ]
    report: dict[str, dict] = {}  # 报告 / Report
    print(f"{'config':18s} | {'surrogate enrich':>16s} | {'COMSOL RMS enrich':>17s} | {'COMSOL best-1 enrich':>20s} | {'best-1 freq':>11s}")  # 表头 / Header
    print("-" * 96)  # 分隔 / Sep
    for tag, summary, prefix in configs:  # 遍历 / Iterate
        sp = Path(summary)  # 路径 / Path
        if not sp.exists():  # 不存在 / Missing
            print(f"{tag:18s} | skipping (no summary)")  # 跳过 / Skip
            continue  # 跳过 / Skip
        try:  # 尝试 / Try
            r = analyze_one(prefix, target_path, exports_root, sp)  # 分析 / Analyse
        except FileNotFoundError as e:  # 文件缺失 / Missing
            print(f"{tag:18s} | skipping ({e})")  # 跳过 / Skip
            continue  # 跳过 / Skip
        s = r["surrogate"]  # 代理 / Surrogate
        cm = r.get("comsol_rms_composite") or {}  # COMSOL / COMSOL
        bs = r.get("comsol_best_single") or {}  # 单频最佳 / Best single
        bs_m = bs.get("metrics", {})  # 单频 metrics / Single freq metrics
        print(f"{tag:18s} | {s.get('enrichment', 0.0):>16.3f} | {cm.get('enrichment_factor', 0.0):>17.3f} | {bs_m.get('enrichment_factor', 0.0):>20.3f} | {bs.get('freq_hz', 0.0):>10.1f}")  # 表格 / Row
        report[tag] = r  # 保存 / Save
    out_path = Path("reports/sprint1_comsol_validation.json")  # 输出 / Output
    out_path.parent.mkdir(parents=True, exist_ok=True)  # 建目录 / Mkdir
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=lambda v: float(v) if hasattr(v, "item") else str(v)), encoding="utf-8")  # 写 / Write
    print(f"\nReport saved: {out_path}")  # 路径 / Path
    return 0  # 返回 / Return


if __name__ == "__main__":  # 直接 / Direct
    raise SystemExit(main())  # 退出 / Exit
