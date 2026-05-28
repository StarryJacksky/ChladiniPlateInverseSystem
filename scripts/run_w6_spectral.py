from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析 / Import argument parsing
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

import numpy as np  # 导入数值库 / Import numerical library

from scripts.run_w3_optimization import derive_candidate_dir  # 复用候选目录构造 / Reuse candidate-dir builder
from scripts.run_w3_optimization import derive_drive_frequency  # 复用驱动频率推导 / Reuse drive-freq derivation
from scripts.run_w3_optimization import load_initial_H  # 复用厚度初值加载 / Reuse initial-H loader
from scripts.run_w3_optimization import load_verdict  # 复用判定加载 / Reuse verdict loader
from src.config import load_config  # 复用配置加载 / Reuse config loader
from src.optimisation.spectral_placement import SpectralPlacementConfig  # 引入 W6 配置 / Import W6 config
from src.optimisation.spectral_placement import run_spectral_placement  # 引入 W6 主入口 / Import W6 entry
from src.physics.plate_loss_adapter import load_target_binary  # 复用目标加载 / Reuse target loader
from src.subspace.manifold_pca import load_manifold  # 复用流形加载 / Reuse manifold loader


def build_argument_parser() -> argparse.ArgumentParser:  # 构造参数解析器 / Build argument parser
    parser = argparse.ArgumentParser(description="Run W6 spectral-placement optimisation (clustering eigenvalues onto ω while matching the target). / 运行 W6 频谱聚簇优化（让本征值聚到驱动频率附近同时匹配目标）。")  # 解析器 / Parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config path. / 项目配置路径。")  # 配置 / Config
    parser.add_argument("--target", type=str, default=None, help="Target binary NPY override. / 目标 NPY 覆盖。")  # 目标 / Target
    parser.add_argument("--verdict-report", type=str, default=None, help="Optional W1 verdict JSON override. / 可选 W1 判定 JSON 覆盖。")  # 判定 / Verdict
    parser.add_argument("--manifold", type=str, default="reports/design_manifold_pca.npz", help="PCA manifold NPZ; pass empty string to disable. / PCA 流形 NPZ；传空字符串关闭。")  # 流形 / Manifold
    parser.add_argument("--candidate-id", type=str, default="w6_spectral_candidate_v1", help="Output candidate id. / 输出候选编号。")  # 候选 / Candidate
    parser.add_argument("--drive-frequency-hz", type=float, default=None, help="Optional drive frequency override. / 可选驱动频率覆盖。")  # 频率 / Frequency
    parser.add_argument("--proxy-grid-size", type=int, default=25, help="Proxy grid resolution. / 代理网格分辨率。")  # 代理网格 / Proxy grid
    parser.add_argument("--damping-ratio", type=float, default=0.02, help="Rayleigh modal damping ratio. / Rayleigh 模态阻尼比。")  # 阻尼 / Damping
    parser.add_argument("--epsilon", type=float, default=0.060, help="Soft valley epsilon. / 软谷线 epsilon。")  # epsilon / epsilon
    parser.add_argument("--num-modes", type=int, default=12, help="Number of leading modes monitored. / 监测的前若干阶模态。")  # 模态数 / Modes
    parser.add_argument("--num-steps", type=int, default=200, help="Adam step budget. / Adam 步数预算。")  # 步数 / Steps
    parser.add_argument("--learning-rate", type=float, default=0.20, help="Adam learning rate. / Adam 学习率。")  # 学习率 / LR
    parser.add_argument("--cluster-weight", type=float, default=1.0, help="Spectral-cluster term weight. / 聚簇项权重。")  # 聚簇权重 / Cluster weight
    parser.add_argument("--amplitude-weight", type=float, default=1.0, help="Amplitude-valley term weight. / 振幅谷线项权重。")  # 振幅权重 / Amplitude weight
    parser.add_argument("--smoothness-weight", type=float, default=2.0, help="Neighbour-difference penalty weight. / 邻格差惩罚权重。")  # 平滑权重 / Smoothness weight
    parser.add_argument("--coeff-l2-weight", type=float, default=1.0e-3, help="PCA coefficient L2 (when manifold given). / PCA 系数 L2（启用流形时）。")  # L2 / L2
    parser.add_argument("--realign-every", type=int, default=10, help="Refresh per-mode alignment weights every N steps. / 每 N 步刷新一次模态契合权重。")  # 刷新 / Realign
    parser.add_argument("--plateau-patience", type=int, default=40, help="Early-stop plateau patience. / 早停容忍步。")  # 平台 / Plateau
    parser.add_argument("--snapshot-every", type=int, default=25, help="Snapshot save interval. / 快照保存间隔。")  # 快照 / Snapshot
    parser.add_argument("--initial-H", type=str, default=None, help="Optional initial 15x15 thickness (CSV or NPY). / 可选 15x15 厚度初值。")  # 初值 / Init H
    parser.add_argument("--output-dir", type=str, default=None, help="Optional output dir; defaults to candidate dir. / 可选输出目录，默认候选目录。")  # 输出 / Output
    return parser  # 返回 / Return


def main(argv: list[str] | None = None) -> int:  # 主入口 / Main entry
    parser = build_argument_parser()  # 构造解析器 / Build parser
    args = parser.parse_args(argv)  # 解析 / Parse
    config = load_config(args.config)  # 配置 / Config
    target = load_target_binary(config, args.target)  # 目标 / Target
    verdict = load_verdict(Path(args.verdict_report) if args.verdict_report else None)  # 判定 / Verdict
    drive_freq = derive_drive_frequency(verdict, args.drive_frequency_hz)  # 频率 / Frequency
    manifold = None  # 默认无流形 / Default no manifold
    if args.manifold and args.manifold.strip():  # 检查流形参数 / Check manifold
        manifold = load_manifold(Path(args.manifold))  # 加载 / Load
    candidate_dir = derive_candidate_dir(config, args.candidate_id)  # 候选目录 / Candidate dir
    output_dir = Path(args.output_dir) if args.output_dir else candidate_dir  # 输出目录 / Output dir
    initial_H = load_initial_H(Path(args.initial_H)) if args.initial_H else None  # 初值 / Initial H
    opt_config = SpectralPlacementConfig(proxy_grid_size=int(args.proxy_grid_size), drive_frequency_hz=float(drive_freq), damping_ratio=float(args.damping_ratio), epsilon=float(args.epsilon), num_modes=int(args.num_modes), num_steps=int(args.num_steps), learning_rate=float(args.learning_rate), plateau_patience=int(args.plateau_patience), snapshot_every=int(args.snapshot_every), smoothness_weight=float(args.smoothness_weight), manifold=manifold, manifold_coeff_l2_weight=float(args.coeff_l2_weight), cluster_weight=float(args.cluster_weight), amplitude_weight=float(args.amplitude_weight), cluster_realignment_every=int(args.realign_every))  # 构造配置 / Build config
    print(f"W6 spectral start / 启动 W6 频谱聚簇: candidate={args.candidate_id}, drive_hz={drive_freq:.1f}, modes={opt_config.num_modes}, manifold={'on' if manifold is not None else 'off'}, steps={opt_config.num_steps}")  # 打印开始 / Print start
    summary = run_spectral_placement(config, target, opt_config, output_dir, verdict=verdict, initial_H_mm=initial_H)  # 调用 / Call
    losses = summary["trace"]["total_loss"]  # 损失 / Loss
    cluster_losses = summary["trace"]["cluster_loss"]  # 聚簇 / Cluster
    amp_losses = summary["trace"]["amplitude_loss"]  # 振幅 / Amplitude
    omega2 = summary["trace"]["omega_squared"][-1] if summary["trace"]["omega_squared"] else 0.0  # ω² / ω²
    eig_first = summary["final_eigenvalues_tracked"][:8]  # 前 8 阶本征值 / Leading 8 eigenvalues
    print(f"steps={len(losses)}  best_loss={summary['best_loss']:.6f}@step{summary['best_step']}  first/last total={losses[0]:.4f} / {losses[-1]:.4f}  cluster={cluster_losses[0]:.4f}→{cluster_losses[-1]:.4f}  amp={amp_losses[0]:.4f}→{amp_losses[-1]:.4f}")  # 打印 / Print
    print(f"final eigenvalues (first 8): {[f'{v:.3e}' for v in eig_first]}, omega² = {omega2:.3e} / 末步前 8 阶本征值与 ω²")  # 打印本征值 / Print eigenvalues
    print(f"output dir: {output_dir} / 输出：{output_dir}")  # 路径 / Path
    print(f"summary json: {output_dir / 'w6_optimization_summary.json'} / 摘要：{output_dir / 'w6_optimization_summary.json'}")  # 摘要 / Summary
    return 0  # 返回 / Return


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出 / Exit
