from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import numpy as np  # 导入数值计算库 / Import numerical library

SCORING_VERSION = "strict_precision_topology_v5"  # 记录当前评分口径版本 / Record current scoring-rule version

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


def connected_component_count(binary: np.ndarray, min_pixels: int = 4) -> int:  # 计算前景连通块数量 / Count foreground connected components
    data = binary.astype(bool)  # 转换布尔图 / Convert to boolean map
    visited = np.zeros(data.shape, dtype=bool)  # 创建访问标记 / Create visited flags
    rows, cols = data.shape  # 读取图像尺寸 / Read image shape
    count = 0  # 初始化连通块计数 / Initialize component count
    for start_row, start_col in np.argwhere(data):  # 遍历所有前景像素 / Iterate all foreground pixels
        start = (int(start_row), int(start_col))  # 转换起点坐标 / Convert start coordinate
        if visited[start]:  # 检查是否已访问 / Check whether already visited
            continue  # 跳过已访问像素 / Skip visited pixel
        visited[start] = True  # 标记起点已访问 / Mark start visited
        stack = [start]  # 创建深度搜索栈 / Create depth-first stack
        size = 0  # 初始化当前块大小 / Initialize current component size
        while stack:  # 遍历当前连通块 / Traverse current component
            row, col = stack.pop()  # 取出一个像素 / Pop one pixel
            size += 1  # 累加块大小 / Increase component size
            for next_row, next_col in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):  # 遍历四邻域 / Iterate four-neighbourhood
                if 0 <= next_row < rows and 0 <= next_col < cols and data[next_row, next_col] and not visited[next_row, next_col]:  # 检查邻居是否可加入 / Check whether neighbour can join
                    visited[next_row, next_col] = True  # 标记邻居已访问 / Mark neighbour visited
                    stack.append((next_row, next_col))  # 加入搜索栈 / Add neighbour to stack
        if size >= min_pixels:  # 忽略极小噪声块 / Ignore tiny noise components
            count += 1  # 记录有效连通块 / Count valid component
    return count  # 返回连通块数量 / Return component count


def component_similarity(A: np.ndarray, B: np.ndarray) -> float:  # 计算连通拓扑相似度 / Compute connected-topology similarity
    left_count = connected_component_count(A)  # 计算第一张图连通块 / Count first-map components
    right_count = connected_component_count(B)  # 计算第二张图连通块 / Count second-map components
    if left_count == 0 and right_count == 0:  # 检查双空图 / Check both-empty maps
        return 1.0  # 双空拓扑一致 / Both empty maps match topologically
    denominator = max(left_count, right_count, 1)  # 计算归一化分母 / Compute normalization denominator
    return float(max(0.0, 1.0 - abs(left_count - right_count) / denominator))  # 返回连通块数量相似度 / Return component-count similarity


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


def coverage_f_score(precision: float, recall: float) -> float:  # 计算覆盖 F 分数 / Compute coverage F-score
    denominator = precision + recall  # 计算调和均值分母 / Compute harmonic-mean denominator
    if denominator <= 1.0e-12:  # 检查空精度召回 / Check empty precision-recall pair
        return 0.0  # 返回零分 / Return zero score
    return float(2.0 * precision * recall / denominator)  # 返回 F1 覆盖分 / Return F1 coverage score


def overcoverage_penalty(precision: float, recall: float, area: float) -> float:  # 计算过覆盖惩罚 / Compute overcoverage penalty
    recall_precision_gap = max(0.0, recall - precision)  # 读取只靠召回撑分的差距 / Read recall-over-precision gap
    area_gap = max(0.0, 1.0 - area)  # 读取面积不匹配程度 / Read area mismatch level
    return float(0.70 * recall_precision_gap + 0.30 * area_gap * recall_precision_gap)  # 返回过覆盖惩罚 / Return overcoverage penalty


def centerline_overreach_penalty(A: np.ndarray, B: np.ndarray) -> float:  # 惩罚中心十字和辐射骨架 / Penalize centre-cross and radiating skeletons
    left = A.astype(bool)  # 转换仿真图 / Convert simulated map
    right = B.astype(bool)  # 转换目标图 / Convert target map
    rows, cols = left.shape  # 读取图像尺寸 / Read map shape
    yy, xx = np.meshgrid(np.linspace(-1.0, 1.0, rows), np.linspace(-1.0, 1.0, cols), indexing="ij")  # 构造归一化坐标 / Build normalized coordinates
    radius = np.sqrt(xx * xx + yy * yy)  # 计算半径 / Compute radius
    central = radius < 0.34  # 定义中心区域 / Define central zone
    edge = (np.abs(xx) > 0.78) | (np.abs(yy) > 0.78)  # 定义边缘区域 / Define edge zone
    simulated_centre = float(left[central].mean()) if central.any() else 0.0  # 计算仿真中心占用 / Compute simulated centre occupancy
    target_centre = float(right[central].mean()) if central.any() else 0.0  # 计算目标中心占用 / Compute target centre occupancy
    simulated_edge = float(left[edge].mean()) if edge.any() else 0.0  # 计算仿真边缘占用 / Compute simulated edge occupancy
    target_edge = float(right[edge].mean()) if edge.any() else 0.0  # 计算目标边缘占用 / Compute target edge occupancy
    centre_excess = float(np.clip((simulated_centre - target_centre - 0.035) / 0.24, 0.0, 1.0))  # 计算中心过量 / Compute centre excess
    edge_excess = float(np.clip((simulated_edge - target_edge - 0.025) / 0.20, 0.0, 1.0))  # 计算边缘过量 / Compute edge excess
    horizontal = np.abs(yy) < 0.12  # 定义水平中心带 / Define horizontal centre band
    vertical = np.abs(xx) < 0.12  # 定义垂直中心带 / Define vertical centre band
    simulated_cross = 0.5 * (float(left[horizontal].mean()) + float(left[vertical].mean()))  # 计算仿真十字占用 / Compute simulated cross occupancy
    target_cross = 0.5 * (float(right[horizontal].mean()) + float(right[vertical].mean()))  # 计算目标十字占用 / Compute target cross occupancy
    cross_excess = float(np.clip((simulated_cross - target_cross - 0.035) / 0.25, 0.0, 1.0))  # 计算十字过量 / Compute cross excess
    return float(np.clip(0.44 * centre_excess + 0.30 * centre_excess * edge_excess + 0.26 * cross_excess, 0.0, 1.0))  # 返回中心骨架惩罚 / Return centre-skeleton penalty


def pattern_similarity(iou: float, dice: float, distance_similarity: float = 0.0, overlap_balance: float = 0.0, layout: float = 0.0, area: float = 0.0, precision: float = 0.0, recall: float = 0.0, projection: float = 0.0, extent: float = 0.0, complexity: float = 0.0, topology: float = 0.0, centerline_penalty: float = 0.0) -> float:  # 合成图案相似度 / Combine pattern similarity
    balance = coverage_f_score(precision, recall)  # 计算精度召回平衡分 / Compute precision-recall balance score
    raw = 0.10 * iou + 0.15 * dice + 0.06 * distance_similarity + 0.15 * overlap_balance + 0.06 * layout + 0.03 * area + 0.16 * precision + 0.04 * recall + 0.10 * projection + 0.04 * extent + 0.03 * complexity + 0.04 * balance + 0.04 * topology  # 合成偏精确和拓扑的基础分 / Combine precision-and-topology-biased base score
    penalty = overcoverage_penalty(precision, recall, area)  # 计算多余响应惩罚 / Compute extra-response penalty
    precision_gate = float(np.clip(precision / 0.34, 0.0, 1.0))  # 构造精度硬门控 / Build precision hard gate
    balance_gate = float(np.clip(balance / 0.32, 0.0, 1.0))  # 构造 F 分数硬门控 / Build F-score hard gate
    topology_gate = 0.15 + 0.85 * float(np.clip(topology, 0.0, 1.0))  # 构造拓扑硬门控 / Build topology hard gate
    gated = raw * max(0.05, 0.58 * precision_gate + 0.42 * balance_gate) * topology_gate  # 应用硬门控压低假匹配 / Apply hard gates to suppress false matches
    return float(max(0.0, gated - 0.22 * penalty - 0.20 * centerline_penalty))  # 返回严格抑制过覆盖和中心骨架后的相似度 / Return strictly overcoverage-and-centre-skeleton-suppressed similarity
