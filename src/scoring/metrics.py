from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import numpy as np  # 导入数值计算库 / Import numerical library


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


def chamfer_distance(binary: np.ndarray) -> np.ndarray:  # 计算到最近前景像素的近似距离 / Compute approximate distance to nearest foreground pixel
    data = binary.astype(bool)  # 转为布尔图 / Convert to boolean map
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


def pattern_similarity(iou: float, dice: float, distance_similarity: float = 0.0, overlap_balance: float = 0.0, layout: float = 0.0) -> float:  # 合成图案相似度 / Combine pattern similarity
    return float(0.18 * iou + 0.22 * dice + 0.18 * distance_similarity + 0.24 * overlap_balance + 0.18 * layout)  # 返回加权相似度 / Return weighted similarity
