from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析工具 / Import command-line parsing utilities
import json  # 导入 JSON 输出工具 / Import JSON output utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.config import load_config  # 导入配置读取函数 / Import config loader
from src.topology_grammar.generator import generate_target_topology_primitives  # 导入拓扑基元生成器 / Import topology primitive generator
from src.topology_grammar.primitives import write_topology_primitives  # 导入拓扑 CSV 写入函数 / Import topology CSV writer


def build_parser() -> argparse.ArgumentParser:  # 构造命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Generate MOSAIC-Z topology primitive CSVs from a target pattern. / 从目标图案生成 MOSAIC-Z 拓扑基元 CSV。")  # 初始化解析器 / Initialise parser
    parser.add_argument("--config", default="config.yaml", help="Project config path. / 项目配置路径。")  # 添加配置路径 / Add config path
    parser.add_argument("--target", default="data/processed_targets/target_binary.npy", help="Processed target npy path. / 预处理目标 npy 路径。")  # 添加目标路径 / Add target path
    parser.add_argument("--family", choices=["groove", "slot", "rib", "mass_pad"], default="groove", help="Primitive family. / 基元家族。")  # 添加基元家族 / Add primitive family
    parser.add_argument("--max-primitives", type=int, default=8, help="Maximum primitive count. / 最大基元数量。")  # 添加最大数量 / Add max count
    parser.add_argument("--output", default="reports/mosaic_z/topology_primitives.csv", help="Output CSV path. / 输出 CSV 路径。")  # 添加输出路径 / Add output path
    return parser  # 返回解析器 / Return parser


def main() -> None:  # 脚本入口 / Script entry point
    args = build_parser().parse_args()  # 解析命令行参数 / Parse command-line arguments
    config = load_config(args.config)  # 读取项目配置 / Load project config
    target = np.load(args.target).astype(bool)  # 读取目标二值图 / Load target binary map
    primitives = generate_target_topology_primitives(target, plate_length_mm=float(config.get("project", {}).get("plate_length_mm", 150.0)), family=str(args.family), max_primitives=int(args.max_primitives))  # 生成拓扑基元 / Generate topology primitives
    output_path = write_topology_primitives(args.output, primitives)  # 写入拓扑 CSV / Write topology CSV
    summary = {"output": str(output_path), "family": args.family, "primitive_count": len(primitives), "primitives": [primitive.as_row() for primitive in primitives]}  # 构造摘要 / Build summary
    print(json.dumps(summary, indent=2, ensure_ascii=False))  # 打印摘要 / Print summary


if __name__ == "__main__":  # 检查是否直接执行 / Check direct execution
    main()  # 执行入口 / Run entry point
