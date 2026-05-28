from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
import json  # 导入 JSON 工具 / Import JSON utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
import torch  # 导入张量优化库 / Import tensor optimisation library

from src.forced_response.actuator_projection import aligned_frequencies  # 导入频率对齐函数 / Import frequency alignment helper
from src.forced_response.actuator_projection import decode_drive_frequency  # 导入频率解码函数 / Import frequency decoder
from src.forced_response.actuator_projection import decode_positions  # 导入位置解码函数 / Import position decoder
from src.forced_response.actuator_projection import reshape_basis_to_fields  # 导入基底转场函数 / Import basis-to-fields helper
from src.forced_response.calibrate_modal_response import load_modal_scale_csv  # 导入模态校准读取函数 / Import modal-calibration loader
from src.forced_response.modal_response_coefficients import forced_modal_coefficients  # 导入强迫响应系数函数 / Import forced-response coefficient helper
from src.forced_response.predict_response import response_preview  # 导入预览图写入函数 / Import preview writer
from src.forced_response.predict_response import score_amplitude_valley  # 导入振幅谷线评分函数 / Import amplitude-valley scorer
from src.scoring.amplitude_valley_loss import amplitude_valley_loss  # 导入可微振幅谷线损失 / Import differentiable amplitude-valley loss
from src.subspace.mosaic_z import build_target_data  # 导入目标数据构造函数 / Import target-data builder
from src.subspace.mosaic_z import load_modal_basis  # 导入模态基底读取函数 / Import modal-basis loader


def actuator_rows_from_variables(positions_px: np.ndarray, amplitudes: np.ndarray, phases: np.ndarray, image_size: int, plate_length_mm: float) -> list[dict[str, float]]:  # 将优化变量转为激振器行 / Convert optimised variables to actuator rows
    positions_mm = (positions_px / max(float(image_size - 1), 1.0) - 0.5) * float(plate_length_mm)  # 像素坐标转毫米坐标 / Convert pixel coordinates to millimetres
    rows = []  # 创建行列表 / Create row list
    for index in range(len(amplitudes)):  # 遍历激振器 / Iterate actuators
        rows.append({"id": index + 1, "x_mm": float(positions_mm[index, 1]), "y_mm": float(positions_mm[index, 0]), "amplitude": float(amplitudes[index]), "phase_deg": float(np.degrees(phases[index]))})  # 添加激振器行 / Add actuator row
    return rows  # 返回激振器行 / Return actuator rows


def write_actuator_csv(path: Path, rows: list[dict[str, float]]) -> None:  # 写入激振器 CSV / Write actuator CSV
    with path.open("w", encoding="utf-8", newline="") as file_obj:  # 打开输出文件 / Open output file
        writer = csv.DictWriter(file_obj, fieldnames=["id", "x_mm", "y_mm", "amplitude", "phase_deg"])  # 创建字典写入器 / Create dictionary writer
        writer.writeheader()  # 写入表头 / Write header
        for row in rows:  # 遍历激振器行 / Iterate actuator rows
            writer.writerow(row)  # 写入一行 / Write one row


def write_frequency_csv(path: Path, drive_frequency_hz: float, damping_ratio: float, force_sigma_mm: float = 2.5) -> None:  # 写入频率 CSV / Write frequency CSV
    path.write_text(f"drive_frequency_hz,damping_ratio,force_sigma_mm\n{float(drive_frequency_hz)},{float(damping_ratio)},{float(force_sigma_mm)}\n", encoding="utf-8")  # 写入频率参数 / Write frequency parameters


def actuator_center_penalty(positions: torch.Tensor, image_size: int, center_radius_px: int) -> torch.Tensor:  # 计算中心夹持禁区惩罚 / Compute centre-clamp exclusion penalty
    if center_radius_px <= 0:  # 检查是否没有禁区 / Check whether exclusion zone is absent
        return positions.new_tensor(0.0)  # 返回零惩罚 / Return zero penalty
    center = positions.new_tensor([(image_size - 1) / 2.0, (image_size - 1) / 2.0])  # 构造中心坐标 / Build centre coordinate
    distances = torch.linalg.norm(positions - center.unsqueeze(0), dim=1)  # 计算激振点到中心距离 / Compute actuator-to-centre distances
    margin = float(center_radius_px + 2)  # 给中心夹持区添加安全余量 / Add safety margin around centre clamp
    violation = torch.relu((margin - distances) / max(margin, 1.0))  # 计算归一化违规量 / Compute normalised violation
    return torch.mean(violation * violation)  # 返回平均平方惩罚 / Return mean squared penalty


def optimise_actuators_for_valley(modal_export_dir: str | Path, target_binary: np.ndarray, modes: list[int], output_dir: str | Path, image_size: int = 128, actuator_count: int = 4, steps: int = 1200, restarts: int = 8, learning_rate: float = 0.035, damping_ratio: float = 0.015, epsilon: float = 0.060, center_radius_px: int = 0, plate_length_mm: float = 150.0, seed: int = 31, loss_weights: dict[str, float] | None = None, center_penalty_weight: float = 2.0, modal_scale_csv: str | Path | None = None, fixed_frequency_hz: float | None = None) -> dict[str, object]:  # 直接优化激振器以匹配低振幅谷线 / Directly optimise actuators to match low-amplitude valleys
    torch.manual_seed(int(seed))  # 固定 Torch 随机种子 / Fix Torch random seed
    np.random.seed(int(seed))  # 固定 NumPy 随机种子 / Fix NumPy random seed
    device = torch.device("cpu")  # 使用 CPU 保持部署稳定 / Use CPU for deployment stability
    basis_np, loaded_modes = load_modal_basis(modal_export_dir, modes, image_size)  # 读取模态基底 / Load modal basis
    basis_complex = torch.as_tensor(basis_np, dtype=torch.float32, device=device).to(torch.complex64)  # 构造复数基底 / Build complex basis
    mode_fields = reshape_basis_to_fields(basis_np, image_size).to(device)  # 构造模态场张量 / Build modal-field tensor
    frequencies = torch.as_tensor(aligned_frequencies(modal_export_dir, loaded_modes), dtype=torch.float32, device=device)  # 读取模态频率 / Load modal frequencies
    modal_scale = torch.as_tensor(load_modal_scale_csv(modal_scale_csv, loaded_modes), dtype=torch.complex64, device=device) if modal_scale_csv else None  # 读取可选真实校准 / Load optional real calibration
    target_data = build_target_data(target_binary, image_size, center_radius_px, device)  # 构造目标数据 / Build target data
    min_hz = max(1.0, float(torch.min(frequencies).detach().cpu()) * 0.70)  # 设置频率下限 / Set lower frequency bound
    max_hz = float(torch.max(frequencies).detach().cpu()) * 1.30  # 设置频率上限 / Set upper frequency bound
    fixed_frequency = None if fixed_frequency_hz is None else float(fixed_frequency_hz)  # 读取可选固定频率 / Read optional fixed frequency
    best: dict[str, object] | None = None  # 初始化最佳结果 / Initialise best result
    for restart in range(max(1, int(restarts))):  # 多起点优化 / Run multi-start optimisation
        raw_positions = torch.randn((int(actuator_count), 2), dtype=torch.float32, device=device, requires_grad=True)  # 初始化位置变量 / Initialise position variables
        raw_amplitudes = torch.randn(int(actuator_count), dtype=torch.float32, device=device, requires_grad=True)  # 初始化幅值变量 / Initialise amplitude variables
        raw_phases = torch.randn(int(actuator_count), dtype=torch.float32, device=device, requires_grad=True)  # 初始化相位变量 / Initialise phase variables
        raw_frequency = torch.randn((), dtype=torch.float32, device=device, requires_grad=True)  # 初始化频率变量 / Initialise frequency variable
        optimisation_parameters = [raw_positions, raw_amplitudes, raw_phases] + ([] if fixed_frequency is not None else [raw_frequency])  # 组合优化变量 / Combine optimisation variables
        optimiser = torch.optim.Adam(optimisation_parameters, lr=float(learning_rate))  # 创建 Adam 优化器 / Create Adam optimiser
        for _step in range(max(1, int(steps))):  # 遍历优化步 / Iterate optimisation steps
            positions = decode_positions(raw_positions, image_size)  # 解码像素位置 / Decode pixel positions
            amplitudes = torch.nn.functional.softplus(raw_amplitudes) + 1.0e-4  # 解码正幅值 / Decode positive amplitudes
            phases = torch.pi * torch.tanh(raw_phases)  # 解码有限相位 / Decode finite phases
            drive_frequency = torch.as_tensor(fixed_frequency, dtype=torch.float32, device=device) if fixed_frequency is not None else decode_drive_frequency(raw_frequency, min_hz, max_hz)  # 读取或解码驱动频率 / Read or decode drive frequency
            coeffs = forced_modal_coefficients(mode_fields, frequencies, positions, amplitudes, phases, drive_frequency, float(damping_ratio), modal_scale)  # 计算模态响应系数 / Compute modal response coefficients
            response = torch.matmul(basis_complex, coeffs).reshape(image_size, image_size)  # 合成复数响应 / Compose complex response
            loss, parts = amplitude_valley_loss(response, target_data["target_points"], target_data["distance_to_target"], target_data["valid_mask"], target_data["plus_points"], target_data["minus_points"], epsilon=float(epsilon), weights=loss_weights)  # 计算振幅谷线损失 / Compute amplitude-valley loss
            centre_penalty = actuator_center_penalty(positions, image_size, center_radius_px)  # 计算中心禁区惩罚 / Compute centre exclusion penalty
            loss = loss + float(center_penalty_weight) * centre_penalty  # 加入中心禁区惩罚 / Add centre exclusion penalty
            optimiser.zero_grad()  # 清空梯度 / Clear gradients
            loss.backward()  # 反向传播 / Backpropagate
            optimiser.step()  # 更新参数 / Update parameters
        positions = decode_positions(raw_positions, image_size).detach().cpu().numpy()  # 读取最终位置 / Read final positions
        amplitudes = (torch.nn.functional.softplus(raw_amplitudes) + 1.0e-4).detach().cpu().numpy()  # 读取最终幅值 / Read final amplitudes
        phases = (torch.pi * torch.tanh(raw_phases)).detach().cpu().numpy()  # 读取最终相位 / Read final phases
        drive_frequency = float(fixed_frequency) if fixed_frequency is not None else float(decode_drive_frequency(raw_frequency, min_hz, max_hz).detach().cpu().numpy())  # 读取最终频率 / Read final frequency
        coeffs = forced_modal_coefficients(mode_fields, frequencies, torch.as_tensor(positions), torch.as_tensor(amplitudes), torch.as_tensor(phases), torch.as_tensor(drive_frequency), float(damping_ratio), modal_scale.detach().cpu() if modal_scale is not None else None)  # 重新计算系数 / Recompute coefficients
        response = torch.matmul(basis_complex, coeffs).reshape(image_size, image_size)  # 重新合成响应 / Recompose response
        loss, parts = amplitude_valley_loss(response, target_data["target_points"], target_data["distance_to_target"], target_data["valid_mask"], target_data["plus_points"], target_data["minus_points"], epsilon=float(epsilon), weights=loss_weights)  # 重新计算损失 / Recompute loss
        centre_penalty = actuator_center_penalty(torch.as_tensor(positions), image_size, center_radius_px)  # 重新计算中心禁区惩罚 / Recompute centre exclusion penalty
        loss = loss + float(center_penalty_weight) * centre_penalty  # 加入中心禁区惩罚 / Add centre exclusion penalty
        loss_value = float(loss.detach().cpu())  # 读取损失数值 / Read loss value
        if best is None or loss_value < float(best["loss"]):  # 检查是否刷新最佳 / Check whether best improved
            best = {"loss": loss_value, "loss_parts": {**{key: float(value.detach().cpu()) for key, value in parts.items()}, "centre_penalty": float(centre_penalty.detach().cpu())}, "positions_px": positions, "amplitudes": amplitudes, "phases": phases, "drive_frequency_hz": drive_frequency, "best_restart": restart, "response": response.detach().cpu().numpy()}  # 保存最佳结果 / Store best result
    assert best is not None  # 帮助类型检查确认最佳存在 / Help type checker know best exists
    amplitude = np.abs(np.asarray(best["response"])).astype(np.float32)  # 计算最佳响应振幅 / Compute best-response amplitude
    amplitude = amplitude / max(float(amplitude.max()), 1.0e-12)  # 归一化振幅 / Normalise amplitude
    valley, metrics = score_amplitude_valley(amplitude, target_binary, float(epsilon), center_radius_px)  # 评分最佳谷线 / Score best valley map
    rows = actuator_rows_from_variables(np.asarray(best["positions_px"]), np.asarray(best["amplitudes"]), np.asarray(best["phases"]), image_size, plate_length_mm)  # 生成激振器行 / Build actuator rows
    out_dir = Path(output_dir)  # 转换输出目录 / Convert output directory
    out_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    write_actuator_csv(out_dir / "actuator_parameters.csv", rows)  # 写入激振器合同 / Write actuator contract
    write_frequency_csv(out_dir / "frequency_parameters.csv", float(best["drive_frequency_hz"]), float(damping_ratio))  # 写入频率合同 / Write frequency contract
    np.save(out_dir / "direct_forced_response_complex.npy", np.asarray(best["response"]))  # 保存复数响应 / Save complex response
    np.save(out_dir / "direct_forced_response_amplitude.npy", amplitude)  # 保存振幅场 / Save amplitude field
    np.save(out_dir / "direct_forced_response_valley.npy", valley.astype(np.uint8))  # 保存谷线图 / Save valley map
    response_preview(out_dir / "direct_forced_response_preview.png", target_binary, amplitude, valley)  # 写入预览图 / Write preview image
    summary = {"modes": loaded_modes, "actuator_count": int(actuator_count), "drive_frequency_hz": float(best["drive_frequency_hz"]), "fixed_frequency_hz": fixed_frequency, "damping_ratio": float(damping_ratio), "epsilon": float(epsilon), "center_penalty_weight": float(center_penalty_weight), "modal_scale_csv": str(modal_scale_csv or ""), "loss": float(best["loss"]), "loss_parts": best["loss_parts"], "metrics": metrics, "actuators": rows, "best_restart": int(best["best_restart"])}  # 构造摘要 / Build summary
    (out_dir / "direct_forced_response_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")  # 写入摘要 JSON / Write summary JSON
    return summary  # 返回摘要 / Return summary
