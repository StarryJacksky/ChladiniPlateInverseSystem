from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import numpy as np  # 导入数值计算库 / Import numerical library


def center_cells_for_grid(grid_size: int) -> list[tuple[int, int]]:  # 计算中心单元 / Compute center cells
    if grid_size % 2 == 1:  # 判断是否为奇数网格 / Check whether grid is odd
        center = grid_size // 2  # 计算中心索引 / Compute center index
        return [(center, center)]  # 返回单个中心单元 / Return single center cell
    left = grid_size // 2 - 1  # 中心左上索引 / Top-left center index
    right = grid_size // 2  # 中心右下索引 / Bottom-right center index
    return [(left, left), (left, right), (right, left), (right, right)]  # 返回 2x2 中心单元 / Return 2x2 center cells


def enforce_center_constraint(H: np.ndarray, center_cells: list[tuple[int, int]], fixed_thickness: float) -> np.ndarray:  # 固定中心区域 / Fix center area
    constrained = H.copy()  # 复制厚度矩阵 / Copy thickness matrix
    for row, col in center_cells:  # 遍历中心单元 / Iterate center cells
        constrained[row, col] = fixed_thickness  # 设置固定厚度 / Set fixed thickness
    return constrained  # 返回约束后矩阵 / Return constrained matrix


def check_neighbor_constraint(H: np.ndarray, max_diff: float) -> bool:  # 检查相邻厚度差 / Check neighbour thickness difference
    row_diff = np.abs(np.diff(H, axis=0))  # 计算上下相邻差 / Compute vertical differences
    col_diff = np.abs(np.diff(H, axis=1))  # 计算左右相邻差 / Compute horizontal differences
    return bool(np.all(row_diff <= max_diff) and np.all(col_diff <= max_diff))  # 返回是否满足约束 / Return whether constraint passes


def nearest_allowed_level(value: float, levels: list[float]) -> float:  # 找最近厚度等级 / Find nearest thickness level
    level_array = np.asarray(levels, dtype=float)  # 转为数组 / Convert to array
    index = int(np.argmin(np.abs(level_array - value)))  # 找最小差值索引 / Find nearest index
    return float(level_array[index])  # 返回最近等级 / Return nearest level


def repair_neighbor_constraint(H: np.ndarray, levels: list[float], max_diff: float, passes: int = 12, fixed_cells: list[tuple[int, int]] | None = None) -> np.ndarray:  # 修复相邻约束 / Repair neighbour constraint
    repaired = H.copy()  # 复制矩阵 / Copy matrix
    rows, cols = repaired.shape  # 获取矩阵尺寸 / Get matrix size
    fixed = set(fixed_cells or [])  # 创建固定单元集合 / Create fixed-cell set
    for _ in range(passes):  # 多轮平滑修复 / Run several repair passes
        for row in range(rows):  # 遍历行 / Iterate rows
            for col in range(cols):  # 遍历列 / Iterate columns
                if (row, col) in fixed:  # 判断是否为固定单元 / Check fixed cell
                    continue  # 跳过固定单元 / Skip fixed cell
                neighbours = []  # 创建邻居列表 / Create neighbour list
                if row > 0:  # 判断上邻居 / Check upper neighbour
                    neighbours.append(repaired[row - 1, col])  # 加入上邻居 / Add upper neighbour
                if row + 1 < rows:  # 判断下邻居 / Check lower neighbour
                    neighbours.append(repaired[row + 1, col])  # 加入下邻居 / Add lower neighbour
                if col > 0:  # 判断左邻居 / Check left neighbour
                    neighbours.append(repaired[row, col - 1])  # 加入左邻居 / Add left neighbour
                if col + 1 < cols:  # 判断右邻居 / Check right neighbour
                    neighbours.append(repaired[row, col + 1])  # 加入右邻居 / Add right neighbour
                average = float(np.mean(neighbours)) if neighbours else float(repaired[row, col])  # 计算邻居均值 / Compute neighbour average
                if any(abs(repaired[row, col] - neighbour) > max_diff for neighbour in neighbours):  # 检查是否违规 / Check whether cell violates constraint
                    valid_levels = [level for level in levels if all(abs(float(level) - float(neighbour)) <= max_diff for neighbour in neighbours)]  # 筛选满足邻居约束的等级 / Filter neighbour-compatible levels
                    repaired[row, col] = nearest_allowed_level(average, valid_levels or levels)  # 调整到最近可行等级 / Move to nearest feasible level
        if check_neighbor_constraint(repaired, max_diff):  # 判断是否已修好 / Check whether repaired
            break  # 结束修复循环 / Stop repair loop
    return repaired  # 返回修复结果 / Return repaired result


def repair_continuous_neighbor_constraint(H: np.ndarray, h_min: float, h_max: float, max_diff: float, passes: int = 12, fixed_cells: list[tuple[int, int]] | None = None) -> np.ndarray:  # 修复连续厚度相邻约束 / Repair continuous-thickness neighbour constraint
    repaired = np.clip(H.astype(float), h_min, h_max)  # 裁剪到厚度范围 / Clip to thickness range
    rows, cols = repaired.shape  # 获取矩阵尺寸 / Get matrix size
    fixed = set(fixed_cells or [])  # 创建固定单元集合 / Create fixed-cell set
    for _ in range(passes):  # 多轮连续修复 / Run continuous repair passes
        for row in range(rows):  # 遍历行 / Iterate rows
            for col in range(cols):  # 遍历列 / Iterate columns
                if (row, col) in fixed:  # 判断是否为固定单元 / Check fixed cell
                    continue  # 跳过固定单元 / Skip fixed cell
                neighbours = []  # 创建邻居列表 / Create neighbour list
                if row > 0:  # 判断上邻居 / Check upper neighbour
                    neighbours.append(repaired[row - 1, col])  # 加入上邻居 / Add upper neighbour
                if row + 1 < rows:  # 判断下邻居 / Check lower neighbour
                    neighbours.append(repaired[row + 1, col])  # 加入下邻居 / Add lower neighbour
                if col > 0:  # 判断左邻居 / Check left neighbour
                    neighbours.append(repaired[row, col - 1])  # 加入左邻居 / Add left neighbour
                if col + 1 < cols:  # 判断右邻居 / Check right neighbour
                    neighbours.append(repaired[row, col + 1])  # 加入右邻居 / Add right neighbour
                lower = max([h_min] + [float(value) - max_diff for value in neighbours])  # 计算允许下界 / Compute allowed lower bound
                upper = min([h_max] + [float(value) + max_diff for value in neighbours])  # 计算允许上界 / Compute allowed upper bound
                repaired[row, col] = float(np.clip(repaired[row, col], lower, upper))  # 裁剪当前单元 / Clip current cell
        if check_neighbor_constraint(repaired, max_diff):  # 判断是否已满足约束 / Check whether constraint is satisfied
            break  # 停止修复 / Stop repair
    return np.round(repaired, 3)  # 返回三位小数连续厚度 / Return continuous thickness rounded to 0.001 mm


def roughness_penalty(H: np.ndarray) -> float:  # 计算粗糙度惩罚 / Compute roughness penalty
    row_penalty = np.square(np.diff(H, axis=0)).sum()  # 计算上下差平方和 / Sum vertical squared differences
    col_penalty = np.square(np.diff(H, axis=1)).sum()  # 计算左右差平方和 / Sum horizontal squared differences
    return float(row_penalty + col_penalty)  # 返回总惩罚 / Return total penalty


def normalized_roughness_penalty(H: np.ndarray, h_min: float, h_max: float) -> float:  # 计算归一化粗糙度惩罚 / Compute normalized roughness penalty
    raw = roughness_penalty(H)  # 计算原始粗糙度 / Compute raw roughness
    rows, cols = H.shape  # 读取矩阵尺寸 / Read matrix shape
    edge_count = rows * max(cols - 1, 0) + cols * max(rows - 1, 0)  # 计算相邻边数量 / Count neighbour edges
    span = max(float(h_max) - float(h_min), 1.0e-9)  # 计算厚度范围 / Compute thickness span
    return float(raw / max(edge_count * span * span, 1.0e-9))  # 返回 0 附近到 1 附近的惩罚 / Return near-0 to near-1 penalty


def mass_penalty(H: np.ndarray, h_min: float, h_max: float) -> float:  # 计算质量惩罚 / Compute mass penalty
    return float((H.mean() - h_min) / (h_max - h_min))  # 返回归一化平均厚度 / Return normalised mean thickness
