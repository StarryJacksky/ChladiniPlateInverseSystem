from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import numpy as np  # 导入数值库 / Import numerical library


def chladni_powder_density(amplitude_grid: np.ndarray, sigma_rel: float = 0.05) -> np.ndarray:  # 估算 Chladni 撒粉密度 / Estimate Chladni powder density
    peak = float(np.max(np.abs(amplitude_grid)))  # 取绝对最大 / Absolute max
    if peak <= 0.0:  # 全零保护 / Guard zero field
        return np.ones_like(amplitude_grid, dtype=np.float64)  # 全粉 / All powder
    norm = np.abs(amplitude_grid).astype(np.float64) / peak  # 用 max 归一化（避免与 COMSOL 1e-12 量级冲突的加性 epsilon） / Use multiplicative max normalisation to avoid additive-epsilon bug at COMSOL 1e-12 scale
    return np.exp(-((norm / float(sigma_rel)) ** 2))  # 高斯撒粉模型 / Gaussian powder model


def enrichment_factor(amplitude_grid: np.ndarray, target_binary: np.ndarray, sigma_rel: float = 0.05) -> float:  # 计算撒粉富集倍数 / Compute powder enrichment factor
    target = target_binary.astype(bool)  # 目标二值 / Target binary
    if int(target.sum()) == 0:  # 空目标保护 / Guard empty target
        return 0.0  # 返回零 / Return zero
    powder = chladni_powder_density(amplitude_grid, sigma_rel=float(sigma_rel))  # 撒粉密度 / Powder density
    total_powder = float(powder.sum()) + 1.0e-9  # 总粉量 / Total powder
    target_powder = float(powder[target].sum())  # 目标区粉量 / Target-zone powder
    target_area_fraction = float(target.sum()) / float(target.size)  # 目标占地比例 / Target area fraction
    return (target_powder / total_powder) / max(target_area_fraction, 1.0e-9)  # 富集倍数 / Enrichment factor


def coverage_recall(amplitude_grid: np.ndarray, target_binary: np.ndarray, percentile: float = 20.0) -> float:  # 目标线被低振幅区覆盖的比例 / Fraction of target covered by low-amplitude valley
    target = target_binary.astype(bool)  # 目标 / Target
    if int(target.sum()) == 0:  # 空目标保护 / Guard empty
        return 0.0  # 零 / Zero
    peak = float(np.max(np.abs(amplitude_grid)))  # 绝对最大 / Absolute max
    if peak <= 0.0:  # 全零 / Empty
        return 1.0  # 全部 / All
    norm = np.abs(amplitude_grid).astype(np.float64) / peak  # 用 max 归一化（修复 1e-9 加性 epsilon bug） / Multiplicative max normalisation (fix additive 1e-9 epsilon bug)
    threshold = float(np.percentile(norm, float(percentile)))  # 第 K 分位数阈值 / Percentile threshold
    valley = norm < threshold  # 低振幅掩码 / Valley mask
    return float((target & valley).sum()) / float(target.sum())  # recall / Recall


def gaussian_contrast(amplitude_grid: np.ndarray, target_binary: np.ndarray, sigma_rel: float = 0.05) -> float:  # 高斯加权目标 vs 背景对比度 / Gaussian-weighted target-vs-background contrast
    target = target_binary.astype(bool)  # 目标 / Target
    if int(target.sum()) == 0 or int((~target).sum()) == 0:  # 边界保护 / Boundary guards
        return 0.0  # 零 / Zero
    powder = chladni_powder_density(amplitude_grid, sigma_rel=float(sigma_rel))  # 撒粉密度 / Powder density
    mean_target = float(powder[target].mean())  # 目标区均值 / Target mean
    mean_background = float(powder[~target].mean()) + 1.0e-9  # 背景区均值 / Background mean
    return mean_target / mean_background  # 对比度 / Contrast


def directional_alignment(amplitude_grid: np.ndarray, target_binary: np.ndarray, sigma_rel: float = 0.05) -> float:  # 撒粉主方向与目标主方向的余弦相似度 / Cosine alignment between powder and target principal axes
    target = target_binary.astype(bool)  # 目标 / Target
    if int(target.sum()) < 10:  # 目标太小 / Target too small
        return 0.0  # 零 / Zero
    powder = chladni_powder_density(amplitude_grid, sigma_rel=float(sigma_rel))  # 撒粉密度 / Powder density
    yy, xx = np.indices(amplitude_grid.shape, dtype=np.float64)  # 像素坐标 / Pixel coords
    coords_target = np.stack([yy[target], xx[target]], axis=1)  # 目标坐标 / Target coords
    coords_target = coords_target - coords_target.mean(axis=0, keepdims=True)  # 去均值 / Centre
    cov_t = (coords_target.T @ coords_target) / max(len(coords_target), 1)  # 协方差 / Covariance
    eigvals_t, eigvecs_t = np.linalg.eigh(cov_t)  # 主轴 / Principal axes
    main_axis_t = eigvecs_t[:, np.argmax(eigvals_t)]  # 目标主方向 / Target main direction
    w = powder.flatten()  # 粉密度权重 / Powder weights
    if float(w.sum()) <= 1.0e-9:  # 没有撒粉 / No powder
        return 0.0  # 零 / Zero
    coords_p = np.stack([yy.flatten(), xx.flatten()], axis=1)  # 全图坐标 / All coords
    mean_p = (coords_p * w[:, None]).sum(axis=0) / max(float(w.sum()), 1.0e-9)  # 加权均值 / Weighted mean
    centred = coords_p - mean_p  # 去均值 / Centre
    cov_p = (centred.T * w) @ centred / max(float(w.sum()), 1.0e-9)  # 加权协方差 / Weighted covariance
    eigvals_p, eigvecs_p = np.linalg.eigh(cov_p)  # 主轴 / Principal axes
    main_axis_p = eigvecs_p[:, np.argmax(eigvals_p)]  # 粉主方向 / Powder main direction
    return float(abs(main_axis_t @ main_axis_p))  # |余弦| / |cosine|


def recognisability_score_grid(amplitude_grid: np.ndarray, target_binary: np.ndarray, sigma_rel: float = 0.05, percentile: float = 20.0) -> dict[str, float]:  # 综合可识别度评分 / Composite recognisability scoring
    enrichment = float(enrichment_factor(amplitude_grid, target_binary, sigma_rel=float(sigma_rel)))  # 富集 / Enrichment
    recall = float(coverage_recall(amplitude_grid, target_binary, percentile=float(percentile)))  # recall / Recall
    contrast = float(gaussian_contrast(amplitude_grid, target_binary, sigma_rel=float(sigma_rel)))  # 高斯对比 / Gaussian contrast
    direction = float(directional_alignment(amplitude_grid, target_binary, sigma_rel=float(sigma_rel)))  # 方向 / Direction
    composite = float(0.40 * np.clip(np.log1p(max(enrichment - 1.0, 0.0)), 0.0, 2.0) + 0.30 * recall + 0.20 * np.clip(np.log1p(max(contrast - 1.0, 0.0)), 0.0, 2.0) + 0.10 * direction)  # 综合 / Composite
    return {"enrichment_factor": enrichment, "coverage_recall": recall, "gaussian_contrast": contrast, "directional_alignment": direction, "composite_recognisability": composite, "sigma_rel": float(sigma_rel), "percentile": float(percentile)}  # 返回字典 / Return dict


def score_frequency_response_recognisability(frequency_response_csv: str, target_binary: np.ndarray, image_size: int = 256, sigma_rel: float = 0.05, percentile: float = 20.0) -> dict[str, object]:  # 用新指标扫描频率响应 CSV / Recognisability-rank a frequency-response CSV
    from src.frequency_domain.load_frequency_response import load_frequency_response  # 延迟导入 / Lazy import
    responses, _ = load_frequency_response(frequency_response_csv, int(image_size))  # 加载 / Load
    if not responses:  # 空响应 / Empty
        return {"best": None, "rows": []}  # 空结果 / Empty result
    rows: list[dict[str, object]] = []  # 行列表 / Row list
    best_row: dict[str, object] | None = None  # 最佳 / Best
    for freq in sorted(responses.keys()):  # 遍历频率 / Iterate
        amp = responses[freq]  # 振幅图 / Amplitude grid
        scores = recognisability_score_grid(amp, target_binary, sigma_rel=float(sigma_rel), percentile=float(percentile))  # 评分 / Score
        row = {"frequency_hz": float(freq), **scores}  # 行字典 / Row dict
        rows.append(row)  # 追加 / Append
        if best_row is None or float(row["composite_recognisability"]) > float(best_row["composite_recognisability"]):  # 比较 / Compare
            best_row = row  # 更新 / Update
    return {"best": best_row, "rows": rows}  # 返回 / Return
