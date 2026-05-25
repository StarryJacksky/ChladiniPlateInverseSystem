from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import numpy as np  # 导入数值计算库 / Import numerical library

try:  # 优先使用 SciPy 加速距离变换 / Prefer SciPy to accelerate distance transforms
    from scipy.ndimage import distance_transform_edt as scipy_distance_transform_edt  # 导入欧氏距离变换 / Import Euclidean distance transform
except Exception:  # 兼容未安装 SciPy 的部署环境 / Support deployments without SciPy
    scipy_distance_transform_edt = None  # 标记不可用并回退纯 NumPy / Mark unavailable and fall back to pure NumPy


def compute_iou(A: np.ndarray, B: np.ndarray) -> float:  # 计算 IoU / Compute IoU
    intersection = np.logical_and(A, B).sum()  # 计算交集像素数 / Count intersection pixels
    union = np.logical_or(A, B).sum()  # 计算并集像素数 / Count union pixels
    if union == 0:  # 避免除以零 / Avoid division by zero
        return 0.0  # 返回零分 / Return zero score
    return float(intersection / union)  # 返回 IoU / Return IoU


def compute_dice(A: np.ndarray, B: np.ndarray) -> float:  # 计算 Dice 系数 / Compute Dice coefficient
    intersection = np.logical_and(A, B).sum()  # 计算交集像素数 / Count intersection pixels
    total = A.sum() + B.sum()  # 计算两个区域总像素 / Count total positive pixels
    if total == 0:  # 避免除以零 / Avoid division by zero
        return 0.0  # 返回零分 / Return zero score
    return float(2.0 * intersection / total)  # 返回 Dice / Return Dice


def compute_overlap_balance(A: np.ndarray, B: np.ndarray) -> float:  # 计算覆盖平衡分数 / Compute overlap balance score
    left = A.astype(bool)  # 转换第一张图 / Convert first map
    right = B.astype(bool)  # 转换第二张图 / Convert second map
    intersection = np.logical_and(left, right).sum()  # 计算交集像素 / Count intersection pixels
    if left.sum() == 0 or right.sum() == 0:  # 检查空前景 / Check empty foreground
        return 0.0  # 空图返回零分 / Return zero score for empty maps
    precision = float(intersection / left.sum())  # 计算仿真前景精度 / Compute simulated foreground precision
    recall = float(intersection / right.sum())  # 计算目标覆盖召回 / Compute target coverage recall
    return float(min(precision, recall))  # 返回较弱一侧作为平衡分 / Return weaker side as balance score


def compute_precision_recall(A: np.ndarray, B: np.ndarray) -> tuple[float, float]:  # 计算仿真精度和目标召回 / Compute simulation precision and target recall
    left = A.astype(bool)  # 转换仿真图 / Convert simulation map
    right = B.astype(bool)  # 转换目标图 / Convert target map
    intersection = np.logical_and(left, right).sum()  # 计算交集像素 / Count intersection pixels
    precision = float(intersection / left.sum()) if left.sum() else 0.0  # 计算仿真前景精度 / Compute simulated foreground precision
    recall = float(intersection / right.sum()) if right.sum() else 0.0  # 计算目标召回率 / Compute target recall
    return precision, recall  # 返回精度和召回 / Return precision and recall


def area_similarity(A: np.ndarray, B: np.ndarray) -> float:  # 计算前景面积相似度 / Compute foreground area similarity
    left_area = float(A.astype(bool).mean())  # 计算仿真前景面积比例 / Compute simulated foreground area ratio
    right_area = float(B.astype(bool).mean())  # 计算目标前景面积比例 / Compute target foreground area ratio
    if left_area == 0.0 and right_area == 0.0:  # 检查双空图 / Check both-empty maps
        return 1.0  # 双空面积完全一致 / Both empty maps match in area
    denominator = max(left_area, right_area, 1.0e-9)  # 计算归一化分母 / Compute normalization denominator
    return float(max(0.0, 1.0 - abs(left_area - right_area) / denominator))  # 返回面积相似度 / Return area similarity


def coarse_occupancy(binary: np.ndarray, cells: int = 16) -> np.ndarray:  # 计算粗网格占用图 / Compute coarse occupancy map
    data = binary.astype(float)  # 转为浮点图 / Convert to float map
    rows, cols = data.shape  # 读取图像尺寸 / Read image shape
    row_edges = np.linspace(0, rows, cells + 1).astype(int)  # 构造行边界 / Build row edges
    col_edges = np.linspace(0, cols, cells + 1).astype(int)  # 构造列边界 / Build column edges
    occupancy = np.zeros((cells, cells), dtype=float)  # 创建占用矩阵 / Create occupancy matrix
    for row in range(cells):  # 遍历粗网格行 / Iterate coarse rows
        for col in range(cells):  # 遍历粗网格列 / Iterate coarse columns
            block = data[row_edges[row]:row_edges[row + 1], col_edges[col]:col_edges[col + 1]]  # 读取局部块 / Read local block
            occupancy[row, col] = float(block.mean()) if block.size else 0.0  # 保存占用比例 / Store occupancy ratio
    return occupancy  # 返回粗网格占用 / Return coarse occupancy


def layout_similarity(A: np.ndarray, B: np.ndarray, cells: int = 16) -> float:  # 计算粗布局相似度 / Compute coarse layout similarity
    left = coarse_occupancy(A, cells).ravel()  # 计算第一张图占用向量 / Compute first occupancy vector
    right = coarse_occupancy(B, cells).ravel()  # 计算第二张图占用向量 / Compute second occupancy vector
    left_norm = float(np.linalg.norm(left))  # 计算第一向量范数 / Compute first vector norm
    right_norm = float(np.linalg.norm(right))  # 计算第二向量范数 / Compute second vector norm
    if left_norm == 0.0 or right_norm == 0.0:  # 检查空布局 / Check empty layout
        return 0.0  # 空布局返回零 / Return zero for empty layout
    return float(np.dot(left, right) / (left_norm * right_norm))  # 返回余弦相似度 / Return cosine similarity


def profile_similarity(left_profile: np.ndarray, right_profile: np.ndarray) -> float:  # 计算一维投影相似度 / Compute one-dimensional projection similarity
    left_sum = float(left_profile.sum())  # 计算左侧投影总量 / Compute left projection total
    right_sum = float(right_profile.sum())  # 计算右侧投影总量 / Compute right projection total
    if left_sum <= 0.0 or right_sum <= 0.0:  # 检查空投影 / Check empty projections
        return 0.0  # 空投影返回零 / Return zero for empty projections
    left = left_profile.astype(float) / left_sum  # 归一化左侧投影 / Normalize left projection
    right = right_profile.astype(float) / right_sum  # 归一化右侧投影 / Normalize right projection
    left_norm = float(np.linalg.norm(left))  # 计算左侧范数 / Compute left norm
    right_norm = float(np.linalg.norm(right))  # 计算右侧范数 / Compute right norm
    cosine = float(np.dot(left, right) / max(left_norm * right_norm, 1.0e-9))  # 计算余弦相似度 / Compute cosine similarity
    l1_similarity = float(max(0.0, 1.0 - 0.5 * np.abs(left - right).sum()))  # 计算归一化 L1 相似度 / Compute normalized L1 similarity
    return float(0.45 * cosine + 0.55 * l1_similarity)  # 返回混合投影分数 / Return blended projection score


def projection_similarity(A: np.ndarray, B: np.ndarray) -> float:  # 计算横纵投影相似度 / Compute horizontal and vertical projection similarity
    left = A.astype(bool)  # 转换第一张图 / Convert first map
    right = B.astype(bool)  # 转换第二张图 / Convert second map
    x_score = profile_similarity(left.sum(axis=0), right.sum(axis=0))  # 计算水平投影分数 / Compute x-projection score
    y_score = profile_similarity(left.sum(axis=1), right.sum(axis=1))  # 计算垂直投影分数 / Compute y-projection score
    return float(0.58 * x_score + 0.42 * y_score)  # 横向结构更重要 / Weight horizontal structure more strongly


def foreground_extent(binary: np.ndarray) -> tuple[float, float, float, float, float]:  # 计算前景包围盒特征 / Compute foreground bounding-box features
    data = binary.astype(bool)  # 转换布尔图 / Convert to boolean map
    coords = np.argwhere(data)  # 获取前景坐标 / Read foreground coordinates
    if coords.size == 0:  # 检查空前景 / Check empty foreground
        return 0.0, 0.0, 0.5, 0.5, 1.0  # 返回中性空特征 / Return neutral empty features
    rows, cols = data.shape  # 读取图像尺寸 / Read image shape
    row_min, col_min = coords.min(axis=0)  # 读取最小坐标 / Read minimum coordinates
    row_max, col_max = coords.max(axis=0)  # 读取最大坐标 / Read maximum coordinates
    width = float((col_max - col_min + 1) / max(cols, 1))  # 计算归一化宽度 / Compute normalized width
    height = float((row_max - row_min + 1) / max(rows, 1))  # 计算归一化高度 / Compute normalized height
    center_x = float((col_min + col_max + 1) / (2.0 * max(cols, 1)))  # 计算归一化中心 x / Compute normalized centre x
    center_y = float((row_min + row_max + 1) / (2.0 * max(rows, 1)))  # 计算归一化中心 y / Compute normalized centre y
    aspect = float(width / max(height, 1.0e-9))  # 计算宽高比 / Compute aspect ratio
    return width, height, center_x, center_y, aspect  # 返回包围盒特征 / Return bounding-box features


def ratio_similarity(left_value: float, right_value: float) -> float:  # 计算比例相似度 / Compute ratio similarity
    denominator = max(abs(left_value), abs(right_value), 1.0e-9)  # 计算稳定分母 / Compute stable denominator
    return float(max(0.0, 1.0 - abs(left_value - right_value) / denominator))  # 返回比例分数 / Return ratio score


def extent_similarity(A: np.ndarray, B: np.ndarray) -> float:  # 计算包围盒尺度相似度 / Compute bounding-box extent similarity
    left_width, left_height, left_x, left_y, left_aspect = foreground_extent(A)  # 读取第一张图特征 / Read first-map features
    right_width, right_height, right_x, right_y, right_aspect = foreground_extent(B)  # 读取第二张图特征 / Read second-map features
    width_score = ratio_similarity(left_width, right_width)  # 计算宽度相似 / Compute width similarity
    height_score = ratio_similarity(left_height, right_height)  # 计算高度相似 / Compute height similarity
    aspect_score = ratio_similarity(left_aspect, right_aspect)  # 计算宽高比相似 / Compute aspect similarity
    center_distance = float(np.hypot(left_x - right_x, left_y - right_y))  # 计算中心距离 / Compute centre distance
    center_score = float(max(0.0, 1.0 - center_distance / 0.70710678118))  # 归一化中心分数 / Normalize centre score
    return float(0.32 * width_score + 0.24 * height_score + 0.24 * center_score + 0.20 * aspect_score)  # 返回尺度结构分数 / Return extent structure score


def boundary_complexity(binary: np.ndarray) -> float:  # 计算边界复杂度 / Compute boundary complexity
    data = binary.astype(bool)  # 转换布尔图 / Convert to boolean map
    foreground = int(data.sum())  # 计算前景数量 / Count foreground pixels
    if foreground == 0:  # 检查空前景 / Check empty foreground
        return 0.0  # 空前景复杂度为零 / Empty foreground has zero complexity
    padded = np.pad(data, ((1, 1), (1, 1)), mode="constant", constant_values=False)  # 填充边界 / Pad boundaries
    center = padded[1:-1, 1:-1]  # 读取中心区域 / Read centre region
    interior = center & padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]  # 判断四邻域内部点 / Detect four-neighbour interior pixels
    boundary = center & ~interior  # 提取边界像素 / Extract boundary pixels
    return float(boundary.sum() / foreground)  # 返回边界占前景比例 / Return boundary-to-foreground ratio


def complexity_similarity(A: np.ndarray, B: np.ndarray) -> float:  # 计算结构复杂度相似度 / Compute structural complexity similarity
    left_complexity = boundary_complexity(A)  # 计算第一张图复杂度 / Compute first-map complexity
    right_complexity = boundary_complexity(B)  # 计算第二张图复杂度 / Compute second-map complexity
    return ratio_similarity(left_complexity, right_complexity)  # 返回复杂度比例相似 / Return complexity ratio similarity


def chamfer_distance(binary: np.ndarray) -> np.ndarray:  # 计算到最近前景像素的近似距离 / Compute approximate distance to nearest foreground pixel
    data = binary.astype(bool)  # 转为布尔图 / Convert to boolean map
    if scipy_distance_transform_edt is not None:  # 检查 SciPy 快路径 / Check SciPy fast path
        return scipy_distance_transform_edt(~data)  # 返回到最近前景的欧氏距离 / Return Euclidean distance to nearest foreground
    height, width = data.shape  # 读取图像尺寸 / Read image shape
    large = float(height + width + 1)  # 设置足够大的初始距离 / Set sufficiently large initial distance
    distances = np.where(data, 0.0, large)  # 前景距离为零，背景为大值 / Set foreground distance zero and background large
    diagonal = 1.41421356237  # 设置对角移动代价 / Set diagonal move cost
    for row in range(height):  # 正向遍历行 / Forward row pass
        for col in range(width):  # 正向遍历列 / Forward column pass
            best = distances[row, col]  # 读取当前最佳距离 / Read current best distance
            if row > 0:  # 检查上方邻居 / Check upper neighbour
                best = min(best, distances[row - 1, col] + 1.0)  # 更新垂直距离 / Update vertical distance
            if col > 0:  # 检查左侧邻居 / Check left neighbour
                best = min(best, distances[row, col - 1] + 1.0)  # 更新水平距离 / Update horizontal distance
            if row > 0 and col > 0:  # 检查左上邻居 / Check upper-left neighbour
                best = min(best, distances[row - 1, col - 1] + diagonal)  # 更新对角距离 / Update diagonal distance
            if row > 0 and col + 1 < width:  # 检查右上邻居 / Check upper-right neighbour
                best = min(best, distances[row - 1, col + 1] + diagonal)  # 更新对角距离 / Update diagonal distance
            distances[row, col] = best  # 写回最佳距离 / Store best distance
    for row in range(height - 1, -1, -1):  # 反向遍历行 / Backward row pass
        for col in range(width - 1, -1, -1):  # 反向遍历列 / Backward column pass
            best = distances[row, col]  # 读取当前最佳距离 / Read current best distance
            if row + 1 < height:  # 检查下方邻居 / Check lower neighbour
                best = min(best, distances[row + 1, col] + 1.0)  # 更新垂直距离 / Update vertical distance
            if col + 1 < width:  # 检查右侧邻居 / Check right neighbour
                best = min(best, distances[row, col + 1] + 1.0)  # 更新水平距离 / Update horizontal distance
            if row + 1 < height and col + 1 < width:  # 检查右下邻居 / Check lower-right neighbour
                best = min(best, distances[row + 1, col + 1] + diagonal)  # 更新对角距离 / Update diagonal distance
            if row + 1 < height and col > 0:  # 检查左下邻居 / Check lower-left neighbour
                best = min(best, distances[row + 1, col - 1] + diagonal)  # 更新对角距离 / Update diagonal distance
            distances[row, col] = best  # 写回最佳距离 / Store best distance
    return distances  # 返回距离图 / Return distance map


def chamfer_similarity(A: np.ndarray, B: np.ndarray) -> float:  # 计算双向距离相似度 / Compute symmetric distance similarity
    left = A.astype(bool)  # 转换第一张二值图 / Convert first binary map
    right = B.astype(bool)  # 转换第二张二值图 / Convert second binary map
    if not left.any() or not right.any():  # 检查空图 / Check empty maps
        return 0.0  # 空图没有有效相似度 / Empty maps have no useful similarity
    right_distance = chamfer_distance(right)  # 计算到第二张图的距离 / Compute distance to second map
    left_distance = chamfer_distance(left)  # 计算到第一张图的距离 / Compute distance to first map
    forward = float(right_distance[left].mean())  # 计算 A 到 B 的平均距离 / Compute average A-to-B distance
    backward = float(left_distance[right].mean())  # 计算 B 到 A 的平均距离 / Compute average B-to-A distance
    normalizer = max(float(np.hypot(*left.shape)), 1.0)  # 计算图像对角线归一化 / Compute diagonal normalizer
    distance = (forward + backward) / (2.0 * normalizer)  # 合成归一化双向距离 / Combine normalized bidirectional distance
    return float(1.0 / (1.0 + 12.0 * distance))  # 转成 0 到 1 的相似度 / Convert distance to 0..1 similarity


def frequency_penalty(frequency: float, f_min: float, f_max: float) -> float:  # 计算频率惩罚 / Compute frequency penalty
    if f_min <= frequency <= f_max:  # 判断频率是否在范围内 / Check whether frequency is in range
        return 0.0  # 范围内不惩罚 / No penalty in range
    if frequency < f_min:  # 判断频率是否过低 / Check whether frequency is too low
        return float((f_min - frequency) / max(f_min, 1.0))  # 返回低频惩罚 / Return low-frequency penalty
    return float((frequency - f_max) / max(f_max, 1.0))  # 返回高频惩罚 / Return high-frequency penalty


def pattern_similarity(iou: float, dice: float, distance_similarity: float = 0.0, overlap_balance: float = 0.0, layout: float = 0.0, area: float = 0.0, precision: float = 0.0, recall: float = 0.0, projection: float = 0.0, extent: float = 0.0, complexity: float = 0.0) -> float:  # 合成图案相似度 / Combine pattern similarity
    return float(0.08 * iou + 0.12 * dice + 0.06 * distance_similarity + 0.08 * overlap_balance + 0.08 * layout + 0.05 * area + 0.05 * precision + 0.20 * recall + 0.16 * projection + 0.08 * extent + 0.04 * complexity)  # 返回偏重完整覆盖的加权相似度 / Return coverage-weighted similarity
