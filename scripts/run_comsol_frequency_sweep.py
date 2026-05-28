from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行参数工具 / Import command-line argument tools
import csv  # 导入 CSV 写入工具 / Import CSV writing utilities
import json  # 导入 JSON 工具 / Import JSON utilities
import os  # 导入环境变量工具 / Import environment-variable utilities
import shutil  # 导入目录复制工具 / Import directory copy utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)  # 创建 Matplotlib 缓存目录 / Create Matplotlib cache directory
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))  # 设置可写 Matplotlib 缓存 / Set writable Matplotlib cache

from src.comsol.run_livelink import run_livelink_forced_response  # 导入真实 COMSOL 强迫响应 runner / Import real COMSOL forced-response runner
from src.analysis.run_frequency_domain_validation import run_validation as run_frequency_domain_validation  # 导入新频域验证入口 / Import new frequency-domain validation entrypoint
from src.config import ensure_project_dirs  # 导入项目目录创建函数 / Import project-directory helper
from src.config import load_config  # 导入配置读取函数 / Import config loader
from src.forced_response.score_comsol_response import score_comsol_forced_response  # 导入真实响应评分器 / Import real-response scorer
from src.scoring.amplitude_valley_score import rank_frequency_responses  # 导入新频域排序评分 / Import new frequency-domain ranking scorer
from src.frequency_domain.load_frequency_response import load_frequency_response  # 导入新频域导出读取器 / Import new frequency-domain export loader
from src.target.target_bands import build_target_bands_from_binary  # 导入目标 band 构造 / Import target-band builder


def build_parser() -> argparse.ArgumentParser:  # 构造命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Run a COMSOL-in-the-loop frequency sweep for one forced-response candidate. / 对一个强迫响应候选执行 COMSOL 闭环频率扫描。")  # 初始化解析器 / Initialise parser
    parser.add_argument("--config", default="config.yaml", help="Project config path. / 项目配置路径。")  # 添加配置路径 / Add config path
    parser.add_argument("--base-candidate-id", required=True, help="Candidate directory to clone for each frequency. / 每个频率要克隆的基准候选目录。")  # 添加基准候选 / Add base candidate
    parser.add_argument("--run-name", default="", help="Optional run name for report output. / 可选报告运行名称。")  # 添加运行名称 / Add run name
    parser.add_argument("--frequencies", required=True, help="Comma-separated drive frequencies in Hz. / 逗号分隔的驱动频率 Hz。")  # 添加频率列表 / Add frequency list
    parser.add_argument("--epsilons", default="0.04,0.05,0.06", help="Comma-separated scoring epsilons. / 逗号分隔的评分阈值。")  # 添加阈值列表 / Add epsilon list
    parser.add_argument("--image-size", type=int, default=160, help="Scoring image size. / 评分图像尺寸。")  # 添加图像尺寸 / Add image size
    parser.add_argument("--damping-ratio", type=float, default=0.015, help="Damping ratio to write into each variant. / 写入每个变体的阻尼比。")  # 添加阻尼比 / Add damping ratio
    parser.add_argument("--force-sigma-mm", type=float, default=2.5, help="Gaussian actuator force width in mm. / 高斯激励力宽度 mm。")  # 添加力宽 / Add force width
    parser.add_argument("--candidate-prefix", default="", help="Optional generated candidate prefix. / 可选生成候选前缀。")  # 添加候选前缀 / Add candidate prefix
    parser.add_argument("--force-run", action="store_true", help="Run COMSOL even if response CSV already exists. / 即使已有响应 CSV 也重新运行 COMSOL。")  # 添加强制运行开关 / Add force-run flag
    parser.add_argument("--overwrite-candidates", action="store_true", help="Replace generated candidate directories if they already exist. / 若生成候选已存在则替换。")  # 添加覆盖候选开关 / Add overwrite flag
    parser.add_argument("--frequency-export-case", default="", help="Optional case id for combined frequency-domain export. / 可选统一频域导出案例名。")  # 添加统一频域导出名 / Add combined frequency export id
    parser.add_argument("--validation-output-dir", default="", help="Optional output directory for new amplitude-valley validation report. / 可选新振幅谷线验证报告目录。")  # 添加新验证报告目录 / Add new validation report directory
    parser.add_argument("--skip-legacy-epsilon-score", action="store_true", help="Skip old epsilon-threshold forced-response scoring. / 跳过旧阈值强迫响应评分。")  # 添加跳过旧评分开关 / Add skip legacy scoring flag
    return parser  # 返回解析器 / Return parser


def parse_float_list(text: str) -> list[float]:  # 解析浮点列表 / Parse float list
    values = []  # 创建数值列表 / Create value list
    for item in text.split(","):  # 遍历逗号片段 / Iterate comma-separated chunks
        stripped = item.strip()  # 去除空白 / Trim whitespace
        if stripped:  # 检查片段是否非空 / Check whether chunk is non-empty
            values.append(float(stripped))  # 添加浮点值 / Add float value
    if not values:  # 检查是否为空 / Check whether list is empty
        raise ValueError("At least one numeric value is required. / 至少需要一个数值。")  # 抛出参数错误 / Raise argument error
    return values  # 返回数值列表 / Return value list


def frequency_token(frequency_hz: float) -> str:  # 构造频率安全名称 / Build frequency-safe name
    rounded = f"{float(frequency_hz):.3f}".rstrip("0").rstrip(".")  # 格式化频率 / Format frequency
    return rounded.replace("-", "m").replace(".", "p")  # 替换路径不友好字符 / Replace path-unfriendly characters


def load_json(path: Path) -> dict[str, object]:  # 读取可选 JSON / Load optional JSON
    if not path.exists():  # 检查文件是否存在 / Check file existence
        return {}  # 缺失时返回空字典 / Return empty dict when missing
    return json.loads(path.read_text(encoding="utf-8"))  # 读取 JSON 内容 / Read JSON content


def write_frequency_csv(path: Path, frequency_hz: float, damping_ratio: float, force_sigma_mm: float) -> None:  # 写入频率合同 / Write frequency contract
    with path.open("w", encoding="utf-8", newline="") as file_obj:  # 打开输出文件 / Open output file
        writer = csv.DictWriter(file_obj, fieldnames=["drive_frequency_hz", "damping_ratio", "force_sigma_mm"])  # 创建字典写入器 / Create dictionary writer
        writer.writeheader()  # 写入表头 / Write header
        writer.writerow({"drive_frequency_hz": float(frequency_hz), "damping_ratio": float(damping_ratio), "force_sigma_mm": float(force_sigma_mm)})  # 写入频率参数 / Write frequency parameters


def initialise_combined_export(path: Path) -> None:  # 初始化统一频域导出 CSV / Initialise combined frequency-domain export CSV
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    with path.open("w", encoding="utf-8", newline="") as file_obj:  # 打开统一导出文件 / Open combined export file
        writer = csv.writer(file_obj)  # 创建 CSV 写入器 / Create CSV writer
        writer.writerow(["frequency_hz", "x", "y", "real_uz", "imag_uz"])  # 写入统一表头 / Write combined header


def append_forced_response_to_combined_export(response_csv: Path, frequency_hz: float, combined_path: Path) -> None:  # 追加单频强迫响应到统一导出 / Append one forced response to combined export
    if not response_csv.exists():  # 检查响应 CSV 是否存在 / Check response CSV existence
        raise FileNotFoundError(f"Forced response CSV not found: {response_csv}. / 未找到强迫响应 CSV：{response_csv}。")  # 抛出缺失错误 / Raise missing error
    with response_csv.open("r", encoding="utf-8", newline="") as input_obj, combined_path.open("a", encoding="utf-8", newline="") as output_obj:  # 打开输入和输出 / Open input and output
        reader = csv.DictReader(input_obj)  # 创建输入读取器 / Create input reader
        writer = csv.writer(output_obj)  # 创建输出写入器 / Create output writer
        for row in reader:  # 遍历响应行 / Iterate response rows
            real_value = row.get("w_real", row.get("real_uz", row.get("real", "0")))  # 读取实部 / Read real component
            imag_value = row.get("w_imag", row.get("imag_uz", row.get("imag", "0")))  # 读取虚部 / Read imaginary component
            writer.writerow([float(frequency_hz), row["x"], row["y"], real_value, imag_value])  # 写入统一频域行 / Write combined frequency row


def write_new_frequency_validation_summary(export_file: Path, target: np.ndarray, output_dir: Path, image_size: int) -> dict[str, object]:  # 写新频域评分摘要 / Write new frequency-validation summary
    responses, _metadata = load_frequency_response(export_file, int(image_size))  # 读取统一频域导出 / Load combined frequency-domain export
    target_data = build_target_bands_from_binary(target, int(image_size))  # 构造目标 band 数据 / Build target band data
    ranked = rank_frequency_responses(responses, target_data)  # 对频率响应排序 / Rank frequency responses
    output_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    with (output_dir / "amplitude_valley_frequency_scores.csv").open("w", encoding="utf-8", newline="") as file_obj:  # 打开新评分 CSV / Open new score CSV
        fieldnames = ["frequency_hz", "target_mean_amplitude", "side_mean_amplitude", "valley_contrast", "extra_valley_penalty", "final_amplitude_valley_score"]  # 定义关键列 / Define key columns
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)  # 创建字典写入器 / Create dict writer
        writer.writeheader()  # 写入表头 / Write header
        for row in ranked:  # 遍历排序行 / Iterate ranked rows
            writer.writerow({key: row.get(key, "") for key in fieldnames})  # 写入评分行 / Write score row
    best = ranked[0] if ranked else {}  # 读取最佳行 / Read best row
    (output_dir / "amplitude_valley_frequency_summary.json").write_text(json.dumps({"best": best, "rows": ranked}, indent=2, ensure_ascii=False), encoding="utf-8")  # 写入 JSON 摘要 / Write JSON summary
    return {"best": best, "rows": ranked}  # 返回新评分摘要 / Return new score summary


def run_full_validation_report(case_id: str, export_dir: Path, target_path: Path, output_dir: Path, image_size: int) -> None:  # 运行完整频域验证报告 / Run full frequency-domain validation report
    validation_args = argparse.Namespace(case=case_id, export_path=str(export_dir), target=str(target_path), output_dir=str(output_dir), grid_size=int(image_size), target_band_radius_px=2, side_band_inner_radius_px=4, side_band_outer_radius_px=10, center_mask_radius_px=0, epsilon=0.080, strong_contrast=3.0, good_contrast=2.0, weak_contrast=1.5, max_extra_penalty=0.32)  # 构造验证入口参数 / Build validation entrypoint arguments
    run_frequency_domain_validation(validation_args)  # 执行完整验证报告 / Run full validation report


def clone_frequency_variant(base_dir: Path, output_dir: Path, candidate_id: str, frequency_hz: float, damping_ratio: float, force_sigma_mm: float, overwrite: bool) -> None:  # 克隆频率变体 / Clone frequency variant
    if output_dir.exists() and overwrite:  # 检查是否需要覆盖 / Check whether overwrite is requested
        shutil.rmtree(output_dir)  # 删除旧变体目录 / Remove old variant directory
    if not output_dir.exists():  # 检查变体是否缺失 / Check whether variant is missing
        shutil.copytree(base_dir, output_dir)  # 复制基准候选 / Copy base candidate
    write_frequency_csv(output_dir / "frequency_parameters.csv", frequency_hz, damping_ratio, force_sigma_mm)  # 写入频率合同 / Write frequency contract
    metadata = load_json(output_dir / "metadata.json")  # 读取元数据 / Load metadata
    metadata.update({"candidate_id": candidate_id, "source_candidate": metadata.get("source_candidate", base_dir.name), "sweep_frequency_hz": float(frequency_hz), "force_sigma_mm": float(force_sigma_mm), "notes": f"COMSOL-in-the-loop frequency sweep variant at {float(frequency_hz):.3f} Hz. / COMSOL 闭环频率扫描变体，频率 {float(frequency_hz):.3f} Hz。"})  # 更新元数据 / Update metadata
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")  # 写回元数据 / Write metadata


def center_radius_px(config: dict, image_size: int) -> int:  # 计算中心掩膜半径 / Compute centre mask radius
    if not config.get("nodal_extraction", {}).get("remove_center_region", True):  # 检查中心掩膜开关 / Check centre-mask switch
        return 0  # 禁用时返回零 / Return zero when disabled
    return int(int(image_size) * float(config["project"]["center_clamp_radius_mm"]) / float(config["project"]["plate_length_mm"]))  # 换算像素半径 / Convert to pixel radius


def score_candidate_epsilons(config: dict, candidate_id: str, target: np.ndarray, epsilons: list[float], image_size: int, run_dir: Path) -> list[dict[str, object]]:  # 对一个候选执行多阈值评分 / Score one candidate across epsilons
    response_csv = Path(config["paths"]["comsol_exports_dir"]) / candidate_id / "forced_response" / "forced_response.csv"  # 构造响应 CSV 路径 / Build response CSV path
    if not response_csv.exists():  # 检查响应文件 / Check response file
        raise FileNotFoundError(f"Forced response CSV not found: {response_csv}. / 未找到强迫响应 CSV：{response_csv}。")  # 抛出响应缺失 / Raise missing response
    rows = []  # 创建评分行列表 / Create score row list
    for epsilon in epsilons:  # 遍历评分阈值 / Iterate scoring epsilons
        output_dir = run_dir / candidate_id / f"eps_{frequency_token(epsilon)}"  # 构造阈值输出目录 / Build epsilon output directory
        summary = score_comsol_forced_response(response_csv, target, output_dir, image_size=image_size, epsilon=float(epsilon), center_radius_px=center_radius_px(config, image_size))  # 执行评分 / Run scoring
        rows.append({"candidate_id": candidate_id, "epsilon": float(epsilon), "preview": str(output_dir / "comsol_forced_response_preview.png"), **summary["metrics"], **summary["stats"]})  # 添加评分行 / Add score row
    return rows  # 返回评分行 / Return score rows


def best_score(rows: list[dict[str, object]]) -> dict[str, object]:  # 选择最佳评分行 / Select best score row
    return max(rows, key=lambda row: (float(row["dice"]), float(row["iou"]), float(row["layout"])))  # 按 Dice/IoU/Layout 排序 / Sort by Dice/IoU/Layout


def write_summary(run_dir: Path, all_rows: list[dict[str, object]]) -> dict[str, object]:  # 写入总报告 / Write sweep summary
    run_dir.mkdir(parents=True, exist_ok=True)  # 创建报告目录 / Create report directory
    best = best_score(all_rows) if all_rows else {}  # 选择最佳结果 / Select best result
    summary = {"best": best, "rows": all_rows}  # 构造摘要 / Build summary
    (run_dir / "frequency_sweep_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")  # 写入 JSON 摘要 / Write JSON summary
    with (run_dir / "frequency_sweep_summary.csv").open("w", encoding="utf-8", newline="") as file_obj:  # 打开 CSV 摘要 / Open CSV summary
        fieldnames = list(all_rows[0].keys()) if all_rows else ["candidate_id"]  # 构造表头 / Build fieldnames
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)  # 创建 CSV 写入器 / Create CSV writer
        writer.writeheader()  # 写入表头 / Write header
        writer.writerows(all_rows)  # 写入所有行 / Write all rows
    return summary  # 返回摘要 / Return summary


def main() -> None:  # 脚本入口 / Script entry point
    args = build_parser().parse_args()  # 解析命令行参数 / Parse command-line arguments
    config = load_config(args.config)  # 读取配置 / Load config
    ensure_project_dirs(config)  # 确保项目目录存在 / Ensure project directories exist
    frequencies = parse_float_list(args.frequencies)  # 解析频率列表 / Parse frequency list
    epsilons = parse_float_list(args.epsilons)  # 解析阈值列表 / Parse epsilon list
    candidates_root = Path(config["paths"]["candidates_dir"])  # 读取候选根目录 / Read candidate root
    base_dir = candidates_root / args.base_candidate_id  # 构造基准候选目录 / Build base candidate directory
    if not base_dir.exists():  # 检查基准候选 / Check base candidate
        raise FileNotFoundError(f"Base candidate not found: {base_dir}. / 未找到基准候选：{base_dir}。")  # 抛出缺失错误 / Raise missing error
    run_name = args.run_name or f"{args.base_candidate_id}_frequency_sweep"  # 构造运行名称 / Build run name
    report_dir = Path("reports") / "mosaic_z" / "comsol_closed_loop" / run_name  # 构造报告目录 / Build report directory
    target_path = Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 构造目标数组路径 / Build target array path
    target = np.load(target_path).astype(bool)  # 读取目标二值图 / Load target binary map
    all_rows = []  # 创建全部结果列表 / Create all-result list
    frequency_export_case = args.frequency_export_case or args.base_candidate_id  # 读取统一频域导出案例名 / Read combined frequency export case id
    combined_export_path = Path("data/comsol_frequency_exports") / frequency_export_case / "frequency_response.csv"  # 构造统一频域导出路径 / Build combined frequency export path
    initialise_combined_export(combined_export_path)  # 初始化统一频域导出 / Initialise combined frequency export
    for frequency_hz in frequencies:  # 遍历频率 / Iterate frequencies
        token = frequency_token(frequency_hz)  # 构造频率 token / Build frequency token
        candidate_id = f"{args.candidate_prefix or args.base_candidate_id}_sweep_f{token}"  # 构造候选编号 / Build candidate id
        candidate_dir = candidates_root / candidate_id  # 构造候选目录 / Build candidate directory
        clone_frequency_variant(base_dir, candidate_dir, candidate_id, frequency_hz, float(args.damping_ratio), float(args.force_sigma_mm), bool(args.overwrite_candidates))  # 创建候选变体 / Create candidate variant
        response_csv = Path(config["paths"]["comsol_exports_dir"]) / candidate_id / "forced_response" / "forced_response.csv"  # 构造响应 CSV 路径 / Build response CSV path
        if args.force_run or not response_csv.exists():  # 判断是否需要运行 COMSOL / Decide whether COMSOL run is needed
            run_livelink_forced_response(config, candidate_id, None)  # 运行真实 COMSOL 强迫响应 / Run real COMSOL forced response
        append_forced_response_to_combined_export(response_csv, float(frequency_hz), combined_export_path)  # 汇总到新频域导出 / Append to new frequency-domain export
        if not args.skip_legacy_epsilon_score:  # 检查是否保留旧评分 / Check whether legacy scoring is kept
            all_rows.extend(score_candidate_epsilons(config, candidate_id, target, epsilons, int(args.image_size), report_dir))  # 评分并合并结果 / Score and merge results
        write_summary(report_dir, all_rows)  # 每个频率后写一次摘要 / Write summary after each frequency
    summary = write_summary(report_dir, all_rows)  # 写入最终摘要 / Write final summary
    amplitude_valley_summary = write_new_frequency_validation_summary(combined_export_path, target, report_dir, int(args.image_size))  # 写新振幅谷线摘要 / Write new amplitude-valley summary
    validation_output_dir = Path(args.validation_output_dir) if args.validation_output_dir else Path("reports") / "frequency_domain_validation" / frequency_export_case  # 构造完整验证报告目录 / Build full validation report directory
    run_full_validation_report(frequency_export_case, combined_export_path.parent, target_path, validation_output_dir, int(args.image_size))  # 生成完整频域验证报告 / Generate full frequency-domain validation report
    summary["combined_frequency_export"] = str(combined_export_path)  # 记录统一频域导出路径 / Record combined frequency export path
    summary["frequency_domain_validation_report"] = str(validation_output_dir / "frequency_domain_validation_summary.md")  # 记录完整验证报告路径 / Record full validation report path
    summary["amplitude_valley_best"] = amplitude_valley_summary.get("best", {})  # 记录新振幅谷线最佳频率 / Record new amplitude-valley best frequency
    print(json.dumps(summary, indent=2, ensure_ascii=False))  # 打印摘要 / Print summary


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行入口 / Run entry point
