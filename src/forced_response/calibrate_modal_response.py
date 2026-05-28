from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
import json  # 导入 JSON 工具 / Import JSON utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
import torch  # 导入张量计算库 / Import tensor library

from src.comsol.import_results import interpolate_to_grid  # 导入散点插值函数 / Import scattered interpolation helper
from src.forced_response.actuator_projection import aligned_frequencies  # 导入频率对齐函数 / Import frequency alignment helper
from src.forced_response.actuator_projection import reshape_basis_to_fields  # 导入基底转场函数 / Import basis-to-fields helper
from src.forced_response.modal_response_coefficients import forced_modal_coefficients  # 导入强迫响应系数函数 / Import forced-response coefficient helper
from src.forced_response.predict_response import load_actuator_rows  # 导入激振器读取函数 / Import actuator loader
from src.forced_response.predict_response import load_frequency_row  # 导入频率读取函数 / Import frequency loader
from src.forced_response.predict_response import millimetres_to_pixels  # 导入毫米转像素函数 / Import millimetre-to-pixel converter
from src.forced_response.score_comsol_response import load_forced_response_csv  # 导入真实响应读取函数 / Import real-response loader
from src.subspace.mosaic_z import load_modal_basis  # 导入模态基底读取函数 / Import modal-basis loader


def normalise_complex_vector(values: np.ndarray) -> np.ndarray:  # 归一化复向量 / Normalise complex vector
    norm = float(np.linalg.norm(values))  # 计算向量范数 / Compute vector norm
    return values if norm <= 1.0e-12 else values / norm  # 返回归一化结果 / Return normalised result


def load_real_response_grid(response_csv: str | Path, image_size: int) -> np.ndarray:  # 读取真实 COMSOL 响应网格 / Load real COMSOL response grid
    x, y, w_real, w_imag, _w_abs = load_forced_response_csv(response_csv)  # 读取真实响应列 / Load real response columns
    real_grid = interpolate_to_grid(x, y, w_real, image_size)  # 插值实部 / Interpolate real component
    imag_grid = interpolate_to_grid(x, y, w_imag, image_size)  # 插值虚部 / Interpolate imaginary component
    return real_grid.astype(np.complex64) + 1j * imag_grid.astype(np.complex64)  # 返回复响应网格 / Return complex response grid


def project_response_to_basis(basis: np.ndarray, response_grid: np.ndarray, ridge: float = 1.0e-5) -> np.ndarray:  # 将真实响应投影到模态基底 / Project real response onto modal basis
    matrix = basis.astype(np.complex64)  # 转换模态矩阵为复数 / Convert modal matrix to complex
    target = response_grid.reshape(-1).astype(np.complex64)  # 拉平目标响应 / Flatten target response
    gram = matrix.conj().T @ matrix  # 计算正规方程矩阵 / Compute normal-equation matrix
    rhs = matrix.conj().T @ target  # 计算右端项 / Compute right-hand side
    regularised = gram + float(ridge) * np.eye(gram.shape[0], dtype=np.complex64)  # 加入岭正则 / Add ridge regularisation
    coeffs = np.linalg.solve(regularised, rhs)  # 求解复模态系数 / Solve complex modal coefficients
    return normalise_complex_vector(coeffs.astype(np.complex64))  # 返回归一化系数 / Return normalised coefficients


def predicted_coefficients(modal_export_dir: str | Path, operator_dir: str | Path, basis: np.ndarray, modes: list[int], image_size: int, plate_length_mm: float) -> np.ndarray:  # 计算当前模型预测系数 / Compute current-model predicted coefficients
    mode_fields = reshape_basis_to_fields(basis, image_size)  # 转换模态基底为场 / Convert modal basis to fields
    frequencies = torch.as_tensor(aligned_frequencies(modal_export_dir, modes), dtype=torch.float32)  # 读取模态频率 / Load modal frequencies
    positions_mm, amplitudes_np, phases_np = load_actuator_rows(Path(operator_dir) / "actuator_parameters.csv")  # 读取激振器参数 / Load actuator parameters
    drive_frequency_hz, damping_ratio = load_frequency_row(Path(operator_dir) / "frequency_parameters.csv")  # 读取驱动频率 / Load drive frequency
    positions_px = millimetres_to_pixels(positions_mm, image_size, plate_length_mm)  # 转换激振位置 / Convert actuator positions
    coeffs = forced_modal_coefficients(mode_fields, frequencies, torch.as_tensor(positions_px), torch.as_tensor(amplitudes_np), torch.as_tensor(phases_np), torch.as_tensor(float(drive_frequency_hz)), float(damping_ratio))  # 计算预测系数 / Compute predicted coefficients
    return normalise_complex_vector(coeffs.detach().cpu().numpy().astype(np.complex64))  # 返回 NumPy 系数 / Return NumPy coefficients


def align_prediction_to_observation(predicted: np.ndarray, observed: np.ndarray) -> tuple[np.ndarray, complex, float]:  # 对齐全局复比例 / Align global complex scale
    denominator = np.vdot(predicted, predicted) + 1.0e-12  # 计算稳定分母 / Compute stable denominator
    scale = np.vdot(predicted, observed) / denominator  # 求最佳全局复比例 / Solve best global complex scale
    aligned = predicted * scale  # 应用全局比例 / Apply global scale
    residual = observed - aligned  # 计算残差 / Compute residual
    error = float(np.linalg.norm(residual) / max(np.linalg.norm(observed), 1.0e-12))  # 计算相对误差 / Compute relative error
    return aligned.astype(np.complex64), complex(scale), error  # 返回对齐预测和误差 / Return aligned prediction and error


def fit_modal_scale(predicted_cases: list[np.ndarray], observed_cases: list[np.ndarray], shrink: float = 0.35) -> np.ndarray:  # 拟合每个模态的复比例 / Fit per-mode complex scale
    predicted_stack = np.stack(predicted_cases, axis=0).astype(np.complex64)  # 堆叠预测系数 / Stack predicted coefficients
    observed_stack = np.stack(observed_cases, axis=0).astype(np.complex64)  # 堆叠观测系数 / Stack observed coefficients
    numerator = np.sum(observed_stack * np.conj(predicted_stack), axis=0) + float(shrink)  # 构造带收缩的分子 / Build shrinkage numerator
    denominator = np.sum(np.abs(predicted_stack) ** 2, axis=0) + float(shrink)  # 构造带收缩的分母 / Build shrinkage denominator
    scale = numerator / np.maximum(denominator, 1.0e-12)  # 计算 per-mode scale / Compute per-mode scale
    magnitude = np.clip(np.abs(scale), 0.20, 5.00)  # 限制修正幅度 / Clamp correction magnitude
    phase = np.angle(scale)  # 读取修正相位 / Read correction phase
    return (magnitude * np.exp(1j * phase)).astype(np.complex64)  # 返回稳定复修正 / Return stable complex correction


def write_modal_scale_csv(path: str | Path, modes: list[int], scale: np.ndarray) -> Path:  # 写入模态校准 CSV / Write modal calibration CSV
    output_path = Path(path)  # 转换输出路径 / Convert output path
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    with output_path.open("w", encoding="utf-8", newline="") as file_obj:  # 打开 CSV 文件 / Open CSV file
        writer = csv.DictWriter(file_obj, fieldnames=["mode", "scale_real", "scale_imag", "scale_abs", "scale_phase_deg"])  # 创建写入器 / Create writer
        writer.writeheader()  # 写入表头 / Write header
        for mode, value in zip(modes, scale):  # 遍历模态修正 / Iterate modal scales
            writer.writerow({"mode": int(mode), "scale_real": float(np.real(value)), "scale_imag": float(np.imag(value)), "scale_abs": float(np.abs(value)), "scale_phase_deg": float(np.degrees(np.angle(value)))})  # 写入一行 / Write one row
    return output_path  # 返回输出路径 / Return output path


def load_modal_scale_csv(path: str | Path, modes: list[int]) -> np.ndarray:  # 读取模态校准 CSV / Load modal calibration CSV
    by_mode = {}  # 创建模态到修正的映射 / Create mode-to-scale map
    with Path(path).open("r", encoding="utf-8", newline="") as file_obj:  # 打开 CSV 文件 / Open CSV file
        reader = csv.DictReader(file_obj)  # 创建读取器 / Create reader
        for row in reader:  # 遍历 CSV 行 / Iterate CSV rows
            by_mode[int(row["mode"])] = complex(float(row["scale_real"]), float(row["scale_imag"]))  # 读取复数修正 / Read complex scale
    return np.asarray([by_mode.get(int(mode), 1.0 + 0.0j) for mode in modes], dtype=np.complex64)  # 按模态顺序返回 / Return in mode order


def calibration_case_summary(name: str, predicted: np.ndarray, observed: np.ndarray) -> dict[str, object]:  # 汇总单个校准样本 / Summarise one calibration case
    aligned, global_scale, relative_error = align_prediction_to_observation(predicted, observed)  # 对齐预测与观测 / Align prediction and observation
    cosine = np.vdot(normalise_complex_vector(aligned), normalise_complex_vector(observed))  # 计算复余弦 / Compute complex cosine
    return {"case": name, "relative_error": float(relative_error), "coherence_abs": float(np.abs(cosine)), "global_scale_real": float(np.real(global_scale)), "global_scale_imag": float(np.imag(global_scale))}  # 返回摘要 / Return summary


def calibrate_modal_response(modal_export_dir: str | Path, cases: list[dict[str, str]], modes: list[int], output_dir: str | Path, image_size: int = 160, plate_length_mm: float = 150.0, ridge: float = 1.0e-5, shrink: float = 0.35) -> dict[str, object]:  # 校准模态强迫响应模型 / Calibrate modal forced-response model
    basis, loaded_modes = load_modal_basis(modal_export_dir, modes, image_size)  # 读取模态基底 / Load modal basis
    if loaded_modes != list(modes):  # 检查模态顺序一致 / Check mode-order consistency
        modes = loaded_modes  # 使用实际加载模态 / Use actually loaded modes
    aligned_predictions = []  # 创建对齐预测列表 / Create aligned prediction list
    observations = []  # 创建观测系数列表 / Create observed coefficient list
    summaries = []  # 创建样本摘要列表 / Create case-summary list
    for case in cases:  # 遍历校准样本 / Iterate calibration cases
        observed_grid = load_real_response_grid(case["response_csv"], image_size)  # 读取真实响应网格 / Load real response grid
        observed = project_response_to_basis(basis, observed_grid, ridge)  # 投影真实响应 / Project real response
        predicted = predicted_coefficients(modal_export_dir, case["operator_dir"], basis, modes, image_size, plate_length_mm)  # 计算预测系数 / Compute predicted coefficients
        aligned, _global_scale, _error = align_prediction_to_observation(predicted, observed)  # 对齐预测系数 / Align predicted coefficients
        aligned_predictions.append(aligned)  # 保存对齐预测 / Store aligned prediction
        observations.append(observed)  # 保存观测系数 / Store observation
        summaries.append(calibration_case_summary(case["name"], predicted, observed))  # 保存样本摘要 / Store case summary
    scale = fit_modal_scale(aligned_predictions, observations, shrink)  # 拟合模态修正 / Fit modal correction
    out_dir = Path(output_dir)  # 转换输出目录 / Convert output directory
    out_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    scale_path = write_modal_scale_csv(out_dir / "modal_participation_scale.csv", modes, scale)  # 写入修正 CSV / Write scale CSV
    summary = {"modal_export_dir": str(modal_export_dir), "image_size": int(image_size), "modes": [int(mode) for mode in modes], "case_count": len(cases), "ridge": float(ridge), "shrink": float(shrink), "scale_path": str(scale_path), "cases": summaries, "scale_abs_min": float(np.min(np.abs(scale))), "scale_abs_max": float(np.max(np.abs(scale))), "scale_abs_mean": float(np.mean(np.abs(scale)))}  # 构造校准摘要 / Build calibration summary
    (out_dir / "modal_calibration_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")  # 写入摘要 JSON / Write summary JSON
    return summary  # 返回摘要 / Return summary
