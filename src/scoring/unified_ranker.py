from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
import json  # 导入 JSON 工具 / Import JSON utilities
import math  # 导入数学函数 / Import math helpers
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.scoring.amplitude_valley_score import score_frequency_response_csv  # 复用频域振幅谷线评分 / Reuse frequency-domain amplitude-valley scorer
from src.scoring.metrics import SCORING_VERSION  # 导入旧节点线评分版本 / Import legacy nodal-line scoring version


UNIFIED_SCORING_VERSION = "amplitude_valley_v1"  # 振幅谷线优先排序版本号 / Amplitude-valley primary ranking version
PRIMARY_METRIC_AMPLITUDE = "final_score_amplitude_valley"  # 振幅谷线主指标字段 / Amplitude-valley primary metric field
PRIMARY_METRIC_NODAL = "final_score_nodal"  # 节点线主指标字段 / Nodal-line primary metric field
AMPLITUDE_PREFERRED_KINDS = {"open_stroke_pattern", "filled_amplitude_target"}  # 偏向振幅模式的目标类别 / Target kinds preferring amplitude mode
AMPLITUDE_PREFERRED_VERDICTS = {"needs_amplitude_pattern", "requires_topology", "infeasible_as_nodal_set"}  # 偏向振幅模式的判定标签 / Verdict labels preferring amplitude mode


def _safe_float(value, default: float | None = None) -> float | None:  # 安全转浮点 / Safely convert to float
    if value is None:  # 处理空值 / Handle None
        return default  # 返回默认值 / Return default
    try:  # 尝试转换 / Try conversion
        result = float(value)  # 转浮点 / Convert to float
    except (TypeError, ValueError):  # 处理无效值 / Handle invalid value
        return default  # 返回默认值 / Return default
    if not math.isfinite(result):  # 处理 nan/inf / Handle non-finite values
        return default  # 返回默认值 / Return default
    return result  # 返回结果 / Return result


def load_target_verdict(config: dict, report_path: str | Path | None = None) -> dict | None:  # 读取目标可达性判定 / Load target realizability verdict
    candidates = [Path(report_path)] if report_path else []  # 拼接候选路径列表 / Build candidate path list
    candidates.append(Path("reports/target_realizability.json"))  # 默认输出路径 / Default output path
    candidates.append(Path("reports/target_realizability_ic.json"))  # IC 默认报告 / IC default report
    processed_dir = Path(config.get("paths", {}).get("processed_targets_dir", "data/processed_targets"))  # 处理后目录 / Processed targets directory
    candidates.append(processed_dir / "target_realizability.json")  # 处理后目录候选 / Processed-dir candidate
    for path in candidates:  # 遍历候选路径 / Iterate candidate paths
        if path.exists():  # 命中存在文件 / Hit existing file
            try:  # 尝试读取 JSON / Try reading JSON
                return json.loads(path.read_text(encoding="utf-8"))  # 返回报告字典 / Return report dict
            except (OSError, json.JSONDecodeError):  # 跳过坏文件 / Skip bad file
                continue  # 继续尝试 / Continue trying
    return None  # 未找到则返回空 / Return None when missing


def select_primary_metric(verdict: dict | None, manual_mode: str | None = None) -> str:  # 选择主排序指标 / Select primary ranking metric
    if manual_mode == "amplitude":  # 显式振幅模式 / Explicit amplitude mode
        return PRIMARY_METRIC_AMPLITUDE  # 返回振幅指标 / Return amplitude metric
    if manual_mode == "nodal":  # 显式节点线模式 / Explicit nodal mode
        return PRIMARY_METRIC_NODAL  # 返回节点线指标 / Return nodal metric
    if verdict is None:  # 无 W1 报告时回退节点线 / Fall back to nodal without W1 report
        return PRIMARY_METRIC_NODAL  # 返回节点线指标 / Return nodal metric
    kind = str(verdict.get("metrics", {}).get("target_kind", ""))  # 读取目标类别 / Read target kind
    verdict_label = str(verdict.get("verdict", ""))  # 读取判定标签 / Read verdict label
    if kind in AMPLITUDE_PREFERRED_KINDS or verdict_label in AMPLITUDE_PREFERRED_VERDICTS:  # 检查是否偏向振幅 / Check whether amplitude is preferred
        return PRIMARY_METRIC_AMPLITUDE  # 返回振幅指标 / Return amplitude metric
    return PRIMARY_METRIC_NODAL  # 默认节点线 / Default to nodal


def locate_forced_response_csv(exports_dir: Path, candidate_id: str) -> Path | None:  # 查找候选的频域响应 CSV / Locate forced-response CSV for a candidate
    base = exports_dir / candidate_id  # 构造候选导出目录 / Build candidate export directory
    nested = base / "forced_response" / "forced_response.csv"  # 嵌套目录候选 / Nested-folder candidate
    if nested.exists():  # 嵌套版本优先 / Prefer nested version
        return nested  # 返回嵌套路径 / Return nested path
    flat = base / "forced_response.csv"  # 平铺候选 / Flat candidate
    if flat.exists():  # 命中平铺版本 / Hit flat version
        return flat  # 返回平铺路径 / Return flat path
    return None  # 无可用 CSV / No CSV available


def amplitude_valley_for_candidate(exports_dir: Path, candidate_id: str, target_binary: np.ndarray, image_size: int = 256, epsilon: float = 0.080) -> dict | None:  # 计算候选振幅谷线评分 / Compute amplitude-valley score for a candidate
    csv_path = locate_forced_response_csv(exports_dir, candidate_id)  # 定位频域 CSV / Locate frequency-domain CSV
    if csv_path is None:  # 无 CSV 则跳过 / Skip when CSV missing
        return None  # 返回空结果 / Return no result
    try:  # 尝试评分 / Try scoring
        result = score_frequency_response_csv(csv_path, target_binary, int(image_size), float(epsilon))  # 调用现成评分函数 / Call existing scorer
    except Exception:  # 捕获任何评分错误 / Catch any scoring error
        return None  # 返回空结果 / Return no result
    return {"final_amplitude_valley_score": float(result.get("final_amplitude_valley_score", 0.0)), "amplitude_valley_iou": float(result.get("iou", 0.0)), "amplitude_valley_dice": float(result.get("dice", 0.0)), "amplitude_valley_layout": float(result.get("layout", 0.0)), "amplitude_valley_chamfer": float(result.get("chamfer", 0.0)), "amplitude_valley_contrast": float(result.get("valley_contrast", 0.0)), "amplitude_valley_extra_penalty": float(result.get("extra_valley_penalty", 0.0)), "amplitude_valley_target_mean": float(result.get("target_mean_amplitude", 0.0)), "amplitude_valley_side_mean": float(result.get("side_mean_amplitude", 0.0)), "amplitude_valley_csv": str(csv_path)}  # 返回扁平字段 / Return flat fields


def load_score_json(candidate_path: Path) -> dict | None:  # 读取节点线评分 JSON / Load nodal-line score JSON
    score_file = candidate_path / "score.json"  # 拼接评分路径 / Build score-file path
    if not score_file.exists():  # 检查文件存在 / Check file existence
        return None  # 返回空 / Return None
    try:  # 尝试读取 / Try reading
        return json.loads(score_file.read_text(encoding="utf-8"))  # 返回评分字典 / Return score dict
    except (OSError, json.JSONDecodeError):  # 处理坏文件 / Handle bad file
        return None  # 返回空 / Return None


def compose_unified_record(candidate_id: str, nodal_score: dict | None, amplitude_score: dict | None, primary_metric: str) -> dict | None:  # 组装统一记录 / Compose unified record
    if nodal_score is None and amplitude_score is None:  # 两侧都无数据 / Neither side has data
        return None  # 返回空 / Return None
    record: dict[str, object] = {"candidate_id": candidate_id, "scoring_version_legacy": (nodal_score or {}).get("scoring_version", SCORING_VERSION), "scoring_version_primary": UNIFIED_SCORING_VERSION, "primary_metric": primary_metric}  # 创建基础记录 / Build base record
    final_score_nodal = _safe_float((nodal_score or {}).get("final_score"))  # 读取节点线最终分 / Read nodal-line final score
    record["final_score_nodal"] = final_score_nodal  # 写入节点线最终分 / Store nodal-line final score
    record["best_mode"] = (nodal_score or {}).get("best_mode")  # 写入最佳模态 / Store best mode
    record["best_iou"] = _safe_float((nodal_score or {}).get("best_iou"))  # 写入最佳 IoU / Store best IoU
    record["best_dice"] = _safe_float((nodal_score or {}).get("best_dice"))  # 写入最佳 Dice / Store best Dice
    record["best_precision"] = _safe_float((nodal_score or {}).get("best_precision"))  # 写入精度 / Store precision
    record["best_recall"] = _safe_float((nodal_score or {}).get("best_recall"))  # 写入召回 / Store recall
    record["frequency_hz"] = _safe_float((nodal_score or {}).get("frequency_hz"))  # 写入模态频率 / Store modal frequency
    amplitude_data = amplitude_score or {}  # 备份振幅字段 / Backup amplitude fields
    record["final_score_amplitude_valley"] = _safe_float(amplitude_data.get("final_amplitude_valley_score"))  # 写入振幅谷线最终分 / Store amplitude-valley final score
    record["amplitude_valley_iou"] = _safe_float(amplitude_data.get("amplitude_valley_iou"))  # 写入振幅谷线 IoU / Store amplitude-valley IoU
    record["amplitude_valley_dice"] = _safe_float(amplitude_data.get("amplitude_valley_dice"))  # 写入振幅谷线 Dice / Store amplitude-valley Dice
    record["amplitude_valley_layout"] = _safe_float(amplitude_data.get("amplitude_valley_layout"))  # 写入振幅谷线 Layout / Store amplitude-valley layout
    record["amplitude_valley_contrast"] = _safe_float(amplitude_data.get("amplitude_valley_contrast"))  # 写入振幅谷线对比 / Store amplitude-valley contrast
    record["amplitude_valley_csv"] = amplitude_data.get("amplitude_valley_csv")  # 写入响应 CSV 路径 / Store response CSV path
    primary_value = record.get(primary_metric)  # 读取主指标 / Read primary metric value
    record["primary_score"] = primary_value if isinstance(primary_value, float) else _safe_float(primary_value)  # 写入主排序分 / Store primary ranking score
    return record  # 返回组装结果 / Return composed record


def score_candidate_unified(candidate_path: Path, exports_dir: Path, target_binary: np.ndarray, config: dict, primary_metric: str) -> dict | None:  # 评分单个候选 / Score one candidate
    candidate_id = candidate_path.name  # 读取候选编号 / Read candidate id
    export_path = exports_dir / candidate_id  # 拼接导出路径 / Build export path
    nodal_score = _maybe_run_nodal_score(candidate_path, export_path, target_binary, config)  # 尝试运行节点线评分 / Try running nodal-line scorer
    amplitude_score = amplitude_valley_for_candidate(exports_dir, candidate_id, target_binary, int(config.get("nodal_extraction", {}).get("image_size", 256)))  # 计算振幅谷线评分 / Compute amplitude-valley score
    return compose_unified_record(candidate_id, nodal_score, amplitude_score, primary_metric)  # 组装统一记录 / Compose unified record


def _maybe_run_nodal_score(candidate_path: Path, export_path: Path, target_binary: np.ndarray, config: dict) -> dict | None:  # 在条件允许时跑节点线评分 / Run nodal scoring when feasible
    cached = load_score_json(candidate_path)  # 优先读取缓存评分 / Prefer cached score
    if cached is not None and cached.get("scoring_version") == SCORING_VERSION:  # 命中当前版本缓存 / Hit current-version cache
        return cached  # 返回缓存评分 / Return cached score
    if not export_path.exists():  # 无导出目录则放弃 / Give up without export directory
        return cached  # 返回旧缓存或空 / Return stale cache or None
    mode_files = sorted(export_path.glob("mode_*.csv"))  # 查找模态文件 / Find mode files
    if not mode_files:  # 无模态文件无法跑 v5 / Cannot run v5 without modes
        return cached  # 返回旧缓存或空 / Return stale cache or None
    from src.scoring.score_candidate import score_candidate  # 延迟导入避免循环 / Lazy import to avoid cycle
    try:  # 尝试评分 / Try scoring
        return score_candidate(candidate_path, export_path, target_binary, config)  # 调用旧评分链路 / Call legacy scorer
    except Exception:  # 评分失败时不抛 / Do not raise on failure
        return cached  # 返回旧缓存或空 / Return stale cache or None


def rank_records(records: list[dict], primary_metric: str) -> list[dict]:  # 对统一记录排序 / Sort unified records
    secondary = PRIMARY_METRIC_NODAL if primary_metric == PRIMARY_METRIC_AMPLITUDE else PRIMARY_METRIC_AMPLITUDE  # 选择副指标 / Pick secondary metric
    def key(item: dict) -> tuple[float, float]:  # 创建排序键 / Build sort key
        primary = _safe_float(item.get("primary_score"), default=-1.0e9) or -1.0e9  # 主指标缺失视为最低 / Treat missing primary as lowest
        secondary_value = _safe_float(item.get(secondary), default=-1.0e9) or -1.0e9  # 次指标缺失视为最低 / Treat missing secondary as lowest
        return (primary, secondary_value)  # 返回元组键 / Return tuple key
    return sorted(records, key=key, reverse=True)  # 按主副指标降序 / Sort by primary then secondary descending


def write_unified_csv(records: list[dict], output_path: Path, primary_metric: str) -> None:  # 写入双列排行 CSV / Write dual-column ranking CSV
    fieldnames = ["candidate_id", "primary_metric", "primary_score", "final_score_nodal", "final_score_amplitude_valley", "best_mode", "best_iou", "best_dice", "best_precision", "best_recall", "frequency_hz", "amplitude_valley_iou", "amplitude_valley_dice", "amplitude_valley_layout", "amplitude_valley_contrast", "amplitude_valley_csv", "scoring_version_legacy", "scoring_version_primary"]  # 定义列字段 / Define CSV columns
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent dir
    with output_path.open("w", encoding="utf-8", newline="") as file_obj:  # 打开输出文件 / Open output file
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames, extrasaction="ignore")  # 创建 CSV 写入器 / Create CSV writer
        writer.writeheader()  # 写表头 / Write header
        for row in records:  # 遍历记录 / Iterate records
            cleaned = {key: _csv_cell(row.get(key)) for key in fieldnames}  # 清理单元格 / Sanitize cells
            cleaned["primary_metric"] = primary_metric  # 写入主指标名 / Write primary metric name
            writer.writerow(cleaned)  # 写入一行 / Write one row


def _csv_cell(value: object) -> object:  # 转换 CSV 单元格 / Convert CSV cell
    if value is None:  # 空值 / Missing value
        return ""  # 返回空字符串 / Return empty string
    if isinstance(value, float) and not math.isfinite(value):  # 非有限浮点 / Non-finite float
        return ""  # 返回空字符串 / Return empty string
    return value  # 返回原值 / Return original value


def write_leaderboard_json(records: list[dict], primary_metric: str, verdict: dict | None, output_path: Path, top_k: int = 20) -> dict:  # 写入排行榜 JSON / Write leaderboard JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent dir
    payload = {"scoring_version_primary": UNIFIED_SCORING_VERSION, "primary_metric": primary_metric, "verdict": verdict, "total_candidates": len(records), "ranked_candidates": records[: int(top_k)]}  # 构造写入字典 / Build payload dict
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")  # 写 JSON 文件 / Write JSON file
    return payload  # 返回写入内容 / Return written payload


def _json_default(value: object) -> object:  # 处理 JSON 不识别类型 / Handle unsupported JSON types
    if isinstance(value, (np.integer,)):  # numpy 整数 / numpy integer
        return int(value)  # 转 Python 整数 / Convert to Python int
    if isinstance(value, (np.floating,)):  # numpy 浮点 / numpy float
        return float(value) if math.isfinite(float(value)) else None  # 处理非有限 / Handle non-finite
    if isinstance(value, np.ndarray):  # numpy 数组 / numpy array
        return value.tolist()  # 转列表 / Convert to list
    if isinstance(value, float) and not math.isfinite(value):  # Python 非有限浮点 / Python non-finite float
        return None  # 写为 null / Encode as null
    raise TypeError(f"Object of type {type(value).__name__} not JSON serialisable. / 类型 {type(value).__name__} 无法序列化。")  # 抛出错误 / Raise error


def rank_candidates_unified(config: dict, target_binary: np.ndarray, candidate_filter: list[str] | None = None, manual_mode: str | None = None, verdict_report_path: str | Path | None = None) -> dict:  # 统一排序入口 / Unified ranking entry point
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选根目录 / Read candidate root directory
    exports_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取导出根目录 / Read export root directory
    verdict = load_target_verdict(config, verdict_report_path)  # 读取可达性判定 / Load realizability verdict
    primary_metric = select_primary_metric(verdict, manual_mode)  # 选择主指标 / Select primary metric
    candidate_paths = []  # 创建候选路径列表 / Create candidate path list
    if candidate_filter:  # 显式给定候选名 / Explicit candidate names
        for name in candidate_filter:  # 遍历候选名 / Iterate candidate names
            path = candidates_dir / name  # 拼接候选路径 / Build candidate path
            if path.exists():  # 存在则加入 / Add if exists
                candidate_paths.append(path)  # 加入列表 / Append path
    else:  # 默认遍历所有候选 / Default iterate all candidates
        candidate_paths = sorted(p for p in candidates_dir.glob("*") if p.is_dir() and (p / "H.csv").exists())  # 收集所有候选 / Collect all candidates
    records: list[dict] = []  # 创建记录列表 / Create record list
    for candidate_path in candidate_paths:  # 遍历候选 / Iterate candidates
        record = score_candidate_unified(candidate_path, exports_dir, target_binary, config, primary_metric)  # 评分候选 / Score candidate
        if record is None:  # 无可用数据 / Skip empty
            continue  # 跳过 / Skip
        records.append(record)  # 加入记录 / Append record
    ranked = rank_records(records, primary_metric)  # 排序 / Sort records
    csv_path = candidates_dir / "ranked_candidates_unified.csv"  # 排行 CSV 路径 / Ranking CSV path
    json_path = Path("reports") / "leaderboard.json"  # 排行 JSON 路径 / Ranking JSON path
    write_unified_csv(ranked, csv_path, primary_metric)  # 写排行 CSV / Write ranking CSV
    payload = write_leaderboard_json(ranked, primary_metric, verdict, json_path)  # 写排行 JSON / Write ranking JSON
    payload["ranked_candidates_csv"] = str(csv_path)  # 附加 CSV 路径 / Attach CSV path
    payload["leaderboard_json"] = str(json_path)  # 附加 JSON 路径 / Attach JSON path
    return payload  # 返回排行结果 / Return ranking payload


def summarize_leaderboard(payload: dict, top_k: int = 10) -> str:  # 生成排行摘要 / Generate ranking summary
    lines: list[str] = []  # 创建行列表 / Create line list
    lines.append(f"Primary metric: {payload['primary_metric']} / 主指标：{payload['primary_metric']}")  # 主指标行 / Primary metric line
    verdict = payload.get("verdict") or {}  # 读取判定 / Read verdict
    if verdict:  # 存在判定时打印 / Print when verdict exists
        kind = verdict.get("metrics", {}).get("target_kind", "unknown")  # 读取类别 / Read kind
        lines.append(f"Target verdict: {verdict.get('verdict', 'unknown')} (kind={kind}) / 目标判定：{verdict.get('verdict', 'unknown')}（类别={kind}）")  # 写判定行 / Write verdict line
    lines.append(f"Total candidates scored: {payload.get('total_candidates', 0)} / 已评分候选数：{payload.get('total_candidates', 0)}")  # 总候选行 / Total candidates line
    lines.append("Top {0} (primary | nodal | amplitude): / 前 {0} 名 (主指标 | 节点线 | 振幅谷)：".format(int(top_k)))  # 表头行 / Header line
    for idx, row in enumerate(payload.get("ranked_candidates", [])[: int(top_k)], start=1):  # 遍历前 K 名 / Iterate top-K
        primary = row.get("primary_score")  # 读取主指标 / Read primary
        nodal = row.get("final_score_nodal")  # 读取节点线 / Read nodal
        amplitude = row.get("final_score_amplitude_valley")  # 读取振幅 / Read amplitude
        primary_text = f"{primary:.4f}" if isinstance(primary, (int, float)) and primary is not None else "n/a"  # 主指标文本 / Primary text
        nodal_text = f"{nodal:.4f}" if isinstance(nodal, (int, float)) and nodal is not None else "n/a"  # 节点线文本 / Nodal text
        amplitude_text = f"{amplitude:.4f}" if isinstance(amplitude, (int, float)) and amplitude is not None else "n/a"  # 振幅文本 / Amplitude text
        lines.append(f"  {idx:2d}. {row.get('candidate_id', ''):60s}  primary={primary_text:>10s}  nodal={nodal_text:>9s}  amp={amplitude_text:>9s}")  # 一行排行 / One ranking line
    return "\n".join(lines)  # 返回多行文本 / Return multi-line text
