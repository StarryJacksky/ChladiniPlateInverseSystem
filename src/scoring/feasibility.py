from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

from src.scoring.metrics import SCORING_VERSION  # 导入当前评分版本 / Import current scoring version


CURRENT_CONTRACT_VARIABLES = ["thickness_mm", "global_material"]  # 定义当前 COMSOL 合约变量 / Define current COMSOL contract variables
NEXT_CONTRACT_VARIABLES = ["per_cell_density_or_mass", "per_cell_loss_factor", "hole_or_slot_topology", "support_position", "actuator_position_phase"]  # 定义下一阶段变量 / Define next-stage variables


def safe_float(value, default: float = 0.0) -> float:  # 安全转换浮点数 / Safely convert a float
    try:  # 尝试转换数值 / Try numeric conversion
        return float(value)  # 返回浮点数 / Return float value
    except (TypeError, ValueError):  # 捕获缺失或非法值 / Catch missing or invalid values
        return default  # 返回默认值 / Return default value


def load_score_json(path: Path) -> dict | None:  # 读取评分文件 / Load a score file
    try:  # 尝试读取 JSON / Try reading JSON
        return json.loads(path.read_text(encoding="utf-8"))  # 返回解析结果 / Return parsed result
    except (OSError, json.JSONDecodeError):  # 捕获文件或格式错误 / Catch file or format errors
        return None  # 返回空结果 / Return no result


def has_real_comsol_export(config: dict, candidate_id: str) -> bool:  # 判断是否有真实 COMSOL 导出 / Decide whether real COMSOL export exists
    export_dir = Path(config["paths"]["comsol_exports_dir"]) / candidate_id  # 构造导出目录 / Build export directory
    return export_dir.exists() and any(export_dir.glob("mode_*.csv"))  # 检查模态文件 / Check mode files


def collect_score_records(config: dict) -> list[dict]:  # 收集当前版本评分记录 / Collect current-version score records
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    records = []  # 创建记录列表 / Create record list
    for score_path in sorted(candidates_dir.glob("candidate_*/score.json")):  # 遍历评分文件 / Iterate score files
        score = load_score_json(score_path)  # 读取评分内容 / Load score content
        candidate_id = score_path.parent.name  # 读取候选编号 / Read candidate id
        if not score or score.get("scoring_version") != SCORING_VERSION:  # 跳过旧版本或坏文件 / Skip old-version or bad files
            continue  # 继续下一项 / Continue to next item
        if not has_real_comsol_export(config, candidate_id):  # 跳过非真实导出结果 / Skip non-real export results
            continue  # 继续下一项 / Continue to next item
        records.append({"candidate_id": candidate_id, "score_path": str(score_path), "best_mode": score.get("best_mode"), "final_score": safe_float(score.get("final_score")), "precision": safe_float(score.get("best_precision")), "recall": safe_float(score.get("best_recall")), "centerline_penalty": safe_float(score.get("best_centerline_penalty")), "frequency_hz": safe_float(score.get("frequency_hz"))})  # 添加标准记录 / Add normalized record
    return sorted(records, key=lambda item: item["final_score"], reverse=True)  # 按最终分数排序 / Sort by final score


def mean_value(records: list[dict], key: str) -> float:  # 计算均值 / Compute mean value
    if not records:  # 检查空列表 / Check empty list
        return 0.0  # 返回零 / Return zero
    return float(sum(safe_float(item.get(key)) for item in records) / len(records))  # 返回均值 / Return mean value


def determine_status(records: list[dict], config: dict) -> str:  # 判断当前搜索状态 / Determine current search status
    optimisation = config.get("optimisation", {})  # 读取优化配置 / Read optimisation config
    min_real = int(optimisation.get("feasibility_min_real_candidates", 4))  # 读取最少真实样本数 / Read minimum real sample count
    score_floor = float(optimisation.get("feasibility_score_floor", 0.08))  # 读取分数地板 / Read score floor
    precision_floor = float(optimisation.get("feasibility_precision_floor", 0.20))  # 读取精度地板 / Read precision floor
    if len(records) < min_real:  # 检查真实样本是否不足 / Check whether real samples are insufficient
        return "insufficient_real_samples"  # 返回样本不足 / Return insufficient samples
    best = records[0]  # 读取最佳记录 / Read best record
    if best["final_score"] < score_floor or best["precision"] < precision_floor:  # 检查是否低于工程门槛 / Check engineering thresholds
        return "physics_limited_thickness_only"  # 返回厚度单变量受限 / Return thickness-only limitation
    return "continue_thickness_search"  # 返回继续厚度搜索 / Return continue thickness search


def build_recommendations(status: str) -> list[str]:  # 构建建议列表 / Build recommendation list
    if status == "insufficient_real_samples":  # 检查样本不足状态 / Check insufficient-sample status
        return ["Run a few more real COMSOL candidates before declaring a physical bottleneck. / 先多跑几个真实 COMSOL 候选，再判断是否确实遇到物理瓶颈。"]  # 返回样本建议 / Return sample advice
    if status == "physics_limited_thickness_only":  # 检查厚度受限状态 / Check thickness-limited status
        return ["Expand the COMSOL parameter contract beyond thickness-only fields. / 将 COMSOL 参数合约从单一厚度场扩展出去。", "Add per-cell mass or density loading so the inverse search can reshape modal inertia. / 加入单元级质量或密度加载，让逆向搜索能改变模态惯性分布。", "Add local damping or loss-factor variables to suppress false centre-radiating modes. / 加入局部阻尼或损耗因子变量，压制中心放射类假阳性模态。", "Add optional topology variables such as holes or slots after the mass/damping bridge is stable. / 在质量和阻尼桥接稳定后，再加入孔洞或开槽等拓扑变量。"]  # 返回升级建议 / Return expansion advice
    return ["Continue thickness search, but keep scoring v5 strictness enabled. / 可以继续厚度搜索，但保持 v5 严格评分。"]  # 返回继续建议 / Return continue advice


def build_feasibility_report(config: dict) -> dict:  # 构建可行性报告 / Build feasibility report
    records = collect_score_records(config)  # 收集评分记录 / Collect score records
    status = determine_status(records, config)  # 判断状态 / Determine status
    best = records[0] if records else {}  # 读取最佳结果 / Read best result
    return {"scoring_version": SCORING_VERSION, "status": status, "current_contract_variables": CURRENT_CONTRACT_VARIABLES, "recommended_next_variables": NEXT_CONTRACT_VARIABLES, "real_candidate_count": len(records), "best_candidate": best.get("candidate_id", ""), "best_final_score": safe_float(best.get("final_score")), "best_precision": safe_float(best.get("precision")), "best_recall": safe_float(best.get("recall")), "mean_centerline_penalty": mean_value(records, "centerline_penalty"), "records": records[:20], "recommendations": build_recommendations(status)}  # 返回报告字典 / Return report dictionary


def save_feasibility_report(config: dict, report_path: str | Path = "reports/feasibility_report.json") -> dict:  # 保存可行性报告 / Save feasibility report
    report = build_feasibility_report(config)  # 构建报告 / Build report
    path = Path(report_path)  # 转换报告路径 / Convert report path
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建报告目录 / Create report directory
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")  # 写入报告 JSON / Write report JSON
    return {**report, "report_path": str(path)}  # 返回报告和路径 / Return report and path


def summarize_feasibility_report(report: dict) -> str:  # 汇总报告为命令行文本 / Summarize report for CLI
    lines = [f"Status: {report['status']} / 状态：{report['status']}", f"Real candidates: {report['real_candidate_count']} / 真实候选数：{report['real_candidate_count']}", f"Best: {report['best_candidate']} score={report['best_final_score']:.4f} precision={report['best_precision']:.4f} recall={report['best_recall']:.4f} / 最佳：{report['best_candidate']} 分数={report['best_final_score']:.4f} 精度={report['best_precision']:.4f} 召回={report['best_recall']:.4f}", f"Report: {report.get('report_path', '')} / 报告：{report.get('report_path', '')}"]  # 创建摘要行 / Create summary lines
    lines.extend(report.get("recommendations", []))  # 追加建议 / Append recommendations
    return "\n".join(lines)  # 返回多行文本 / Return multiline text
