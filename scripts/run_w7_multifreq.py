from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析 / Import argument parsing
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

from scripts.run_w3_optimization import derive_candidate_dir  # 复用候选目录构造 / Reuse candidate-dir builder
from scripts.run_w3_optimization import load_initial_H  # 复用厚度初值加载 / Reuse initial-H loader
from scripts.run_w3_optimization import load_verdict  # 复用判定加载 / Reuse verdict loader
from src.config import load_config  # 复用配置加载 / Reuse config loader
from src.optimisation.multifreq_placement import MultiFrequencyPlacementConfig  # 引入 W7 配置 / Import W7 config
from src.optimisation.multifreq_placement import run_multifreq_placement  # 引入 W7 主入口 / Import W7 entry
from src.physics.plate_loss_adapter import load_target_binary  # 复用目标加载 / Reuse target loader
from src.subspace.manifold_pca import load_manifold  # 复用流形加载 / Reuse manifold loader


def parse_freq_list(text: str) -> list[float]:  # 解析逗号分隔的浮点列表 / Parse comma-separated float list
    return [float(x.strip()) for x in text.split(",") if x.strip()]  # 拆分并转换 / Split and convert


def build_argument_parser() -> argparse.ArgumentParser:  # 构造参数解析器 / Build argument parser
    parser = argparse.ArgumentParser(description="Run W7 multi-frequency joint optimisation (H + frequencies + weights). / 运行 W7 多频联合优化（H + 频率 + 权重）。")  # 解析器 / Parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config path. / 项目配置路径。")  # 配置 / Config
    parser.add_argument("--target", type=str, default=None, help="Target binary NPY override. / 目标 NPY 覆盖。")  # 目标 / Target
    parser.add_argument("--verdict-report", type=str, default=None, help="Optional W1 verdict JSON. / 可选 W1 判定 JSON。")  # 判定 / Verdict
    parser.add_argument("--manifold", type=str, default="reports/design_manifold_pca.npz", help="PCA manifold NPZ; pass empty string to disable. / PCA 流形 NPZ；传空字符串关闭。")  # 流形 / Manifold
    parser.add_argument("--candidate-id", type=str, default="w7_multifreq_candidate_v1", help="Output candidate id. / 输出候选编号。")  # 候选 / Candidate
    parser.add_argument("--num-frequencies", type=int, default=6, help="Number of jointly optimised drive frequencies K. / 联合优化的驱动频率数 K。")  # 频率数 / K
    parser.add_argument("--f-min-hz", type=float, default=150.0, help="Lower bound of frequency search. / 频率搜索下限。")  # 下限 / Lower
    parser.add_argument("--f-max-hz", type=float, default=1000.0, help="Upper bound of frequency search. / 频率搜索上限。")  # 上限 / Upper
    parser.add_argument("--initial-frequencies-hz", type=str, default=None, help="Comma-separated initial frequencies (length must match K). / 逗号分隔的频率初值（数量等于 K）。")  # 频率初值 / Init freqs
    parser.add_argument("--proxy-grid-size", type=int, default=25, help="Proxy grid resolution. / 代理网格分辨率。")  # 代理网格 / Proxy
    parser.add_argument("--damping-ratio", type=float, default=0.02, help="Damping ratio. / 阻尼比。")  # 阻尼 / Damping
    parser.add_argument("--epsilon", type=float, default=0.060, help="Valley epsilon. / 谷线 epsilon。")  # epsilon / Epsilon
    parser.add_argument("--num-steps", type=int, default=250, help="Adam steps. / Adam 步数。")  # 步数 / Steps
    parser.add_argument("--learning-rate-h", type=float, default=0.05, help="Learning rate for H / coeffs. / H/系数学习率。")  # H LR / H LR
    parser.add_argument("--learning-rate-freq", type=float, default=0.10, help="Learning rate for freq logits. / 频率 logits 学习率。")  # freq LR / Freq LR
    parser.add_argument("--learning-rate-weight", type=float, default=0.10, help="Learning rate for weight logits. / 权重 logits 学习率。")  # weight LR / Weight LR
    parser.add_argument("--smoothness-weight", type=float, default=2.0, help="Neighbour-difference penalty weight. / 邻格差惩罚权重。")  # 平滑 / Smoothness
    parser.add_argument("--coeff-l2-weight", type=float, default=1.0e-3, help="PCA coefficient L2 (with manifold). / PCA 系数 L2（启用流形时）。")  # L2 / L2
    parser.add_argument("--freq-separation-min-hz", type=float, default=30.0, help="Minimum gap between frequencies in Hz. / 最小频率间隔 Hz。")  # 间隔 / Min gap
    parser.add_argument("--freq-separation-weight", type=float, default=0.5, help="Penalty weight for frequency separation. / 频率间隔惩罚权重。")  # 间隔权重 / Sep weight
    parser.add_argument("--sparsity-target-active", type=int, default=0, help="0 disables sparsity guide; else encourage roughly this many active freqs. / 0 关闭稀疏；否则引导有效频率数。")  # 稀疏 / Sparsity
    parser.add_argument("--sparsity-weight", type=float, default=0.0, help="Sparsity penalty weight. / 稀疏罚权重。")  # 稀疏权重 / Sparsity weight
    parser.add_argument("--freeze-freq-first-steps", type=int, default=50, help="Freeze freq/weight logits for first N steps (let H settle). / 前 N 步冻结 freq/weight。")  # 冻结 / Freeze
    parser.add_argument("--plateau-patience", type=int, default=50, help="Early-stop plateau patience. / 早停容忍步。")  # 平台 / Plateau
    parser.add_argument("--snapshot-every", type=int, default=25, help="Snapshot save interval. / 快照间隔。")  # 快照 / Snapshot
    parser.add_argument("--initial-H", type=str, default=None, help="Optional initial 15x15 thickness (CSV or NPY). / 可选 15x15 厚度初值。")  # 初值 / Init
    parser.add_argument("--output-dir", type=str, default=None, help="Optional output dir override. / 可选输出目录。")  # 输出 / Output
    return parser  # 返回 / Return


def main(argv: list[str] | None = None) -> int:  # 主入口 / Main entry
    parser = build_argument_parser()  # 解析器 / Parser
    args = parser.parse_args(argv)  # 解析 / Parse
    config = load_config(args.config)  # 配置 / Config
    target = load_target_binary(config, args.target)  # 目标 / Target
    verdict = load_verdict(Path(args.verdict_report) if args.verdict_report else None)  # 判定 / Verdict
    manifold = None  # 默认无流形 / Default no manifold
    if args.manifold and args.manifold.strip():  # 检查 / Check
        manifold = load_manifold(Path(args.manifold))  # 加载 / Load
    candidate_dir = derive_candidate_dir(config, args.candidate_id)  # 候选目录 / Candidate dir
    output_dir = Path(args.output_dir) if args.output_dir else candidate_dir  # 输出目录 / Output dir
    initial_H = load_initial_H(Path(args.initial_H)) if args.initial_H else None  # 初值 / Initial H
    initial_freqs = parse_freq_list(args.initial_frequencies_hz) if args.initial_frequencies_hz else None  # 频率初值 / Frequency init
    opt_config = MultiFrequencyPlacementConfig(proxy_grid_size=int(args.proxy_grid_size), num_frequencies=int(args.num_frequencies), f_min_hz=float(args.f_min_hz), f_max_hz=float(args.f_max_hz), damping_ratio=float(args.damping_ratio), epsilon=float(args.epsilon), num_steps=int(args.num_steps), learning_rate_H=float(args.learning_rate_h), learning_rate_freq=float(args.learning_rate_freq), learning_rate_weight=float(args.learning_rate_weight), plateau_patience=int(args.plateau_patience), snapshot_every=int(args.snapshot_every), smoothness_weight=float(args.smoothness_weight), manifold=manifold, manifold_coeff_l2_weight=float(args.coeff_l2_weight), freq_separation_min_hz=float(args.freq_separation_min_hz), freq_separation_weight=float(args.freq_separation_weight), sparsity_target_active=int(args.sparsity_target_active), sparsity_weight=float(args.sparsity_weight), freeze_freq_first_steps=int(args.freeze_freq_first_steps), initial_frequencies_hz=initial_freqs)  # 配置 / Config
    print(f"W7 multifreq start / 启动 W7 多频联合: candidate={args.candidate_id}, K={opt_config.num_frequencies}, freq_range=[{opt_config.f_min_hz:.0f},{opt_config.f_max_hz:.0f}]Hz, manifold={'on' if manifold is not None else 'off'}, steps={opt_config.num_steps}")  # 打印 / Print
    summary = run_multifreq_placement(config, target, opt_config, output_dir, verdict=verdict, initial_H_mm=initial_H)  # 运行 / Run
    losses = summary["trace"]["total_loss"]  # 损失 / Loss
    amp_losses = summary["trace"]["amp_loss"]  # 振幅 / Amplitude
    freqs_final = summary["frequencies_hz"]  # 最终频率 / Final freqs
    weights_final = summary["weights"]  # 最终权重 / Final weights
    wdist = summary["weight_distribution"]  # 权重分布 / Weight distribution
    print(f"steps={len(losses)}  best_loss={summary['best_loss']:.6f}@step{summary['best_step']}  first/last total={losses[0]:.4f} / {losses[-1]:.4f}  amp={amp_losses[0]:.4f}→{amp_losses[-1]:.4f}")  # 打印 / Print
    print(f"final frequencies (Hz): {[round(v,2) for v in freqs_final]}")  # 频率 / Freqs
    print(f"final weights         : {[round(v,3) for v in weights_final]}")  # 权重 / Weights
    print(f"effective active freqs: {wdist['effective_count']:.2f}  top freq={wdist['top_frequency_hz']:.1f} Hz (w={wdist['top_weight']:.3f})")  # 摘要 / Summary
    print(f"output dir: {output_dir} / 输出：{output_dir}")  # 路径 / Path
    print(f"summary json: {output_dir / 'w7_optimization_summary.json'} / 摘要：{output_dir / 'w7_optimization_summary.json'}")  # 摘要 / Summary
    return 0  # 返回 / Return


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出 / Exit
