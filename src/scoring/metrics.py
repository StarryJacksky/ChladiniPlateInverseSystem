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


def frequency_penalty(frequency: float, f_min: float, f_max: float) -> float:  # 计算频率惩罚 / Compute frequency penalty
    if f_min <= frequency <= f_max:  # 判断频率是否在范围内 / Check whether frequency is in range
        return 0.0  # 范围内不惩罚 / No penalty in range
    if frequency < f_min:  # 判断频率是否过低 / Check whether frequency is too low
        return float((f_min - frequency) / max(f_min, 1.0))  # 返回低频惩罚 / Return low-frequency penalty
    return float((frequency - f_max) / max(f_max, 1.0))  # 返回高频惩罚 / Return high-frequency penalty


def pattern_similarity(iou: float, dice: float) -> float:  # 合成图案相似度 / Combine pattern similarity
    return float(0.3 * iou + 0.7 * dice)  # 返回加权相似度 / Return weighted similarity
