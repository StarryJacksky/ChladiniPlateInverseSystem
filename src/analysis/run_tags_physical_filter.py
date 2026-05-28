from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析工具 / Import command-line parsing utilities
import csv  # 导入 CSV 写入工具 / Import CSV writing utilities
import os  # 导入环境变量工具 / Import environment-variable utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

os.environ.setdefault("MPLCONFIGDIR", str((Path("reports") / ".matplotlib").resolve()))  # 设置可写 Matplotlib 缓存目录 / Set writable Matplotlib cache directory

import numpy as np  # 导入数值计算库 / Import numerical library

from src.physics.drive_reachability import drive_reachability  # 导入中心驱动可达性诊断 / Import centre-drive reachability diagnostic
from src.subspace.free_subspace_feasibility import SubspaceResult  # 导入子空间结果类型 / Import subspace result type
from src.subspace.free_subspace_feasibility import optimise_modal_combination  # 导入自由组合优化器 / Import free-combination optimiser
from src.subspace.load_modal_basis import ModalBasis  # 导入模态基底类型 / Import modal-basis type
from src.subspace.load_modal_basis import load_modal_basis  # 导入 COMSOL 模态加载器 / Import COMSOL modal-basis loader
from src.subspace.narrowband_feasibility import DEFAULT_BETAS  # 导入默认窄频窗宽 / Import default narrowband widths
from src.subspace.narrowband_feasibility import run_narrowband_scan  # 导入窄频扫描 / Import narrowband scan
from src.visualisation.plot_physical_filter_results import save_alpha_frequency_barplot  # 导入 alpha 频率图 / Import alpha-frequency plotter
from src.visualisation.plot_physical_filter_results import save_drive_participation_barplot  # 导入中心参与度图 / Import centre-participation plotter
from src.visualisation.plot_physical_filter_results import save_response_triptych  # 导入响应三联图 / Import response triptych plotter
from src.visualisation.plot_physical_filter_results import save_summary_score_barplot  # 导入汇总分数图 / Import summary-score plotter


DEFAULT_CASES = ("tags_ic_case_a_target_thick", "tags_ic_case_b_target_thin", "tags_ic_case_c_target_thin_side_thick")  # 定义默认 TAGS 三案例 / Define default three TAGS cases


def case_label(case_name: str) -> str:  # 生成短案例标签 / Build short case label
    if "_case_a_" in case_name:  # 判断 A 案例 / Detect case A
        return "A"  # 返回 A / Return A
    if "_case_b_" in case_name:  # 判断 B 案例 / Detect case B
        return "B"  # 返回 B / Return B
    if "_case_c_" in case_name:  # 判断 C 案例 / Detect case C
        return "C"  # 返回 C / Return C
    return case_name.replace("tags_ic_", "")[:12]  # 回退短名 / Fallback short name


def load_target_binary(path: str | Path) -> np.ndarray:  # 读取目标二值图 / Load target binary map
    target = np.load(Path(path))  # 读取 NPY 文件 / Load NPY file
    if target.ndim != 2:  # 检查维度 / Check rank
        raise ValueError(f"Target must be 2-D: {path}. / 目标必须是二维图：{path}。")  # 抛出目标错误 / Raise target error
    return target.astype(bool)  # 返回布尔目标 / Return boolean target


def physical_score(result: SubspaceResult, drive: dict[str, object], weights: dict[str, float]) -> float:  # 计算综合物理可达性分数 / Compute combined physical feasibility score
    layout = float(result.metrics.get("layout", result.metrics.get("dice", 0.0)))  # 读取布局分 / Read layout score
    dice = float(result.metrics.get("dice", 0.0))  # 读取 Dice / Read Dice score
    bandwidth = float(result.frequency_spread)  # 读取系数频散 / Read coefficient frequency spread
    r_drive = float(drive.get("R_drive", 0.0))  # 读取中心驱动可达性 / Read centre-drive reachability
    n_eff = float(result.effective_modal_count)  # 读取有效模态数 / Read effective modal count
    n_target = max(float(weights["N_eff_target"]), 1.0e-12)  # 读取目标有效模态数 / Read target effective-mode count
    neff_penalty = max(0.0, n_eff - n_target) / n_target  # 计算多模态惩罚 / Compute many-mode penalty
    return float(weights["w_layout"] * layout + weights["w_dice"] * dice - weights["w_band"] * bandwidth - weights["w_drive"] * (1.0 - r_drive) - weights["w_neff"] * neff_penalty)  # 返回物理分数 / Return physical score


def recommend_frequency_domain(row: dict[str, object]) -> bool:  # 判断是否建议进入 COMSOL 频域验证 / Decide whether to recommend COMSOL frequency-domain validation
    score = float(row.get("physical_score", -1.0))  # 读取物理分 / Read physical score
    drive = float(row.get("center_drive_reachability", 0.0))  # 读取驱动可达性 / Read drive reachability
    dice = float(row.get("narrowband_dice", 0.0))  # 读取窄频 Dice / Read narrowband Dice
    spread = float(row.get("narrowband_frequency_spread", 1.0))  # 读取频散 / Read frequency spread
    return bool(score > -0.08 and drive >= 0.25 and dice >= 0.045 and spread <= 0.22)  # 使用宽松门槛筛选验证对象 / Use permissive thresholds for validation candidate


def note_for_row(row: dict[str, object]) -> str:  # 为 CSV 生成解释备注 / Build explanatory note for CSV
    if bool(row.get("recommended_for_frequency_domain", False)):  # 检查是否推荐 / Check recommendation state
        return "Proceed to COMSOL frequency-domain validation around the narrowband centre. / 建议围绕窄频中心进入 COMSOL 频域验证。"  # 返回推荐备注 / Return recommended note
    if float(row.get("center_drive_reachability", 0.0)) < 0.25:  # 检查中心可达性低 / Check low centre reachability
        return "Low centre-drive participation; free-looking pattern may not be excitable. / 中心驱动参与度低，看似漂亮的组合可能激不出来。"  # 返回低驱动备注 / Return low-drive note
    if float(row.get("narrowband_frequency_spread", 1.0)) > 0.22:  # 检查频散过大 / Check excessive frequency spread
        return "Combination remains too broadband for single-frequency drive. / 组合仍过宽频，不适合单频激励。"  # 返回宽频备注 / Return broadband note
    return "Narrowband visual match is still weak; use geometry redesign before validation. / 窄频视觉匹配仍弱，建议先做几何重设。"  # 返回弱匹配备注 / Return weak-match note


def flat_row(case_name: str, label: str, free_result: SubspaceResult, beta: float, narrow_result: SubspaceResult, drive: dict[str, object], score: float) -> dict[str, object]:  # 构造 CSV 行 / Build CSV row
    row = {"case_name": case_name, "case_label": label, "free_iou": float(free_result.metrics.get("iou", 0.0)), "free_dice": float(free_result.metrics.get("dice", 0.0)), "free_layout": float(free_result.metrics.get("layout", 0.0)), "free_frequency_spread": float(free_result.frequency_spread), "free_N_eff": float(free_result.effective_modal_count), "beta": float(beta), "narrowband_iou": float(narrow_result.metrics.get("iou", 0.0)), "narrowband_dice": float(narrow_result.metrics.get("dice", 0.0)), "narrowband_layout": float(narrow_result.metrics.get("layout", 0.0)), "narrowband_center_frequency": float(narrow_result.metadata.get("window_center_frequency_hz", narrow_result.frequency_mean_hz)), "narrowband_frequency_spread": float(narrow_result.frequency_spread), "narrowband_N_eff": float(narrow_result.effective_modal_count), "center_drive_reachability": float(drive.get("R_drive", 0.0)), "physical_score": float(score)}  # 填充基础字段 / Fill base fields
    row["recommended_for_frequency_domain"] = recommend_frequency_domain(row)  # 写入推荐标记 / Store recommendation flag
    row["notes"] = note_for_row(row)  # 写入备注 / Store note
    return row  # 返回 CSV 行 / Return CSV row


def write_csv(path: str | Path, rows: list[dict[str, object]]) -> None:  # 写出 CSV 表 / Write CSV table
    output = Path(path)  # 转换输出路径 / Convert output path
    output.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    fieldnames = ["case_name", "free_iou", "free_dice", "free_layout", "free_frequency_spread", "free_N_eff", "beta", "narrowband_iou", "narrowband_dice", "narrowband_layout", "narrowband_center_frequency", "narrowband_frequency_spread", "narrowband_N_eff", "center_drive_reachability", "physical_score", "recommended_for_frequency_domain", "notes"]  # 定义 CSV 列 / Define CSV columns
    with output.open("w", encoding="utf-8", newline="") as file_obj:  # 打开 CSV 文件 / Open CSV file
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)  # 创建字典写入器 / Create dict writer
        writer.writeheader()  # 写入表头 / Write header
        for row in rows:  # 遍历数据行 / Iterate data rows
            writer.writerow({key: row.get(key, "") for key in fieldnames})  # 写入一行 / Write one row


def best_rows_by_case(rows: list[dict[str, object]]) -> list[dict[str, object]]:  # 每个案例选择最佳物理行 / Select best physical row per case
    best: dict[str, dict[str, object]] = {}  # 创建最佳表 / Create best table
    for row in rows:  # 遍历所有行 / Iterate all rows
        case = str(row["case_name"])  # 读取案例名 / Read case name
        if case not in best or float(row["physical_score"]) > float(best[case]["physical_score"]):  # 检查是否刷新最佳 / Check whether best improves
            best[case] = row  # 保存最佳行 / Store best row
    return list(best.values())  # 返回最佳行列表 / Return best rows


def sweep_range_text(center_hz: float) -> str:  # 生成推荐扫频范围文本 / Build recommended sweep range text
    low = center_hz * 0.85  # 计算低端频率 / Compute low frequency
    high = center_hz * 1.15  # 计算高端频率 / Compute high frequency
    return f"{low:.1f}-{high:.1f} Hz"  # 返回范围文本 / Return range text


def write_markdown_report(path: str | Path, rows: list[dict[str, object]], warnings_by_case: dict[str, list[str]]) -> None:  # 写出 Markdown 报告 / Write Markdown report
    best_rows = sorted(best_rows_by_case(rows), key=lambda item: float(item["physical_score"]), reverse=True)  # 按物理分排序最佳行 / Sort best rows by physical score
    lines: list[str] = []  # 创建报告行列表 / Create report lines
    lines.append("# TAGS Physical Reachability Summary / TAGS 物理可达性总结")  # 写标题 / Write title
    lines.append("")  # 空行 / Blank line
    lines.append("Single-eigenmode scoring underestimates TAGS, but full free modal-subspace scoring overestimates physical reachability. Therefore, the relevant decision metric is narrowband, center-drive-reachable modal-subspace feasibility, followed by COMSOL frequency-domain validation using amplitude-valley scoring.")  # 写核心结论 / Write core conclusion
    lines.append("")  # 空行 / Blank line
    lines.append("本报告把自由模态组合只当作数学表达能力参考，不把它当成真实单频中心激励实验预测。")  # 写中文说明 / Write Chinese explanation
    lines.append("")  # 空行 / Blank line
    lines.append("## A/B/C Comparison / A/B/C 对比")  # 写小节 / Write section
    lines.append("")  # 空行 / Blank line
    lines.append("| Case | Free Dice | Free Layout | Best beta | NB Dice | NB Layout | B_alpha | R_drive | PhysicalScore | Recommendation | Sweep |")  # 写表头 / Write table header
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")  # 写分隔行 / Write separator
    for row in best_rows:  # 遍历最佳行 / Iterate best rows
        recommendation = "validate" if bool(row["recommended_for_frequency_domain"]) else "redesign first"  # 生成推荐短语 / Build recommendation phrase
        sweep = sweep_range_text(float(row["narrowband_center_frequency"]))  # 生成扫频范围 / Build sweep range
        lines.append(f"| {row['case_name']} | {float(row['free_dice']):.3f} | {float(row['free_layout']):.3f} | {float(row['beta']):.2f} | {float(row['narrowband_dice']):.3f} | {float(row['narrowband_layout']):.3f} | {float(row['narrowband_frequency_spread']):.3f} | {float(row['center_drive_reachability']):.3f} | {float(row['physical_score']):.3f} | {recommendation} | {sweep} |")  # 写表格行 / Write table row
    lines.append("")  # 空行 / Blank line
    lines.append("## Interpretation / 解读")  # 写小节 / Write section
    lines.append("")  # 空行 / Blank line
    if best_rows and bool(best_rows[0]["recommended_for_frequency_domain"]):  # 检查是否有推荐验证对象 / Check whether validation candidate exists
        lines.append(f"当前最适合进入 COMSOL 频域验证的是 `{best_rows[0]['case_name']}`，推荐围绕 `{float(best_rows[0]['narrowband_center_frequency']):.1f} Hz` 做约 ±15% 扫频。")  # 写推荐对象 / Write recommended candidate
    else:  # 没有推荐对象 / No recommended candidate
        lines.append("当前 A/B/C 的窄频中心驱动可达性还不足以把自由组合分数当成物理候选，建议进入 TAGS-A+ 几何重设，而不是继续盲搜 225 个格子。")  # 写重设建议 / Write redesign recommendation
    lines.append("")  # 空行 / Blank line
    lines.append("若某案例自由分数高但窄频分数、中心驱动参与度低，它只能说明该结构的 COMSOL 模态字典在数学上能拼出目标轮廓，不能说明单频中心激励能真实出现该图案。")  # 写自由组合警告 / Write free-subspace warning
    lines.append("")  # 空行 / Blank line
    lines.append("## Boundary Condition Warning / 频域边界条件提醒")  # 写小节 / Write section
    lines.append("")  # 空行 / Blank line
    lines.append("Eigenfrequency 里中心固定区可用于自然模态分析；但 Frequency Domain 里不要在同一个中心区域同时施加零位移固定和谐波激励，否则模型会过约束。建议选择：小中心区谐波 z 位移、小中心区谐波力，或简化 shaker/contact connector 三者之一。")  # 写边界条件提醒 / Write boundary-condition warning
    lines.append("")  # 空行 / Blank line
    lines.append("## TAGS-A+ Recommendation / TAGS-A+ 建议")  # 写小节 / Write section
    lines.append("")  # 空行 / Blank line
    lines.append("15×15 网格应继续作为输出分辨率，而不是 225 维独立优化变量。下一轮建议使用低维目标对齐参数：target band offset、side band offset、I stem/top/bottom offsets、C upper/left/lower arc offsets、edge tuning offsets、background thickness、smoothing radius。")  # 写低维参数建议 / Write low-dimensional parameter advice
    lines.append("")  # 空行 / Blank line
    lines.append("建议几何族：A1 target thick mild，A2 target thick medium，A3 target thick strong，A4 target thick + side soft mild，A5 target thick + side soft strong，A6 segmented target thick，A7 segmented target thick + side soft，A8 target thick + edge tuning，A9 segmented target thick + edge tuning，A10 segmented target thick + side soft + edge tuning。")  # 写几何族建议 / Write geometry-family advice
    lines.append("")  # 空行 / Blank line
    lines.append("## Loader Warnings / 数据加载警告")  # 写小节 / Write section
    lines.append("")  # 空行 / Blank line
    for case, warnings in warnings_by_case.items():  # 遍历警告 / Iterate warnings
        if warnings:  # 检查是否有警告 / Check warnings
            lines.append(f"- `{case}`: " + "；".join(warnings[:6]))  # 写警告摘要 / Write warning summary
        else:  # 无警告 / No warnings
            lines.append(f"- `{case}`: no modal-loading warnings. / 无模态加载警告。")  # 写无警告 / Write no warnings
    Path(path).parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")  # 写入报告 / Write report


def result_drive_for_window(basis: ModalBasis, result: SubspaceResult, radius_fraction: float) -> dict[str, object]:  # 对一个窗口结果计算中心驱动可达性 / Compute centre-drive reachability for one window result
    mode_to_index = {int(mode): index for index, mode in enumerate(basis.mode_ids)}  # 建立模态编号到索引的映射 / Build mode-id to index map
    indices = [mode_to_index[int(mode)] for mode in result.mode_ids]  # 找到结果模态对应索引 / Find basis indices for result modes
    return drive_reachability(result.alpha, basis.Phi[indices], result.mode_ids, result.freqs, radius_fraction=float(radius_fraction))  # 返回可达性结果 / Return reachability result


def run_case(case_name: str, args: argparse.Namespace, target_binary: np.ndarray, weights: dict[str, float]) -> dict[str, object]:  # 运行一个 TAGS 案例 / Run one TAGS case
    label = case_label(case_name)  # 生成案例标签 / Build case label
    export_dir = Path(args.exports_dir) / case_name  # 构造 COMSOL 导出目录 / Build COMSOL export directory
    figures_dir = Path(args.figures_dir)  # 读取图像目录 / Read figure directory
    basis = load_modal_basis(export_dir, int(args.mode_start), int(args.mode_end), int(args.image_size))  # 读取 COMSOL 模态基底 / Load COMSOL modal basis
    free_result = optimise_modal_combination(basis.Phi, basis.freqs, basis.mode_ids, target_binary, steps=int(args.free_steps), restarts=int(args.restarts), center_radius_px=int(args.center_radius_px), epsilon=float(args.epsilon), seed=int(args.seed), label=f"free_case_{label}")  # 运行自由组合参考 / Run free-combination reference
    save_response_triptych(figures_dir / f"free_response_case_{label}.png", target_binary, free_result)  # 保存自由组合图 / Save free-combination image
    save_alpha_frequency_barplot(figures_dir / f"alpha_frequency_barplot_case_{label}.png", free_result)  # 保存自由组合频率权重图 / Save free-combination frequency-weight chart
    scan = run_narrowband_scan(basis, target_binary, betas=tuple(float(beta) for beta in args.betas), steps=int(args.narrow_steps), restarts=int(args.restarts), seed=int(args.seed) + 37, min_modes=int(args.min_window_modes), center_radius_px=int(args.center_radius_px), epsilon=float(args.epsilon))  # 运行窄频扫描 / Run narrowband scan
    rows: list[dict[str, object]] = []  # 创建 CSV 行列表 / Create CSV row list
    best_bundle: dict[str, object] | None = None  # 初始化案例最佳包 / Initialise best bundle for case
    for beta, result in scan["best_by_beta"].items():  # 遍历每个 beta 的最佳窄频结果 / Iterate best narrowband result per beta
        drive = result_drive_for_window(basis, result, float(args.center_radius_fraction))  # 计算中心驱动可达性 / Compute centre-drive reachability
        score = physical_score(result, drive, weights)  # 计算物理分 / Compute physical score
        row = flat_row(case_name, label, free_result, float(beta), result, drive, score)  # 构造 CSV 行 / Build CSV row
        rows.append(row)  # 保存行 / Store row
        beta_text = f"{float(beta):.2f}".replace(".", "p")  # 构造 beta 文件名片段 / Build beta filename fragment
        save_response_triptych(figures_dir / f"best_narrowband_response_case_{label}_beta_{beta_text}.png", target_binary, result)  # 保存窄频响应图 / Save narrowband response image
        if best_bundle is None or float(score) > float(best_bundle["score"]):  # 检查是否刷新案例最佳 / Check whether case best improves
            best_bundle = {"score": float(score), "row": row, "result": result, "drive": drive}  # 保存案例最佳包 / Store case best bundle
    if best_bundle is not None:  # 检查是否有案例最佳 / Check whether case best exists
        save_drive_participation_barplot(figures_dir / f"drive_participation_barplot_case_{label}.png", best_bundle["result"].mode_ids, best_bundle["result"].freqs, np.asarray(best_bundle["drive"]["center_participation"], dtype=float))  # 保存中心参与度图 / Save centre-participation chart
    return {"case_name": case_name, "label": label, "basis": basis, "free_result": free_result, "rows": rows, "best_bundle": best_bundle, "warnings": list(basis.metadata.get("warnings", []))}  # 返回案例结果 / Return case result


def parse_args() -> argparse.Namespace:  # 解析命令行参数 / Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run TAGS physical reachability filtering. / 运行 TAGS 物理可达性过滤。")  # 创建解析器 / Create parser
    parser.add_argument("--cases", nargs="+", default=list(DEFAULT_CASES))  # 添加案例参数 / Add cases argument
    parser.add_argument("--exports-dir", default="data/comsol_exports")  # 添加导出目录参数 / Add exports-dir argument
    parser.add_argument("--target", default="data/processed_targets/target_binary.npy")  # 添加目标路径参数 / Add target path argument
    parser.add_argument("--mode-start", type=int, default=8)  # 添加起始模态参数 / Add mode-start argument
    parser.add_argument("--mode-end", type=int, default=40)  # 添加结束模态参数 / Add mode-end argument
    parser.add_argument("--image-size", type=int, default=128)  # 添加图像尺寸参数 / Add image-size argument
    parser.add_argument("--free-steps", type=int, default=520)  # 添加自由组合步数参数 / Add free-step argument
    parser.add_argument("--narrow-steps", type=int, default=230)  # 添加窄频步数参数 / Add narrow-step argument
    parser.add_argument("--restarts", type=int, default=2)  # 添加重启次数参数 / Add restarts argument
    parser.add_argument("--seed", type=int, default=29)  # 添加随机种子参数 / Add seed argument
    parser.add_argument("--epsilon", type=float, default=0.045)  # 添加零线宽度参数 / Add zero-contour width argument
    parser.add_argument("--center-radius-px", type=int, default=0)  # 添加评分中心移除半径 / Add scoring centre-removal radius
    parser.add_argument("--center-radius-fraction", type=float, default=0.07)  # 添加中心驱动半径比例 / Add centre-drive radius fraction
    parser.add_argument("--min-window-modes", type=int, default=2)  # 添加最少窗口模态数 / Add minimum window modes
    parser.add_argument("--betas", type=float, nargs="+", default=list(DEFAULT_BETAS))  # 添加 beta 列表 / Add beta list
    parser.add_argument("--csv-out", default="reports/tags_physical_filter_results.csv")  # 添加 CSV 输出路径 / Add CSV output path
    parser.add_argument("--report-out", default="reports/tags_physical_reachability_summary.md")  # 添加报告输出路径 / Add report output path
    parser.add_argument("--figures-dir", default="reports/figures")  # 添加图像输出目录 / Add figure output directory
    return parser.parse_args()  # 返回参数 / Return arguments


def default_weights() -> dict[str, float]:  # 默认物理评分权重 / Default physical-score weights
    return {"w_layout": 1.0, "w_dice": 0.5, "w_band": 0.7, "w_drive": 0.7, "w_neff": 0.2, "N_eff_target": 4.0}  # 返回权重 / Return weights


def main() -> None:  # 主入口 / Main entry point
    args = parse_args()  # 解析参数 / Parse arguments
    target_binary = load_target_binary(args.target)  # 读取目标图案 / Load target pattern
    weights = default_weights()  # 读取默认权重 / Read default weights
    all_rows: list[dict[str, object]] = []  # 创建总 CSV 行 / Create aggregate CSV rows
    warnings_by_case: dict[str, list[str]] = {}  # 创建案例警告表 / Create case-warning table
    for case_name in args.cases:  # 遍历案例 / Iterate cases
        case_result = run_case(str(case_name), args, target_binary, weights)  # 运行案例 / Run case
        all_rows.extend(case_result["rows"])  # 合并 CSV 行 / Merge CSV rows
        warnings_by_case[str(case_name)] = case_result["warnings"]  # 保存警告 / Store warnings
    write_csv(args.csv_out, all_rows)  # 写出 CSV / Write CSV
    write_markdown_report(args.report_out, all_rows, warnings_by_case)  # 写出 Markdown 报告 / Write Markdown report
    save_summary_score_barplot(Path(args.figures_dir) / "summary_physical_score_barplot.png", best_rows_by_case(all_rows))  # 保存总览图 / Save summary chart
    print(f"Wrote {args.csv_out} and {args.report_out}. / 已写出 {args.csv_out} 和 {args.report_out}。")  # 打印完成信息 / Print completion message


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
