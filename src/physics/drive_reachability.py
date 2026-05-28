from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import numpy as np  # 导入数值计算库 / Import numerical library


def center_region_mask(shape: tuple[int, int], radius_fraction: float = 0.07, radius_px: int | None = None) -> np.ndarray:  # 构造中心激励区域掩膜 / Build centre-drive region mask
    rows, cols = int(shape[0]), int(shape[1])  # 读取图像尺寸 / Read image dimensions
    yy, xx = np.ogrid[:rows, :cols]  # 构造行列坐标 / Build row-column coordinates
    center_y = (rows - 1) / 2.0  # 计算中心 y / Compute centre y
    center_x = (cols - 1) / 2.0  # 计算中心 x / Compute centre x
    radius = int(radius_px) if radius_px is not None else max(1, int(round(min(rows, cols) * float(radius_fraction))))  # 计算半径像素 / Compute radius in pixels
    return ((yy - center_y) ** 2 + (xx - center_x) ** 2 <= float(radius) ** 2).astype(bool)  # 返回圆形掩膜 / Return circular mask


def center_participation(fields: np.ndarray, radius_fraction: float = 0.07, radius_px: int | None = None, method: str = "mean_abs") -> tuple[np.ndarray, np.ndarray]:  # 计算每个模态的中心参与度 / Compute centre participation for each mode
    if fields.ndim != 3:  # 检查输入维度 / Check input rank
        raise ValueError("fields must have shape [num_modes, height, width]. / fields 必须是 [模态数, 高, 宽]。")  # 抛出维度错误 / Raise shape error
    mask = center_region_mask((fields.shape[1], fields.shape[2]), float(radius_fraction), radius_px)  # 构造中心掩膜 / Build centre mask
    region = np.asarray(fields, dtype=float)[:, mask]  # 取出中心区域值 / Select centre-region values
    if method == "rms":  # 检查 RMS 方法 / Check RMS method
        raw = np.sqrt(np.mean(np.square(region), axis=1))  # 计算均方根参与度 / Compute RMS participation
    else:  # 默认使用平均值绝对值 / Default to absolute mean
        raw = np.abs(np.mean(region, axis=1))  # 计算中心平均位移绝对值 / Compute absolute centre-mean displacement
    max_value = max(float(np.max(raw)), 1.0e-12)  # 计算归一化分母 / Compute normalization denominator
    normalised = (raw / max_value).astype(np.float32)  # 归一化到 0-1 / Normalize to 0-1
    return raw.astype(np.float32), normalised  # 返回原始和归一化参与度 / Return raw and normalized participation


def drive_reachability(alpha: np.ndarray, fields: np.ndarray, mode_ids: list[int], freqs: np.ndarray, radius_fraction: float = 0.07, radius_px: int | None = None, method: str = "mean_abs", dominant_count: int = 8) -> dict[str, object]:  # 计算中心驱动可达性 / Compute centre-drive reachability
    coeff = np.asarray(alpha, dtype=float).reshape(-1)  # 转成一维系数 / Convert to one-dimensional coefficients
    if fields.shape[0] != len(coeff):  # 检查模态数量一致性 / Check modal-count consistency
        raise ValueError("alpha and fields must use the same number of modes. / alpha 与 fields 的模态数量必须一致。")  # 抛出一致性错误 / Raise consistency error
    _raw, participation = center_participation(fields, float(radius_fraction), radius_px, method)  # 计算中心参与度 / Compute centre participation
    weights = np.square(np.abs(coeff))  # 计算系数能量权重 / Compute coefficient energy weights
    weights = weights / max(float(weights.sum()), 1.0e-12)  # 归一化权重 / Normalize weights
    score = float(np.sum(weights * participation))  # 计算加权可达性分数 / Compute weighted reachability score
    order = np.argsort(-weights)[: int(dominant_count)]  # 按权重选择主导模态 / Select dominant modes by weight
    dominant = [{"mode": float(mode_ids[index]), "frequency_hz": float(np.asarray(freqs, dtype=float)[index]), "weight": float(weights[index]), "center_participation": float(participation[index])} for index in order]  # 构造主导模态表 / Build dominant-mode table
    warning = "low_center_drive_reachability" if score < 0.25 else ""  # 低分时给出警告 / Emit warning on low score
    return {"R_drive": score, "center_participation": participation, "dominant_modes": dominant, "warning": warning, "method": method, "radius_fraction": float(radius_fraction), "radius_px": None if radius_px is None else int(radius_px)}  # 返回诊断结果 / Return diagnostic result
