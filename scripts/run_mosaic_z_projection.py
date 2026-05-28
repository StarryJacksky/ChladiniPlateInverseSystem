from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析工具 / Import command-line parsing utilities
import json  # 导入 JSON 输出工具 / Import JSON output utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

from src.forced_response.actuator_projection import project_modal_coefficients  # 导入激振器投影函数 / Import actuator projection helper


def build_parser() -> argparse.ArgumentParser:  # 构造命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Project MOSAIC-Z alpha coefficients to actuator parameters. / 将 MOSAIC-Z alpha 投影为激振器参数。")  # 初始化解析器 / Initialise parser
    parser.add_argument("candidate_dir", help="Candidate COMSOL export directory. / 候选 COMSOL 导出目录。")  # 添加候选目录 / Add candidate directory
    parser.add_argument("alpha_csv", help="MOSAIC-Z best_alpha.csv path. / MOSAIC-Z best_alpha.csv 路径。")  # 添加 alpha 路径 / Add alpha path
    parser.add_argument("--output-dir", default="reports/mosaic_z/projection", help="Projection output directory. / 投影输出目录。")  # 添加输出目录 / Add output directory
    parser.add_argument("--image-size", type=int, default=160, help="Modal field grid size. / 模态场网格尺寸。")  # 添加图像尺寸 / Add image size
    parser.add_argument("--actuators", type=int, default=1, help="Number of actuators. / 激振器数量。")  # 添加激振器数量 / Add actuator count
    parser.add_argument("--steps", type=int, default=1200, help="Optimisation steps per restart. / 每个重启的优化步数。")  # 添加步数 / Add step count
    parser.add_argument("--restarts", type=int, default=8, help="Random restart count. / 随机重启次数。")  # 添加重启次数 / Add restart count
    parser.add_argument("--learning-rate", type=float, default=0.035, help="Adam learning rate. / Adam 学习率。")  # 添加学习率 / Add learning rate
    parser.add_argument("--damping-ratio", type=float, default=0.015, help="Modal damping ratio. / 模态阻尼比。")  # 添加阻尼比 / Add damping ratio
    parser.add_argument("--seed", type=int, default=23, help="Random seed. / 随机种子。")  # 添加随机种子 / Add random seed
    return parser  # 返回解析器 / Return parser


def main() -> None:  # 脚本入口 / Script entry point
    args = build_parser().parse_args()  # 解析参数 / Parse arguments
    result = project_modal_coefficients(args.candidate_dir, args.alpha_csv, args.output_dir, image_size=int(args.image_size), actuator_count=int(args.actuators), steps=int(args.steps), restarts=int(args.restarts), learning_rate=float(args.learning_rate), damping_ratio=float(args.damping_ratio), seed=int(args.seed))  # 运行投影优化 / Run projection optimisation
    print(json.dumps(result, indent=2, ensure_ascii=False))  # 打印投影结果 / Print projection result


if __name__ == "__main__":  # 检查是否直接执行 / Check direct execution
    main()  # 执行入口 / Run entry point
