from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析 / Import argument parsing
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

import numpy as np  # 导入数值库 / Import numerical library

from src.config import load_config  # 复用配置加载 / Reuse config loader
from src.scoring.unified_ranker import rank_candidates_unified  # 复用统一排序入口 / Reuse unified ranking entry
from src.scoring.unified_ranker import summarize_leaderboard  # 复用排行摘要 / Reuse leaderboard summary


def build_argument_parser() -> argparse.ArgumentParser:  # 构造参数解析器 / Build argument parser
    parser = argparse.ArgumentParser(description="Rank Chladni candidates with W2 unified scoring (amplitude valley + nodal-line). / 使用 W2 统一评分对 Chladni 候选排序。")  # 创建解析器 / Create parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config path. / 项目配置路径。")  # 配置参数 / Config option
    parser.add_argument("--mode", type=str, choices=["auto", "amplitude", "nodal"], default="auto", help="Primary metric mode. auto reads target_realizability verdict. / 主指标模式。auto 表示读取目标可达性判定。")  # 模式参数 / Mode option
    parser.add_argument("--top", type=int, default=10, help="Number of top candidates to print. / 摘要打印的前 N 名数量。")  # Top 参数 / Top option
    parser.add_argument("--verdict-report", type=str, default=None, help="Optional realizability report override path. / 可选可达性报告覆盖路径。")  # 报告覆盖 / Report override
    parser.add_argument("--candidate", type=str, action="append", help="Restrict ranking to these candidate ids (repeatable). / 限定候选编号（可重复传递）。")  # 候选筛选 / Candidate filter
    parser.add_argument("--quiet", action="store_true", help="Suppress stdout summary. / 不打印摘要。")  # 静默 / Quiet option
    return parser  # 返回解析器 / Return parser


def main(argv: list[str] | None = None) -> int:  # 主入口 / Main entry
    parser = build_argument_parser()  # 构造解析器 / Build parser
    args = parser.parse_args(argv)  # 解析参数 / Parse arguments
    config = load_config(args.config)  # 读取配置 / Load config
    processed_dir = Path(config["paths"]["processed_targets_dir"])  # 读取处理后目标目录 / Read processed-target directory
    target_path = processed_dir / "target_binary.npy"  # 拼接目标二值图 / Build target binary path
    if not target_path.exists():  # 检查目标是否存在 / Check target existence
        print(f"Target binary not found: {target_path}. Run target preprocessing first. / 未找到目标二值图：{target_path}，请先预处理目标。", file=sys.stderr)  # 缺失提示 / Missing message
        return 2  # 返回错误码 / Return error code
    target_binary = np.load(target_path).astype(bool)  # 读取目标 / Load target
    manual_mode = None if args.mode == "auto" else args.mode  # 转换模式参数 / Convert mode argument
    payload = rank_candidates_unified(config, target_binary, candidate_filter=args.candidate, manual_mode=manual_mode, verdict_report_path=args.verdict_report)  # 调用统一排序 / Call unified ranker
    if not args.quiet:  # 检查是否打印 / Check whether to print
        print(summarize_leaderboard(payload, top_k=int(args.top)))  # 打印摘要 / Print summary
        print(f"CSV : {payload.get('ranked_candidates_csv', '')} / 排行 CSV：{payload.get('ranked_candidates_csv', '')}")  # CSV 路径 / CSV path
        print(f"JSON: {payload.get('leaderboard_json', '')} / 排行 JSON：{payload.get('leaderboard_json', '')}")  # JSON 路径 / JSON path
    return 0  # 返回成功码 / Return success


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出运行 / Exit run
