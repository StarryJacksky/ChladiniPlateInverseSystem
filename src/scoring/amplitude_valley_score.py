from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 读取工具 / Import CSV reading utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
from scipy.ndimage import distance_transform_edt  # 导入距离变换 / Import distance transform

from src.comsol.import_results import interpolate_to_grid  # 导入散点插值 / Import scattered interpolation
from src.scoring.metrics import chamfer_similarity  # 导入 Chamfer 相似度 / Import Chamfer similarity
from src.scoring.metrics import compute_dice  # 导入 Dice 指标 / Import Dice metric
from src.scoring.metrics import compute_iou  # 导入 IoU 指标 / Import IoU metric
from src.scoring.metrics import layout_similarity  # 导入布局相似度 / Import layout similarity
from src.scoring.geometry_helpers import build_target_skeleton  # 复用目标骨架构造 / Reuse target skeleton builder
from src.scoring.geometry_helpers import resize_binary_nearest  # 复用目标缩放 / Reuse target resizing helper


MAGNITUDE_COLUMNS = ("abs_uz", "w_abs", "abs", "amplitude", "magnitude", "uz_abs", "u_abs")  # 定义振幅列候选 / Define magnitude-column candidates
REAL_COLUMNS = ("real_uz", "w_real", "real", "uz_real", "u_real", "real_w")  # 定义实部列候选 / Define real-column candidates
IMAG_COLUMNS = ("imag_uz", "w_imag", "imag", "uz_imag", "u_imag", "imag_w")  # 定义虚部列候选 / Define imaginary-column candidates


def _normalise_key(text: str) -> str:  # 规范化表头 / Normalize header key
    return text.strip().lower().replace(" ", "_")  # 小写并替换空格 / Lowercase and replace spaces


def _pick_column(field_map: dict[str, str], candidates: tuple[str, ...]) -> str | None:  # 从候选列里选一个 / Pick one column from candidates
    for candidate in candidates:  # 遍历候选名称 / Iterate candidate names
        key = _normalise_key(candidate)  # 规范化候选名称 / Normalize candidate name
        if key in field_map:  # 检查是否命中 / Check whether candidate exists
            return field_map[key]  # 返回原始列名 / Return original column name
    return None  # 未命中则返回空 / Return missing when unmatched


def normalise_amplitude_grid(amplitude: np.ndarray) -> np.ndarray:  # 归一化振幅网格 / Normalize amplitude grid
    data = np.nan_to_num(np.asarray(amplitude, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)  # 清理非有限值 / Clean non-finite values
    max_value = max(float(np.max(np.abs(data))) if data.size else 0.0, 1.0e-12)  # 计算最大振幅 / Compute maximum amplitude
    return (np.abs(data) / max_value).astype(np.float32)  # 返回 0-1 振幅 / Return 0-1 amplitude


def target_valley_bands(target_binary: np.ndarray, image_size: int, target_radius_px: int = 2, side_inner_px: int = 4, side_outer_px: int = 10, center_radius_px: int = 0) -> dict[str, np.ndarray]:  # 构造目标带和侧带 / Build target and side bands
    target = resize_binary_nearest(target_binary, int(image_size)).astype(bool)  # 缩放目标图 / Resize target map
    skeleton = build_target_skeleton(target).astype(bool)  # 提取目标骨架 / Extract target skeleton
    distance = distance_transform_edt(~skeleton).astype(np.float32)  # 计算到骨架距离 / Compute distance to skeleton
    target_band = distance <= float(target_radius_px)  # 构造目标低振幅带 / Build target low-amplitude band
    side_band = (distance >= float(side_inner_px)) & (distance <= float(side_outer_px))  # 构造侧向对比带 / Build side contrast band
    if int(center_radius_px) > 0:  # 检查是否需要移除中心 / Check whether centre removal is needed
        rows, cols = target.shape  # 读取尺寸 / Read shape
        yy, xx = np.ogrid[:rows, :cols]  # 构造坐标 / Build coordinates
        cy, cx = (rows - 1) / 2.0, (cols - 1) / 2.0  # 计算中心 / Compute centre
        centre = (yy - cy) ** 2 + (xx - cx) ** 2 <= float(center_radius_px) ** 2  # 构造中心区 / Build centre region
        target_band = target_band & ~centre  # 移除中心目标带 / Remove centre from target band
        side_band = side_band & ~centre  # 移除中心侧带 / Remove centre from side band
    return {"target": target, "skeleton": skeleton, "distance": distance, "target_band": target_band, "side_band": side_band}  # 返回几何带 / Return geometry bands


def soft_valley_map(amplitude: np.ndarray, epsilon: float = 0.080) -> np.ndarray:  # 计算软低振幅谷线权重 / Compute soft low-amplitude valley weights
    amp = normalise_amplitude_grid(amplitude)  # 归一化振幅 / Normalize amplitude
    return np.exp(-np.square(amp / float(epsilon))).astype(np.float32)  # 返回软谷线图 / Return soft valley map


def score_amplitude_valley(amplitude: np.ndarray, target_band: np.ndarray, side_band: np.ndarray, distance_to_target: np.ndarray | None = None, config: dict | None = None) -> dict[str, object]:  # 评分给定目标带的频域低振幅谷线 / Score frequency-domain low-amplitude valley for given bands
    selected = {"epsilon": 0.080, "contrast_scale": 5.0, "extra_weight": 0.35, "layout_weight": 0.15, "dice_weight": 0.08, **(config or {})}  # 合并默认评分参数 / Merge default scoring config
    amp = normalise_amplitude_grid(amplitude)  # 归一化振幅图 / Normalize amplitude map
    target = target_band.astype(bool)  # 转换目标带 / Convert target band
    side = side_band.astype(bool)  # 转换侧带 / Convert side band
    if not target.any():  # 检查目标带是否为空 / Check empty target band
        raise ValueError("target_band is empty. / target_band 为空。")  # 抛出目标带错误 / Raise target-band error
    if not side.any():  # 检查侧带是否为空 / Check empty side band
        raise ValueError("side_band is empty. / side_band 为空。")  # 抛出侧带错误 / Raise side-band error
    target_values = amp[target]  # 读取目标带振幅 / Read target-band amplitude values
    side_values = amp[side]  # 读取侧带振幅 / Read side-band amplitude values
    target_mean = float(np.mean(target_values))  # 计算目标均值 / Compute target mean
    target_median = float(np.median(target_values))  # 计算目标中位数 / Compute target median
    side_mean = float(np.mean(side_values))  # 计算侧带均值 / Compute side mean
    side_median = float(np.median(side_values))  # 计算侧带中位数 / Compute side median
    valley = soft_valley_map(amp, float(selected["epsilon"]))  # 计算软低振幅权重 / Compute soft low-amplitude weights
    if distance_to_target is None:  # 检查是否缺少距离图 / Check missing distance map
        distance = distance_transform_edt(~target).astype(np.float32)  # 用目标带构造距离图 / Build distance map from target band
    else:  # 使用传入距离图 / Use provided distance map
        distance = np.asarray(distance_to_target, dtype=np.float32)  # 转换距离图 / Convert distance map
    normalizer = max(float(np.hypot(*amp.shape)), 1.0)  # 计算距离归一化分母 / Compute distance normalizer
    extra_penalty = float(np.sum(valley * distance) / max(float(np.sum(valley)), 1.0e-12) / normalizer)  # 惩罚远离目标的低谷 / Penalize off-target low valleys
    hard_valley = (amp <= float(selected["epsilon"])).astype(bool)  # 提取硬低振幅区 / Extract hard low-amplitude region
    iou = compute_iou(hard_valley, target)  # 计算低谷与目标带 IoU / Compute valley-target IoU
    dice = compute_dice(hard_valley, target)  # 计算低谷与目标带 Dice / Compute valley-target Dice
    layout = layout_similarity(hard_valley, target)  # 计算布局相似度 / Compute layout similarity
    chamfer = chamfer_similarity(hard_valley, target)  # 计算距离相似度 / Compute distance similarity
    contrast = float(side_mean / max(target_mean, 1.0e-8))  # 计算均值对比倍率 / Compute mean contrast ratio
    median_contrast = float(side_median / max(target_median, 1.0e-8))  # 计算中位数对比倍率 / Compute median contrast ratio
    margin = float(side_mean - target_mean)  # 计算均值差距 / Compute mean contrast margin
    median_margin = float(side_median - target_median)  # 计算中位数差距 / Compute median contrast margin
    contrast_score = min(contrast / float(selected["contrast_scale"]), 1.0)  # 将对比倍率截断为分数 / Convert contrast ratio into capped score
    margin_score = max(0.0, margin)  # 目标低于侧带才加分 / Reward target lower than side band
    final_score = float(0.50 * contrast_score + 0.25 * margin_score + float(selected["layout_weight"]) * layout + float(selected["dice_weight"]) * dice - float(selected["extra_weight"]) * extra_penalty)  # 合成最终振幅谷线分 / Combine final amplitude-valley score
    return {"target_mean_amplitude": target_mean, "target_median_amplitude": target_median, "side_mean_amplitude": side_mean, "side_median_amplitude": side_median, "valley_contrast": contrast, "median_valley_contrast": median_contrast, "contrast_margin": margin, "median_contrast_margin": median_margin, "extra_valley_penalty": extra_penalty, "iou": float(iou), "dice": float(dice), "layout": float(layout), "chamfer": float(chamfer), "final_amplitude_valley_score": final_score, "final_frequency_response_score": final_score, "hard_valley": hard_valley, "soft_valley": valley}  # 返回评分结果 / Return scoring result


def rank_frequency_responses(responses: dict[float, np.ndarray], target_data: dict, config: dict | None = None) -> list[dict[str, object]]:  # 对多个频率响应排序 / Rank multiple frequency responses
    rows: list[dict[str, object]] = []  # 创建结果列表 / Create result list
    for frequency, amplitude in sorted(responses.items()):  # 按频率遍历响应 / Iterate responses by frequency
        score = score_amplitude_valley(amplitude, target_data["target_band"], target_data["side_band"], target_data.get("distance_to_target"), config)  # 计算振幅谷线分 / Compute amplitude-valley score
        row = {key: value for key, value in score.items() if key not in {"hard_valley", "soft_valley"}}  # 去掉大数组字段 / Remove large array fields
        row["frequency_hz"] = float(frequency)  # 写入频率 / Store frequency
        rows.append(row)  # 保存一行结果 / Store one result row
    rows.sort(key=lambda item: float(item["final_amplitude_valley_score"]), reverse=True)  # 按最终分降序排序 / Sort by final score descending
    return rows  # 返回排序结果 / Return ranked rows


def score_amplitude_valley_grid(amplitude: np.ndarray, target_binary: np.ndarray, epsilon: float = 0.080, target_radius_px: int = 2, side_inner_px: int = 4, side_outer_px: int = 10, center_radius_px: int = 0) -> dict[str, object]:  # 评分 COMSOL 频域振幅谷线 / Score COMSOL frequency-domain amplitude valley
    amp = normalise_amplitude_grid(amplitude)  # 归一化振幅 / Normalize amplitude
    bands = target_valley_bands(target_binary, amp.shape[0], int(target_radius_px), int(side_inner_px), int(side_outer_px), int(center_radius_px))  # 构造目标带和侧带 / Build target and side bands
    result = score_amplitude_valley(amp, bands["target_band"], bands["side_band"], bands["distance"], {"epsilon": float(epsilon)})  # 使用通用评分函数 / Use generic scoring function
    result["bands"] = bands  # 附加 band 数据 / Attach band data
    return result  # 返回评分结果 / Return scoring result


def load_frequency_response_csv(path: str | Path, grid_size: int = 256) -> np.ndarray:  # 读取 COMSOL 频域响应 CSV 为振幅网格 / Load COMSOL frequency-response CSV as amplitude grid
    xs: list[float] = []  # 创建 x 坐标列表 / Create x-coordinate list
    ys: list[float] = []  # 创建 y 坐标列表 / Create y-coordinate list
    real_values: list[float] = []  # 创建实部列表 / Create real-component list
    imag_values: list[float] = []  # 创建虚部列表 / Create imaginary-component list
    abs_values: list[float] = []  # 创建振幅列表 / Create magnitude list
    with Path(path).open("r", encoding="utf-8", errors="ignore", newline="") as file_obj:  # 打开响应 CSV / Open response CSV
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dictionary reader
        field_map = {_normalise_key(name): name for name in (reader.fieldnames or [])}  # 建立表头映射 / Build header map
        x_key = field_map.get("x") or field_map.get("x_m") or field_map.get("x_mm")  # 选择 x 列 / Select x column
        y_key = field_map.get("y") or field_map.get("y_m") or field_map.get("y_mm")  # 选择 y 列 / Select y column
        mag_key = _pick_column(field_map, MAGNITUDE_COLUMNS)  # 选择振幅列 / Select magnitude column
        real_key = _pick_column(field_map, REAL_COLUMNS)  # 选择实部列 / Select real column
        imag_key = _pick_column(field_map, IMAG_COLUMNS)  # 选择虚部列 / Select imaginary column
        if not x_key or not y_key or (not mag_key and not (real_key and imag_key)):  # 检查必要列 / Check required columns
            raise ValueError(f"{path} needs x/y and either magnitude or real+imag columns. / {path} 需要 x/y 以及振幅列或实部+虚部列。")  # 抛出清晰错误 / Raise clear error
        for row in reader:  # 遍历响应行 / Iterate response rows
            xs.append(float(row[x_key]))  # 保存 x / Store x
            ys.append(float(row[y_key]))  # 保存 y / Store y
            if mag_key:  # 检查是否已有振幅列 / Check whether magnitude is available
                abs_values.append(abs(float(row[mag_key])))  # 保存振幅 / Store magnitude
            else:  # 否则用实部虚部合成 / Otherwise combine real and imaginary parts
                real = float(row[real_key])  # 读取实部 / Read real component
                imag = float(row[imag_key])  # 读取虚部 / Read imaginary component
                real_values.append(real)  # 保存实部 / Store real component
                imag_values.append(imag)  # 保存虚部 / Store imaginary component
                abs_values.append(float(np.hypot(real, imag)))  # 合成振幅 / Compose magnitude
    return normalise_amplitude_grid(interpolate_to_grid(np.asarray(xs), np.asarray(ys), np.asarray(abs_values), int(grid_size)))  # 插值并归一化振幅 / Interpolate and normalize amplitude


def score_frequency_response_csv(path: str | Path, target_binary: np.ndarray, grid_size: int = 256, epsilon: float = 0.080) -> dict[str, object]:  # 读取并评分频域响应 CSV / Load and score frequency-response CSV
    amplitude = load_frequency_response_csv(path, int(grid_size))  # 读取振幅网格 / Load amplitude grid
    result = score_amplitude_valley_grid(amplitude, target_binary, float(epsilon))  # 计算振幅谷线评分 / Compute amplitude-valley score
    result["amplitude"] = amplitude  # 附加振幅网格 / Attach amplitude grid
    return result  # 返回评分结果 / Return score result
