from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行参数工具 / Import command-line argument tools
import json  # 导入 JSON 输出工具 / Import JSON output utilities
import os  # 导入系统环境工具 / Import operating-system environment tools
from pathlib import Path  # 导入路径工具 / Import path utilities

os.environ.setdefault("MPLCONFIGDIR", str(Path("reports/.matplotlib").resolve()))  # 固定 Matplotlib 缓存目录 / Pin Matplotlib cache directory

from src.config import load_config  # 导入配置读取函数 / Import config loader
from src.forced_response.calibrate_modal_response import calibrate_modal_response  # 导入模态校准函数 / Import modal calibration function
from src.subspace.mosaic_z import parse_mode_span  # 导入模态范围解析 / Import mode-span parser


def build_parser() -> argparse.ArgumentParser:  # 构造命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Calibrate MOSAIC-Z modal forcing against real COMSOL responses. / 用真实 COMSOL 响应校准 MOSAIC-Z 模态强迫模型。")  # 初始化解析器 / Initialise parser
    parser.add_argument("modal_export_dir", help="Directory containing eigenmode exports. / 包含本征模态导出的目录。")  # 添加模态目录参数 / Add modal directory argument
    parser.add_argument("--config", default="config.yaml", help="Project config path. / 项目配置路径。")  # 添加配置路径 / Add config path
    parser.add_argument("--case", action="append", required=True, help="Candidate id with a forced_response export; repeatable. / 带 forced_response 导出的候选编号，可重复。")  # 添加样本参数 / Add case argument
    parser.add_argument("--modes", default="8:60", help="Mode span such as 8:60. / 模态范围，例如 8:60。")  # 添加模态范围 / Add mode span
    parser.add_argument("--output-dir", default="reports/mosaic_z/modal_calibration", help="Output directory. / 输出目录。")  # 添加输出目录 / Add output directory
    parser.add_argument("--image-size", type=int, default=160, help="Calibration grid size. / 校准网格尺寸。")  # 添加图像尺寸 / Add image size
    parser.add_argument("--ridge", type=float, default=1.0e-5, help="Least-squares ridge value. / 最小二乘岭正则值。")  # 添加岭正则 / Add ridge value
    parser.add_argument("--shrink", type=float, default=0.35, help="Shrinkage toward unit modal scale. / 向单位模态修正收缩的强度。")  # 添加收缩强度 / Add shrinkage strength
    return parser  # 返回解析器 / Return parser


def case_from_id(config: dict, candidate_id: str) -> dict[str, str]:  # 从候选编号构造校准样本 / Build calibration case from candidate id
    candidate_dir = Path(config["paths"]["candidates_dir"]) / candidate_id  # 构造候选目录 / Build candidate directory
    response_csv = Path(config["paths"]["comsol_exports_dir"]) / candidate_id / "forced_response" / "forced_response.csv"  # 构造响应 CSV 路径 / Build response CSV path
    if not candidate_dir.exists():  # 检查候选目录 / Check candidate directory
        raise FileNotFoundError(f"Candidate directory not found: {candidate_dir}. / 未找到候选目录：{candidate_dir}。")  # 抛出候选缺失 / Raise missing candidate
    if not response_csv.exists():  # 检查响应文件 / Check response file
        raise FileNotFoundError(f"Forced response CSV not found: {response_csv}. / 未找到强迫响应 CSV：{response_csv}。")  # 抛出响应缺失 / Raise missing response
    return {"name": candidate_id, "operator_dir": str(candidate_dir), "response_csv": str(response_csv)}  # 返回样本定义 / Return case definition


def main() -> None:  # 脚本入口 / Script entry point
    args = build_parser().parse_args()  # 解析命令行参数 / Parse command-line arguments
    config = load_config(args.config)  # 读取配置 / Load config
    modes = parse_mode_span(args.modes)  # 解析模态范围 / Parse mode span
    cases = [case_from_id(config, candidate_id) for candidate_id in args.case]  # 构造样本列表 / Build case list
    summary = calibrate_modal_response(args.modal_export_dir, cases, modes, args.output_dir, image_size=int(args.image_size), plate_length_mm=float(config.get("project", {}).get("plate_length_mm", 150.0)), ridge=float(args.ridge), shrink=float(args.shrink))  # 运行模态校准 / Run modal calibration
    print(json.dumps(summary, indent=2, ensure_ascii=False))  # 打印摘要 / Print summary


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行入口 / Run entry point
