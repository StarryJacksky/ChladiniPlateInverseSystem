from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析 / Import argument parsing
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

import numpy as np  # 导入数值库 / Import numerical library

from src.config import load_config  # 复用配置加载 / Reuse config loader
from src.subspace.manifold_pca import build_manifold  # 复用流形构造 / Reuse manifold builder
from src.subspace.manifold_pca import reconstruction_error  # 复用重建误差 / Reuse reconstruction error
from src.subspace.manifold_pca import save_manifold  # 复用流形保存 / Reuse manifold saver


def build_argument_parser() -> argparse.ArgumentParser:  # 构造参数解析器 / Build argument parser
    parser = argparse.ArgumentParser(description="Fit a PCA design manifold from historical candidate H.csv pool (W4). / 用历史候选 H.csv 池拟合 W4 设计流形。")  # 解析器 / Parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config path. / 项目配置路径。")  # 配置 / Config
    parser.add_argument("--variance-target", type=float, default=0.95, help="Cumulative variance ratio to keep. / 保留的累计方差比例。")  # 方差目标 / Variance target
    parser.add_argument("--max-components", type=int, default=None, help="Optional hard cap on number of components. / 主成分数上限。")  # 主成分上限 / Components cap
    parser.add_argument("--min-final-score", type=float, default=None, help="Optional minimum legacy final_score filter. / 旧 final_score 下限。")  # 评分下限 / Score floor
    parser.add_argument("--name-prefix", type=str, action="append", default=None, help="Optional candidate-name prefix filter (repeatable). / 候选名前缀过滤（可重复）。")  # 名称前缀 / Name prefix
    parser.add_argument("--output", type=str, default="reports/design_manifold_pca.npz", help="Output NPZ path. / 输出 NPZ 路径。")  # 输出路径 / Output path
    parser.add_argument("--quiet", action="store_true", help="Suppress summary. / 不打印摘要。")  # 静默 / Quiet
    return parser  # 返回解析器 / Return parser


def main(argv: list[str] | None = None) -> int:  # 主入口 / Main entry
    parser = build_argument_parser()  # 构造解析器 / Build parser
    args = parser.parse_args(argv)  # 解析参数 / Parse args
    config = load_config(args.config)  # 读取配置 / Load config
    grid_size = int(config["project"]["grid_size"])  # 读取设计网格 / Read design grid
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 候选目录 / Candidate dir
    manifold = build_manifold(candidates_dir, variance_target=float(args.variance_target), grid_size=grid_size, min_final_score=args.min_final_score, max_components=args.max_components, name_prefixes=args.name_prefix)  # 构造流形 / Build manifold
    output_path = Path(args.output)  # 输出路径 / Output path
    saved_npz = save_manifold(manifold, output_path)  # 保存流形 / Save manifold
    if not args.quiet:  # 检查是否输出摘要 / Check whether to print
        from src.subspace.manifold_pca import collect_design_pool  # 延迟导入 / Lazy import
        pool, _ = collect_design_pool(candidates_dir, grid_size=grid_size, min_final_score=args.min_final_score, name_prefixes=args.name_prefix)  # 收集验证池 / Collect pool for diagnostics
        errors = reconstruction_error(pool, manifold)  # 重建误差 / Reconstruction error
        print(f"Pool size: {manifold.sample_count}  Components kept: {manifold.components.shape[0]}  / 池规模 {manifold.sample_count}，保留主成分 {manifold.components.shape[0]}")  # 摘要行 / Summary line
        print(f"Cumulative variance kept: {float(manifold.explained_variance_ratio[-1])*100:.2f}%  / 累计方差 {float(manifold.explained_variance_ratio[-1])*100:.2f}%")  # 方差行 / Variance line
        print(f"Reconstruction mean abs error: {errors['mean_abs_error_mm']:.4f} mm  max: {errors['max_abs_error_mm']:.4f} mm  / 重建平均误差 {errors['mean_abs_error_mm']:.4f}mm，最大 {errors['max_abs_error_mm']:.4f}mm")  # 误差行 / Error line
        print(f"NPZ: {saved_npz}  Metadata JSON: {saved_npz.with_suffix('.json')} / NPZ：{saved_npz}，元数据 JSON：{saved_npz.with_suffix('.json')}")  # 路径行 / Path line
    return 0  # 返回成功 / Return success


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出运行 / Exit run
