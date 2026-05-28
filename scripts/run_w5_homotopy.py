from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析 / Import argument parsing
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

import numpy as np  # 导入数值库 / Import numerical library

from scripts.run_w3_optimization import derive_drive_frequency  # 复用驱动频率推导 / Reuse drive-frequency derivation
from scripts.run_w3_optimization import load_verdict  # 复用判定加载 / Reuse verdict loader
from src.config import load_config  # 复用配置加载 / Reuse config loader
from src.optimisation.gradient_optimizer import GradientOptimizerConfig  # 复用优化器配置 / Reuse optimiser config
from src.optimisation.homotopy import HomotopyConfig  # 引入同伦配置 / Import homotopy config
from src.optimisation.homotopy import run_homotopy  # 引入同伦入口 / Import homotopy entry
from src.physics.plate_loss_adapter import load_target_binary  # 复用目标加载 / Reuse target loader
from src.subspace.manifold_pca import load_manifold  # 复用流形加载 / Reuse manifold loader


def parse_lambda_grid(spec: str | None) -> tuple[float, ...]:  # 解析 λ 网格 / Parse λ grid
    if spec is None or not spec.strip():  # 缺省 / Default
        return tuple(float(x) for x in np.linspace(0.0, 1.0, 11))  # 11 等分 / 11-point linspace
    parts = [chunk.strip() for chunk in spec.split(",") if chunk.strip()]  # 切分项 / Split chunks
    return tuple(float(p) for p in parts)  # 返回浮点元组 / Return float tuple


def build_argument_parser() -> argparse.ArgumentParser:  # 构造参数解析器 / Build argument parser
    parser = argparse.ArgumentParser(description="Run W5 homotopy continuation from a natural T_0 to the user target T_1. / 从板自然图案 T_0 同伦延拓到用户目标 T_1。")  # 创建解析器 / Create parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config path. / 项目配置路径。")  # 配置 / Config
    parser.add_argument("--target", type=str, default=None, help="Target binary NPY (T_1). / 目标二值 NPY（T_1）。")  # 目标 / Target
    parser.add_argument("--verdict-report", type=str, default=None, help="Optional W1 verdict JSON override. / 可选 W1 可达性报告路径。")  # 判定 / Verdict
    parser.add_argument("--drive-frequency-hz", type=float, default=None, help="Optional drive frequency override. / 可选驱动频率覆盖。")  # 驱动频率 / Drive frequency
    parser.add_argument("--manifold", type=str, default="reports/design_manifold_pca.npz", help="PCA manifold NPZ; pass empty string to disable. / PCA 流形 NPZ；传空字符串可关闭。")  # 流形 / Manifold
    parser.add_argument("--proxy-grid-size", type=int, default=25, help="Differentiable proxy grid resolution. / 可微代理网格分辨率。")  # 代理网格 / Proxy grid
    parser.add_argument("--damping-ratio", type=float, default=0.02, help="Rayleigh modal damping ratio. / Rayleigh 模态阻尼比。")  # 阻尼比 / Damping ratio
    parser.add_argument("--epsilon", type=float, default=0.060, help="Soft valley epsilon. / 软谷线 epsilon。")  # epsilon
    parser.add_argument("--learning-rate", type=float, default=0.20, help="Adam learning rate. / Adam 学习率。")  # 学习率 / LR
    parser.add_argument("--smoothness-weight", type=float, default=2.0, help="Neighbour-delta penalty weight. / 邻格差惩罚权重。")  # 平滑 / Smoothness
    parser.add_argument("--coeff-l2-weight", type=float, default=1.0e-3, help="PCA coefficient L2 weight (when --manifold given). / PCA 系数 L2 权重（启用流形时）。")  # L2 / L2
    parser.add_argument("--lambda-grid", type=str, default=None, help="Comma-separated λ values, default linspace(0,1,11). / 逗号分隔 λ 序列，默认 linspace(0,1,11)。")  # λ 网格 / λ grid
    parser.add_argument("--steps-per-lambda", type=int, default=50, help="Adam steps per λ except the seed step. / 除暖身外每 λ 的 Adam 步数。")  # 步数 / Steps
    parser.add_argument("--seed-lambda-steps", type=int, default=80, help="Adam steps at λ=0 (warm-up). / λ=0 暖身 Adam 步数。")  # 暖身步数 / Seed steps
    parser.add_argument("--seed-strategy", type=str, default="natural_amplitude", choices=("natural_amplitude", "explicit_npy"), help="T_0 selection strategy. / T_0 选取策略。")  # 策略 / Strategy
    parser.add_argument("--natural-quantile", type=float, default=0.20, help="Amplitude quantile defining the natural-valley band as T_0. / 自然态振幅分位（视为 T_0 节点带）。")  # 分位 / Quantile
    parser.add_argument("--explicit-t0", type=str, default=None, help="Path to T_0 binary NPY (only when --seed-strategy explicit_npy). / 显式 T_0 NPY 路径（仅 explicit_npy 时）。")  # 显式 T_0 / Explicit T_0
    parser.add_argument("--stall-factor", type=float, default=2.0, help="Loss ratio threshold (relative to running best) for declaring stall. / 损失抖动阈值（相对滚动最优）。")  # 抖动阈值 / Stall factor
    parser.add_argument("--stall-consecutive", type=int, default=3, help="Consecutive stalls before declaring lambda_max. / 连续抖动几次声明 λ_max。")  # 抖动连续数 / Stall consecutive
    parser.add_argument("--target-tag", type=str, default="target", help="Tag used in output directory naming. / 输出目录命名标签。")  # 标签 / Tag
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory; default reports/homotopy/<tag>/. / 输出目录，默认 reports/homotopy/<tag>/。")  # 输出 / Output
    return parser  # 返回解析器 / Return parser


def main(argv: list[str] | None = None) -> int:  # 主入口 / Main entry
    parser = build_argument_parser()  # 构造解析器 / Build parser
    args = parser.parse_args(argv)  # 解析参数 / Parse args
    config = load_config(args.config)  # 读取配置 / Load config
    target = load_target_binary(config, args.target)  # 读取目标 / Load target
    verdict = load_verdict(Path(args.verdict_report) if args.verdict_report else None)  # 读取判定 / Load verdict
    drive_freq = derive_drive_frequency(verdict, args.drive_frequency_hz)  # 决定驱动频率 / Decide drive frequency
    manifold = None  # 默认不启用流形 / Default no manifold
    if args.manifold and args.manifold.strip():  # 检查流形参数 / Check manifold arg
        manifold = load_manifold(Path(args.manifold))  # 加载流形 / Load manifold
    output_dir = Path(args.output_dir) if args.output_dir else Path("reports/homotopy") / args.target_tag  # 输出目录 / Output dir
    opt_config = GradientOptimizerConfig(proxy_grid_size=int(args.proxy_grid_size), drive_frequency_hz=float(drive_freq), damping_ratio=float(args.damping_ratio), epsilon=float(args.epsilon), learning_rate=float(args.learning_rate), smoothness_weight=float(args.smoothness_weight), manifold=manifold, manifold_coeff_l2_weight=float(args.coeff_l2_weight))  # 构造优化器配置 / Build optimiser config
    hom_config = HomotopyConfig(lambda_grid=parse_lambda_grid(args.lambda_grid), steps_per_lambda=int(args.steps_per_lambda), seed_lambda_steps=int(args.seed_lambda_steps), seed_strategy=str(args.seed_strategy), natural_quantile=float(args.natural_quantile), stall_factor=float(args.stall_factor), stall_consecutive=int(args.stall_consecutive), explicit_T0_path=Path(args.explicit_t0) if args.explicit_t0 else None)  # 构造同伦配置 / Build homotopy config
    print(f"W5 homotopy start / 启动 W5 同伦: tag={args.target_tag}, drive_hz={drive_freq:.1f}, manifold={'on' if manifold is not None else 'off'}, lambdas={len(hom_config.lambda_grid)}")  # 打印开始 / Print start
    summary = run_homotopy(config, np.asarray(target, dtype=bool), opt_config, hom_config, output_dir, verdict=verdict)  # 调用同伦入口 / Call homotopy entry
    steps = summary["steps"]  # 读取每步记录 / Read step records
    print(f"lambda_max = {summary['lambda_max']:.3f}  (lambda_reached={summary['lambda_reached_with_quality']:.3f}, lambda_max_streaming={summary['lambda_max_streaming']})  / λ_max = {summary['lambda_max']:.3f}（事后扫描={summary['lambda_reached_with_quality']:.3f}，流式={summary['lambda_max_streaming']}）")  # 打印 λ_max / Print λ_max
    print(f"best loss = {summary['best_loss_seen']:.4f}, acceptance threshold = best × stall_factor = {summary['acceptance_threshold']:.4f}, final λ=1 loss = {summary['final_loss_at_lambda_1']:.4f} / 最优 {summary['best_loss_seen']:.4f}，接受阈值 = 最优×stall = {summary['acceptance_threshold']:.4f}，λ=1 末 {summary['final_loss_at_lambda_1']:.4f}")  # 打印 best 信息 / Print best info
    print("lambda | total_loss | target | contrast | compact | iou_band / λ | 总损失 | 目标项 | 对比项 | 紧凑项 | IoU 带")  # 表头 / Header
    for s in steps:  # 打印每行 / Print rows
        print(f"{s['lambda_value']:0.3f}  |  {s['total_loss']:6.3f}  |  {s['target_loss']:5.3f}  |  {s['contrast_loss']:5.3f}  |  {s['compact_loss']:5.3f}  |  {s['iou']:.3f}")  # 每 λ 行 / Per-λ row
    print(f"summary: {output_dir / 'homotopy_summary.json'} / 摘要：{output_dir / 'homotopy_summary.json'}")  # 摘要路径 / Summary path
    print(f"lambda curve: {summary['lambda_curve_csv']} / λ 曲线：{summary['lambda_curve_csv']}")  # CSV 路径 / CSV path
    return 0  # 返回成功 / Return success


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出运行 / Exit run
