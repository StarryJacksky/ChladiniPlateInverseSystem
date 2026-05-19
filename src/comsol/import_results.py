from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library


def load_mode_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:  # 读取模态 CSV / Load mode CSV
    xs = []  # 创建 x 列表 / Create x list
    ys = []  # 创建 y 列表 / Create y list
    ws = []  # 创建位移列表 / Create displacement list
    with Path(path).open("r", encoding="utf-8") as file_obj:  # 打开 CSV 文件 / Open CSV file
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dictionary reader
        for row in reader:  # 遍历数据行 / Iterate data rows
            xs.append(float(row["x"]))  # 读取 x 坐标 / Read x coordinate
            ys.append(float(row["y"]))  # 读取 y 坐标 / Read y coordinate
            ws.append(float(row["w"]))  # 读取位移值 / Read displacement value
    return np.asarray(xs), np.asarray(ys), np.asarray(ws)  # 返回三列数组 / Return three arrays


def interpolate_to_grid(x: np.ndarray, y: np.ndarray, w: np.ndarray, grid_size: int = 256) -> np.ndarray:  # 插值到规则网格 / Interpolate to regular grid
    xi = np.rint((x - x.min()) / max(x.max() - x.min(), 1e-12) * (grid_size - 1)).astype(int)  # 映射 x 到像素索引 / Map x to pixel index
    yi = np.rint((y - y.min()) / max(y.max() - y.min(), 1e-12) * (grid_size - 1)).astype(int)  # 映射 y 到像素索引 / Map y to pixel index
    W = np.zeros((grid_size, grid_size), dtype=float)  # 创建位移网格 / Create displacement grid
    counts = np.zeros((grid_size, grid_size), dtype=float)  # 创建计数网格 / Create count grid
    np.add.at(W, (yi, xi), w)  # 累加同像素位移 / Accumulate displacement per pixel
    np.add.at(counts, (yi, xi), 1.0)  # 累加同像素计数 / Accumulate count per pixel
    filled = counts > 0.0  # 标记有数据像素 / Mark filled pixels
    W[filled] = W[filled] / counts[filled]  # 计算平均位移 / Compute mean displacement
    return W.astype(float)  # 返回浮点网格 / Return float grid


def normalize_mode(W: np.ndarray) -> np.ndarray:  # 归一化模态位移 / Normalise mode displacement
    max_abs = float(np.max(np.abs(W)))  # 计算最大绝对值 / Compute maximum absolute value
    if max_abs == 0.0:  # 检查零场 / Check zero field
        return W  # 直接返回零场 / Return zero field directly
    return W / max_abs  # 返回归一化场 / Return normalised field


def load_frequencies(path: str | Path) -> dict[int, float]:  # 读取频率表 / Load frequency table
    frequencies = {}  # 创建频率字典 / Create frequency dictionary
    with Path(path).open("r", encoding="utf-8") as file_obj:  # 打开频率文件 / Open frequency file
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dictionary reader
        for row in reader:  # 遍历频率行 / Iterate frequency rows
            frequencies[int(row["mode"])] = float(row["frequency_hz"])  # 写入模态频率 / Store mode frequency
    return frequencies  # 返回频率字典 / Return frequency dictionary


def find_mode_files(candidate_export_dir: str | Path) -> list[Path]:  # 查找模态文件 / Find mode files
    path = Path(candidate_export_dir)  # 转换为路径对象 / Convert to path object
    return sorted(path.glob("mode_*.csv"))  # 返回排序后的模态文件 / Return sorted mode files
