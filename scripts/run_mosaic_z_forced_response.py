from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析工具 / Import command-line parsing utilities
import json  # 导入 JSON 输出工具 / Import JSON output utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.config import load_config  # 导入配置读取函数 / Import config loader
from src.forced_response.predict_response import predict_and_score_forced_response  # 导入强迫响应预测函数 / Import forced-response predictor
from src.subspace.mosaic_z import parse_mode_span  # 导入模态范围解析器 / Import mode-span parser


def build_parser() -> argparse.ArgumentParser:  # 构造命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Predict a MOSAIC-Z forced response from modal exports and actuator contracts. / 根据模态导出和激振合同预测 MOSAIC-Z 强迫响应。")  # 初始化解析器 / Initialise parser
    parser.add_argument("modal_export_dir", help="Directory containing mode_*.csv and frequencies.csv. / 包含 mode_*.csv 与 frequencies.csv 的目录。")  # 添加模态导出目录 / Add modal export directory
    parser.add_argument("operator_dir", help="Directory containing actuator/frequency CSV contracts. / 包含激振器和频率 CSV 合同的目录。")  # 添加算子合同目录 / Add operator contract directory
    parser.add_argument("--config", default="config.yaml", help="Project config path. / 项目配置路径。")  # 添加配置路径 / Add config path
    parser.add_argument("--target", default="data/processed_targets/target_binary.npy", help="Processed target npy path. / 预处理目标 npy 路径。")  # 添加目标路径 / Add target path
    parser.add_argument("--modes", default="8:60", help="Mode span such as 8:60. / 模态范围，例如 8:60。")  # 添加模态范围 / Add mode span
    parser.add_argument("--output-dir", default="reports/mosaic_z/forced_response", help="Output directory. / 输出目录。")  # 添加输出目录 / Add output directory
    parser.add_argument("--image-size", type=int, default=160, help="Prediction grid size. / 预测网格尺寸。")  # 添加图像尺寸 / Add image size
    parser.add_argument("--epsilon", type=float, default=0.080, help="Amplitude-valley threshold. / 振幅谷线阈值。")  # 添加振幅阈值 / Add amplitude threshold
    return parser  # 返回解析器 / Return parser


def compute_center_radius_px(config: dict, image_size: int) -> int:  # 计算中心夹持半径像素值 / Compute centre-clamp radius in pixels
    if not config.get("nodal_extraction", {}).get("remove_center_region", True):  # 检查是否禁用中心移除 / Check whether centre removal is disabled
        return 0  # 返回零半径 / Return zero radius
    radius_mm = float(config.get("project", {}).get("center_clamp_radius_mm", 8.0))  # 读取夹持半径 / Read clamp radius
    plate_mm = float(config.get("project", {}).get("plate_length_mm", 150.0))  # 读取板长 / Read plate length
    return int(round(float(image_size) * radius_mm / max(plate_mm, 1.0e-9)))  # 换算像素半径 / Convert to pixel radius


def main() -> None:  # 脚本入口 / Script entry point
    args = build_parser().parse_args()  # 解析命令行参数 / Parse command-line arguments
    config = load_config(args.config)  # 读取配置 / Load config
    target = np.load(args.target).astype(bool)  # 读取目标图 / Load target map
    modes = parse_mode_span(args.modes)  # 解析模态范围 / Parse mode span
    center_radius_px = compute_center_radius_px(config, int(args.image_size))  # 计算中心夹持像素半径 / Compute centre clamp radius
    summary = predict_and_score_forced_response(args.modal_export_dir, args.operator_dir, target, modes, args.output_dir, image_size=int(args.image_size), epsilon=float(args.epsilon), center_radius_px=center_radius_px, plate_length_mm=float(config.get("project", {}).get("plate_length_mm", 150.0)))  # 预测并评分强迫响应 / Predict and score forced response
    print(json.dumps(summary, indent=2, ensure_ascii=False))  # 打印摘要 / Print summary


if __name__ == "__main__":  # 检查是否直接执行 / Check direct execution
    main()  # 执行主函数 / Run main function
