from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
import math  # 导入数学函数 / Import math functions
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
from scipy.ndimage import distance_transform_edt  # 导入距离变换 / Import distance transform
from scipy.ndimage import label as scipy_label  # 导入连通分量标记 / Import connected-component labelling

from src.target.preprocess_target import skeletonize_binary  # 复用项目内骨架化 / Reuse in-repo skeletonisation


DEFAULT_REALIZABILITY_THRESHOLDS = {"infeasible_courant_min_mode_index": 60, "infeasible_stroke_min_gap_mm": 6.0, "requires_topology_courant_min_mode_index": 30, "requires_topology_stroke_min_gap_mm": 7.0, "requires_topology_d4_symmetry_mismatch": 0.55, "borderline_courant_min_mode_index": 18, "borderline_stroke_min_gap_mm": 10.0, "borderline_d4_symmetry_mismatch": 0.35, "filled_target_foreground_ratio": 0.18, "thin_stroke_feature_mm": 8.0, "clamp_buffer_mm": 4.0, "max_endpoints_easy": 0}  # 默认判定阈值：依次为不可达 Courant 上限、不可达笔画间隙、拓扑级 Courant 阈值、拓扑级笔画间隙、拓扑级 D4 偏差、临界 Courant、临界笔画间隙、临界 D4 偏差、填充目标前景比例、薄线条特征宽度、夹持缓冲、easy 端点上限 / Default verdict thresholds: infeasible Courant upper bound, infeasible stroke gap, topology Courant threshold, topology stroke gap, topology D4 mismatch, borderline Courant, borderline stroke gap, borderline D4 mismatch, filled-target foreground ratio, thin-stroke feature width, clamp buffer, easy endpoint limit


def count_connected_components(binary: np.ndarray, structure: np.ndarray | None = None) -> tuple[int, np.ndarray]:  # 统计连通分量 / Count connected components
    labelled, count = scipy_label(binary.astype(bool), structure=structure)  # 调用 scipy 连通分量 / Call scipy connected components
    return int(count), labelled.astype(np.int32)  # 返回数量和标签图 / Return count and label map


def count_background_holes(foreground: np.ndarray) -> int:  # 统计前景内部背景洞数 / Count background holes inside foreground
    inverted = ~foreground.astype(bool)  # 反转得到背景 / Invert to background
    labelled, count = scipy_label(inverted, structure=np.ones((3, 3), dtype=bool))  # 用 8 邻接标记背景 / Label background with 8-connectivity
    if count == 0:  # 检查是否无背景 / Check whether background is missing
        return 0  # 无背景则无洞 / Return zero when no background
    touches_border = set()  # 创建边界标签集合 / Create boundary-label set
    touches_border.update(labelled[0, :].tolist())  # 收集第一行标签 / Collect first-row labels
    touches_border.update(labelled[-1, :].tolist())  # 收集最后一行标签 / Collect last-row labels
    touches_border.update(labelled[:, 0].tolist())  # 收集第一列标签 / Collect first-column labels
    touches_border.update(labelled[:, -1].tolist())  # 收集最后一列标签 / Collect last-column labels
    touches_border.discard(0)  # 移除空标签 / Remove empty label
    interior_count = count - len(touches_border)  # 计算内部背景区域数 / Compute interior background regions
    return int(max(0, interior_count))  # 返回非负洞数 / Return non-negative hole count


def count_skeleton_endpoints(binary: np.ndarray, boundary_margin_px: int = 5) -> int:  # 统计骨架端点数 / Count skeleton endpoints
    skeleton = skeletonize_binary(binary.astype(bool))  # 细化为骨架 / Thin to skeleton
    if not skeleton.any():  # 检查是否空骨架 / Check whether skeleton is empty
        return 0  # 空骨架返回 0 / Return zero for empty skeleton
    padded = np.pad(skeleton, 1, mode="constant", constant_values=False)  # 在边界外补零 / Pad with background
    rows, cols = skeleton.shape  # 读取尺寸 / Read shape
    margin = max(0, int(boundary_margin_px))  # 计算边界余量 / Compute boundary margin
    endpoint_count = 0  # 初始化端点计数 / Initialise endpoint counter
    offsets = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]  # 定义八邻域偏移 / Define eight-neighbour offsets
    for row in range(rows):  # 遍历每一行 / Iterate every row
        for col in range(cols):  # 遍历每一列 / Iterate every column
            if not skeleton[row, col]:  # 跳过背景像素 / Skip background pixels
                continue  # 继续下一个像素 / Continue to next pixel
            if row < margin or row >= rows - margin or col < margin or col >= cols - margin:  # 排除靠近板边的终止点 / Exclude termini near the plate boundary
                continue  # 边界终止视为延伸到板边 / Treat boundary termini as extending to plate edge
            neighbour_count = sum(1 for dr, dc in offsets if padded[row + 1 + dr, col + 1 + dc])  # 统计八邻域前景 / Count eight-neighbour foreground
            if neighbour_count <= 1:  # 端点只有 0 或 1 个邻居 / Endpoint has at most one neighbour
                endpoint_count += 1  # 端点计数加一 / Increment endpoint counter
    return int(endpoint_count)  # 返回端点数 / Return endpoint count


def stroke_min_feature_mm(binary: np.ndarray, mm_per_pixel: float) -> float:  # 估算最小笔画宽度 / Estimate minimum stroke width
    if not binary.any():  # 检查是否前景为空 / Check whether foreground is empty
        return 0.0  # 空前景返回 0 / Return zero for empty foreground
    distance = distance_transform_edt(binary.astype(bool))  # 计算前景内部到背景距离 / Distance from foreground interior to background
    interior_values = distance[binary]  # 取前景内距离值 / Take interior distance values
    if interior_values.size == 0:  # 检查是否无前景 / Check missing foreground
        return 0.0  # 返回 0 / Return zero
    percentile = float(np.percentile(interior_values, 25))  # 取下四分位避免极值 / Use lower quartile to avoid outliers
    return float(percentile * 2.0 * mm_per_pixel)  # 转换成毫米宽度 / Convert to millimetre width


def stroke_min_gap_mm(label_map: np.ndarray, component_count: int, mm_per_pixel: float) -> float:  # 估算分量间最小间隙 / Estimate minimum gap between components
    if component_count <= 1:  # 检查是否单一分量 / Check single-component case
        return float("inf")  # 单分量无间隙概念 / Single component implies infinite gap
    min_gap_pixels = float("inf")  # 初始化最小间隙 / Initialise minimum gap
    for index in range(1, component_count + 1):  # 遍历每个分量 / Iterate each component
        component_mask = label_map == index  # 取出当前分量 / Take current component
        distance = distance_transform_edt(~component_mask)  # 计算到当前分量外部距离 / Distance from outside to current component
        for other_index in range(index + 1, component_count + 1):  # 遍历更高编号分量 / Iterate higher-index components
            other_mask = label_map == other_index  # 取出另一个分量 / Take other component
            if not other_mask.any():  # 检查空分量 / Check empty component
                continue  # 跳过 / Skip
            pair_distance = float(distance[other_mask].min())  # 读取对外最近距离 / Read closest cross-distance
            if pair_distance < min_gap_pixels:  # 更新更小距离 / Update smaller distance
                min_gap_pixels = pair_distance  # 记录最小值 / Record minimum
    if not math.isfinite(min_gap_pixels):  # 检查是否仍为无穷 / Check whether still infinite
        return float("inf")  # 返回无穷 / Return infinity
    return float(min_gap_pixels * mm_per_pixel)  # 转换为毫米 / Convert to millimetres


def d4_symmetry_mismatch(binary: np.ndarray) -> float:  # 计算 D4 对称偏差 / Compute D4 symmetry mismatch
    target = binary.astype(bool)  # 转换为布尔图 / Convert to boolean image
    if not target.any():  # 检查空目标 / Check empty target
        return 0.0  # 空目标视为完全对称 / Treat empty target as symmetric
    transforms = [np.rot90(target, k=1), np.rot90(target, k=2), np.rot90(target, k=3), np.fliplr(target), np.flipud(target), target.T, np.fliplr(target.T)]  # 列出 7 个非平凡 D4 变换 / Enumerate seven non-trivial D4 transforms
    iou_values = []  # 创建 IoU 列表 / Create IoU list
    target_sum = int(target.sum())  # 缓存目标像素数 / Cache target pixel count
    for transformed in transforms:  # 遍历每个变换 / Iterate each transform
        intersection = int(np.logical_and(target, transformed).sum())  # 计算交集 / Compute intersection
        union = int(np.logical_or(target, transformed).sum())  # 计算并集 / Compute union
        iou = float(intersection / union) if union > 0 else 0.0  # 计算 IoU / Compute IoU
        iou_values.append(iou)  # 收集 IoU / Collect IoU
        _ = target_sum  # 占位避免未使用警告 / Placeholder to keep cached value referenced
    mean_iou = float(np.mean(iou_values)) if iou_values else 0.0  # 计算平均 IoU / Compute mean IoU
    return float(max(0.0, 1.0 - mean_iou))  # 返回对称偏差 / Return symmetry mismatch


def estimate_min_frequency_hz(courant_min_mode_index: int, plate_size_mm: float, thickness_mm: float, youngs_modulus_pa: float, poisson_ratio: float, density_kg_m3: float) -> float:  # 估计目标所需最低频率 / Estimate minimum required frequency
    if courant_min_mode_index <= 0:  # 检查 mode 阶为零或负 / Check non-positive mode index
        return 0.0  # 返回 0 / Return zero
    length_m = float(plate_size_mm) / 1000.0  # 转板长为米 / Convert plate length to metres
    thickness_m = float(thickness_mm) / 1000.0  # 转厚度为米 / Convert thickness to metres
    area_m2 = length_m * length_m  # 计算板面积 / Compute plate area
    flexural_rigidity = float(youngs_modulus_pa) * (thickness_m**3) / (12.0 * (1.0 - float(poisson_ratio) ** 2))  # 计算抗弯刚度 D / Compute flexural rigidity D
    mass_per_area = float(density_kg_m3) * thickness_m  # 计算单位面积质量 ρh / Compute mass per area
    if flexural_rigidity <= 0.0 or mass_per_area <= 0.0:  # 检查物理参数有效性 / Check physical-parameter validity
        return 0.0  # 返回 0 / Return zero
    omega = 4.0 * math.pi * float(courant_min_mode_index) * math.sqrt(flexural_rigidity / mass_per_area) / area_m2  # Weyl 渐近反推角频率 / Weyl asymptotic angular frequency
    return float(omega / (2.0 * math.pi))  # 转换为 Hz / Convert to Hz


def near_center_clamp_ratio(binary: np.ndarray, plate_size_mm: float, clamp_radius_mm: float, clamp_buffer_mm: float) -> float:  # 计算目标贴近夹持区比例 / Compute target ratio inside clamp influence
    rows, cols = binary.shape  # 读取图像尺寸 / Read image shape
    mm_per_pixel = float(plate_size_mm) / float(max(rows, cols))  # 计算每像素毫米 / Compute mm per pixel
    influence_radius_px = float(clamp_radius_mm + clamp_buffer_mm) / max(mm_per_pixel, 1.0e-6)  # 计算影响半径像素 / Compute influence radius in pixels
    yy, xx = np.ogrid[:rows, :cols]  # 创建坐标网格 / Create coordinate grid
    center_y = (rows - 1) / 2.0  # 计算图中心 y / Compute centre y
    center_x = (cols - 1) / 2.0  # 计算图中心 x / Compute centre x
    influence_mask = (yy - center_y) ** 2 + (xx - center_x) ** 2 <= influence_radius_px**2  # 构造影响圆掩膜 / Build influence circular mask
    target = binary.astype(bool)  # 转换为布尔图 / Convert to boolean image
    target_sum = int(target.sum())  # 计算目标像素数 / Compute target pixel count
    if target_sum == 0:  # 检查空目标 / Check empty target
        return 0.0  # 返回 0 / Return zero
    overlap = int(np.logical_and(target, influence_mask).sum())  # 计算与影响区交集 / Compute overlap with influence region
    return float(overlap / target_sum)  # 返回贴近比例 / Return overlap ratio


def classify_target_kind(metrics: dict[str, float | int], thresholds: dict[str, float]) -> str:  # 判定目标语义类别 / Classify target semantic kind
    endpoints = int(metrics["n_skeleton_endpoints"])  # 读取端点数 / Read endpoint count
    foreground_ratio = float(metrics["foreground_ratio"])  # 读取前景占比 / Read foreground ratio
    feature_mm = float(metrics["stroke_min_feature_mm"])  # 读取特征宽度 / Read feature width
    if foreground_ratio >= float(thresholds["filled_target_foreground_ratio"]):  # 检查是否填充图案 / Check filled-pattern target
        return "filled_amplitude_target"  # 视为填充振幅目标 / Treat as filled amplitude target
    if endpoints > 0 and feature_mm <= float(thresholds["thin_stroke_feature_mm"]):  # 检查薄线条带端点 / Check thin stroke with endpoints
        return "open_stroke_pattern"  # 视为带端点的线条 / Treat as open-stroke pattern
    if endpoints > 0:  # 检查含端点厚目标 / Check thick target with endpoints
        return "open_stroke_pattern"  # 仍视为带端点目标 / Still treat as open-stroke pattern
    return "closed_curve_set"  # 默认视为闭合曲线集 / Default to closed-curve set


def determine_verdict(metrics: dict[str, float | int], thresholds: dict[str, float]) -> tuple[str, list[str]]:  # 综合各项指标判定 / Combine metrics into a verdict
    notes: list[str] = []  # 创建说明列表 / Create note list
    courant = int(metrics["courant_min_mode_index"])  # 读取 Courant 下界 / Read Courant lower bound
    gap_mm = float(metrics["stroke_min_gap_mm"])  # 读取最小笔画间隙 / Read minimum stroke gap
    d4_mismatch = float(metrics["d4_symmetry_mismatch"])  # 读取 D4 对称偏差 / Read D4 symmetry mismatch
    endpoints = int(metrics["n_skeleton_endpoints"])  # 读取骨架端点数 / Read skeleton endpoint count
    clamp_ratio = float(metrics["near_clamp_ratio"])  # 读取贴夹持区比例 / Read near-clamp ratio
    target_kind = str(metrics["target_kind"])  # 读取目标类别 / Read target kind
    finite_gap = math.isfinite(gap_mm)  # 检查间隙是否有限 / Check whether gap is finite
    if courant > thresholds["infeasible_courant_min_mode_index"]:  # 判断 Courant 是否超不可达阈值 / Check Courant infeasibility
        notes.append(f"Courant lower bound {courant} exceeds infeasible threshold {thresholds['infeasible_courant_min_mode_index']}. / Courant 下界 {courant} 超过不可达阈值 {thresholds['infeasible_courant_min_mode_index']}。")  # 记录原因 / Record reason
        return "infeasible_as_nodal_set", notes  # 返回不可达 / Return infeasible
    if finite_gap and gap_mm < thresholds["infeasible_stroke_min_gap_mm"]:  # 判断笔画间隙是否过窄 / Check stroke gap infeasibility
        notes.append(f"Stroke gap {gap_mm:.2f} mm below infeasible threshold {thresholds['infeasible_stroke_min_gap_mm']} mm. / 笔画间隙 {gap_mm:.2f} mm 低于不可达阈值 {thresholds['infeasible_stroke_min_gap_mm']} mm。")  # 记录原因 / Record reason
        return "infeasible_as_nodal_set", notes  # 返回不可达 / Return infeasible
    if clamp_ratio > 0.20:  # 检查目标是否大量落在夹持影响区 / Check target near clamp
        notes.append(f"{clamp_ratio * 100:.1f}% of target pixels sit inside clamp influence zone; response there is suppressed. / {clamp_ratio * 100:.1f}% 的目标像素落在夹持影响区内，该处响应被压制。")  # 记录原因 / Record reason
    if courant > thresholds["requires_topology_courant_min_mode_index"]:  # 判断是否需要拓扑突破 / Check topology-required Courant
        notes.append(f"Courant lower bound {courant} exceeds soft threshold {thresholds['requires_topology_courant_min_mode_index']}; needs high-order modes or topology break. / Courant 下界 {courant} 超过软阈值 {thresholds['requires_topology_courant_min_mode_index']}，需要高阶模态或拓扑突破。")  # 记录原因 / Record reason
        return "requires_topology", notes  # 返回需要拓扑 / Return requires topology
    if finite_gap and gap_mm < thresholds["requires_topology_stroke_min_gap_mm"]:  # 判断笔画间隙过窄 / Check too-narrow stroke gap
        notes.append(f"Stroke gap {gap_mm:.2f} mm below {thresholds['requires_topology_stroke_min_gap_mm']} mm; 15x15 grid cannot independently shape each stroke. / 笔画间隙 {gap_mm:.2f} mm 低于 {thresholds['requires_topology_stroke_min_gap_mm']} mm，15x15 网格无法独立塑形。")  # 记录原因 / Record reason
        return "requires_topology", notes  # 返回需要拓扑 / Return requires topology
    if d4_mismatch > thresholds["requires_topology_d4_symmetry_mismatch"]:  # 判断 D4 对称偏差 / Check D4 mismatch
        notes.append(f"D4 symmetry mismatch {d4_mismatch:.2f} exceeds {thresholds['requires_topology_d4_symmetry_mismatch']}; square plate natural modes resist this asymmetry. / D4 对称偏差 {d4_mismatch:.2f} 超过 {thresholds['requires_topology_d4_symmetry_mismatch']}，方板自然模态会抵抗这种不对称。")  # 记录原因 / Record reason
        return "requires_topology", notes  # 返回需要拓扑 / Return requires topology
    if target_kind in {"open_stroke_pattern", "filled_amplitude_target"} and endpoints > thresholds["max_endpoints_easy"]:  # 含端点目标必须走振幅模式 / Endpoint target must use amplitude mode
        notes.append(f"Skeleton has {endpoints} open endpoints; switch from nodal-line matching to amplitude-pattern matching (W2). / 骨架存在 {endpoints} 个端点，应从节点线匹配切换到振幅模式匹配 (W2)。")  # 记录原因 / Record reason
        return "needs_amplitude_pattern", notes  # 返回需要振幅模式 / Return amplitude-pattern mode
    if courant > thresholds["borderline_courant_min_mode_index"]:  # 判断临界 mode 阶 / Check borderline mode index
        notes.append(f"Courant lower bound {courant} above borderline {thresholds['borderline_courant_min_mode_index']}; expect tight modal budget. / Courant 下界 {courant} 高于临界 {thresholds['borderline_courant_min_mode_index']}，模态预算紧张。")  # 记录原因 / Record reason
        return "borderline", notes  # 返回临界 / Return borderline
    if finite_gap and gap_mm < thresholds["borderline_stroke_min_gap_mm"]:  # 判断临界间隙 / Check borderline gap
        notes.append(f"Stroke gap {gap_mm:.2f} mm below borderline {thresholds['borderline_stroke_min_gap_mm']} mm. / 笔画间隙 {gap_mm:.2f} mm 低于临界 {thresholds['borderline_stroke_min_gap_mm']} mm。")  # 记录原因 / Record reason
        return "borderline", notes  # 返回临界 / Return borderline
    if d4_mismatch > thresholds["borderline_d4_symmetry_mismatch"]:  # 判断临界 D4 偏差 / Check borderline D4 mismatch
        notes.append(f"D4 symmetry mismatch {d4_mismatch:.2f} above borderline {thresholds['borderline_d4_symmetry_mismatch']}. / D4 对称偏差 {d4_mismatch:.2f} 高于临界 {thresholds['borderline_d4_symmetry_mismatch']}。")  # 记录原因 / Record reason
        return "borderline", notes  # 返回临界 / Return borderline
    notes.append("Target is within easy realizability bounds. / 目标处于易于实现的范围内。")  # 记录顺利结论 / Record favourable conclusion
    return "easy", notes  # 返回 easy / Return easy


def analyze_target_realizability(target_binary: np.ndarray, plate_size_mm: float = 150.0, grid_size: int = 15, center_clamp_radius_mm: float = 8.0, thickness_mm_default: float = 1.0, youngs_modulus_pa: float = 2.0e9, poisson_ratio: float = 0.35, density_kg_m3: float = 1200.0, thresholds: dict[str, float] | None = None) -> dict:  # 计算目标可达性 / Compute target realizability
    selected = {**DEFAULT_REALIZABILITY_THRESHOLDS, **(thresholds or {})}  # 合并默认阈值 / Merge default thresholds
    binary = target_binary.astype(bool)  # 转换为布尔图 / Convert to boolean
    image_size = int(max(binary.shape))  # 取图像尺寸 / Take image dimension
    mm_per_pixel = float(plate_size_mm) / float(image_size)  # 计算每像素毫米 / Compute mm per pixel
    cell_size_mm = float(plate_size_mm) / float(grid_size)  # 计算单元毫米 / Compute cell millimetre size
    component_count, label_map = count_connected_components(binary)  # 计算前景连通分量 / Count foreground components
    hole_count = count_background_holes(binary)  # 计算前景内部洞数 / Count interior holes
    courant_lower_bound = int(max(1, component_count + hole_count))  # 计算 Courant 下界 / Compute Courant lower bound
    endpoint_count = count_skeleton_endpoints(binary)  # 统计骨架端点 / Count skeleton endpoints
    feature_mm = stroke_min_feature_mm(binary, mm_per_pixel)  # 估算最小笔画宽度 / Estimate minimum feature width
    gap_mm = stroke_min_gap_mm(label_map, component_count, mm_per_pixel)  # 估算最小笔画间隙 / Estimate minimum stroke gap
    d4_mismatch = d4_symmetry_mismatch(binary)  # 计算 D4 对称偏差 / Compute D4 mismatch
    min_frequency_hz = estimate_min_frequency_hz(courant_lower_bound, plate_size_mm, thickness_mm_default, youngs_modulus_pa, poisson_ratio, density_kg_m3)  # 估算最小所需频率 / Estimate minimum required frequency
    clamp_ratio = near_center_clamp_ratio(binary, plate_size_mm, center_clamp_radius_mm, float(selected["clamp_buffer_mm"]))  # 计算贴夹持区比例 / Compute near-clamp ratio
    foreground_ratio = float(binary.mean())  # 计算前景占比 / Compute foreground ratio
    finite_gap_mm = float(gap_mm) if math.isfinite(gap_mm) else float("inf")  # 保留有限或无穷间隙 / Keep finite or infinite gap
    metrics: dict[str, float | int | str] = {"image_size": image_size, "plate_size_mm": float(plate_size_mm), "grid_size": int(grid_size), "cell_size_mm": cell_size_mm, "mm_per_pixel": mm_per_pixel, "foreground_ratio": foreground_ratio, "n_connected_components": int(component_count), "n_closed_loops": int(hole_count), "n_skeleton_endpoints": int(endpoint_count), "courant_min_mode_index": courant_lower_bound, "stroke_min_gap_mm": finite_gap_mm, "stroke_min_feature_mm": float(feature_mm), "d4_symmetry_mismatch": float(d4_mismatch), "estimated_min_frequency_hz": float(min_frequency_hz), "near_clamp_ratio": float(clamp_ratio)}  # 收集所有指标 / Collect all metrics
    metrics["target_kind"] = classify_target_kind(metrics, selected)  # 标注目标类别 / Tag target kind
    from src.symmetry.d4_decomposition import coupling_accessibility  # 延迟导入避免循环 / Lazy import to avoid cycles
    from src.symmetry.d4_decomposition import irrep_energy_ratios  # 延迟导入 / Lazy import
    irrep_ratios = irrep_energy_ratios(binary.astype(np.float64))  # 计算 D4 irrep 能量占比 / Compute D4 irrep energy ratios
    a1_fraction = float(coupling_accessibility(binary.astype(np.float64), ("A1",)))  # 中心激振只耦合 A1：可达上限 / Centre excitation couples only A1
    metrics["irrep_energy_ratios"] = {k: float(v) for k, v in irrep_ratios.items()}  # 写入指标 / Store
    metrics["central_excitation_accessibility"] = a1_fraction  # 写入可达上限 / Store upper bound
    metrics["central_excitation_inaccessible_fraction"] = float(1.0 - a1_fraction)  # 不可达能量比例 / Inaccessible fraction
    verdict, notes = determine_verdict(metrics, selected)  # 综合判定 / Compose verdict
    if a1_fraction < 0.70:  # A1 占比低于 70% 时补充诊断 / Add diagnostic when A1 is low
        dominant_inaccessible = max(((k, v) for k, v in irrep_ratios.items() if k != "A1"), key=lambda kv: kv[1])  # 找最大不可达 irrep / Find largest non-A1 irrep
        notes.append(f"D4 irrep accessibility: only {a1_fraction*100:.1f}% of target energy in A1 (central-excitation reachable); dominant inaccessible irrep is {dominant_inaccessible[0]} with {dominant_inaccessible[1]*100:.1f}%. / D4 irrep 可达性：仅 {a1_fraction*100:.1f}% 能量在 A1 子空间（中心激振可达），最大不可达 irrep 是 {dominant_inaccessible[0]}（{dominant_inaccessible[1]*100:.1f}%）。")  # 记录原因 / Record reason
    advisory = build_advisory(verdict, metrics)  # 构造可执行建议 / Build actionable advisory
    return {"verdict": verdict, "metrics": metrics, "thresholds": selected, "diagnosis_notes": notes, "advisory": advisory}  # 返回报告字典 / Return report dictionary


def build_advisory(verdict: str, metrics: dict[str, float | int | str]) -> list[str]:  # 构造执行建议 / Build executable advisory
    advice: list[str] = []  # 创建建议列表 / Create advisory list
    target_kind = str(metrics.get("target_kind", "closed_curve_set"))  # 读取目标类别 / Read target kind
    if verdict == "easy":  # 简单目标分支 / Easy-target branch
        advice.append("Proceed with current 15x15 search; gradient-based loop (W3) should converge quickly under nodal-line matching. / 可直接使用 15x15 搜索；W3 梯度链路下节点线匹配应快速收敛。")  # 推荐路径 / Recommend path
    elif verdict == "needs_amplitude_pattern":  # 需要振幅模式分支 / Amplitude-mode branch
        advice.append("Switch from nodal-line matching to amplitude-valley loss (W2). Target strokes will be matched as low-amplitude bands, not nodal contours. / 从节点线匹配切换到 W2 振幅谷损失；目标笔画将匹配为低振幅带，而非节点等值线。")  # 推荐路径 / Recommend path
        advice.append("Then run W5 homotopy and record lambda_max so the customer sees a quantitative reachability number. / 随后运行 W5 同伦延拓并记录 lambda_max，向客户给出量化可达性指标。")  # 推荐路径 / Recommend path
    elif verdict == "borderline":  # 临界目标分支 / Borderline-target branch
        advice.append("Use W2 amplitude-valley loss and W5 homotopy continuation; record lambda_max instead of expecting full match. / 使用 W2 振幅谷损失与 W5 同伦延拓；记录 lambda_max 而非追求完全匹配。")  # 推荐路径 / Recommend path
    elif verdict == "requires_topology":  # 需要拓扑突破分支 / Topology-break branch
        advice.append("Single passive plate at 15x15 likely insufficient. Document infeasibility for the user, then run W5 to report lambda_max under W2 amplitude-valley loss. / 单块 15x15 被动板很可能无法实现；向用户说明，并通过 W5 在 W2 振幅谷损失下报告 lambda_max。")  # 推荐路径 / Recommend path
    else:  # 不可达分支 / Infeasible branch
        advice.append("Decline the nodal-line interpretation. Offer the user: (a) amplitude-pattern matching mode (W2), (b) simplified target with closed strokes reaching the boundary, (c) finer printable plate as a future contract upgrade. / 拒绝节点线解释；建议用户使用 (a) W2 振幅模式匹配、(b) 闭合到边界的简化目标、(c) 未来合同中更精细的可打印板。")  # 推荐路径 / Recommend path
    if target_kind == "filled_amplitude_target":  # 填充目标提醒 / Filled-target reminder
        advice.append("Target is filled rather than line-like; amplitude-pattern matching is the natural interpretation. / 目标为填充图案而非线条，振幅模式匹配是自然解释。")  # 填充提醒 / Filled reminder
    if float(metrics.get("near_clamp_ratio", 0.0)) > 0.20:  # 贴夹持区提醒 / Near-clamp reminder
        advice.append("Consider redrawing target away from the centre clamp; modal response near the clamp is heavily damped. / 建议把目标远离中心夹持区，因为夹持附近模态响应被强烈衰减。")  # 夹持提醒 / Clamp reminder
    return advice  # 返回建议 / Return advisory


def load_target_binary_from_path(path: str | Path, image_size: int) -> np.ndarray:  # 从路径载入目标二值图 / Load target binary from path
    target_path = Path(path)  # 转换路径 / Convert path
    if not target_path.exists():  # 检查文件存在 / Check file existence
        raise FileNotFoundError(f"Target file not found: {target_path}. / 未找到目标文件：{target_path}。")  # 抛出错误 / Raise error
    if target_path.suffix.lower() == ".npy":  # 检查是否为 NPY / Check NPY input
        data = np.load(target_path).astype(bool)  # 读取 NPY / Load NPY
        return data  # 直接返回 / Return directly
    from src.target.preprocess_target import binarize_target  # 延迟导入避免循环 / Lazy import to avoid cycles
    from src.target.preprocess_target import load_target_image  # 延迟导入图像读取 / Lazy import image loader
    from src.target.preprocess_target import resize_image  # 延迟导入缩放 / Lazy import resize
    image = load_target_image(target_path)  # 读取图像 / Load image
    resized = resize_image(image, int(image_size))  # 缩放图像 / Resize image
    return binarize_target(resized).astype(bool)  # 二值化并返回 / Binarise and return


def save_realizability_report(report: dict, output_path: str | Path) -> Path:  # 保存可达性报告 / Save realizability report
    path = Path(output_path)  # 转换路径 / Convert path
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    serialisable = json.loads(json.dumps(report, default=_json_default))  # 转可序列化对象 / Convert to JSON-safe object
    path.write_text(json.dumps(serialisable, ensure_ascii=False, indent=2), encoding="utf-8")  # 写入 JSON / Write JSON file
    return path  # 返回写入路径 / Return written path


def _json_default(value: object) -> object:  # 处理 JSON 不识别类型 / Handle JSON-unsupported types
    if isinstance(value, (np.integer,)):  # 检查 numpy 整数 / Check numpy integer
        return int(value)  # 转 Python 整数 / Convert to Python int
    if isinstance(value, (np.floating,)):  # 检查 numpy 浮点 / Check numpy float
        if not math.isfinite(float(value)):  # 检查非有限数 / Check non-finite
            return None  # 写为 null / Encode as null
        return float(value)  # 转 Python 浮点 / Convert to Python float
    if isinstance(value, float) and not math.isfinite(value):  # 检查 Python 非有限 / Check Python non-finite
        return None  # 写为 null / Encode as null
    if isinstance(value, np.ndarray):  # 检查 numpy 数组 / Check numpy array
        return value.tolist()  # 转 Python 列表 / Convert to Python list
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serialisable. / 类型 {type(value).__name__} 无法序列化。")  # 抛出未知类型 / Raise unknown type


def summarize_realizability_report(report: dict) -> str:  # 汇总可达性报告 / Summarise realizability report
    metrics = report["metrics"]  # 读取指标 / Read metrics
    irrep_ratios = metrics.get("irrep_energy_ratios") or {}  # 读取 irrep 占比 / Read irrep ratios
    irrep_summary = ", ".join(f"{k}={float(v)*100:.1f}%" for k, v in sorted(dict(irrep_ratios).items(), key=lambda kv: -float(kv[1])) if float(v) > 0.005)  # 摘要 / Summary
    lines = [f"Verdict: {report['verdict']} / 判定：{report['verdict']}", f"Target kind: {metrics.get('target_kind', 'unknown')} / 目标类别：{metrics.get('target_kind', 'unknown')}", f"Foreground ratio: {metrics['foreground_ratio']:.3f} / 前景占比：{metrics['foreground_ratio']:.3f}", f"Connected components: {metrics['n_connected_components']} / 连通分量：{metrics['n_connected_components']}", f"Closed loops: {metrics['n_closed_loops']} / 闭合环数：{metrics['n_closed_loops']}", f"Skeleton endpoints: {metrics['n_skeleton_endpoints']} / 骨架端点：{metrics['n_skeleton_endpoints']}", f"Courant min mode index: {metrics['courant_min_mode_index']} / Courant 下界 mode：{metrics['courant_min_mode_index']}", f"Stroke min feature: {metrics['stroke_min_feature_mm']:.2f} mm / 最小笔画宽度：{metrics['stroke_min_feature_mm']:.2f} mm", f"Stroke min gap: {metrics['stroke_min_gap_mm']:.2f} mm / 最小笔画间隙：{metrics['stroke_min_gap_mm']:.2f} mm", f"D4 mismatch: {metrics['d4_symmetry_mismatch']:.3f} / D4 对称偏差：{metrics['d4_symmetry_mismatch']:.3f}", f"D4 irrep energy: {irrep_summary} / D4 irrep 能量分布：{irrep_summary}", f"Central-excitation accessibility (A1 only): {float(metrics.get('central_excitation_accessibility', 0.0))*100:.2f}% / 中心激振可达比例（仅 A1）：{float(metrics.get('central_excitation_accessibility', 0.0))*100:.2f}%", f"Near-clamp ratio: {metrics['near_clamp_ratio']:.3f} / 贴夹持区比例：{metrics['near_clamp_ratio']:.3f}", f"Estimated min frequency: {metrics['estimated_min_frequency_hz']:.1f} Hz / 估算所需最低频率：{metrics['estimated_min_frequency_hz']:.1f} Hz"]  # 创建摘要行 / Create summary lines
    lines.extend(report.get("diagnosis_notes", []))  # 追加诊断说明 / Append diagnosis notes
    lines.extend(report.get("advisory", []))  # 追加可执行建议 / Append advisory
    return "\n".join(lines)  # 返回多行文本 / Return multiline text
