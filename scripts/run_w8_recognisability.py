from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 命令行 / Argparse
import sys  # 系统 / System
from pathlib import Path  # 路径 / Paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 项目根 / Project root
if str(PROJECT_ROOT) not in sys.path:  # 检查 / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加 / Add

from scripts.run_w3_optimization import derive_candidate_dir  # 候选目录 / Candidate dir
from scripts.run_w3_optimization import load_initial_H  # H 初值 / H init
from scripts.run_w3_optimization import load_verdict  # 判定 / Verdict
from src.config import load_config  # 配置 / Config
from src.optimisation.recognisability_placement import RecognisabilityPlacementConfig  # 配置 / Config
from src.optimisation.recognisability_placement import run_recognisability_placement  # 入口 / Entry
from src.physics.plate_loss_adapter import load_target_binary  # 目标 / Target
from src.subspace.manifold_pca import load_manifold  # 流形 / Manifold


def parse_floats(text: str) -> list[float]:  # 解析浮点列表 / Parse floats
    return [float(x.strip()) for x in text.split(",") if x.strip()]  # 解析 / Parse


def build_argument_parser() -> argparse.ArgumentParser:  # 解析器 / Parser
    parser = argparse.ArgumentParser(description="Run W8 recognisability joint optimisation (H + frequencies + weights under enrichment/contrast/recall loss). / 运行 W8 可识别度联合优化。")  # 解析器 / Parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config. / 项目配置。")  # 配置 / Config
    parser.add_argument("--target", type=str, default=None, help="Target NPY override. / 目标 NPY 覆盖。")  # 目标 / Target
    parser.add_argument("--verdict-report", type=str, default=None, help="Optional verdict report. / 可选判定报告。")  # 判定 / Verdict
    parser.add_argument("--manifold", type=str, default="reports/design_manifold_pca.npz", help="PCA manifold NPZ; empty disables. / PCA 流形；传空关闭。")  # 流形 / Manifold
    parser.add_argument("--candidate-id", type=str, default="w8_recognisability_v1", help="Output candidate id. / 候选编号。")  # 候选 / Candidate
    parser.add_argument("--num-frequencies", type=int, default=6, help="Joint frequencies K. / 联合频率数 K。")  # K / K
    parser.add_argument("--f-min-hz", type=float, default=120.0, help="Freq lower bound. / 频率下限。")  # 下限 / Lower
    parser.add_argument("--f-max-hz", type=float, default=1200.0, help="Freq upper bound. / 频率上限。")  # 上限 / Upper
    parser.add_argument("--initial-frequencies-hz", type=str, default=None, help="Comma-separated initial freqs (length=K). / 初始频率（数量=K）。")  # 初值 / Init
    parser.add_argument("--proxy-grid-size", type=int, default=25, help="Proxy grid. / 代理网格。")  # 网格 / Grid
    parser.add_argument("--damping-ratio", type=float, default=0.02, help="Damping. / 阻尼比。")  # 阻尼 / Damping
    parser.add_argument("--num-steps", type=int, default=250, help="Adam steps. / Adam 步数。")  # 步数 / Steps
    parser.add_argument("--learning-rate-h", type=float, default=0.05, help="H/coeff LR. / H 学习率。")  # H LR / H LR
    parser.add_argument("--learning-rate-freq", type=float, default=0.10, help="Freq logits LR. / 频率学习率。")  # Freq LR / Freq LR
    parser.add_argument("--learning-rate-weight", type=float, default=0.10, help="Weight logits LR. / 权重学习率。")  # Weight LR / Weight LR
    parser.add_argument("--enrichment-weight", type=float, default=1.0, help="Enrichment loss weight. / 富集项权重。")  # Enr / Enr
    parser.add_argument("--contrast-weight", type=float, default=1.0, help="Gaussian contrast loss weight. / 高斯对比项权重。")  # Ct / Ct
    parser.add_argument("--recall-weight", type=float, default=0.5, help="Soft recall loss weight. / 软 recall 权重。")  # Rc / Rc
    parser.add_argument("--sigma-rel", type=float, default=0.05, help="Gaussian sigma (relative to peak). / 高斯 sigma。")  # sigma / Sigma
    parser.add_argument("--recall-percentile-frac", type=float, default=0.20, help="Recall percentile fraction. / Recall 分位比例。")  # Recall pct / Pct
    parser.add_argument("--smoothness-weight", type=float, default=2.0, help="Smoothness penalty weight. / 平滑罚权重。")  # Sm / Sm
    parser.add_argument("--coeff-l2-weight", type=float, default=1.0e-3, help="PCA coeff L2 weight. / PCA L2 权重。")  # L2 / L2
    parser.add_argument("--freq-separation-min-hz", type=float, default=30.0, help="Min freq gap. / 最小频率间隔。")  # Sep / Sep
    parser.add_argument("--freq-separation-weight", type=float, default=0.5, help="Freq separation weight. / 间隔罚权重。")  # SepW / SepW
    parser.add_argument("--freeze-freq-first-steps", type=int, default=60, help="Freeze freq/weight for first N steps. / 冻结步数。")  # Frz / Frz
    parser.add_argument("--plateau-patience", type=int, default=60, help="Plateau patience. / 平台容忍。")  # Plat / Plat
    parser.add_argument("--snapshot-every", type=int, default=25, help="Snapshot interval. / 快照间隔。")  # Snap / Snap
    parser.add_argument("--initial-H", type=str, default=None, help="Optional initial 15x15 thickness. / 可选 H 初值。")  # Init / Init
    parser.add_argument("--output-dir", type=str, default=None, help="Override output dir. / 覆盖输出目录。")  # Out / Out
    parser.add_argument("--sbs-seed", type=str, default=None, help="Path to SBS seed NPY (Xie-Smidt 2024); empty disables. Use data/sbs_seed.npy for the project default. / SBS 对称破坏种子路径。")  # SBS / SBS
    parser.add_argument("--sinkhorn-weight", type=float, default=0.0, help="Sinkhorn OT loss weight (0 disables). Requires geomloss. / Sinkhorn loss 权重，0 关闭。")  # Sinkhorn / Sinkhorn
    parser.add_argument("--sinkhorn-epsilon", type=float, default=0.01, help="Sinkhorn entropic regularisation. / Sinkhorn 熵正则。")  # eps / eps
    parser.add_argument("--sinkhorn-target-irreps", type=str, default=None, help="Comma-separated D4 irreps to project target to before Sinkhorn (e.g. 'A1' restricts to accessible part). / Sinkhorn 之前把目标投到指定 irrep。")  # irrep / irrep
    parser.add_argument("--calibration-npz", type=str, default=None, help="W9 trust-region calibration anchors NPZ (H_anchors, residual_anchors, sigma_mm). / W9 信赖域校正锚点 NPZ。")  # W9 / W9
    return parser  # 返回 / Return


def main(argv: list[str] | None = None) -> int:  # 主 / Main
    parser = build_argument_parser()  # 解析器 / Parser
    args = parser.parse_args(argv)  # 解析 / Parse
    config = load_config(args.config)  # 配置 / Config
    target = load_target_binary(config, args.target)  # 目标 / Target
    verdict = load_verdict(Path(args.verdict_report) if args.verdict_report else None)  # 判定 / Verdict
    manifold = None  # 流形 / Manifold
    if args.manifold and args.manifold.strip():  # 启用 / Enable
        manifold = load_manifold(Path(args.manifold))  # 加载 / Load
    candidate_dir = derive_candidate_dir(config, args.candidate_id)  # 候选目录 / Dir
    output_dir = Path(args.output_dir) if args.output_dir else candidate_dir  # 输出 / Out
    initial_H = load_initial_H(Path(args.initial_H)) if args.initial_H else None  # H 初值 / H init
    initial_freqs = parse_floats(args.initial_frequencies_hz) if args.initial_frequencies_hz else None  # 频率 / Freqs
    sinkhorn_irreps = [s.strip() for s in args.sinkhorn_target_irreps.split(",")] if args.sinkhorn_target_irreps else None  # irrep 列表 / irrep list
    opt_config = RecognisabilityPlacementConfig(proxy_grid_size=int(args.proxy_grid_size), num_frequencies=int(args.num_frequencies), f_min_hz=float(args.f_min_hz), f_max_hz=float(args.f_max_hz), damping_ratio=float(args.damping_ratio), num_steps=int(args.num_steps), learning_rate_H=float(args.learning_rate_h), learning_rate_freq=float(args.learning_rate_freq), learning_rate_weight=float(args.learning_rate_weight), plateau_patience=int(args.plateau_patience), snapshot_every=int(args.snapshot_every), smoothness_weight=float(args.smoothness_weight), manifold=manifold, manifold_coeff_l2_weight=float(args.coeff_l2_weight), freq_separation_min_hz=float(args.freq_separation_min_hz), freq_separation_weight=float(args.freq_separation_weight), freeze_freq_first_steps=int(args.freeze_freq_first_steps), initial_frequencies_hz=initial_freqs, enrichment_weight=float(args.enrichment_weight), contrast_weight=float(args.contrast_weight), recall_weight=float(args.recall_weight), sigma_rel=float(args.sigma_rel), recall_percentile_frac=float(args.recall_percentile_frac), sbs_seed_path=args.sbs_seed if args.sbs_seed else None, sinkhorn_weight=float(args.sinkhorn_weight), sinkhorn_epsilon=float(args.sinkhorn_epsilon), sinkhorn_target_irreps=sinkhorn_irreps, calibration_npz_path=args.calibration_npz if args.calibration_npz else None)  # 配置 / Config
    print(f"W8 recognisability start / 启动 W8: candidate={args.candidate_id}, K={opt_config.num_frequencies}, range=[{opt_config.f_min_hz:.0f},{opt_config.f_max_hz:.0f}]Hz, manifold={'on' if manifold is not None else 'off'}, steps={opt_config.num_steps}, sigma={opt_config.sigma_rel}")  # 打印 / Print
    summary = run_recognisability_placement(config, target, opt_config, output_dir, verdict=verdict, initial_H_mm=initial_H)  # 运行 / Run
    losses = summary["trace"]["total_loss"]  # 损失 / Loss
    enr = summary["trace"]["enrichment"]  # 富集 / Enrichment
    ct = summary["trace"]["contrast"]  # 对比 / Contrast
    rc = summary["trace"]["recall"]  # recall / Recall
    print(f"steps={len(losses)}  best_loss={summary['best_loss']:.4f}@step{summary['best_step']}  enrichment {enr[0]:.2f}->{enr[-1]:.2f}  contrast {ct[0]:.2f}->{ct[-1]:.2f}  recall {rc[0]:.2%}->{rc[-1]:.2%}")  # 打印 / Print
    print(f"final frequencies (Hz): {[round(v,2) for v in summary['frequencies_hz']]}")  # 频率 / Freqs
    print(f"final weights         : {[round(v,3) for v in summary['weights']]}")  # 权重 / Weights
    wdist = summary["weight_distribution"]  # 摘要 / Summary
    print(f"effective active freqs: {wdist['effective_count']:.2f}  top freq={wdist['top_frequency_hz']:.1f} Hz (w={wdist['top_weight']:.3f})")  # 打印 / Print
    if summary.get("best_surrogate_metrics"):  # 代理指标 / Surrogate
        m = summary["best_surrogate_metrics"]  # 取 / Take
        print(f"surrogate metrics @ best step: enrichment={m['enrichment']:.2f}x  contrast={m['contrast']:.2f}x  recall={m['recall']*100:.1f}%")  # 打印 / Print
    print(f"output dir: {output_dir}")  # 路径 / Path
    print(f"summary json: {output_dir / 'w8_optimization_summary.json'}")  # 摘要 / Summary
    return 0  # 返回 / Return


if __name__ == "__main__":  # 直接运行 / Direct
    raise SystemExit(main())  # 退出 / Exit
