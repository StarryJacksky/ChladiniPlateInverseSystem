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
from src.optimisation.gradient_optimizer import GradientOptimizerConfig  # 复用优化器配置 / Reuse optimiser config
from src.optimisation.gradient_optimizer import run_gradient_optimization  # 复用优化入口 / Reuse optimisation entry
from src.physics.plate_loss_adapter import load_target_binary  # 复用目标加载 / Reuse target loader
from src.subspace.manifold_pca import load_manifold  # 复用流形加载 / Reuse manifold loader


def build_argument_parser() -> argparse.ArgumentParser:  # 构造参数解析器 / Build argument parser
    parser = argparse.ArgumentParser(description="Run W4 manifold-restricted gradient optimisation in PCA-coefficient subspace. / 在 PCA 系数子空间运行 W4 流形受限梯度优化。")  # 创建解析器 / Create parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config path. / 项目配置路径。")  # 配置 / Config
    parser.add_argument("--manifold", type=str, default="reports/design_manifold_pca.npz", help="PCA manifold NPZ produced by build_design_manifold. / 由 build_design_manifold 生成的 PCA 流形 NPZ。")  # 流形路径 / Manifold path
    parser.add_argument("--candidate-id", type=str, default="w4_manifold_candidate_v1", help="Output candidate id. / 输出候选编号。")  # 候选编号 / Candidate id
    parser.add_argument("--drive-frequency-hz", type=float, default=None, help="Optional drive frequency override. / 可选驱动频率覆盖。")  # 驱动频率 / Drive frequency
    parser.add_argument("--proxy-grid-size", type=int, default=25, help="Differentiable proxy grid resolution (odd). / 可微代理网格分辨率（奇数）。")  # 代理网格 / Proxy grid
    parser.add_argument("--damping-ratio", type=float, default=0.02, help="Rayleigh modal damping ratio. / Rayleigh 模态阻尼比。")  # 阻尼比 / Damping ratio
    parser.add_argument("--epsilon", type=float, default=0.060, help="Soft valley epsilon. / 软谷线 epsilon。")  # 软谷 epsilon / Soft valley epsilon
    parser.add_argument("--num-steps", type=int, default=200, help="Adam step budget. / Adam 步数预算。")  # 步数 / Step budget
    parser.add_argument("--learning-rate", type=float, default=0.20, help="Adam learning rate on PCA coefficients (larger than W3 since dim is small). / PCA 系数的 Adam 学习率（维度更低，可比 W3 更大）。")  # 学习率 / Learning rate
    parser.add_argument("--plateau-patience", type=int, default=40, help="Steps without improvement before early stopping. / 早停容忍步数。")  # 平台容忍 / Plateau patience
    parser.add_argument("--snapshot-every", type=int, default=25, help="Steps between snapshot saves. / 快照保存间隔。")  # 快照间隔 / Snapshot interval
    parser.add_argument("--smoothness-weight", type=float, default=2.0, help="Neighbour-delta penalty weight (smaller than W3 because manifold is already smooth). / 相邻差惩罚权重（流形已偏平滑，权重可低于 W3）。")  # 平滑权重 / Smoothness weight
    parser.add_argument("--coeff-l2-weight", type=float, default=1.0e-3, help="L2 penalty on PCA coefficients to stay near training distribution. / 对 PCA 系数的 L2 惩罚，约束系数不偏离训练分布太远。")  # 系数 L2 / Coeff L2
    parser.add_argument("--initial-H", type=str, default=None, help="Optional initial 15x15 thickness (CSV or NPY) projected onto manifold for warm start. / 可选 15x15 厚度初值，投影到流形作热启动。")  # 厚度初值 / Initial thickness
    parser.add_argument("--initial-coeff", type=str, default=None, help="Optional initial PCA coefficient vector (CSV). / 可选 PCA 系数初值（CSV）。")  # 系数初值 / Initial coeffs
    parser.add_argument("--verdict-report", type=str, default=None, help="Optional W1 realizability report override path. / 可选 W1 可达性报告路径。")  # 判定报告 / Verdict report
    parser.add_argument("--target", type=str, default=None, help="Optional target binary NPY override. / 可选目标 NPY 覆盖。")  # 目标覆盖 / Target override
    parser.add_argument("--output-dir", type=str, default=None, help="Optional output directory override (defaults to candidate dir). / 可选输出目录覆盖。")  # 输出目录 / Output dir
    return parser  # 返回解析器 / Return parser


def main(argv: list[str] | None = None) -> int:  # 主入口 / Main entry
    parser = build_argument_parser()  # 构造解析器 / Build parser
    args = parser.parse_args(argv)  # 解析参数 / Parse args
    config = load_config(args.config)  # 读取配置 / Load config
    target = load_target_binary(config, args.target)  # 读取目标 / Load target
    verdict = load_verdict(Path(args.verdict_report) if args.verdict_report else None)  # 读取判定 / Load verdict
    drive_freq = derive_drive_frequency(verdict, args.drive_frequency_hz)  # 决定驱动频率 / Decide drive frequency
    candidate_dir = derive_candidate_dir(config, args.candidate_id)  # 候选目录 / Candidate directory
    output_dir = Path(args.output_dir) if args.output_dir else candidate_dir  # 输出目录 / Output dir
    manifold = load_manifold(Path(args.manifold))  # 读取流形 / Load manifold
    initial_H = load_initial_H(Path(args.initial_H)) if args.initial_H else None  # 读取厚度初值 / Load initial H
    initial_coeff = np.loadtxt(args.initial_coeff, delimiter=",") if args.initial_coeff else None  # 读取系数初值 / Load coeff init
    if initial_coeff is not None and initial_coeff.ndim > 1:  # 处理多维输入 / Handle multi-dim input
        initial_coeff = initial_coeff.reshape(-1)  # 展平 / Flatten
    opt_config = GradientOptimizerConfig(proxy_grid_size=int(args.proxy_grid_size), drive_frequency_hz=float(drive_freq), damping_ratio=float(args.damping_ratio), epsilon=float(args.epsilon), num_steps=int(args.num_steps), learning_rate=float(args.learning_rate), plateau_patience=int(args.plateau_patience), snapshot_every=int(args.snapshot_every), smoothness_weight=float(args.smoothness_weight), manifold=manifold, manifold_coeff_l2_weight=float(args.coeff_l2_weight), manifold_initial_coeff=initial_coeff)  # 构造优化器配置 / Build optimiser config
    print(f"W4 manifold optimisation start / 启动 W4 流形优化: candidate={args.candidate_id}, drive_hz={drive_freq:.1f}, components={manifold.components.shape[0]}, steps={opt_config.num_steps}")  # 打印开始信息 / Print start info
    summary = run_gradient_optimization(config, target, opt_config, output_dir, verdict=verdict, initial_H_mm=initial_H)  # 调用优化器 / Call optimiser
    losses = summary["trace"]["losses"]  # 读取损失序列 / Read loss sequence
    manifold_summary = summary.get("manifold") or {}  # 读取流形摘要 / Read manifold summary
    print(f"steps={len(losses)}  best_loss={summary['best_loss']:.6f}@step{summary['best_step']}  first/last={losses[0]:.4f} / {losses[-1]:.4f}")  # 打印摘要 / Print summary
    print(f"manifold dims={manifold_summary.get('num_components')}  coeff_l2_norm={manifold_summary.get('coefficients_l2_norm'):.3f}  / 流形维度 {manifold_summary.get('num_components')}，系数 L2 范数 {manifold_summary.get('coefficients_l2_norm'):.3f}")  # 打印流形摘要 / Print manifold summary
    print(f"output dir: {output_dir} / 输出目录：{output_dir}")  # 输出目录 / Output dir
    print(f"summary json: {output_dir / 'w3_optimization_summary.json'} / 摘要 JSON: {output_dir / 'w3_optimization_summary.json'}")  # 摘要路径 / Summary path
    return 0  # 返回成功 / Return success


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出 / Exit
