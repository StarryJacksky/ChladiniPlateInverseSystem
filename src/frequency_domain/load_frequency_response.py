from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 读取工具 / Import CSV reading utilities
import re  # 导入正则表达式工具 / Import regular-expression utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.comsol.import_results import interpolate_to_grid  # 复用散点插值工具 / Reuse scattered interpolation helper
from src.scoring.amplitude_valley_score import normalise_amplitude_grid  # 复用振幅归一化 / Reuse amplitude normalisation


MAGNITUDE_COLUMNS = ("abs_uz", "uz_abs", "w_abs", "abs", "amplitude", "magnitude", "u_abs")  # 定义振幅列候选 / Define magnitude column candidates
REAL_COLUMNS = ("real_uz", "uz_real", "w_real", "real", "u_real", "real_w")  # 定义实部列候选 / Define real-part column candidates
IMAG_COLUMNS = ("imag_uz", "uz_imag", "w_imag", "imag", "u_imag", "imag_w")  # 定义虚部列候选 / Define imaginary-part column candidates
FREQUENCY_COLUMNS = ("frequency_hz", "freq_hz", "frequency", "freq")  # 定义频率列候选 / Define frequency column candidates


def normalise_key(text: str) -> str:  # 规范化 CSV 表头 / Normalize CSV header key
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())  # 替换非字母数字为下划线 / Replace non-alphanumeric chars with underscores
    return cleaned.strip("_")  # 去掉首尾下划线 / Trim surrounding underscores


def pick_column(fieldnames: list[str], candidates: tuple[str, ...]) -> str | None:  # 从表头候选中选择列 / Pick a column from header candidates
    field_map = {normalise_key(name): name for name in fieldnames}  # 构造规范表头映射 / Build normalized header map
    for candidate in candidates:  # 遍历候选列名 / Iterate candidate names
        key = normalise_key(candidate)  # 规范化候选列名 / Normalize candidate name
        if key in field_map:  # 检查是否命中 / Check whether candidate exists
            return field_map[key]  # 返回原始列名 / Return original column name
    return None  # 无匹配列则返回空 / Return missing when unmatched


def parse_frequency_from_name(path: Path) -> float | None:  # 从文件名解析频率 / Parse frequency from filename
    match = re.search(r"freq(?:uency)?[_-]?([0-9]+(?:p[0-9]+|\.[0-9]+)?)", path.stem.lower())  # 匹配 freq_301p1 / Match freq_301p1
    if not match:  # 检查是否未匹配 / Check no match
        return None  # 返回空频率 / Return missing frequency
    return float(match.group(1).replace("p", "."))  # 转换 p 为小数点 / Convert p into decimal point


def safe_float(value: object, context: str) -> float:  # 安全转换浮点 / Safely convert float
    try:  # 尝试转换 / Try conversion
        return float(value)  # 返回浮点值 / Return float value
    except (TypeError, ValueError) as exc:  # 捕获非法值 / Catch invalid value
        raise ValueError(f"Invalid numeric value in {context}: {value!r}. / {context} 中存在非法数值：{value!r}。") from exc  # 抛出清晰错误 / Raise clear error


def rows_to_amplitude(rows: list[dict[str, str]], fieldnames: list[str], source: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:  # 将 CSV 行转为散点振幅 / Convert CSV rows to scattered amplitude
    warnings: list[str] = []  # 创建警告列表 / Create warning list
    x_key = pick_column(fieldnames, ("x", "x_m", "x_mm"))  # 选择 x 列 / Select x column
    y_key = pick_column(fieldnames, ("y", "y_m", "y_mm"))  # 选择 y 列 / Select y column
    abs_key = pick_column(fieldnames, MAGNITUDE_COLUMNS)  # 选择振幅列 / Select magnitude column
    real_key = pick_column(fieldnames, REAL_COLUMNS)  # 选择实部列 / Select real column
    imag_key = pick_column(fieldnames, IMAG_COLUMNS)  # 选择虚部列 / Select imaginary column
    if not x_key or not y_key:  # 检查坐标列 / Check coordinate columns
        raise ValueError(f"{source} must contain x and y columns. / {source} 必须包含 x 和 y 列。")  # 抛出缺列错误 / Raise missing-column error
    if not abs_key and not (real_key and imag_key):  # 检查响应列 / Check response columns
        raise ValueError(f"{source} must contain abs_uz or real_uz+imag_uz columns. / {source} 必须包含 abs_uz 或 real_uz+imag_uz 列。")  # 抛出缺列错误 / Raise missing-column error
    xs: list[float] = []  # 创建 x 列表 / Create x list
    ys: list[float] = []  # 创建 y 列表 / Create y list
    amplitudes: list[float] = []  # 创建振幅列表 / Create amplitude list
    for index, row in enumerate(rows, start=1):  # 遍历 CSV 行 / Iterate CSV rows
        xs.append(safe_float(row.get(x_key), f"{source}:{index}:{x_key}"))  # 读取 x / Read x
        ys.append(safe_float(row.get(y_key), f"{source}:{index}:{y_key}"))  # 读取 y / Read y
        if abs_key:  # 如果已有振幅列 / If magnitude column exists
            amplitudes.append(abs(safe_float(row.get(abs_key), f"{source}:{index}:{abs_key}")))  # 读取振幅绝对值 / Read absolute magnitude
        else:  # 否则由实虚部计算 / Otherwise compute from real and imaginary parts
            real = safe_float(row.get(real_key), f"{source}:{index}:{real_key}")  # 读取实部 / Read real part
            imag = safe_float(row.get(imag_key), f"{source}:{index}:{imag_key}")  # 读取虚部 / Read imaginary part
            amplitudes.append(float(np.hypot(real, imag)))  # 计算复数振幅 / Compute complex magnitude
    if not amplitudes:  # 检查空文件 / Check empty file
        raise ValueError(f"{source} contains no response rows. / {source} 没有响应数据行。")  # 抛出空文件错误 / Raise empty-file error
    return np.asarray(xs), np.asarray(ys), np.asarray(amplitudes), warnings  # 返回散点振幅 / Return scattered amplitude


def grid_response(xs: np.ndarray, ys: np.ndarray, amplitudes: np.ndarray, grid_size: int) -> np.ndarray:  # 插值并归一化响应 / Interpolate and normalize response
    if not np.isfinite(amplitudes).all():  # 检查非有限值 / Check non-finite values
        raise ValueError("Amplitude data contains NaN or infinity. / 振幅数据包含 NaN 或无穷值。")  # 抛出非有限错误 / Raise non-finite error
    grid = interpolate_to_grid(xs, ys, amplitudes, int(grid_size))  # 插值到规则网格 / Interpolate to regular grid
    return normalise_amplitude_grid(grid)  # 归一化振幅图 / Normalize amplitude map


def load_single_frequency_file(path: Path, grid_size: int) -> tuple[float, np.ndarray, dict[str, object]]:  # 读取单频率 CSV 文件 / Load one per-frequency CSV file
    frequency = parse_frequency_from_name(path)  # 从文件名解析频率 / Parse frequency from filename
    if frequency is None:  # 检查频率是否缺失 / Check missing frequency
        raise ValueError(f"Cannot parse frequency from filename {path.name}. / 无法从文件名 {path.name} 解析频率。")  # 抛出频率错误 / Raise frequency error
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as file_obj:  # 打开 CSV 文件 / Open CSV file
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dict reader
        fieldnames = list(reader.fieldnames or [])  # 读取表头 / Read headers
        rows = list(reader)  # 读取所有行 / Read all rows
    xs, ys, amplitudes, warnings = rows_to_amplitude(rows, fieldnames, path)  # 转成散点振幅 / Convert rows to scattered amplitude
    response = grid_response(xs, ys, amplitudes, int(grid_size))  # 插值响应图 / Interpolate response map
    meta = {"source": str(path), "row_count": int(len(rows)), "warnings": warnings}  # 构造元数据 / Build metadata
    return float(frequency), response, meta  # 返回频率、响应和元数据 / Return frequency, response, and metadata


def load_combined_frequency_file(path: Path, grid_size: int) -> tuple[dict[float, np.ndarray], dict[str, object]]:  # 读取统一多频 CSV 文件 / Load combined multi-frequency CSV file
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as file_obj:  # 打开统一 CSV / Open combined CSV
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dict reader
        fieldnames = list(reader.fieldnames or [])  # 读取表头 / Read headers
        freq_key = pick_column(fieldnames, FREQUENCY_COLUMNS)  # 选择频率列 / Select frequency column
        if not freq_key:  # 检查频率列是否存在 / Check frequency-column existence
            raise ValueError(f"{path} must contain frequency_hz for combined format. / {path} 统一格式必须包含 frequency_hz。")  # 抛出缺频率列错误 / Raise missing frequency-column error
        grouped: dict[float, list[dict[str, str]]] = {}  # 创建按频率分组的行 / Create rows grouped by frequency
        for index, row in enumerate(reader, start=1):  # 遍历行 / Iterate rows
            frequency = safe_float(row.get(freq_key), f"{path}:{index}:{freq_key}")  # 读取频率 / Read frequency
            grouped.setdefault(float(frequency), []).append(row)  # 加入频率分组 / Add row to frequency group
    if not grouped:  # 检查是否没有数据 / Check no data
        raise ValueError(f"{path} contains no frequency response rows. / {path} 没有频域响应数据。")  # 抛出空数据错误 / Raise empty-data error
    responses: dict[float, np.ndarray] = {}  # 创建响应字典 / Create response dictionary
    warnings: list[str] = []  # 创建警告列表 / Create warning list
    for frequency, rows in sorted(grouped.items()):  # 遍历频率分组 / Iterate frequency groups
        xs, ys, amplitudes, group_warnings = rows_to_amplitude(rows, fieldnames, path)  # 转为散点振幅 / Convert to scattered amplitude
        responses[float(frequency)] = grid_response(xs, ys, amplitudes, int(grid_size))  # 插值并保存响应 / Interpolate and store response
        warnings.extend(group_warnings)  # 合并警告 / Merge warnings
    metadata = {"source": str(path), "frequency_count": int(len(responses)), "warnings": warnings}  # 构造元数据 / Build metadata
    return responses, metadata  # 返回响应和元数据 / Return responses and metadata


def candidate_csv_files(path: Path) -> list[Path]:  # 枚举单频率 CSV 文件 / Enumerate per-frequency CSV files
    files = []  # 创建文件列表 / Create file list
    for item in sorted(path.glob("*.csv")):  # 遍历目录 CSV / Iterate directory CSV files
        if item.name == "frequency_response.csv":  # 跳过统一文件 / Skip combined file
            continue  # 继续下一项 / Continue to next item
        if parse_frequency_from_name(item) is not None:  # 检查文件名是否含频率 / Check whether filename contains frequency
            files.append(item)  # 添加单频文件 / Add per-frequency file
    return files  # 返回单频文件列表 / Return file list


def load_frequency_response(export_dir_or_file: str | Path, grid_size: int = 256) -> tuple[dict[float, np.ndarray], dict[str, object]]:  # 读取 COMSOL 频域导出 / Load COMSOL frequency-domain export
    source = Path(export_dir_or_file)  # 转换输入路径 / Convert source path
    warnings: list[str] = []  # 创建警告列表 / Create warning list
    if not source.exists():  # 检查输入是否存在 / Check source existence
        raise FileNotFoundError(f"Frequency-domain export not found: {source}. / 未找到频域导出：{source}。")  # 抛出缺失错误 / Raise missing export error
    if source.is_file():  # 检查是否是统一文件 / Check file input
        responses, metadata = load_combined_frequency_file(source, int(grid_size))  # 读取统一文件 / Load combined file
        metadata.update({"detected_format": "combined_csv", "original_files": [str(source)], "grid_size": int(grid_size)})  # 更新元数据 / Update metadata
        return responses, metadata  # 返回统一文件结果 / Return combined-file result
    combined = source / "frequency_response.csv"  # 构造统一文件路径 / Build combined-file path
    if combined.exists():  # 优先读取统一文件 / Prefer combined file
        responses, metadata = load_combined_frequency_file(combined, int(grid_size))  # 读取统一文件 / Load combined file
        metadata.update({"detected_format": "combined_csv", "original_files": [str(combined)], "grid_size": int(grid_size)})  # 更新元数据 / Update metadata
        return responses, metadata  # 返回统一文件结果 / Return combined-file result
    files = candidate_csv_files(source)  # 查找单频文件 / Find per-frequency files
    if not files:  # 检查目录是否为空 / Check empty directory
        raise FileNotFoundError(f"No frequency CSV files found in {source}. Expected frequency_response.csv or freq_301p1.csv style files. / {source} 中没有频域 CSV，期望 frequency_response.csv 或 freq_301p1.csv。")  # 抛出清晰错误 / Raise clear error
    responses: dict[float, np.ndarray] = {}  # 创建响应字典 / Create response dictionary
    metas: list[dict[str, object]] = []  # 创建文件元数据列表 / Create file-metadata list
    for file_path in files:  # 遍历单频文件 / Iterate per-frequency files
        frequency, response, meta = load_single_frequency_file(file_path, int(grid_size))  # 读取单频文件 / Load per-frequency file
        if frequency in responses:  # 检查重复频率 / Check duplicate frequency
            warnings.append(f"Duplicate frequency {frequency:.6g} Hz; later file overwrote earlier data. / 频率 {frequency:.6g} Hz 重复，后读文件覆盖前者。")  # 记录重复频率 / Record duplicate frequency
        responses[float(frequency)] = response  # 保存响应 / Store response
        metas.append(meta)  # 保存文件元数据 / Store file metadata
    metadata = {"detected_format": "per_frequency_csv", "original_files": [str(path) for path in files], "grid_size": int(grid_size), "file_metadata": metas, "warnings": warnings}  # 构造目录元数据 / Build directory metadata
    return dict(sorted(responses.items())), metadata  # 返回按频率排序的响应 / Return responses sorted by frequency
