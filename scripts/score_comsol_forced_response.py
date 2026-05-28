from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行参数工具 / Import command-line argument tools
import json  # 导入 JSON 工具 / Import JSON utilities
import os  # 导入环境变量工具 / Import environment-variable utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)  # 创建 Matplotlib 缓存目录 / Create Matplotlib cache directory
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))  # 设置可写 Matplotlib 缓存 / Set writable Matplotlib cache

from src.config import load_config  # 导入配置读取函数 / Import configuration loader
from src.forced_response.score_comsol_response import score_comsol_forced_response  # 导入真实强迫响应评分器 / Import real forced-response scorer


def build_parser() -> argparse.ArgumentParser:  # 创建命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Score a COMSOL forced-response export. / 评分 COMSOL 强迫响应导出。")  # 初始化解析器 / Initialise parser
    parser.add_argument("--config", default="config.yaml", help="Config path. / 配置路径。")  # 添加配置参数 / Add config argument
    parser.add_argument("--response-csv", required=True, help="COMSOL forced_response.csv path. / COMSOL forced_response.csv 路径。")  # 添加响应 CSV 参数 / Add response CSV argument
    parser.add_argument("--output-dir", required=True, help="Output directory. / 输出目录。")  # 添加输出目录参数 / Add output-directory argument
    parser.add_argument("--image-size", type=int, default=160, help="Scoring grid size. / 评分网格尺寸。")  # 添加图像尺寸参数 / Add image-size argument
    parser.add_argument("--epsilon", type=float, default=0.080, help="Low-amplitude threshold. / 低振幅阈值。")  # 添加阈值参数 / Add threshold argument
    return parser  # 返回解析器 / Return parser


def main() -> None:  # 主入口 / Main entry point
    parser = build_parser()  # 创建解析器 / Build parser
    args = parser.parse_args()  # 解析命令行 / Parse command line
    config = load_config(args.config)  # 读取配置 / Load config
    target_path = Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 构造目标数组路径 / Build target array path
    if not target_path.exists():  # 检查目标是否存在 / Check whether target exists
        raise FileNotFoundError(f"Processed target not found: {target_path}. / 未找到处理后的目标：{target_path}。")  # 抛出缺失目标 / Raise missing target
    target = np.load(target_path).astype(bool)  # 读取目标二值图 / Load target binary map
    image_size = int(args.image_size)  # 读取评分尺寸 / Read scoring size
    remove_center = bool(config["nodal_extraction"].get("remove_center_region", True))  # 读取中心移除开关 / Read centre-removal flag
    center_radius_px = int(image_size * float(config["project"]["center_clamp_radius_mm"]) / float(config["project"]["plate_length_mm"])) if remove_center else 0  # 计算中心半径像素 / Compute centre radius in pixels
    summary = score_comsol_forced_response(args.response_csv, target, args.output_dir, image_size=image_size, epsilon=float(args.epsilon), center_radius_px=center_radius_px)  # 执行评分 / Run scoring
    print(json.dumps(summary, indent=2, ensure_ascii=False))  # 打印摘要 / Print summary


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
