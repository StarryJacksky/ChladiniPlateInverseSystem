from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 读取工具 / Import CSV reading utilities
from dataclasses import dataclass  # 导入轻量数据类 / Import lightweight dataclass helper
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.comsol.import_results import interpolate_to_grid  # 复用 COMSOL 散点插值 / Reuse COMSOL scattered interpolation


DISPLACEMENT_COLUMNS = ("w", "uz", "u_z", "disp", "shell.disp", "displacement")  # 定义位移列候选 / Define displacement-column candidates


@dataclass  # 声明模态基底数据结构 / Declare modal-basis data structure
class ModalBasis:  # 保存 COMSOL 模态基底和诊断信息 / Store COMSOL modal basis and diagnostics
    Phi: np.ndarray  # 模态场数组，形状为 [mode, row, col] / Modal field array shaped [mode, row, col]
    freqs: np.ndarray  # 模态频率数组，单位 Hz / Modal frequency array in Hz
    mode_ids: list[int]  # 实际载入的模态编号 / Actually loaded mode identifiers
    metadata: dict[str, object]  # 载入过程元数据和警告 / Loading metadata and warnings


def _mode_number_from_path(path: Path) -> int:  # 从 mode_08.csv 这类文件名取模态编号 / Read mode number from mode_08.csv style filename
    return int(path.stem.split("_")[-1])  # 返回末尾数字 / Return trailing number


def _normalise_key(text: str) -> str:  # 规范化 CSV 表头 / Normalize CSV header key
    return text.strip().lower().replace(" ", "_")  # 小写并替换空格 / Lowercase and replace spaces


def _float_or_none(value: object) -> float | None:  # 安全读取浮点数 / Safely read a float
    try:  # 尝试转换 / Try conversion
        return float(value)  # 返回浮点值 / Return float value
    except (TypeError, ValueError):  # 捕获空值或非法文本 / Catch missing or invalid text
        return None  # 返回空值 / Return missing value


def load_frequency_map(candidate_dir: str | Path) -> tuple[dict[int, float], list[str]]:  # 读取 frequencies.csv / Load frequencies.csv
    path = Path(candidate_dir) / "frequencies.csv"  # 构造频率文件路径 / Build frequency-file path
    warnings: list[str] = []  # 创建警告列表 / Create warning list
    frequencies: dict[int, float] = {}  # 创建频率字典 / Create frequency dictionary
    if not path.exists():  # 检查频率文件是否存在 / Check whether frequency file exists
        return frequencies, [f"Missing frequencies.csv in {candidate_dir}. / {candidate_dir} 中缺少 frequencies.csv。"]  # 返回缺失警告 / Return missing warning
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as file_obj:  # 打开频率文件 / Open frequency file
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dictionary reader
        field_map = {_normalise_key(name): name for name in (reader.fieldnames or [])}  # 建立规范表头映射 / Build normalized header map
        mode_key = field_map.get("mode") or field_map.get("mode_id") or field_map.get("index")  # 选择模态列 / Select mode column
        freq_key = field_map.get("frequency_hz") or field_map.get("frequency") or field_map.get("freq_hz") or field_map.get("freq")  # 选择频率列 / Select frequency column
        for row_index, row in enumerate(reader, start=1):  # 遍历频率行 / Iterate frequency rows
            mode_value = _float_or_none(row.get(mode_key)) if mode_key else float(row_index)  # 读取模态编号 / Read mode identifier
            freq_value = _float_or_none(row.get(freq_key)) if freq_key else None  # 读取频率值 / Read frequency value
            if mode_value is None or freq_value is None:  # 检查当前行是否有效 / Check whether current row is valid
                warnings.append(f"Bad frequency row {row_index} in {path}. / {path} 第 {row_index} 行频率无效。")  # 记录坏行 / Record bad row
                continue  # 跳过坏行 / Skip bad row
            frequencies[int(mode_value)] = float(freq_value)  # 写入频率字典 / Store frequency value
    return frequencies, warnings  # 返回频率和警告 / Return frequencies and warnings


def _select_displacement_column(fieldnames: list[str]) -> str | None:  # 选择位移列 / Select displacement column
    normalised = {_normalise_key(name): name for name in fieldnames}  # 建立规范表头映射 / Build normalized header map
    for candidate in DISPLACEMENT_COLUMNS:  # 遍历位移列候选 / Iterate displacement candidates
        key = _normalise_key(candidate)  # 规范化候选名称 / Normalize candidate name
        if key in normalised:  # 检查是否命中 / Check candidate match
            return normalised[key]  # 返回原始列名 / Return original column name
    numeric_tail = fieldnames[-1] if fieldnames else None  # 回退到最后一列 / Fall back to last column
    return numeric_tail  # 返回回退列名 / Return fallback column


def _load_scattered_mode(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:  # 读取散点模态 CSV / Load scattered modal CSV
    xs: list[float] = []  # 创建 x 坐标列表 / Create x-coordinate list
    ys: list[float] = []  # 创建 y 坐标列表 / Create y-coordinate list
    ws: list[float] = []  # 创建位移列表 / Create displacement list
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as file_obj:  # 打开模态文件 / Open modal file
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dictionary reader
        fieldnames = list(reader.fieldnames or [])  # 读取表头 / Read headers
        field_map = {_normalise_key(name): name for name in fieldnames}  # 建立规范表头映射 / Build normalized header map
        x_key = field_map.get("x") or field_map.get("x_m") or field_map.get("x_mm")  # 选择 x 列 / Select x column
        y_key = field_map.get("y") or field_map.get("y_m") or field_map.get("y_mm")  # 选择 y 列 / Select y column
        w_key = _select_displacement_column(fieldnames)  # 选择位移列 / Select displacement column
        if not x_key or not y_key or not w_key:  # 检查必要列 / Check required columns
            raise ValueError(f"{path} must contain x, y, and displacement columns. / {path} 必须包含 x、y 和位移列。")  # 抛出清晰错误 / Raise clear error
        for row in reader:  # 遍历模态数据行 / Iterate modal rows
            x_value = _float_or_none(row.get(x_key))  # 读取 x / Read x
            y_value = _float_or_none(row.get(y_key))  # 读取 y / Read y
            w_value = _float_or_none(row.get(w_key))  # 读取位移 / Read displacement
            if x_value is None or y_value is None or w_value is None:  # 检查坏数据点 / Check bad sample
                continue  # 跳过坏点 / Skip bad sample
            xs.append(x_value)  # 保存 x / Store x
            ys.append(y_value)  # 保存 y / Store y
            ws.append(w_value)  # 保存位移 / Store displacement
    if not ws:  # 检查是否没有有效采样 / Check whether no valid samples exist
        raise ValueError(f"{path} contains no valid modal samples. / {path} 没有有效模态采样。")  # 抛出空数据错误 / Raise empty-data error
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float), np.asarray(ws, dtype=float)  # 返回散点数组 / Return scattered arrays


def _grid_like_mode(path: Path, grid_size: int) -> np.ndarray | None:  # 尝试读取规则网格模态 / Try loading a grid-like modal file
    try:  # 尝试按纯数值矩阵读取 / Try reading as numeric matrix
        data = np.genfromtxt(path, delimiter=",", dtype=float)  # 读取 CSV 数值矩阵 / Read CSV numeric matrix
    except Exception:  # 捕获读取失败 / Catch read failure
        return None  # 返回不可用 / Return unavailable
    if data.ndim != 2 or data.size == 0 or np.isnan(data).all():  # 检查矩阵有效性 / Check matrix validity
        return None  # 返回不可用 / Return unavailable
    if data.shape == (grid_size, grid_size):  # 检查尺寸是否匹配 / Check exact grid shape
        return data.astype(float)  # 返回原矩阵 / Return original matrix
    row_index = np.rint(np.linspace(0, data.shape[0] - 1, grid_size)).astype(int)  # 构造行采样索引 / Build row sampling indices
    col_index = np.rint(np.linspace(0, data.shape[1] - 1, grid_size)).astype(int)  # 构造列采样索引 / Build column sampling indices
    return data[np.ix_(row_index, col_index)].astype(float)  # 最近邻缩放到目标尺寸 / Resize to target grid by nearest neighbour


def _normalise_mode(field: np.ndarray, path: Path, warnings: list[str]) -> np.ndarray | None:  # 归一化单个模态场 / Normalize one modal field
    if not np.isfinite(field).all():  # 检查 NaN 或无穷值 / Check NaN or infinity
        warnings.append(f"{path.name} contains non-finite values; they were replaced by zero. / {path.name} 含非有限值，已置零。")  # 记录非有限警告 / Record non-finite warning
        field = np.nan_to_num(field, nan=0.0, posinf=0.0, neginf=0.0)  # 修复非有限值 / Repair non-finite values
    max_abs = float(np.max(np.abs(field))) if field.size else 0.0  # 计算最大绝对值 / Compute maximum absolute value
    if max_abs <= 1.0e-18:  # 检查是否全零 / Check whether all-zero
        warnings.append(f"{path.name} is all-zero and was skipped. / {path.name} 全零，已跳过。")  # 记录全零警告 / Record all-zero warning
        return None  # 跳过全零场 / Skip all-zero field
    return (field / max_abs).astype(np.float32)  # 返回归一化场 / Return normalized field


def load_modal_basis(candidate_dir: str | Path, mode_start: int = 8, mode_end: int = 40, grid_size: int = 256) -> ModalBasis:  # 载入 COMSOL 模态基底 / Load COMSOL modal basis
    candidate_path = Path(candidate_dir)  # 转换候选目录 / Convert candidate directory
    warnings: list[str] = []  # 创建警告列表 / Create warning list
    frequency_map, frequency_warnings = load_frequency_map(candidate_path)  # 读取频率表 / Load frequency table
    warnings.extend(frequency_warnings)  # 合并频率警告 / Merge frequency warnings
    fields: list[np.ndarray] = []  # 创建模态场列表 / Create modal-field list
    freqs: list[float] = []  # 创建频率列表 / Create frequency list
    mode_ids: list[int] = []  # 创建模态编号列表 / Create mode-id list
    for mode_id in range(int(mode_start), int(mode_end) + 1):  # 遍历请求模态 / Iterate requested modes
        mode_file = candidate_path / f"mode_{mode_id:02d}.csv"  # 构造模态文件路径 / Build modal-file path
        if not mode_file.exists():  # 检查模态文件是否存在 / Check modal-file existence
            warnings.append(f"Missing {mode_file.name}. / 缺少 {mode_file.name}。")  # 记录缺文件 / Record missing file
            continue  # 继续下一个模态 / Continue to next mode
        try:  # 尝试读取散点 CSV / Try loading scattered CSV
            x, y, w = _load_scattered_mode(mode_file)  # 读取散点模态 / Load scattered mode
            field = interpolate_to_grid(x, y, w, int(grid_size))  # 插值到规则网格 / Interpolate onto regular grid
        except Exception as exc:  # 捕获散点读取失败 / Catch scattered loading failure
            field = _grid_like_mode(mode_file, int(grid_size))  # 尝试规则网格回退 / Try grid-like fallback
            if field is None:  # 检查回退是否失败 / Check fallback failure
                warnings.append(f"Could not load {mode_file.name}: {exc}. / 无法读取 {mode_file.name}：{exc}。")  # 记录读取失败 / Record load failure
                continue  # 跳过该模态 / Skip this mode
        normalised = _normalise_mode(field, mode_file, warnings)  # 归一化模态场 / Normalize modal field
        if normalised is None:  # 检查是否被跳过 / Check whether skipped
            continue  # 跳过无效模态 / Skip invalid mode
        if mode_id not in frequency_map:  # 检查频率是否存在 / Check frequency existence
            warnings.append(f"Missing frequency for mode {mode_id}. / 缺少模态 {mode_id} 的频率。")  # 记录缺频率 / Record missing frequency
            continue  # 跳过缺频率模态 / Skip mode without frequency
        fields.append(normalised)  # 保存模态场 / Store modal field
        freqs.append(float(frequency_map[mode_id]))  # 保存频率 / Store frequency
        mode_ids.append(int(mode_id))  # 保存模态编号 / Store mode id
    if not fields:  # 检查是否没有可用模态 / Check whether no valid modes loaded
        raise FileNotFoundError(f"No valid modes loaded from {candidate_path}. / 未能从 {candidate_path} 读取有效模态。")  # 抛出错误 / Raise error
    Phi = np.stack(fields, axis=0).astype(np.float32)  # 组装 [mode,row,col] 数组 / Assemble [mode,row,col] array
    metadata = {"candidate_dir": str(candidate_path), "grid_size": int(grid_size), "requested_mode_start": int(mode_start), "requested_mode_end": int(mode_end), "loaded_mode_count": int(len(mode_ids)), "warnings": warnings}  # 构造元数据 / Build metadata
    return ModalBasis(Phi=Phi, freqs=np.asarray(freqs, dtype=np.float32), mode_ids=mode_ids, metadata=metadata)  # 返回模态基底 / Return modal basis
