from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行参数工具 / Import command-line argument tools
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

from src.config import ensure_project_dirs  # 导入目录创建函数 / Import directory creation helper
from src.config import load_config  # 导入配置读取函数 / Import configuration loader
from src.optimisation.random_search import generate_random_search_batch  # 导入批量生成函数 / Import batch generation function
from src.optimisation.random_search import score_available_candidates  # 导入候选评分函数 / Import candidate scoring function


def build_parser() -> argparse.ArgumentParser:  # 创建命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Chladni inverse design MVP. / Chladni 逆向设计 MVP。")  # 初始化解析器 / Initialise parser
    parser.add_argument("command", choices=["prepare-target", "generate-candidates", "score-candidates"], help="Workflow command. / 工作流命令。")  # 添加命令参数 / Add command argument
    parser.add_argument("--config", default="config.yaml", help="Config file path. / 配置文件路径。")  # 添加配置路径参数 / Add config path argument
    parser.add_argument("--generation", type=int, default=0, help="Candidate generation index. / 候选代数编号。")  # 添加代数参数 / Add generation argument
    return parser  # 返回解析器 / Return parser


def prepare_target(config: dict):  # 准备目标图案 / Prepare target pattern
    from src.target.preprocess_target import preprocess_target  # 延迟导入目标预处理函数 / Lazily import target preprocessing function
    image_size = int(config["nodal_extraction"]["image_size"])  # 读取图像尺寸 / Read image size
    line_width = int(config["nodal_extraction"]["target_line_width_px"])  # 读取目标线宽 / Read target line width
    plate_radius_px = int(image_size * config["project"]["center_clamp_radius_mm"] / config["project"]["plate_length_mm"])  # 计算中心半径像素 / Compute center radius in pixels
    target = preprocess_target(config["paths"]["target_pattern"], image_size, line_width, plate_radius_px, config["paths"]["processed_targets_dir"])  # 执行目标预处理 / Run target preprocessing
    return target  # 返回目标二值图 / Return target binary map


def main() -> None:  # 主程序入口 / Main program entry
    sys.stdout.reconfigure(encoding="utf-8")  # 设置 UTF-8 输出 / Set UTF-8 output
    parser = build_parser()  # 创建命令行解析器 / Build command-line parser
    args = parser.parse_args()  # 读取命令行参数 / Parse command-line arguments
    config = load_config(args.config)  # 读取配置文件 / Load configuration file
    ensure_project_dirs(config)  # 创建必要目录 / Create required directories
    if args.command == "prepare-target":  # 判断是否处理目标图 / Check target-preparation command
        prepare_target(config)  # 处理目标图 / Prepare target image
        print("Target prepared. / 目标图已处理。")  # 打印完成信息 / Print completion message
    if args.command == "generate-candidates":  # 判断是否生成候选 / Check candidate-generation command
        candidate_ids = generate_random_search_batch(config, args.generation)  # 生成候选批次 / Generate candidate batch
        print(f"Generated {len(candidate_ids)} candidates. / 已生成 {len(candidate_ids)} 个候选。")  # 打印候选数量 / Print candidate count
    if args.command == "score-candidates":  # 判断是否评分候选 / Check candidate-scoring command
        target_path = Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 构造目标数组路径 / Build target array path
        if not target_path.exists():  # 检查目标数组是否存在 / Check whether target array exists
            prepare_target(config)  # 自动处理目标图 / Automatically prepare target
        import numpy as np  # 延迟导入 NumPy / Lazily import NumPy
        target_binary = np.load(target_path).astype(bool)  # 读取目标二值图 / Load target binary map
        ranking = score_available_candidates(config, target_binary)  # 评分已有候选 / Score available candidates
        print(ranking if ranking else "No scored candidates yet. / 暂无可评分候选。")  # 打印排名或提示 / Print ranking or message


if __name__ == "__main__":  # 判断是否直接运行 / Check direct execution
    main()  # 执行主程序 / Run main program
