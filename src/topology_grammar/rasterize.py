from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
import json  # 导入 JSON 工具 / Import JSON utilities
import shutil  # 导入目录复制工具 / Import directory copy helper
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.comsol.export_parameters import export_candidate_for_comsol  # 导入 COMSOL 参数导出函数 / Import COMSOL parameter exporter


def cell_centres_mm(grid_size: int, plate_length_mm: float) -> tuple[np.ndarray, np.ndarray]:  # 构造单元中心坐标 / Build cell-centre coordinates
    cell_size = float(plate_length_mm) / float(grid_size)  # 计算单元尺寸 / Compute cell size
    x_values = -0.5 * float(plate_length_mm) + cell_size * (np.arange(grid_size, dtype=float) + 0.5)  # 计算 x 中心 / Compute x centres
    y_values = 0.5 * float(plate_length_mm) - cell_size * (np.arange(grid_size, dtype=float) + 0.5)  # 计算 y 中心 / Compute y centres
    return np.meshgrid(x_values, y_values)  # 返回网格坐标 / Return coordinate grids


def read_topology_rows(path: str | Path) -> list[dict[str, str]]:  # 读取拓扑基元行 / Read topology primitive rows
    topology_path = Path(path)  # 转换为路径对象 / Convert to path object
    if not topology_path.exists():  # 检查文件是否存在 / Check file existence
        return []  # 缺失时返回空列表 / Return empty list when missing
    with topology_path.open("r", encoding="utf-8") as file_obj:  # 打开 CSV 文件 / Open CSV file
        return list(csv.DictReader(file_obj))  # 返回字典行 / Return dictionary rows


def primitive_float(row: dict[str, str], key: str, default: float) -> float:  # 安全读取浮点字段 / Safely read float field
    value = row.get(key, "")  # 读取原始字段 / Read raw field
    try:  # 尝试转换 / Try conversion
        return float(value)  # 返回浮点值 / Return float value
    except (TypeError, ValueError):  # 捕获缺失或非法值 / Catch missing or invalid value
        return float(default)  # 返回默认值 / Return default value


def grid_cell_size_mm(x_grid: np.ndarray, y_grid: np.ndarray) -> float:  # 估计栅格单元尺寸 / Estimate grid cell size
    x_unique = np.unique(np.round(x_grid[0, :], 9))  # 读取唯一 x 坐标 / Read unique x coordinates
    y_unique = np.unique(np.round(y_grid[:, 0], 9))  # 读取唯一 y 坐标 / Read unique y coordinates
    x_step = float(np.min(np.abs(np.diff(x_unique)))) if len(x_unique) > 1 else 0.0  # 估计 x 步长 / Estimate x step
    y_step = float(np.min(np.abs(np.diff(y_unique)))) if len(y_unique) > 1 else 0.0  # 估计 y 步长 / Estimate y step
    return max(x_step, y_step, 1.0)  # 返回保守单元尺寸 / Return conservative cell size


def rotated_rectangle_mask(x_grid: np.ndarray, y_grid: np.ndarray, row: dict[str, str]) -> np.ndarray:  # 生成旋转矩形掩膜 / Build rotated rectangle mask
    x0 = primitive_float(row, "x_mm", 0.0)  # 读取中心 x / Read centre x
    y0 = primitive_float(row, "y_mm", 0.0)  # 读取中心 y / Read centre y
    cell_size = grid_cell_size_mm(x_grid, y_grid)  # 估计单元尺寸 / Estimate cell size
    length = max(primitive_float(row, "length_mm", 1.0), 0.75 * cell_size)  # 读取并膨胀长度 / Read and inflate length
    width = max(primitive_float(row, "width_mm", 1.0), 0.75 * cell_size)  # 读取并膨胀宽度 / Read and inflate width
    theta = np.deg2rad(primitive_float(row, "angle_deg", 0.0))  # 读取角度弧度 / Read angle in radians
    dx = x_grid - x0  # 计算 x 偏移 / Compute x offset
    dy = y_grid - y0  # 计算 y 偏移 / Compute y offset
    local_x = np.cos(theta) * dx + np.sin(theta) * dy  # 旋转到局部 x / Rotate into local x
    local_y = -np.sin(theta) * dx + np.cos(theta) * dy  # 旋转到局部 y / Rotate into local y
    return (np.abs(local_x) <= 0.5 * length) & (np.abs(local_y) <= 0.5 * width)  # 返回矩形掩膜 / Return rectangle mask


def ellipse_mask(x_grid: np.ndarray, y_grid: np.ndarray, row: dict[str, str]) -> np.ndarray:  # 生成椭圆掩膜 / Build ellipse mask
    x0 = primitive_float(row, "x_mm", 0.0)  # 读取中心 x / Read centre x
    y0 = primitive_float(row, "y_mm", 0.0)  # 读取中心 y / Read centre y
    cell_size = grid_cell_size_mm(x_grid, y_grid)  # 估计单元尺寸 / Estimate cell size
    length = max(primitive_float(row, "length_mm", 1.0), cell_size)  # 读取并膨胀长轴 / Read and inflate major axis
    width = max(primitive_float(row, "width_mm", 1.0), cell_size)  # 读取并膨胀短轴 / Read and inflate minor axis
    theta = np.deg2rad(primitive_float(row, "angle_deg", 0.0))  # 读取旋转角度 / Read rotation angle
    dx = x_grid - x0  # 计算 x 偏移 / Compute x offset
    dy = y_grid - y0  # 计算 y 偏移 / Compute y offset
    local_x = np.cos(theta) * dx + np.sin(theta) * dy  # 旋转到局部 x / Rotate into local x
    local_y = -np.sin(theta) * dx + np.cos(theta) * dy  # 旋转到局部 y / Rotate into local y
    return (local_x / (0.5 * length)) ** 2 + (local_y / (0.5 * width)) ** 2 <= 1.0  # 返回椭圆掩膜 / Return ellipse mask


def ensure_nonempty_mask(mask: np.ndarray, x_grid: np.ndarray, y_grid: np.ndarray, row: dict[str, str]) -> np.ndarray:  # 确保基元至少命中一个单元 / Ensure primitive touches at least one cell
    if np.any(mask):  # 检查掩膜是否已有命中 / Check whether mask already has hits
        return mask  # 直接返回原掩膜 / Return original mask
    x0 = primitive_float(row, "x_mm", 0.0)  # 读取中心 x / Read centre x
    y0 = primitive_float(row, "y_mm", 0.0)  # 读取中心 y / Read centre y
    nearest_index = np.unravel_index(int(np.argmin((x_grid - x0) ** 2 + (y_grid - y0) ** 2)), mask.shape)  # 找到最近单元 / Find nearest cell
    fallback = mask.copy()  # 复制掩膜 / Copy mask
    fallback[nearest_index] = True  # 激活最近单元 / Activate nearest cell
    return fallback  # 返回兜底掩膜 / Return fallback mask


def smooth_mask(mask: np.ndarray, x_grid: np.ndarray, y_grid: np.ndarray, row: dict[str, str]) -> np.ndarray:  # 生成软化掩膜 / Build softened mask
    width = max(primitive_float(row, "width_mm", 1.0), 1.0)  # 读取宽度 / Read width
    if not np.any(mask):  # 检查硬掩膜是否为空 / Check whether hard mask is empty
        return mask.astype(float)  # 返回空浮点掩膜 / Return empty float mask
    x0 = primitive_float(row, "x_mm", 0.0)  # 读取中心 x / Read centre x
    y0 = primitive_float(row, "y_mm", 0.0)  # 读取中心 y / Read centre y
    distance = np.sqrt((x_grid - x0) ** 2 + (y_grid - y0) ** 2)  # 计算中心距离 / Compute centre distance
    local_scale = np.maximum(width, 1.0)  # 设置软化尺度 / Set smoothing scale
    soft = np.exp(-0.5 * (distance / max(local_scale, 1.0e-6)) ** 2)  # 构造高斯软权重 / Build Gaussian soft weight
    return np.maximum(mask.astype(float), 0.35 * soft * mask.astype(float))  # 返回软化权重 / Return softened weights


def initial_auxiliary_field(path: Path, shape: tuple[int, int], default_value: float) -> np.ndarray:  # 读取或创建辅助场 / Load or create auxiliary field
    if path.exists():  # 检查已有矩阵 / Check existing matrix
        return np.loadtxt(path, delimiter=",").astype(float)  # 读取已有矩阵 / Load existing matrix
    return np.full(shape, float(default_value), dtype=float)  # 返回默认矩阵 / Return default matrix


def apply_primitive_fields(H: np.ndarray, density_scale: np.ndarray, loss_factor: np.ndarray, row: dict[str, str], x_grid: np.ndarray, y_grid: np.ndarray, config: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, object]]:  # 应用单个拓扑基元 / Apply one topology primitive
    primitive_type = str(row.get("type", "groove")).strip().lower()  # 读取基元类型 / Read primitive type
    depth_or_height = primitive_float(row, "depth_or_height_mm", 0.5)  # 读取深度或高度 / Read depth or height
    h_min = float(config["thickness"].get("min_mm", 0.6))  # 读取厚度下限 / Read thickness lower bound
    h_max = float(config["thickness"].get("max_mm", 2.0))  # 读取厚度上限 / Read thickness upper bound
    density_min = float(config.get("design_variables", {}).get("density_scale_min", 0.65))  # 读取密度下限 / Read density lower bound
    density_max = float(config.get("design_variables", {}).get("density_scale_max", 1.55))  # 读取密度上限 / Read density upper bound
    loss_max = float(config.get("design_variables", {}).get("loss_factor_max", 0.16))  # 读取损耗上限 / Read loss upper bound
    mask = ellipse_mask(x_grid, y_grid, row) if primitive_type == "mass_pad" else rotated_rectangle_mask(x_grid, y_grid, row)  # 选择掩膜形状 / Select mask shape
    mask = ensure_nonempty_mask(mask, x_grid, y_grid, row)  # 确保粗网格上不丢失基元 / Ensure primitive is not lost on coarse grid
    weight = smooth_mask(mask, x_grid, y_grid, row)  # 生成软化权重 / Build softened weight
    changed_cells = int(np.count_nonzero(mask))  # 统计改变单元数 / Count changed cells
    if primitive_type == "slot":  # 处理贯穿槽近似 / Handle through-slot approximation
        H = np.where(mask, h_min, H)  # 将槽区域降到最小厚度 / Lower slot area to minimum thickness
        density_scale = np.where(mask, density_min, density_scale)  # 降低槽区域等效密度 / Lower equivalent density in slot area
        loss_factor = np.maximum(loss_factor, weight * min(loss_max, 0.08))  # 增加槽边阻尼 / Add slot-edge damping
    elif primitive_type == "groove":  # 处理半深槽 / Handle shallow groove
        H = np.clip(H - weight * abs(depth_or_height), h_min, h_max)  # 按深度降低厚度 / Reduce thickness by groove depth
        density_scale = np.clip(density_scale - 0.10 * weight, density_min, density_max)  # 轻微降低密度 / Slightly lower density
    elif primitive_type == "rib":  # 处理加强肋 / Handle rib
        H = np.clip(H + weight * abs(depth_or_height), h_min, h_max)  # 按高度增加厚度 / Increase thickness by rib height
        density_scale = np.clip(density_scale + 0.08 * weight, density_min, density_max)  # 轻微增加密度 / Slightly raise density
    elif primitive_type == "mass_pad":  # 处理局部质量块 / Handle local mass pad
        density_scale = np.clip(density_scale + 0.35 * weight * max(depth_or_height, 0.1), density_min, density_max)  # 增加局部等效质量 / Increase local equivalent mass
        loss_factor = np.maximum(loss_factor, weight * min(loss_max, 0.05))  # 增加局部损耗 / Increase local damping
    else:  # 处理未知类型 / Handle unknown type
        H = np.clip(H - 0.25 * weight, h_min, h_max)  # 默认按浅槽处理 / Default to shallow-groove behaviour
    record = {"id": row.get("id", ""), "type": primitive_type, "changed_cells": changed_cells, "depth_or_height_mm": depth_or_height}  # 构造应用记录 / Build application record
    return H, density_scale, loss_factor, record  # 返回更新场和记录 / Return updated fields and record


def materialize_topology_candidate(base_candidate_dir: str | Path, topology_csv: str | Path, output_candidate_dir: str | Path, config: dict, overwrite: bool = False) -> dict[str, object]:  # 将拓扑基元物化为真实场 / Materialise topology primitives into real fields
    base_dir = Path(base_candidate_dir)  # 转换基准目录 / Convert base directory
    out_dir = Path(output_candidate_dir)  # 转换输出目录 / Convert output directory
    if out_dir.exists() and overwrite:  # 检查是否覆盖 / Check overwrite request
        shutil.rmtree(out_dir)  # 删除旧输出目录 / Remove old output directory
    if not out_dir.exists():  # 检查输出目录是否缺失 / Check whether output directory is missing
        shutil.copytree(base_dir, out_dir)  # 复制基准候选 / Copy base candidate
    H = np.loadtxt(out_dir / "H.csv", delimiter=",").astype(float)  # 读取厚度矩阵 / Load thickness matrix
    density_scale = initial_auxiliary_field(out_dir / "density_scale.csv", H.shape, 1.0)  # 读取密度倍率场 / Load density-scale field
    loss_factor = initial_auxiliary_field(out_dir / "loss_factor.csv", H.shape, 0.0)  # 读取损耗因子场 / Load loss-factor field
    plate_length = float(config["project"].get("plate_length_mm", 150.0))  # 读取板长 / Read plate length
    x_grid, y_grid = cell_centres_mm(H.shape[0], plate_length)  # 构造单元坐标 / Build cell coordinates
    rows = read_topology_rows(topology_csv)  # 读取拓扑行 / Load topology rows
    records = []  # 创建应用记录 / Create application records
    for row in rows:  # 遍历拓扑基元 / Iterate topology primitives
        H, density_scale, loss_factor, record = apply_primitive_fields(H, density_scale, loss_factor, row, x_grid, y_grid, config)  # 应用基元 / Apply primitive
        records.append(record)  # 保存记录 / Store record
    np.savetxt(out_dir / "H.csv", np.round(H, 3), delimiter=",", fmt="%.3f")  # 保存厚度矩阵 / Save thickness matrix
    np.savetxt(out_dir / "density_scale.csv", np.round(density_scale, 4), delimiter=",", fmt="%.4f")  # 保存密度倍率 / Save density scale
    np.savetxt(out_dir / "loss_factor.csv", np.round(loss_factor, 5), delimiter=",", fmt="%.5f")  # 保存损耗因子 / Save loss factor
    shutil.copyfile(topology_csv, out_dir / "topology_primitives.csv")  # 保存拓扑合同副本 / Save topology contract copy
    export_candidate_for_comsol(out_dir, config.get("material"), config)  # 重新导出 COMSOL 参数 / Re-export COMSOL parameters
    metadata = {"candidate_id": out_dir.name, "source_candidate": base_dir.name, "materialized_topology_csv": str(topology_csv), "primitive_count": len(rows), "primitive_application": records, "operator_sculpting_mode": "rasterized_thickness_density_loss"}  # 构造元数据 / Build metadata
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")  # 写入元数据 / Write metadata
    return metadata  # 返回元数据 / Return metadata
