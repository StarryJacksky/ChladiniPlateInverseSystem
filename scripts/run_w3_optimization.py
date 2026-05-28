from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析 / Import argument parsing
import json  # 导入 JSON 工具 / Import JSON utilities
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

import numpy as np  # 导入数值库 / Import numerical library
import torch  # 导入张量库 / Import tensor library

from src.config import load_config  # 复用配置加载 / Reuse config loader
from src.optimisation.gradient_optimizer import GradientOptimizerConfig  # 引入优化器配置 / Import optimiser config
from src.optimisation.gradient_optimizer import run_gradient_optimization  # 引入优化入口 / Import optimisation entry
from src.physics.plate_loss_adapter import load_target_binary  # 引入目标加载 / Import target loader


def load_verdict(path: Path | None) -> dict | None:  # 读取可达性判定 / Load realizability verdict
    candidates: list[Path] = []  # 创建候选路径列表 / Create candidate path list
    if path is not None:  # 显式路径 / Explicit path
        candidates.append(Path(path))  # 加入显式 / Append explicit
    candidates.append(Path("reports/target_realizability.json"))  # 通用默认路径 / Generic default path
    candidates.extend(sorted(Path("reports").glob("target_realizability_*.json")))  # 历史每目标的判定文件 / Per-target historical verdicts
    for candidate in candidates:  # 遍历候选 / Iterate candidates
        if candidate.exists():  # 命中 / Hit
            try:  # 尝试读取 / Try reading
                return json.loads(candidate.read_text(encoding="utf-8"))  # 返回字典 / Return dict
            except (OSError, json.JSONDecodeError):  # 跳过坏文件 / Skip broken file
                continue  # 继续尝试 / Continue trying
    return None  # 未找到则空 / None when missing


def derive_drive_frequency(verdict: dict | None, manual_freq: float | None) -> float:  # 推导驱动频率 / Derive drive frequency
    if manual_freq is not None:  # 优先手动设定 / Prefer manual setting
        return float(manual_freq)  # 返回手动频率 / Return manual frequency
    if verdict is not None:  # 使用 W1 估计 / Use W1 estimate
        metrics = verdict.get("metrics") or {}  # 读取指标 / Read metrics
        estimated = metrics.get("estimated_min_frequency_hz")  # 读取估计频率 / Read estimated frequency
        if estimated is not None:  # 命中估计 / Hit estimate
            return float(estimated) * 3.0  # 略高于 Weyl 估计以激发足够模态 / Slightly above Weyl estimate to excite enough modes
    return 800.0  # 默认频率 / Default frequency


def derive_candidate_dir(config: dict, candidate_id: str) -> Path:  # 计算候选输出目录 / Compute candidate output directory
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 候选根目录 / Candidate root dir
    return candidates_dir / candidate_id  # 拼接候选目录 / Build candidate dir


def load_initial_H(initial_path: Path | None) -> np.ndarray | None:  # 读取初值厚度 / Load initial thickness
    if initial_path is None:  # 无初值 / No initial
        return None  # 返回空 / Return None
    path = Path(initial_path)  # 转换路径 / Convert path
    if path.suffix.lower() == ".csv":  # CSV 文件 / CSV file
        return np.loadtxt(path, delimiter=",")  # 读取 CSV / Load CSV
    if path.suffix.lower() == ".npy":  # NumPy 数组 / NumPy array
        return np.load(path)  # 读取 NPY / Load NPY
    raise ValueError(f"Unsupported initial-H file extension: {path.suffix}. / 不支持的初值厚度扩展名：{path.suffix}。")  # 抛出错误 / Raise error


def build_argument_parser() -> argparse.ArgumentParser:  # 构造参数解析器 / Build argument parser
    parser = argparse.ArgumentParser(description="Run W3 gradient-based amplitude-valley optimisation on 15x15 thickness. / 在 15x15 厚度上跑 W3 振幅谷线梯度优化。")  # 创建解析器 / Create parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config path. / 项目配置路径。")  # 配置参数 / Config option
    parser.add_argument("--candidate-id", type=str, default="w3_gradient_candidate_v1", help="Output candidate id. / 输出候选编号。")  # 候选编号 / Candidate id
    parser.add_argument("--drive-frequency-hz", type=float, default=None, help="Optional drive frequency override. / 可选驱动频率覆盖。")  # 驱动频率 / Drive frequency
    parser.add_argument("--proxy-grid-size", type=int, default=25, help="Differentiable proxy grid resolution (odd). / 可微代理网格分辨率（奇数）。")  # 代理网格 / Proxy grid
    parser.add_argument("--damping-ratio", type=float, default=0.02, help="Rayleigh modal damping ratio. / Rayleigh 模态阻尼比。")  # 阻尼比 / Damping ratio
    parser.add_argument("--epsilon", type=float, default=0.060, help="Soft valley epsilon. / 软谷线 epsilon。")  # 软谷 epsilon / Soft valley epsilon
    parser.add_argument("--num-steps", type=int, default=200, help="Adam step budget. / Adam 步数预算。")  # 步数 / Step budget
    parser.add_argument("--learning-rate", type=float, default=0.05, help="Adam learning rate on theta (pre-sigmoid). / Adam 学习率（sigmoid 前）。")  # 学习率 / Learning rate
    parser.add_argument("--plateau-patience", type=int, default=40, help="Steps without improvement before early stopping. / 早停容忍步数。")  # 平台容忍 / Plateau patience
    parser.add_argument("--snapshot-every", type=int, default=25, help="Steps between snapshot saves. / 快照保存间隔。")  # 快照间隔 / Snapshot interval
    parser.add_argument("--initial-H", type=str, default=None, help="Optional initial 15x15 thickness (CSV or NPY). / 可选初值厚度（CSV 或 NPY）。")  # 初值厚度 / Initial thickness
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
    output_dir = Path(args.output_dir) if args.output_dir else candidate_dir  # 选择输出目录 / Pick output directory
    initial_H = load_initial_H(Path(args.initial_H)) if args.initial_H else None  # 读取初值 / Load initial
    opt_config = GradientOptimizerConfig(proxy_grid_size=int(args.proxy_grid_size), drive_frequency_hz=float(drive_freq), damping_ratio=float(args.damping_ratio), epsilon=float(args.epsilon), num_steps=int(args.num_steps), learning_rate=float(args.learning_rate), plateau_patience=int(args.plateau_patience), snapshot_every=int(args.snapshot_every))  # 构造优化器配置 / Build optimiser config
    print(f"W3 gradient optimisation start / 启动 W3 梯度优化: candidate={args.candidate_id}, drive_hz={drive_freq:.1f}, proxy={opt_config.proxy_grid_size}x{opt_config.proxy_grid_size}, steps={opt_config.num_steps}")  # 打印开始信息 / Print start info
    summary = run_gradient_optimization(config, target, opt_config, output_dir, verdict=verdict, initial_H_mm=initial_H)  # 调用优化器 / Call optimiser
    losses = summary["trace"]["losses"]  # 读取损失序列 / Read loss sequence
    print(f"steps={len(losses)}  best_loss={summary['best_loss']:.6f}@step{summary['best_step']}  first/last={losses[0]:.4f} / {losses[-1]:.4f}")  # 打印摘要 / Print summary
    print(f"output dir: {output_dir} / 输出目录：{output_dir}")  # 打印输出目录 / Print output dir
    print(f"summary json: {output_dir / 'w3_optimization_summary.json'} / 摘要 JSON: {output_dir / 'w3_optimization_summary.json'}")  # 打印摘要路径 / Print summary path
    return 0  # 返回成功 / Return success


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出 / Exit


