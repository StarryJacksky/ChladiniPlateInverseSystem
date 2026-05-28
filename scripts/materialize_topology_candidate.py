from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行参数工具 / Import command-line argument tools
import json  # 导入 JSON 输出工具 / Import JSON output utilities

from src.config import load_config  # 导入配置读取函数 / Import config loader
from src.topology_grammar.rasterize import materialize_topology_candidate  # 导入拓扑物化函数 / Import topology materialisation helper


def build_parser() -> argparse.ArgumentParser:  # 构造命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Materialize topology primitives into real thickness/density/loss fields. / 将拓扑基元物化为真实厚度、密度、损耗场。")  # 初始化解析器 / Initialise parser
    parser.add_argument("--config", default="config.yaml", help="Project config path. / 项目配置路径。")  # 添加配置路径 / Add config path
    parser.add_argument("--base-candidate-dir", required=True, help="Base candidate directory. / 基准候选目录。")  # 添加基准候选目录 / Add base candidate directory
    parser.add_argument("--topology-csv", required=True, help="Topology primitive CSV. / 拓扑基元 CSV。")  # 添加拓扑 CSV / Add topology CSV
    parser.add_argument("--output-candidate-dir", required=True, help="Output candidate directory. / 输出候选目录。")  # 添加输出候选目录 / Add output candidate directory
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output directory if it exists. / 若输出目录存在则覆盖。")  # 添加覆盖开关 / Add overwrite flag
    return parser  # 返回解析器 / Return parser


def main() -> None:  # 脚本入口 / Script entry point
    args = build_parser().parse_args()  # 解析命令行参数 / Parse command-line arguments
    config = load_config(args.config)  # 读取配置 / Load config
    summary = materialize_topology_candidate(args.base_candidate_dir, args.topology_csv, args.output_candidate_dir, config, overwrite=bool(args.overwrite))  # 执行拓扑物化 / Run topology materialisation
    print(json.dumps(summary, indent=2, ensure_ascii=False))  # 打印摘要 / Print summary


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行入口 / Run entry point
