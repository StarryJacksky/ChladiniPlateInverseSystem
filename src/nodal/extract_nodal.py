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


def postprocess_nodal_region(nodal: np.ndarray, min_size: int = 20, dilation_iters: int = 1) -> np.ndarray:  # 后处理节点线 / Postprocess nodal region
    _ = min_size  # 保留参数以便后续升级 / Keep parameter for future upgrade
    cleaned = nodal.astype(bool)  # 转为布尔节点图 / Convert to boolean nodal map
    dilated = binary_dilation(cleaned, dilation_iters)  # 轻微膨胀线条 / Slightly dilate lines
    return dilated.astype(bool)  # 返回后处理结果 / Return postprocessed result
