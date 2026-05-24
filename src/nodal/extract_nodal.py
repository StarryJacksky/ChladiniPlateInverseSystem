from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import numpy as np  # 导入数值计算库 / Import numerical library


def extract_nodal_region(W: np.ndarray, epsilon_ratio: float = 0.05) -> np.ndarray:  # 提取节点线区域 / Extract nodal region
    max_abs = float(np.max(np.abs(W)))  # 计算最大绝对位移 / Compute maximum absolute displacement
    if max_abs == 0.0:  # 判断是否为空位移场 / Check whether displacement field is empty
        return np.zeros_like(W, dtype=bool)  # 返回空节点图 / Return empty nodal map
    W_norm = W / max_abs  # 归一化位移场 / Normalise displacement field
    nodal = np.abs(W_norm) < epsilon_ratio  # 提取接近零位移区域 / Extract near-zero displacement region
    return nodal.astype(bool)  # 返回布尔节点图 / Return boolean nodal map


def binary_dilation(binary: np.ndarray, iterations: int) -> np.ndarray:  # 执行简单二值膨胀 / Run simple binary dilation
    result = binary.astype(bool)  # 转为布尔数组 / Convert to boolean array
    for _ in range(iterations):  # 遍历膨胀次数 / Iterate dilation passes
        padded = np.pad(result, 1, mode="constant", constant_values=False)  # 给图像加边框 / Pad image border
        result = padded[1:-1, 1:-1] | padded[:-2, 1:-1] | padded[2:, 1:-1] | padded[1:-1, :-2] | padded[1:-1, 2:]  # 十字邻域膨胀 / Cross-neighbour dilation
    return result  # 返回膨胀结果 / Return dilated result


def remove_center_region(binary: np.ndarray, radius_px: int) -> np.ndarray:  # 移除中心夹持区 / Remove centre clamp region
    height, width = binary.shape  # 获取图像尺寸 / Get image dimensions
    yy, xx = np.ogrid[:height, :width]  # 创建坐标网格 / Create coordinate grid
    center_y = (height - 1) / 2.0  # 计算中心 y 坐标 / Compute centre y coordinate
    center_x = (width - 1) / 2.0  # 计算中心 x 坐标 / Compute centre x coordinate
    mask = (yy - center_y) ** 2 + (xx - center_x) ** 2 <= radius_px**2  # 生成中心圆形掩膜 / Build centre circular mask
    cleaned = binary.copy().astype(bool)  # 复制二值图 / Copy binary map
    cleaned[mask] = False  # 清除中心区域 / Clear centre region
    return cleaned  # 返回清理后结果 / Return cleaned result


def remove_small_components(binary: np.ndarray, min_size: int) -> np.ndarray:  # 移除小连通域 / Remove small connected components
    if min_size <= 1:  # 检查是否无需过滤 / Check whether filtering is unnecessary
        return binary.astype(bool)  # 直接返回布尔图 / Return boolean map
    data = binary.astype(bool)  # 转为布尔数组 / Convert to boolean array
    visited = np.zeros_like(data, dtype=bool)  # 创建访问标记 / Create visited mask
    cleaned = np.zeros_like(data, dtype=bool)  # 创建清理结果 / Create cleaned map
    rows, cols = data.shape  # 获取尺寸 / Get dimensions
    for row in range(rows):  # 遍历行 / Iterate rows
        for col in range(cols):  # 遍历列 / Iterate columns
            if visited[row, col] or not data[row, col]:  # 检查是否跳过 / Check whether to skip
                continue  # 跳过已访问或背景 / Skip visited or background
            stack = [(row, col)]  # 创建搜索栈 / Create search stack
            component = []  # 创建连通域列表 / Create component list
            visited[row, col] = True  # 标记起点 / Mark start point
            while stack:  # 搜索连通域 / Search connected component
                current_row, current_col = stack.pop()  # 取出当前像素 / Pop current pixel
                component.append((current_row, current_col))  # 保存当前像素 / Store current pixel
                for next_row, next_col in ((current_row - 1, current_col), (current_row + 1, current_col), (current_row, current_col - 1), (current_row, current_col + 1)):  # 遍历四邻域 / Iterate four-neighbourhood
                    if 0 <= next_row < rows and 0 <= next_col < cols and data[next_row, next_col] and not visited[next_row, next_col]:  # 检查邻居是否有效 / Check valid neighbour
                        visited[next_row, next_col] = True  # 标记邻居 / Mark neighbour
                        stack.append((next_row, next_col))  # 加入搜索栈 / Add neighbour to stack
            if len(component) >= min_size:  # 检查连通域大小 / Check component size
                for keep_row, keep_col in component:  # 遍历保留像素 / Iterate pixels to keep
                    cleaned[keep_row, keep_col] = True  # 写入清理结果 / Store cleaned pixel
    return cleaned  # 返回清理结果 / Return cleaned map


def postprocess_nodal_region(nodal: np.ndarray, min_size: int = 20, dilation_iters: int = 1) -> np.ndarray:  # 后处理节点线 / Postprocess nodal region
    cleaned = nodal.astype(bool)  # 转为布尔节点图 / Convert to boolean nodal map
    cleaned = remove_small_components(cleaned, min_size)  # 移除小孤立区域 / Remove small isolated regions
    dilated = binary_dilation(cleaned, dilation_iters)  # 轻微膨胀线条 / Slightly dilate lines
    return dilated.astype(bool)  # 返回后处理结果 / Return postprocessed result
