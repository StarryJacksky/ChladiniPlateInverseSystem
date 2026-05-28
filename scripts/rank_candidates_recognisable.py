from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 命令行解析 / Argument parsing
import csv  # CSV / CSV
import json  # JSON / JSON
import sys  # 系统 / System
from pathlib import Path  # 路径 / Paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 项目根 / Project root
if str(PROJECT_ROOT) not in sys.path:  # 检查 / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加根 / Add root

import numpy as np  # 数值库 / NumPy

from src.config import load_config  # 配置加载 / Config loader
from src.scoring.recognisability_score import score_frequency_response_recognisability  # 新评分 / New scoring


def build_argument_parser() -> argparse.ArgumentParser:  # 解析器 / Parser
    parser = argparse.ArgumentParser(description="Rank candidates by Chladni recognisability metrics (enrichment + recall + Gaussian contrast + direction). / 用 Chladni 可识别度指标排序候选。")  # 解析器 / Parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config path. / 项目配置。")  # 配置 / Config
    parser.add_argument("--target", type=str, default=None, help="Target NPY override (default: data/processed_targets/target_binary.npy). / 目标 NPY 覆盖。")  # 目标 / Target
    parser.add_argument("--sigma-rel", type=float, default=0.05, help="Gaussian powder sigma (relative to peak). / 高斯撒粉 sigma（相对峰值）。")  # sigma / Sigma
    parser.add_argument("--percentile", type=float, default=20.0, help="Recall percentile threshold. / Recall 分位阈值。")  # 分位 / Percentile
    parser.add_argument("--export-root", type=str, default="data/comsol_frequency_exports", help="Root dir of COMSOL frequency exports. / COMSOL 频域导出根目录。")  # 导出根 / Export root
    parser.add_argument("--top", type=int, default=15, help="Top N to print. / 打印前 N 名。")  # Top / Top
    parser.add_argument("--substring", type=str, default=None, help="Optional substring filter on export dir names. / 仅看名字包含子串的导出。")  # 过滤 / Filter
    parser.add_argument("--output-json", type=str, default="reports/recognisability_leaderboard.json", help="Output JSON path. / 输出 JSON 路径。")  # 输出 / Output
    parser.add_argument("--output-csv", type=str, default="reports/recognisability_leaderboard.csv", help="Output CSV path. / 输出 CSV 路径。")  # CSV / CSV
    return parser  # 返回 / Return


def main(argv: list[str] | None = None) -> int:  # 主入口 / Main entry
    parser = build_argument_parser()  # 解析器 / Parser
    args = parser.parse_args(argv)  # 解析 / Parse
    config = load_config(args.config)  # 配置 / Config
    target_path = Path(args.target) if args.target else Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 目标路径 / Target path
    if not target_path.exists():  # 检查 / Check
        print(f"Target file not found: {target_path}. / 未找到目标文件：{target_path}", file=sys.stderr)  # 缺失 / Missing
        return 2  # 错误 / Error
    target = np.load(target_path).astype(bool)  # 加载目标 / Load target
    print(f"Target: {target_path}, foreground={int(target.sum())}/{int(target.size)} ({float(target.sum())/float(target.size)*100:.2f}%) / 目标信息", flush=True)  # 打印 / Print
    image_size = int(target.shape[0])  # 图像尺寸 / Image size
    export_root = Path(args.export_root)  # 导出目录 / Export dir
    if not export_root.exists():  # 检查 / Check
        print(f"Export root not found: {export_root}. / 未找到导出目录：{export_root}", file=sys.stderr)  # 缺失 / Missing
        return 2  # 错误 / Error
    runs = sorted(export_root.iterdir())  # 列出 / List
    if args.substring:  # 过滤 / Filter
        runs = [r for r in runs if args.substring in r.name]  # 子串匹配 / Substring match
    all_rows: list[dict[str, object]] = []  # 全部行 / All rows
    best_per_run: list[dict[str, object]] = []  # 每候选最佳 / Best per run
    for run_dir in runs:  # 遍历导出 / Iterate
        if not run_dir.is_dir():  # 跳过非目录 / Skip non-dirs
            continue  # 跳过 / Skip
        csv_path = run_dir / "frequency_response.csv"  # CSV 路径 / CSV path
        if not csv_path.exists():  # 跳过缺失 / Skip missing
            continue  # 跳过 / Skip
        try:  # 防错 / Guard
            result = score_frequency_response_recognisability(str(csv_path), target, image_size=image_size, sigma_rel=float(args.sigma_rel), percentile=float(args.percentile))  # 评分 / Score
        except Exception as exc:  # 错误 / Error
            print(f"  skip {run_dir.name}: {exc}", flush=True)  # 跳过提示 / Skip msg
            continue  # 跳过 / Skip
        rows = result.get("rows", [])  # 行 / Rows
        if not rows:  # 空 / Empty
            continue  # 跳过 / Skip
        for r in rows:  # 加入运行名 / Add run name
            r2 = {"run": run_dir.name, **r}  # 字典合并 / Merge
            all_rows.append(r2)  # 追加 / Append
        best = result.get("best")  # 最佳 / Best
        if best is not None:  # 检查 / Check
            best_per_run.append({"run": run_dir.name, **best})  # 追加 / Append
    if not all_rows:  # 空结果 / Empty
        print("No frequency-response CSVs found. / 没找到频域 CSV。", file=sys.stderr)  # 提示 / Hint
        return 2  # 错误 / Error
    all_rows.sort(key=lambda r: -float(r["composite_recognisability"]))  # 排序 / Sort
    best_per_run.sort(key=lambda r: -float(r["composite_recognisability"]))  # 排序 / Sort
    print()  # 空行 / Blank
    header = f"{'rank':>4} {'composite':>9} {'enrich':>7} {'recall':>7} {'contrast':>8} {'direct':>7} {'freq_hz':>8}  run"  # 表头串 / Header line
    print(f"=== Top {args.top} per-frequency entries (all runs) / 全运行的前 {args.top} 个频率条目 ===", flush=True)  # 标题 / Header
    print(header, flush=True)  # 表头 / Table header
    for i, r in enumerate(all_rows[: int(args.top)]):  # 前 N / Top N
        print(f"{i+1:>4d} {float(r['composite_recognisability']):>9.4f} {float(r['enrichment_factor']):>7.2f} {float(r['coverage_recall']):>7.2%} {float(r['gaussian_contrast']):>8.2f} {float(r['directional_alignment']):>7.2f} {float(r['frequency_hz']):>8.1f}  {r['run']}", flush=True)  # 行 / Row
    print()  # 空行 / Blank
    print(f"=== Top {args.top} best-per-run entries / 各运行最佳的前 {args.top} ===", flush=True)  # 标题 / Header
    print(header, flush=True)  # 表头 / Header
    for i, r in enumerate(best_per_run[: int(args.top)]):  # 前 N / Top N
        print(f"{i+1:>4d} {float(r['composite_recognisability']):>9.4f} {float(r['enrichment_factor']):>7.2f} {float(r['coverage_recall']):>7.2%} {float(r['gaussian_contrast']):>8.2f} {float(r['directional_alignment']):>7.2f} {float(r['frequency_hz']):>8.1f}  {r['run']}", flush=True)  # 行 / Row
    out_json_path = Path(args.output_json)  # 输出路径 / Output path
    out_json_path.parent.mkdir(parents=True, exist_ok=True)  # 建目录 / Make dir
    out_json_path.write_text(json.dumps({"target_path": str(target_path), "sigma_rel": float(args.sigma_rel), "percentile": float(args.percentile), "ranked_all": all_rows, "ranked_best_per_run": best_per_run}, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 JSON / Write JSON
    out_csv_path = Path(args.output_csv)  # CSV 路径 / CSV path
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)  # 建目录 / Make dir
    with out_csv_path.open("w", newline="", encoding="utf-8") as f:  # 写 CSV / Write CSV
        writer = csv.writer(f)  # 写器 / Writer
        writer.writerow(["rank", "run", "frequency_hz", "composite_recognisability", "enrichment_factor", "coverage_recall", "gaussian_contrast", "directional_alignment"])  # 表头 / Header
        for i, r in enumerate(all_rows):  # 全部 / All
            writer.writerow([i + 1, r["run"], r["frequency_hz"], r["composite_recognisability"], r["enrichment_factor"], r["coverage_recall"], r["gaussian_contrast"], r["directional_alignment"]])  # 行 / Row
    print(f"\nLeaderboard JSON: {out_json_path}  /  CSV: {out_csv_path}", flush=True)  # 路径 / Path
    return 0  # 成功 / Success


if __name__ == "__main__":  # 直接运行 / Direct run
    raise SystemExit(main())  # 退出 / Exit
