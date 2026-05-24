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


def interpolate_to_grid(x: np.ndarray, y: np.ndarray, w: np.ndarray, grid_size: int = 256, neighbours: int = 8, chunk_size: int = 2048) -> np.ndarray:  # 插值到规则网格 / Interpolate to regular grid
    if len(w) == 0:  # 检查是否无数据 / Check whether data is empty
        return np.zeros((grid_size, grid_size), dtype=float)  # 返回空网格 / Return empty grid
    xi = np.linspace(float(x.min()), float(x.max()), grid_size)  # 生成规则 x 坐标 / Build regular x coordinates
    yi = np.linspace(float(y.min()), float(y.max()), grid_size)  # 生成规则 y 坐标 / Build regular y coordinates
    grid_x, grid_y = np.meshgrid(xi, yi)  # 生成规则网格坐标 / Build regular grid coordinates
    points = np.column_stack([x.astype(float), y.astype(float)])  # 合并采样点坐标 / Combine sample coordinates
    queries = np.column_stack([grid_x.ravel(), grid_y.ravel()])  # 合并查询点坐标 / Combine query coordinates
    k = min(max(int(neighbours), 1), len(w))  # 限制近邻数量 / Clamp neighbour count
    values = np.empty(len(queries), dtype=float)  # 创建插值结果数组 / Create interpolated value array
    sample_values = w.astype(float)  # 转换采样值 / Convert sample values
    for start in range(0, len(queries), chunk_size):  # 分块遍历查询点 / Iterate query points in chunks
        stop = min(start + chunk_size, len(queries))  # 计算分块结束位置 / Compute chunk end index
        chunk = queries[start:stop]  # 取出当前查询分块 / Select query chunk
        diff = chunk[:, None, :] - points[None, :, :]  # 计算查询点到采样点差值 / Compute query-to-sample differences
        dist2 = np.sum(diff * diff, axis=2)  # 计算平方距离 / Compute squared distances
        nearest = np.argpartition(dist2, k - 1, axis=1)[:, :k]  # 找到近邻索引 / Find nearest-neighbour indices
        nearest_dist2 = np.take_along_axis(dist2, nearest, axis=1)  # 取出近邻距离 / Gather nearest-neighbour distances
        nearest_values = sample_values[nearest]  # 取出近邻位移 / Gather nearest-neighbour values
        exact = nearest_dist2[:, 0] <= 1e-24  # 标记完全重合点 / Mark exact coordinate matches
        weights = 1.0 / np.maximum(nearest_dist2, 1e-24)  # 计算反距离权重 / Compute inverse-distance weights
        interpolated = np.sum(weights * nearest_values, axis=1) / np.sum(weights, axis=1)  # 计算加权位移 / Compute weighted displacement
        if np.any(exact):  # 检查是否存在重合点 / Check whether exact matches exist
            interpolated[exact] = nearest_values[exact, 0]  # 重合点直接使用采样值 / Use sample value for exact matches
        values[start:stop] = interpolated  # 写入结果分块 / Store result chunk
    return values.reshape((grid_size, grid_size)).astype(float)  # 返回浮点网格 / Return float grid


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
