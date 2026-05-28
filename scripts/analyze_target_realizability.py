from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行参数解析 / Import argument-parser utilities
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查项目根是否在搜索路径 / Check whether project root is on path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根到搜索路径 / Insert project root into path

from src.config import load_config  # 复用项目配置加载 / Reuse project config loader
from src.target.target_realizability import analyze_target_realizability  # 复用可达性分析 / Reuse realizability analysis
from src.target.target_realizability import load_target_binary_from_path  # 复用目标加载 / Reuse target loader
from src.target.target_realizability import save_realizability_report  # 复用报告保存 / Reuse report saver
from src.target.target_realizability import summarize_realizability_report  # 复用摘要构造 / Reuse summary builder


def resolve_default_target(config: dict) -> Path:  # 解析默认目标路径 / Resolve default target path
    processed_dir = Path(config["paths"]["processed_targets_dir"])  # 读取处理后目标目录 / Read processed-target directory
    processed_npy = processed_dir / "target_binary.npy"  # 拼接 NPY 路径 / Build NPY path
    if processed_npy.exists():  # 优先使用处理后的二值图 / Prefer processed binary
        return processed_npy  # 返回 NPY 路径 / Return NPY path
    return Path(config["paths"]["target_pattern"])  # 退回原始目标图 / Fall back to raw target image


def build_argument_parser() -> argparse.ArgumentParser:  # 构造命令行解析器 / Build argument parser
    parser = argparse.ArgumentParser(description="Analyse pre-COMSOL realizability of a Chladni target. / 分析 Chladni 目标在跑 COMSOL 之前的可达性。")  # 创建解析器 / Create parser
    parser.add_argument("--target", type=str, default=None, help="Target binary npy or image path; defaults to processed target. / 目标二值 npy 或图像路径，默认为处理后目标。")  # 目标路径选项 / Target path option
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config path. / 项目配置路径。")  # 配置路径选项 / Config path option
    parser.add_argument("--output", type=str, default="reports/target_realizability.json", help="Output JSON report path. / 输出 JSON 报告路径。")  # 报告路径选项 / Report path option
    parser.add_argument("--image-size", type=int, default=None, help="Override target image size for raw images. / 处理原始图像时使用的尺寸。")  # 图像尺寸选项 / Image size option
    parser.add_argument("--thickness-mm", type=float, default=None, help="Override default thickness for frequency estimate. / 频率估算使用的默认厚度。")  # 厚度选项 / Thickness option
    parser.add_argument("--quiet", action="store_true", help="Suppress stdout summary. / 不打印摘要。")  # 静默选项 / Quiet option
    return parser  # 返回解析器 / Return parser


def main(argv: list[str] | None = None) -> int:  # 主入口函数 / Main entry function
    parser = build_argument_parser()  # 构造解析器 / Build parser
    args = parser.parse_args(argv)  # 解析参数 / Parse arguments
    config = load_config(args.config)  # 读取项目配置 / Load project config
    nodal_config = config.get("nodal_extraction", {})  # 读取节点提取配置 / Read nodal-extraction config
    project_config = config.get("project", {})  # 读取项目配置 / Read project config
    material_config = config.get("material", {})  # 读取材料配置 / Read material config
    thickness_config = config.get("thickness", {})  # 读取厚度配置 / Read thickness config
    target_path = Path(args.target) if args.target else resolve_default_target(config)  # 选择目标路径 / Choose target path
    image_size = int(args.image_size or nodal_config.get("image_size", 256))  # 选择图像尺寸 / Choose image size
    target_binary = load_target_binary_from_path(target_path, image_size)  # 加载目标二值图 / Load target binary
    thickness_default = float(args.thickness_mm if args.thickness_mm is not None else thickness_config.get("default_mm", 1.0))  # 选择默认厚度 / Choose default thickness
    report = analyze_target_realizability(
        target_binary,
        plate_size_mm=float(project_config.get("plate_length_mm", 150.0)),
        grid_size=int(project_config.get("grid_size", 15)),
        center_clamp_radius_mm=float(project_config.get("center_clamp_radius_mm", 8.0)),
        thickness_mm_default=thickness_default,
        youngs_modulus_pa=float(material_config.get("youngs_modulus_pa", 2.0e9)),
        poisson_ratio=float(material_config.get("poisson_ratio", 0.35)),
        density_kg_m3=float(material_config.get("density_kg_m3", 1200.0)),
    )  # 计算可达性报告 / Compute realizability report
    report["target_path"] = str(target_path)  # 记录目标路径 / Record target path
    output_path = save_realizability_report(report, args.output)  # 保存报告 / Save report
    if not args.quiet:  # 检查是否打印摘要 / Check whether to print summary
        print(summarize_realizability_report(report))  # 打印摘要 / Print summary
        print(f"Report: {output_path} / 报告：{output_path}")  # 打印报告路径 / Print report path
    return 0  # 返回成功码 / Return success code


if __name__ == "__main__":  # 判断是否直接运行 / Check direct execution
    raise SystemExit(main())  # 退出运行 / Exit run
