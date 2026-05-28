from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
import json  # 导入 JSON 工具 / Import JSON utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
import torch  # 导入张量计算库 / Import tensor computation library
from PIL import Image  # 导入图像输出库 / Import image output library

from src.forced_response.actuator_projection import aligned_frequencies  # 导入频率对齐函数 / Import frequency alignment helper
from src.forced_response.actuator_projection import reshape_basis_to_fields  # 导入基底转场函数 / Import basis-to-fields helper
from src.forced_response.modal_response_coefficients import forced_modal_coefficients  # 导入强迫响应系数函数 / Import forced-response coefficient helper
from src.nodal.extract_nodal import postprocess_nodal_region  # 导入二值后处理函数 / Import binary postprocessing helper
from src.nodal.extract_nodal import remove_center_region  # 导入中心区域移除函数 / Import centre-region removal helper
from src.scoring.metrics import chamfer_similarity  # 导入距离相似度 / Import distance similarity
from src.scoring.metrics import compute_dice  # 导入 Dice 指标 / Import Dice metric
from src.scoring.metrics import compute_iou  # 导入 IoU 指标 / Import IoU metric
from src.scoring.metrics import layout_similarity  # 导入布局相似度 / Import layout similarity
from src.subspace.mosaic_z import load_modal_basis  # 导入模态基底读取函数 / Import modal-basis loader
from src.subspace.mosaic_z import resize_binary_nearest  # 导入二值图缩放函数 / Import binary resizing helper


def load_actuator_rows(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:  # 读取激振器参数 / Load actuator parameters
    positions = []  # 创建位置列表 / Create position list
    amplitudes = []  # 创建幅值列表 / Create amplitude list
    phases = []  # 创建相位列表 / Create phase list
    with Path(path).open("r", encoding="utf-8") as file_obj:  # 打开激振器 CSV / Open actuator CSV
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dictionary reader
        for row in reader:  # 遍历激振器行 / Iterate actuator rows
            positions.append((float(row["y_mm"]), float(row["x_mm"])))  # 保存毫米坐标为行列顺序 / Store millimetre coordinates in row-column order
            amplitudes.append(float(row["amplitude"]))  # 保存幅值 / Store amplitude
            phases.append(np.deg2rad(float(row["phase_deg"])))  # 保存弧度相位 / Store phase in radians
    return np.asarray(positions, dtype=np.float32), np.asarray(amplitudes, dtype=np.float32), np.asarray(phases, dtype=np.float32)  # 返回三组数组 / Return three arrays


def load_frequency_row(path: str | Path) -> tuple[float, float]:  # 读取驱动频率参数 / Load drive-frequency parameters
    with Path(path).open("r", encoding="utf-8") as file_obj:  # 打开频率 CSV / Open frequency CSV
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dictionary reader
        row = next(reader)  # 读取第一行参数 / Read first parameter row
    return float(row["drive_frequency_hz"]), float(row["damping_ratio"])  # 返回频率和阻尼 / Return frequency and damping


def millimetres_to_pixels(positions_mm: np.ndarray, image_size: int, plate_length_mm: float = 150.0) -> np.ndarray:  # 毫米坐标转像素坐标 / Convert millimetre coordinates to pixel coordinates
    normalised = positions_mm / float(plate_length_mm) + 0.5  # 映射到 0-1 坐标 / Map to 0-1 coordinates
    return normalised * float(image_size - 1)  # 映射到像素坐标 / Map to pixel coordinates


def compute_forced_response(modal_export_dir: str | Path, operator_dir: str | Path, modes: list[int], image_size: int = 160, plate_length_mm: float = 150.0) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:  # 计算预测强迫响应 / Compute predicted forced response
    basis_np, loaded_modes = load_modal_basis(modal_export_dir, modes, image_size)  # 读取模态基底 / Load modal basis
    mode_fields = reshape_basis_to_fields(basis_np, image_size)  # 转为模态场张量 / Convert basis to modal fields
    frequencies = torch.as_tensor(aligned_frequencies(modal_export_dir, loaded_modes), dtype=torch.float32)  # 读取模态频率 / Load modal frequencies
    positions_mm, amplitudes_np, phases_np = load_actuator_rows(Path(operator_dir) / "actuator_parameters.csv")  # 读取激振器参数 / Load actuator parameters
    drive_frequency_hz, damping_ratio = load_frequency_row(Path(operator_dir) / "frequency_parameters.csv")  # 读取驱动频率参数 / Load drive-frequency parameters
    positions_px = millimetres_to_pixels(positions_mm, image_size, plate_length_mm)  # 转换激振位置到像素 / Convert actuator positions to pixels
    coeffs = forced_modal_coefficients(mode_fields, frequencies, torch.as_tensor(positions_px), torch.as_tensor(amplitudes_np), torch.as_tensor(phases_np), torch.as_tensor(float(drive_frequency_hz)), float(damping_ratio))  # 计算复数模态系数 / Compute complex modal coefficients
    basis_complex = torch.as_tensor(basis_np, dtype=torch.float32).to(torch.complex64)  # 转换基底为复数张量 / Convert basis to complex tensor
    response = torch.matmul(basis_complex, coeffs).reshape(image_size, image_size).detach().cpu().numpy()  # 合成复数响应场 / Compose complex response field
    amplitude = np.abs(response).astype(np.float32)  # 计算振幅场 / Compute amplitude field
    amplitude = amplitude / max(float(amplitude.max()), 1.0e-12)  # 归一化振幅 / Normalise amplitude
    metadata = {"modes": loaded_modes, "drive_frequency_hz": float(drive_frequency_hz), "damping_ratio": float(damping_ratio), "actuator_count": int(len(amplitudes_np))}  # 构造元数据 / Build metadata
    return response, amplitude, metadata  # 返回响应、振幅和元数据 / Return response, amplitude, and metadata


def amplitude_valley_map(amplitude: np.ndarray, epsilon: float, center_radius_px: int) -> np.ndarray:  # 提取低振幅谷线 / Extract low-amplitude valley map
    valley = amplitude <= float(epsilon)  # 阈值提取低振幅区域 / Threshold low-amplitude region
    valley = postprocess_nodal_region(valley, min_size=12, dilation_iters=1)  # 清理并轻微加粗 / Clean and slightly thicken
    return remove_center_region(valley, center_radius_px) if center_radius_px > 0 else valley  # 可选移除中心区域 / Optionally remove centre region


def score_amplitude_valley(amplitude: np.ndarray, target_binary: np.ndarray, epsilon: float, center_radius_px: int) -> tuple[np.ndarray, dict[str, float]]:  # 评分低振幅谷线 / Score low-amplitude valley
    target = resize_binary_nearest(target_binary, amplitude.shape[0])  # 对齐目标尺寸 / Align target size
    if center_radius_px > 0:  # 检查是否移除中心 / Check whether centre removal is needed
        target = remove_center_region(target, center_radius_px)  # 移除目标中心区域 / Remove target centre region
    valley = amplitude_valley_map(amplitude, epsilon, center_radius_px)  # 提取谷线图 / Extract valley map
    metrics = {"iou": compute_iou(valley, target), "dice": compute_dice(valley, target), "chamfer": chamfer_similarity(valley, target), "layout": layout_similarity(valley, target), "valley_area": float(valley.mean())}  # 计算指标 / Compute metrics
    return valley, metrics  # 返回谷线和指标 / Return valley and metrics


def response_preview(path: str | Path, target: np.ndarray, amplitude: np.ndarray, valley: np.ndarray) -> None:  # 写入强迫响应预览图 / Write forced-response preview image
    aligned_target = resize_binary_nearest(target, amplitude.shape[0])  # 对齐目标尺寸 / Align target size
    target_panel = np.full((*aligned_target.shape, 3), 245, dtype=np.uint8)  # 创建目标面板 / Create target panel
    target_panel[aligned_target] = np.asarray([232, 84, 61], dtype=np.uint8)  # 绘制目标红色 / Draw target in red
    gray = np.uint8(np.clip(1.0 - amplitude, 0.0, 1.0) * 255.0)  # 低振幅显示更亮 / Show lower amplitude brighter
    amplitude_panel = np.repeat(gray[:, :, None], 3, axis=2)  # 生成振幅 RGB 面板 / Build amplitude RGB panel
    amplitude_panel[valley] = np.asarray([37, 131, 180], dtype=np.uint8)  # 标出谷线 / Mark valley map
    overlay = np.full((*aligned_target.shape, 3), 245, dtype=np.uint8)  # 创建叠加面板 / Create overlay panel
    overlay[aligned_target] = np.asarray([232, 84, 61], dtype=np.uint8)  # 绘制目标 / Draw target
    overlay[valley] = np.asarray([37, 131, 180], dtype=np.uint8)  # 绘制谷线 / Draw valley
    overlay[aligned_target & valley] = np.asarray([50, 160, 90], dtype=np.uint8)  # 绘制重叠区域 / Draw overlap
    spacer = np.full((aligned_target.shape[0], 8, 3), 255, dtype=np.uint8)  # 创建间隔 / Create spacer
    canvas = np.concatenate([target_panel, spacer, amplitude_panel, spacer, overlay], axis=1)  # 拼接三联图 / Concatenate triptych
    Image.fromarray(canvas).save(path)  # 保存图像 / Save image


def predict_and_score_forced_response(modal_export_dir: str | Path, operator_dir: str | Path, target_binary: np.ndarray, modes: list[int], output_dir: str | Path, image_size: int = 160, epsilon: float = 0.080, center_radius_px: int = 0, plate_length_mm: float = 150.0) -> dict[str, object]:  # 预测并评分强迫响应 / Predict and score forced response
    response, amplitude, metadata = compute_forced_response(modal_export_dir, operator_dir, modes, image_size, plate_length_mm)  # 计算强迫响应 / Compute forced response
    valley, metrics = score_amplitude_valley(amplitude, target_binary, epsilon, center_radius_px)  # 评分低振幅谷线 / Score low-amplitude valley
    out_dir = Path(output_dir)  # 转换输出目录 / Convert output directory
    out_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    np.save(out_dir / "forced_response_complex.npy", response)  # 保存复数响应 / Save complex response
    np.save(out_dir / "forced_response_amplitude.npy", amplitude)  # 保存振幅场 / Save amplitude field
    np.save(out_dir / "forced_response_valley.npy", valley.astype(np.uint8))  # 保存谷线图 / Save valley map
    response_preview(out_dir / "forced_response_preview.png", target_binary, amplitude, valley)  # 保存预览图 / Save preview image
    summary = {**metadata, "epsilon": float(epsilon), "metrics": metrics}  # 构造摘要 / Build summary
    (out_dir / "forced_response_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")  # 写入摘要 JSON / Write summary JSON
    return summary  # 返回摘要 / Return summary
