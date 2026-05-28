from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import numpy as np  # 导入数值计算库 / Import numerical library

from src.target.preprocess_target import skeletonize_binary  # 复用项目内骨架化 / Reuse in-repo skeletonisation

try:  # 优先使用 scikit-image 骨架化 / Prefer scikit-image skeletonisation
    from skimage.morphology import skeletonize as skimage_skeletonize  # 导入 skimage 骨架化 / Import skimage skeletonisation helper
except Exception:  # 兼容未安装环境 / Support deployments without skimage
    skimage_skeletonize = None  # 标记不可用 / Mark unavailable


def resize_binary_nearest(binary: np.ndarray, image_size: int) -> np.ndarray:  # 最近邻缩放二值图 / Resize binary map by nearest neighbour
    data = binary.astype(bool)  # 转布尔图 / Convert to boolean map
    if data.shape == (image_size, image_size):  # 检查尺寸是否已匹配 / Check whether shape already matches
        return data  # 直接返回 / Return as-is
    row_index = np.rint(np.linspace(0, data.shape[0] - 1, image_size)).astype(int)  # 行采样索引 / Row sampling indices
    col_index = np.rint(np.linspace(0, data.shape[1] - 1, image_size)).astype(int)  # 列采样索引 / Column sampling indices
    return data[np.ix_(row_index, col_index)].astype(bool)  # 返回重采样布尔图 / Return resampled boolean map


def build_center_valid_mask(shape: tuple[int, int], center_radius_px: int) -> np.ndarray:  # 构造去中心夹持的有效掩膜 / Build valid mask excluding centre clamp
    mask = np.ones(shape, dtype=bool)  # 默认全有效 / Mark all valid by default
    if center_radius_px <= 0:  # 检查是否禁用中心移除 / Check whether centre removal is disabled
        return mask  # 返回全有效 / Return all valid
    rows, cols = shape  # 读取尺寸 / Read shape
    yy, xx = np.ogrid[:rows, :cols]  # 构造坐标 / Build coordinates
    center_y = (rows - 1) / 2.0  # 中心 y / Centre y
    center_x = (cols - 1) / 2.0  # 中心 x / Centre x
    mask[(yy - center_y) ** 2 + (xx - center_x) ** 2 <= center_radius_px**2] = False  # 移除中心区 / Remove centre region
    return mask  # 返回有效掩膜 / Return valid mask


def build_target_skeleton(target_binary: np.ndarray) -> np.ndarray:  # 构造目标骨架 / Build target skeleton
    if skimage_skeletonize is not None:  # 优先使用 skimage / Prefer skimage
        skeleton = skimage_skeletonize(target_binary.astype(bool))  # 用 skimage 骨架化 / Skeletonise with skimage
    else:  # 退回项目内 Zhang-Suen / Fall back to in-repo Zhang-Suen
        skeleton = skeletonize_binary(target_binary.astype(bool))  # 用项目内骨架化 / Skeletonise with in-repo helper
    if skeleton.any():  # 检查骨架非空 / Check non-empty skeleton
        return skeleton.astype(bool)  # 返回骨架 / Return skeleton
    return target_binary.astype(bool)  # 退回原目标 / Fall back to original target
