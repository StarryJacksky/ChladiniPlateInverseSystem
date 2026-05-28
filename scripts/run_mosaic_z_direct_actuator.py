from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析工具 / Import command-line parsing utilities
import json  # 导入 JSON 输出工具 / Import JSON output utilities
import os  # 导入系统环境工具 / Import operating-system environment tools
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

os.environ.setdefault("MPLCONFIGDIR", str(Path("reports/.matplotlib").resolve()))  # 固定 Matplotlib 缓存目录 / Pin Matplotlib cache directory

from src.config import load_config  # 导入配置读取函数 / Import config loader
from src.forced_response.optimize_actuators import optimise_actuators_for_valley  # 导入直接激振优化函数 / Import direct actuator optimiser
from src.subspace.mosaic_z import parse_mode_span  # 导入模态范围解析函数 / Import mode-span parser


def build_parser() -> argparse.ArgumentParser:  # 构造命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Directly optimise actuator parameters for a MOSAIC-Z amplitude valley. / 直接优化 MOSAIC-Z 振幅谷线激振参数。")  # 初始化解析器 / Initialise parser
    parser.add_argument("modal_export_dir", help="Directory containing COMSOL modal exports. / 包含 COMSOL 模态导出的目录。")  # 添加模态导出目录 / Add modal export directory
    parser.add_argument("--config", default="config.yaml", help="Project config path. / 项目配置路径。")  # 添加配置路径 / Add config path
    parser.add_argument("--target", default="data/processed_targets/target_binary.npy", help="Processed target npy path. / 预处理目标 npy 路径。")  # 添加目标路径 / Add target path
    parser.add_argument("--modes", default="8:60", help="Mode span such as 8:60. / 模态范围，例如 8:60。")  # 添加模态范围 / Add mode span
    parser.add_argument("--output-dir", default="reports/mosaic_z/direct_actuator", help="Output directory. / 输出目录。")  # 添加输出目录 / Add output directory
    parser.add_argument("--image-size", type=int, default=128, help="Optimisation grid size. / 优化网格尺寸。")  # 添加图像尺寸 / Add image size
    parser.add_argument("--actuators", type=int, default=4, help="Number of actuators. / 激振器数量。")  # 添加激振器数量 / Add actuator count
    parser.add_argument("--steps", type=int, default=1200, help="Optimisation steps per restart. / 每个重启优化步数。")  # 添加步数 / Add steps
    parser.add_argument("--restarts", type=int, default=8, help="Random restart count. / 随机重启次数。")  # 添加重启次数 / Add restarts
    parser.add_argument("--learning-rate", type=float, default=0.035, help="Adam learning rate. / Adam 学习率。")  # 添加学习率 / Add learning rate
    parser.add_argument("--damping-ratio", type=float, default=0.015, help="Damping ratio. / 阻尼比。")  # 添加阻尼比 / Add damping ratio
    parser.add_argument("--epsilon", type=float, default=0.060, help="Amplitude-valley softness. / 振幅谷线软阈值。")  # 添加软阈值 / Add soft threshold
    parser.add_argument("--center-penalty-weight", type=float, default=2.0, help="Penalty for actuators inside the centre clamp. / 激振点进入中心夹持区的惩罚权重。")  # 添加中心禁区惩罚权重 / Add centre exclusion penalty weight
    parser.add_argument("--modal-scale-csv", default="", help="Optional COMSOL-calibrated modal scale CSV. / 可选真实 COMSOL 校准模态修正 CSV。")  # 添加模态校准参数 / Add modal-calibration argument
    parser.add_argument("--fixed-frequency-hz", type=float, default=0.0, help="Optional fixed drive frequency; zero keeps it optimised. / 可选固定驱动频率，零表示继续优化频率。")  # 添加固定频率参数 / Add fixed-frequency argument
    parser.add_argument("--seed", type=int, default=31, help="Random seed. / 随机种子。")  # 添加随机种子 / Add random seed
    return parser  # 返回解析器 / Return parser


def compute_center_radius_px(config: dict, image_size: int) -> int:  # 计算中心夹持像素半径 / Compute centre-clamp radius in pixels
    if not config.get("nodal_extraction", {}).get("remove_center_region", True):  # 检查是否禁用中心移除 / Check whether centre removal is disabled
        return 0  # 返回零半径 / Return zero radius
    radius_mm = float(config.get("project", {}).get("center_clamp_radius_mm", 8.0))  # 读取夹持半径 / Read clamp radius
    plate_mm = float(config.get("project", {}).get("plate_length_mm", 150.0))  # 读取板长 / Read plate length
    return int(round(float(image_size) * radius_mm / max(plate_mm, 1.0e-9)))  # 换算像素半径 / Convert to pixel radius


def main() -> None:  # 脚本入口 / Script entry point
    args = build_parser().parse_args()  # 解析参数 / Parse arguments
    config = load_config(args.config)  # 读取配置 / Load config
    target = np.load(args.target).astype(bool)  # 读取目标图 / Load target map
    modes = parse_mode_span(args.modes)  # 解析模态范围 / Parse mode span
    center_radius_px = compute_center_radius_px(config, int(args.image_size))  # 计算中心夹持半径 / Compute centre clamp radius
    fixed_frequency = None if float(args.fixed_frequency_hz) <= 0.0 else float(args.fixed_frequency_hz)  # 解析固定频率 / Parse fixed frequency
    summary = optimise_actuators_for_valley(args.modal_export_dir, target, modes, args.output_dir, image_size=int(args.image_size), actuator_count=int(args.actuators), steps=int(args.steps), restarts=int(args.restarts), learning_rate=float(args.learning_rate), damping_ratio=float(args.damping_ratio), epsilon=float(args.epsilon), center_radius_px=center_radius_px, plate_length_mm=float(config.get("project", {}).get("plate_length_mm", 150.0)), seed=int(args.seed), center_penalty_weight=float(args.center_penalty_weight), modal_scale_csv=args.modal_scale_csv or None, fixed_frequency_hz=fixed_frequency)  # 运行直接激振优化 / Run direct actuator optimisation
    print(json.dumps(summary, indent=2, ensure_ascii=False))  # 打印摘要 / Print summary


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行入口 / Run entry point
