from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
import json  # 导入 JSON 工具 / Import JSON utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library


def read_csv_header(path: Path) -> list[str]:  # 读取 CSV 表头 / Read CSV header
    with path.open("r", encoding="utf-8") as file_obj:  # 打开 CSV 文件 / Open CSV file
        reader = csv.reader(file_obj)  # 创建 CSV 读取器 / Create CSV reader
        return next(reader, [])  # 返回第一行或空列表 / Return first row or empty list


def validate_required_columns(path: Path, required: set[str]) -> list[str]:  # 检查必要列 / Validate required columns
    header = set(read_csv_header(path))  # 读取并转换表头 / Read and convert header
    missing = sorted(required - header)  # 计算缺失列 / Compute missing columns
    return [f"{path.name} missing columns: {', '.join(missing)}"] if missing else []  # 返回问题列表 / Return issue list


def validate_frequency_file(path: Path) -> list[str]:  # 检查频率文件 / Validate frequency file
    issues = []  # 创建问题列表 / Create issue list
    if not path.exists():  # 检查文件是否存在 / Check file existence
        return ["frequencies.csv is missing"]  # 返回缺失问题 / Return missing issue
    issues.extend(validate_required_columns(path, {"mode", "frequency_hz"}))  # 检查必要列 / Check required columns
    if issues:  # 判断是否已有结构问题 / Check whether structural issues exist
        return issues  # 返回结构问题 / Return structural issues
    modes = []  # 创建模态编号列表 / Create mode-number list
    frequencies = []  # 创建频率列表 / Create frequency list
    with path.open("r", encoding="utf-8") as file_obj:  # 打开频率文件 / Open frequency file
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dictionary reader
        for row in reader:  # 遍历频率行 / Iterate frequency rows
            modes.append(int(row["mode"]))  # 读取模态编号 / Read mode number
            frequencies.append(float(row["frequency_hz"]))  # 读取频率值 / Read frequency value
    if not modes:  # 检查是否无数据 / Check whether data is empty
        issues.append("frequencies.csv has no data rows")  # 添加空数据问题 / Add empty-data issue
    if any(value <= 0.0 for value in frequencies):  # 检查非正频率 / Check non-positive frequencies
        issues.append("frequencies.csv contains non-positive frequencies")  # 添加频率问题 / Add frequency issue
    if len(set(modes)) != len(modes):  # 检查重复模态 / Check duplicate modes
        issues.append("frequencies.csv contains duplicate mode numbers")  # 添加重复问题 / Add duplicate issue
    return issues  # 返回问题列表 / Return issue list


def load_numeric_mode_columns(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:  # 读取模态数值列 / Load numeric mode columns
    xs = []  # 创建 x 列表 / Create x list
    ys = []  # 创建 y 列表 / Create y list
    ws = []  # 创建位移列表 / Create displacement list
    with path.open("r", encoding="utf-8") as file_obj:  # 打开模态文件 / Open mode file
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dictionary reader
        for row in reader:  # 遍历模态行 / Iterate mode rows
            xs.append(float(row["x"]))  # 读取 x 坐标 / Read x coordinate
            ys.append(float(row["y"]))  # 读取 y 坐标 / Read y coordinate
            ws.append(float(row["w"]))  # 读取位移值 / Read displacement value
    return np.asarray(xs), np.asarray(ys), np.asarray(ws)  # 返回三列数组 / Return three arrays


def validate_mode_file(path: Path, minimum_points: int = 100) -> list[str]:  # 检查单个模态文件 / Validate one mode file
    issues = []  # 创建问题列表 / Create issue list
    issues.extend(validate_required_columns(path, {"x", "y", "w"}))  # 检查必要列 / Check required columns
    if issues:  # 判断是否已有结构问题 / Check whether structural issues exist
        return issues  # 返回结构问题 / Return structural issues
    try:  # 尝试读取数值 / Try reading numeric data
        x, y, w = load_numeric_mode_columns(path)  # 读取数值列 / Load numeric columns
    except ValueError as exc:  # 捕获数值转换错误 / Catch numeric conversion error
        return [f"{path.name} contains non-numeric values: {exc}"]  # 返回数值问题 / Return numeric issue
    if len(w) < minimum_points:  # 检查采样点数量 / Check sample count
        issues.append(f"{path.name} has too few points: {len(w)}")  # 添加采样不足问题 / Add sparse-sample issue
    if not np.isfinite(x).all() or not np.isfinite(y).all() or not np.isfinite(w).all():  # 检查有限值 / Check finite values
        issues.append(f"{path.name} contains NaN or infinite values")  # 添加非有限值问题 / Add non-finite issue
    if len(w) and float(np.max(np.abs(w))) == 0.0:  # 检查零位移场 / Check zero displacement field
        issues.append(f"{path.name} has an all-zero displacement field")  # 添加零场问题 / Add zero-field issue
    if len(w) and float(np.std(w)) == 0.0:  # 检查常量位移场 / Check constant displacement field
        issues.append(f"{path.name} has a constant displacement field")  # 添加常量场问题 / Add constant-field issue
    return issues  # 返回问题列表 / Return issue list


def validate_candidate_export_dir(candidate_export_dir: str | Path, expected_modes: int) -> dict:  # 检查候选导出目录 / Validate candidate export directory
    path = Path(candidate_export_dir)  # 转换为路径对象 / Convert to path object
    issues = []  # 创建问题列表 / Create issue list
    if not path.exists():  # 检查目录是否存在 / Check directory existence
        return {"candidate_id": path.name, "status": "missing", "issues": [f"{path} is missing"]}  # 返回缺失结果 / Return missing result
    issues.extend(validate_frequency_file(path / "frequencies.csv"))  # 检查频率文件 / Validate frequency file
    mode_files = sorted(path.glob("mode_*.csv"))  # 查找模态文件 / Find mode files
    if len(mode_files) < expected_modes:  # 检查模态数量 / Check mode count
        issues.append(f"expected {expected_modes} mode files but found {len(mode_files)}")  # 添加数量问题 / Add count issue
    for mode_file in mode_files:  # 遍历模态文件 / Iterate mode files
        issues.extend(validate_mode_file(mode_file))  # 检查模态文件 / Validate mode file
    status = "ok" if not issues else "needs_review"  # 生成状态 / Build status
    return {"candidate_id": path.name, "status": status, "mode_file_count": len(mode_files), "issues": issues}  # 返回检查结果 / Return validation result


def validate_all_exports(config: dict) -> list[dict]:  # 检查所有 COMSOL 导出 / Validate all COMSOL exports
    exports_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取导出目录 / Read export directory
    expected_modes = int(config["simulation"]["num_modes"])  # 读取期望模态数量 / Read expected mode count
    candidate_dirs = sorted(path for path in exports_dir.glob("candidate_*") if path.is_dir())  # 查找候选目录 / Find candidate directories
    return [validate_candidate_export_dir(path, expected_modes) for path in candidate_dirs]  # 返回所有结果 / Return all results


def save_validation_report(results: list[dict], output_path: str | Path) -> Path:  # 保存验证报告 / Save validation report
    path = Path(output_path)  # 转换为路径对象 / Convert to path object
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    with path.open("w", encoding="utf-8") as file_obj:  # 打开输出文件 / Open output file
        json.dump(results, file_obj, indent=2, ensure_ascii=False)  # 写入 JSON 报告 / Write JSON report
    return path  # 返回报告路径 / Return report path
