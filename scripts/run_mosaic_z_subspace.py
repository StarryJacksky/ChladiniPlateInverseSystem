from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析工具 / Import command-line parsing utilities
import json  # 导入 JSON 输出工具 / Import JSON output utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.config import load_config  # 导入配置读取函数 / Import config loader
from src.subspace.mosaic_z import optimise_modal_subspace  # 导入 MOSAIC-Z 优化器 / Import MOSAIC-Z optimiser
from src.subspace.mosaic_z import parse_mode_span  # 导入模态范围解析器 / Import mode-span parser


def build_parser() -> argparse.ArgumentParser:  # 构造命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Run MOSAIC-Z modal-subspace feasibility tests. / 运行 MOSAIC-Z 模态子空间可行性测试。")  # 初始化解析器 / Initialise parser
    parser.add_argument("candidates", nargs="+", help="Candidate export directories. / 候选 COMSOL 导出目录。")  # 添加候选目录参数 / Add candidate directory argument
    parser.add_argument("--config", default="config.yaml", help="Project config path. / 项目配置路径。")  # 添加配置路径参数 / Add config path argument
    parser.add_argument("--target", default="data/processed_targets/target_binary.npy", help="Processed target npy path. / 预处理目标 npy 路径。")  # 添加目标路径参数 / Add target path argument
    parser.add_argument("--modes", default="8:60", help="Mode span such as 8:60 or 8,9,10. / 模态范围，例如 8:60 或 8,9,10。")  # 添加模态范围参数 / Add mode-span argument
    parser.add_argument("--output-root", default="reports/mosaic_z", help="Output root directory. / 输出根目录。")  # 添加输出目录参数 / Add output-root argument
    parser.add_argument("--image-size", type=int, default=128, help="Optimisation grid size. / 优化网格尺寸。")  # 添加图像尺寸参数 / Add image-size argument
    parser.add_argument("--steps", type=int, default=600, help="Adam steps per restart. / 每个起点的 Adam 步数。")  # 添加步数参数 / Add step-count argument
    parser.add_argument("--restarts", type=int, default=4, help="Number of random restarts. / 随机重启次数。")  # 添加重启次数参数 / Add restart-count argument
    parser.add_argument("--learning-rate", type=float, default=0.035, help="Adam learning rate. / Adam 学习率。")  # 添加学习率参数 / Add learning-rate argument
    parser.add_argument("--epsilon", type=float, default=0.045, help="Soft zero-line epsilon. / 软零线阈值。")  # 添加零线阈值参数 / Add zero-line epsilon argument
    parser.add_argument("--target-weight", type=float, default=1.15, help="Target-zero loss weight. / 目标零位移损失权重。")  # 添加目标项权重 / Add target-term weight
    parser.add_argument("--extra-weight", type=float, default=1.35, help="Extra-zero loss weight. / 额外零线损失权重。")  # 添加额外零线权重 / Add extra-zero weight
    parser.add_argument("--cross-weight", type=float, default=0.55, help="Sign-crossing loss weight. / 符号穿越损失权重。")  # 添加穿越项权重 / Add crossing-term weight
    parser.add_argument("--sharp-weight", type=float, default=0.12, help="Sharpness loss weight. / 清晰度损失权重。")  # 添加清晰度权重 / Add sharpness weight
    parser.add_argument("--seed", type=int, default=17, help="Random seed. / 随机种子。")  # 添加随机种子参数 / Add random seed argument
    return parser  # 返回解析器 / Return parser


def compute_center_radius_px(config: dict, image_size: int) -> int:  # 计算中心夹持像素半径 / Compute centre-clamp radius in pixels
    if not config.get("nodal_extraction", {}).get("remove_center_region", True):  # 检查是否关闭中心移除 / Check whether centre removal is disabled
        return 0  # 返回零半径 / Return zero radius
    radius_mm = float(config["project"]["center_clamp_radius_mm"])  # 读取中心夹持半径毫米值 / Read centre clamp radius in millimetres
    plate_mm = float(config["project"]["plate_length_mm"])  # 读取板长毫米值 / Read plate length in millimetres
    return int(round(float(image_size) * radius_mm / max(plate_mm, 1.0e-9)))  # 换算为像素半径 / Convert to pixel radius


def main() -> None:  # 脚本入口 / Script entry point
    args = build_parser().parse_args()  # 解析命令行参数 / Parse command-line arguments
    config = load_config(args.config)  # 读取项目配置 / Load project config
    target = np.load(args.target).astype(bool)  # 读取预处理目标 / Load processed target
    modes = parse_mode_span(args.modes)  # 解析模态范围 / Parse mode span
    center_radius_px = compute_center_radius_px(config, int(args.image_size))  # 计算中心夹持半径 / Compute centre clamp radius
    loss_weights = {"target": float(args.target_weight), "extra": float(args.extra_weight), "cross": float(args.cross_weight), "sharp": float(args.sharp_weight)}  # 组装损失权重 / Assemble loss weights
    summaries = []  # 创建结果摘要列表 / Create summary list
    for candidate in args.candidates:  # 遍历候选目录 / Iterate candidate directories
        candidate_path = Path(candidate)  # 转换候选路径 / Convert candidate path
        output_dir = Path(args.output_root) / candidate_path.name  # 构造候选输出目录 / Build candidate output directory
        summary = optimise_modal_subspace(candidate_path, target, modes, output_dir, image_size=int(args.image_size), steps=int(args.steps), restarts=int(args.restarts), learning_rate=float(args.learning_rate), center_radius_px=center_radius_px, epsilon=float(args.epsilon), seed=int(args.seed), loss_weights=loss_weights)  # 运行 MOSAIC-Z 优化 / Run MOSAIC-Z optimisation
        summaries.append(summary)  # 保存摘要 / Store summary
        print(json.dumps(summary, ensure_ascii=False), flush=True)  # 打印单候选摘要 / Print candidate summary
    Path(args.output_root).mkdir(parents=True, exist_ok=True)  # 确保输出根目录存在 / Ensure output root exists
    (Path(args.output_root) / "summary.json").write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")  # 写入总摘要 / Write combined summary


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行入口 / Run entry point
