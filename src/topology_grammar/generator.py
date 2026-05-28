from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import math  # 导入数学工具 / Import math utilities

import numpy as np  # 导入数值计算库 / Import numerical library
from scipy.ndimage import label as scipy_label  # 导入连通域标记函数 / Import connected-component labelling helper

from src.subspace.mosaic_z import build_target_skeleton  # 导入目标骨架构造函数 / Import target skeleton builder
from src.topology_grammar.primitives import TopologyPrimitive  # 导入拓扑基元结构 / Import topology primitive structure


def pixel_coords_to_mm(coords: np.ndarray, shape: tuple[int, int], plate_length_mm: float) -> np.ndarray:  # 像素坐标转换到板面毫米坐标 / Convert pixel coordinates to plate millimetres
    rows, cols = shape  # 读取图像尺寸 / Read image shape
    y_mm = (coords[:, 0].astype(float) / max(rows - 1, 1) - 0.5) * float(plate_length_mm)  # 行坐标转 y 毫米 / Convert row coordinate to y millimetres
    x_mm = (coords[:, 1].astype(float) / max(cols - 1, 1) - 0.5) * float(plate_length_mm)  # 列坐标转 x 毫米 / Convert column coordinate to x millimetres
    return np.column_stack([x_mm, y_mm])  # 返回 x-y 毫米坐标 / Return x-y millimetre coordinates


def principal_component_segment(points_mm: np.ndarray) -> tuple[float, float, float, float]:  # 估计点云主轴线段 / Estimate principal-axis segment from points
    center = points_mm.mean(axis=0)  # 计算中心点 / Compute centre point
    centred = points_mm - center  # 去中心化 / Centre coordinates
    covariance = centred.T @ centred / max(len(points_mm), 1)  # 计算协方差矩阵 / Compute covariance matrix
    values, vectors = np.linalg.eigh(covariance)  # 求主方向 / Solve principal directions
    direction = vectors[:, int(np.argmax(values))]  # 读取最大方差方向 / Read maximum-variance direction
    projection = centred @ direction  # 投影到主轴 / Project onto principal axis
    length = float(max(np.percentile(projection, 95) - np.percentile(projection, 5), 4.0))  # 估计稳健长度 / Estimate robust length
    spread = float(np.sqrt(max(np.min(values), 0.0)))  # 估计横向扩展 / Estimate lateral spread
    angle = float(math.degrees(math.atan2(direction[1], direction[0])))  # 计算主轴角度 / Compute principal-axis angle
    width = float(np.clip(2.0 * spread + 2.0, 2.0, 9.0))  # 估计可制造宽度 / Estimate manufacturable width
    return float(center[0]), float(center[1]), length, width, angle  # 返回中心、长度、宽度、角度 / Return centre, length, width, angle


def component_primitives(target_binary: np.ndarray, primitive_type: str, plate_length_mm: float, max_primitives: int, min_pixels: int, depth_or_height_mm: float | str) -> list[TopologyPrimitive]:  # 从连通目标组件生成基元 / Generate primitives from connected target components
    skeleton = build_target_skeleton(target_binary.astype(bool))  # 构造目标骨架 / Build target skeleton
    labels, component_count = scipy_label(skeleton.astype(bool))  # 标记骨架连通域 / Label skeleton connected components
    components = []  # 创建组件列表 / Create component list
    for component_id in range(1, int(component_count) + 1):  # 遍历连通域编号 / Iterate component labels
        coords = np.argwhere(labels == component_id)  # 读取组件坐标 / Read component coordinates
        if len(coords) >= int(min_pixels):  # 忽略过小组件 / Ignore tiny components
            components.append(coords)  # 保存组件 / Store component
    components.sort(key=len, reverse=True)  # 按像素数降序排列 / Sort components by size descending
    primitives = []  # 创建基元列表 / Create primitive list
    for index, coords in enumerate(components[:max_primitives]):  # 遍历最大组件 / Iterate largest components
        points_mm = pixel_coords_to_mm(coords, target_binary.shape, plate_length_mm)  # 转换到板面毫米坐标 / Convert to plate millimetres
        x_mm, y_mm, length_mm, width_mm, angle_deg = principal_component_segment(points_mm)  # 估计主轴基元 / Estimate principal-axis primitive
        primitives.append(TopologyPrimitive(index + 1, primitive_type, x_mm, y_mm, float(np.clip(length_mm, 8.0, 95.0)), float(width_mm), angle_deg, depth_or_height_mm))  # 添加拓扑基元 / Add topology primitive
    return primitives  # 返回组件基元 / Return component primitives


def radial_mass_pad_primitives(target_binary: np.ndarray, plate_length_mm: float, max_primitives: int = 4) -> list[TopologyPrimitive]:  # 生成局部质量块基元 / Generate local mass-pad primitives
    foreground = np.argwhere(target_binary.astype(bool))  # 读取目标前景坐标 / Read target foreground coordinates
    if foreground.size == 0:  # 检查目标是否为空 / Check whether target is empty
        return []  # 空目标返回空 / Return empty list for empty target
    points_mm = pixel_coords_to_mm(foreground, target_binary.shape, plate_length_mm)  # 转换目标点到毫米 / Convert target points to millimetres
    angles = np.arctan2(points_mm[:, 1], points_mm[:, 0])  # 计算极角 / Compute polar angles
    bins = np.linspace(-np.pi, np.pi, max_primitives + 1)  # 构造角向分箱 / Build angular bins
    primitives = []  # 创建基元列表 / Create primitive list
    for index in range(max_primitives):  # 遍历角向分箱 / Iterate angular bins
        mask = (angles >= bins[index]) & (angles < bins[index + 1])  # 选择当前角向点 / Select points in current angular bin
        if not np.any(mask):  # 检查分箱是否为空 / Check whether bin is empty
            continue  # 跳过空分箱 / Skip empty bin
        local = points_mm[mask]  # 读取局部点 / Read local points
        radius = np.linalg.norm(local, axis=1)  # 计算半径 / Compute radii
        centre = local[int(np.argmax(radius))]  # 选择外侧代表点 / Select outer representative point
        primitives.append(TopologyPrimitive(len(primitives) + 1, "mass_pad", float(centre[0]), float(centre[1]), 10.0, 10.0, 0.0, 1.0))  # 添加质量块 / Add mass pad
    return primitives  # 返回质量块基元 / Return mass-pad primitives


def generate_target_topology_primitives(target_binary: np.ndarray, plate_length_mm: float = 150.0, family: str = "groove", max_primitives: int = 8) -> list[TopologyPrimitive]:  # 生成目标对齐拓扑基元 / Generate target-aligned topology primitives
    if family == "slot":  # 检查是否生成贯穿槽 / Check whether to generate slots
        return component_primitives(target_binary, "slot", plate_length_mm, max_primitives, 8, "through")  # 返回槽基元 / Return slot primitives
    if family == "rib":  # 检查是否生成加强肋 / Check whether to generate ribs
        return component_primitives(target_binary, "rib", plate_length_mm, max_primitives, 8, 1.0)  # 返回肋基元 / Return rib primitives
    if family == "mass_pad":  # 检查是否生成质量块 / Check whether to generate mass pads
        return radial_mass_pad_primitives(target_binary, plate_length_mm, max_primitives=max_primitives)  # 返回质量块基元 / Return mass-pad primitives
    return component_primitives(target_binary, "groove", plate_length_mm, max_primitives, 8, 0.5)  # 默认返回半深槽基元 / Return half-depth groove primitives by default
