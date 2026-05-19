from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library


def count_connected_components(binary: np.ndarray) -> tuple[int, list[int]]:  # 统计连通区域 / Count connected components
    visited = np.zeros(binary.shape, dtype=bool)  # 创建访问记录 / Create visited map
    sizes = []  # 创建区域大小列表 / Create component-size list
    rows, cols = binary.shape  # 获取图像尺寸 / Get image shape
    for start_row in range(rows):  # 遍历起始行 / Iterate start rows
        for start_col in range(cols):  # 遍历起始列 / Iterate start columns
            if visited[start_row, start_col] or not binary[start_row, start_col]:  # 跳过已访问或背景像素 / Skip visited or background pixels
                continue  # 继续下一个像素 / Continue to next pixel
            stack = [(start_row, start_col)]  # 创建深度优先搜索栈 / Create DFS stack
            visited[start_row, start_col] = True  # 标记起点已访问 / Mark start as visited
            size = 0  # 初始化区域大小 / Initialise component size
            while stack:  # 搜索当前连通区域 / Search current component
                row, col = stack.pop()  # 取出一个像素 / Pop one pixel
                size += 1  # 增加区域大小 / Increase component size
                neighbours = [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]  # 创建四邻域 / Create four-neighbourhood
                for next_row, next_col in neighbours:  # 遍历邻居像素 / Iterate neighbour pixels
                    inside = 0 <= next_row < rows and 0 <= next_col < cols  # 判断是否在图像内 / Check whether inside image
                    if inside and binary[next_row, next_col] and not visited[next_row, next_col]:  # 判断是否可加入区域 / Check whether neighbour belongs to component
                        visited[next_row, next_col] = True  # 标记邻居已访问 / Mark neighbour as visited
                        stack.append((next_row, next_col))  # 将邻居加入栈 / Push neighbour to stack
            sizes.append(size)  # 记录区域大小 / Record component size
    return len(sizes), sizes  # 返回区域数量和大小 / Return component count and sizes


def compute_boundary_ratio(binary: np.ndarray) -> float:  # 计算边界复杂度比例 / Compute boundary-complexity ratio
    padded = np.pad(binary.astype(bool), 1, mode="constant", constant_values=False)  # 给图像加边框 / Pad image border
    center = padded[1:-1, 1:-1]  # 取中心区域 / Take center area
    neighbour_same = padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]  # 判断四邻域都为前景 / Check whether four neighbours are foreground
    boundary = center & ~neighbour_same  # 识别前景边界 / Detect foreground boundary
    foreground = max(int(center.sum()), 1)  # 计算前景像素数 / Count foreground pixels
    return float(boundary.sum() / foreground)  # 返回边界比例 / Return boundary ratio


def bounding_box(binary: np.ndarray) -> dict[str, int]:  # 计算前景包围盒 / Compute foreground bounding box
    points = np.argwhere(binary)  # 获取前景坐标 / Get foreground coordinates
    if points.size == 0:  # 检查是否没有前景 / Check whether foreground is empty
        return {"top": 0, "left": 0, "bottom": 0, "right": 0, "height": 0, "width": 0}  # 返回空包围盒 / Return empty bounding box
    top, left = points.min(axis=0)  # 计算左上角 / Compute top-left corner
    bottom, right = points.max(axis=0)  # 计算右下角 / Compute bottom-right corner
    return {"top": int(top), "left": int(left), "bottom": int(bottom), "right": int(right), "height": int(bottom - top + 1), "width": int(right - left + 1)}  # 返回包围盒 / Return bounding box


def estimate_target_suitability(binary: np.ndarray, grid_size: int, line_width_px: int) -> dict:  # 估计目标适配性 / Estimate target suitability
    component_count, component_sizes = count_connected_components(binary)  # 统计连通区域 / Count connected components
    foreground_ratio = float(binary.mean())  # 计算前景面积比例 / Compute foreground area ratio
    boundary_ratio = compute_boundary_ratio(binary)  # 计算边界复杂度 / Compute boundary complexity
    box = bounding_box(binary)  # 计算包围盒 / Compute bounding box
    min_feature_px = max(line_width_px, 1)  # 设置最小特征宽度 / Set minimum feature width
    pixels_per_cell = binary.shape[0] / grid_size  # 计算每个厚度单元像素数 / Compute pixels per thickness cell
    grid_resolution_warning = min_feature_px < pixels_per_cell * 0.35  # 判断特征是否过细 / Check whether features are too fine
    logo_complexity_warning = component_count > 2 or boundary_ratio > 0.45  # 判断图案是否偏复杂 / Check whether logo is complex
    area_warning = foreground_ratio < 0.03 or foreground_ratio > 0.45  # 判断面积比例是否异常 / Check whether area ratio is unusual
    recommendation = "use_as_late_stage_target" if grid_resolution_warning or logo_complexity_warning else "suitable_for_first_loop"  # 生成建议 / Build recommendation
    return {"foreground_ratio": foreground_ratio, "component_count": component_count, "component_sizes": component_sizes, "boundary_ratio": boundary_ratio, "bounding_box": box, "pixels_per_cell": pixels_per_cell, "grid_resolution_warning": grid_resolution_warning, "logo_complexity_warning": logo_complexity_warning, "area_warning": area_warning, "recommendation": recommendation}  # 返回分析结果 / Return analysis result


def save_target_analysis(binary: np.ndarray, output_dir: str | Path, grid_size: int, line_width_px: int) -> dict:  # 保存目标分析 / Save target analysis
    analysis = estimate_target_suitability(binary, grid_size, line_width_px)  # 计算目标分析 / Compute target analysis
    output_path = Path(output_dir) / "target_analysis.json"  # 构造输出路径 / Build output path
    with output_path.open("w", encoding="utf-8") as file_obj:  # 打开输出文件 / Open output file
        json.dump(analysis, file_obj, indent=2, ensure_ascii=False)  # 写入 JSON 分析 / Write JSON analysis
    return analysis  # 返回分析结果 / Return analysis result
