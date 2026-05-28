from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
import json  # 导入 JSON 工具 / Import JSON utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
import torch  # 导入张量优化库 / Import tensor optimisation library

from src.comsol.import_results import load_frequencies  # 导入频率读取函数 / Import frequency loader
from src.forced_response.modal_response_coefficients import complex_projection_loss  # 导入复数投影损失 / Import complex projection loss
from src.forced_response.modal_response_coefficients import forced_modal_coefficients  # 导入强迫响应系数函数 / Import forced-response coefficient helper
from src.subspace.mosaic_z import load_modal_basis  # 导入模态基底读取函数 / Import modal-basis loader


def load_alpha_csv(path: str | Path) -> tuple[list[int], np.ndarray]:  # 读取模态组合系数 / Load modal combination coefficients
    modes = []  # 创建模态编号列表 / Create mode-number list
    alpha = []  # 创建系数列表 / Create coefficient list
    with Path(path).open("r", encoding="utf-8") as file_obj:  # 打开 CSV 文件 / Open CSV file
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dictionary reader
        for row in reader:  # 遍历系数行 / Iterate coefficient rows
            modes.append(int(row["mode"]))  # 读取模态编号 / Read mode number
            alpha.append(float(row["alpha"]))  # 读取模态系数 / Read modal coefficient
    values = np.asarray(alpha, dtype=np.float32)  # 转换为浮点数组 / Convert to float array
    values = values / max(float(np.linalg.norm(values)), 1.0e-12)  # 归一化系数 / Normalise coefficients
    return modes, values  # 返回模态和系数 / Return modes and coefficients


def aligned_frequencies(candidate_dir: str | Path, modes: list[int]) -> np.ndarray:  # 读取并对齐频率 / Load and align frequencies
    frequencies = load_frequencies(Path(candidate_dir) / "frequencies.csv")  # 读取候选频率表 / Load candidate frequency table
    return np.asarray([float(frequencies[int(mode)]) for mode in modes], dtype=np.float32)  # 按模态顺序返回频率 / Return frequencies in mode order


def reshape_basis_to_fields(basis: np.ndarray, image_size: int) -> torch.Tensor:  # 将基底矩阵转为模态场张量 / Reshape basis matrix into modal-field tensor
    num_modes = int(basis.shape[1])  # 读取模态数量 / Read mode count
    fields = basis.T.reshape(num_modes, image_size, image_size)  # 转换为模态场堆栈 / Convert to modal-field stack
    return torch.as_tensor(fields, dtype=torch.float32)  # 返回 Torch 张量 / Return Torch tensor


def decode_positions(raw_positions: torch.Tensor, image_size: int) -> torch.Tensor:  # 将无界变量映射到板面坐标 / Decode unconstrained variables to plate coordinates
    return torch.sigmoid(raw_positions) * float(image_size - 1)  # 映射到像素范围 / Map to pixel range


def decode_drive_frequency(raw_frequency: torch.Tensor, min_hz: float, max_hz: float) -> torch.Tensor:  # 将无界变量映射到驱动频率 / Decode unconstrained variable to drive frequency
    return torch.sigmoid(raw_frequency) * float(max_hz - min_hz) + float(min_hz)  # 映射到频率范围 / Map to frequency range


def projection_result_dict(candidate_dir: str | Path, actuator_count: int, image_size: int, best_loss: float, positions_px: np.ndarray, amplitudes: np.ndarray, phases: np.ndarray, drive_frequency_hz: float, damping_ratio: float) -> dict[str, object]:  # 组装投影结果字典 / Assemble projection result dictionary
    plate_length_mm = 150.0  # 使用项目默认板长毫米值 / Use project default plate length in millimetres
    positions_mm = (positions_px / max(float(image_size - 1), 1.0) - 0.5) * plate_length_mm  # 像素坐标转换为板面毫米坐标 / Convert pixel coordinates to plate millimetres
    actuators = []  # 创建激振器列表 / Create actuator list
    for index in range(int(actuator_count)):  # 遍历激振器 / Iterate actuators
        actuators.append({"id": index + 1, "row_px": float(positions_px[index, 0]), "col_px": float(positions_px[index, 1]), "x_mm": float(positions_mm[index, 1]), "y_mm": float(positions_mm[index, 0]), "amplitude": float(amplitudes[index]), "phase_deg": float(np.degrees(phases[index]))})  # 写入一个激振器 / Store one actuator
    return {"candidate": Path(candidate_dir).name, "actuator_count": int(actuator_count), "projection_loss": float(best_loss), "drive_frequency_hz": float(drive_frequency_hz), "damping_ratio": float(damping_ratio), "actuators": actuators}  # 返回结果字典 / Return result dictionary


def project_modal_coefficients(candidate_dir: str | Path, alpha_csv: str | Path, output_dir: str | Path, image_size: int = 160, actuator_count: int = 1, steps: int = 1200, restarts: int = 8, learning_rate: float = 0.035, damping_ratio: float = 0.015, seed: int = 23) -> dict[str, object]:  # 将理想模态系数投影成激振参数 / Project ideal modal coefficients to actuator parameters
    torch.manual_seed(int(seed))  # 固定 Torch 随机种子 / Fix Torch random seed
    np.random.seed(int(seed))  # 固定 NumPy 随机种子 / Fix NumPy random seed
    modes, alpha_np = load_alpha_csv(alpha_csv)  # 读取目标模态系数 / Load target modal coefficients
    basis_np, loaded_modes = load_modal_basis(candidate_dir, modes, image_size)  # 读取对应模态基底 / Load matching modal basis
    if loaded_modes != modes:  # 检查模态顺序一致性 / Check mode-order consistency
        raise ValueError("Loaded modes do not match alpha modes. / 读取的模态与 alpha 模态不一致。")  # 抛出一致性错误 / Raise consistency error
    mode_fields = reshape_basis_to_fields(basis_np, image_size)  # 构造模态场张量 / Build modal-field tensor
    frequencies = torch.as_tensor(aligned_frequencies(candidate_dir, modes), dtype=torch.float32)  # 读取模态频率张量 / Load modal frequencies tensor
    target_alpha = torch.as_tensor(alpha_np, dtype=torch.float32)  # 构造目标 alpha 张量 / Build target alpha tensor
    min_hz = max(1.0, float(np.min(frequencies.numpy()) * 0.75))  # 设置驱动频率下限 / Set drive-frequency lower bound
    max_hz = float(np.max(frequencies.numpy()) * 1.25)  # 设置驱动频率上限 / Set drive-frequency upper bound
    best: dict[str, object] | None = None  # 初始化最佳结果 / Initialise best result
    for restart in range(max(1, int(restarts))):  # 多起点优化 / Run multi-start optimisation
        raw_positions = torch.randn((int(actuator_count), 2), dtype=torch.float32, requires_grad=True)  # 初始化位置变量 / Initialise position variables
        raw_amplitudes = torch.randn(int(actuator_count), dtype=torch.float32, requires_grad=True)  # 初始化幅值变量 / Initialise amplitude variables
        raw_phases = torch.randn(int(actuator_count), dtype=torch.float32, requires_grad=True)  # 初始化相位变量 / Initialise phase variables
        raw_frequency = torch.randn((), dtype=torch.float32, requires_grad=True)  # 初始化频率变量 / Initialise frequency variable
        optimiser = torch.optim.Adam([raw_positions, raw_amplitudes, raw_phases, raw_frequency], lr=float(learning_rate))  # 创建优化器 / Create optimiser
        for _ in range(max(1, int(steps))):  # 运行优化步 / Run optimisation steps
            positions = decode_positions(raw_positions, image_size)  # 解码激振位置 / Decode actuator positions
            amplitudes = torch.nn.functional.softplus(raw_amplitudes) + 1.0e-4  # 解码正幅值 / Decode positive amplitudes
            phases = torch.pi * torch.tanh(raw_phases)  # 解码相位到有限范围 / Decode phases into finite range
            drive_frequency = decode_drive_frequency(raw_frequency, min_hz, max_hz)  # 解码驱动频率 / Decode drive frequency
            coeffs = forced_modal_coefficients(mode_fields, frequencies, positions, amplitudes, phases, drive_frequency, float(damping_ratio))  # 计算强迫响应系数 / Compute forced-response coefficients
            loss = complex_projection_loss(coeffs, target_alpha)  # 计算投影误差 / Compute projection error
            optimiser.zero_grad()  # 清空梯度 / Clear gradients
            loss.backward()  # 反向传播 / Backpropagate
            optimiser.step()  # 更新变量 / Update variables
        positions = decode_positions(raw_positions, image_size).detach().numpy()  # 读取最终位置 / Read final positions
        amplitudes = (torch.nn.functional.softplus(raw_amplitudes) + 1.0e-4).detach().numpy()  # 读取最终幅值 / Read final amplitudes
        phases = (torch.pi * torch.tanh(raw_phases)).detach().numpy()  # 读取最终相位 / Read final phases
        drive_frequency = float(decode_drive_frequency(raw_frequency, min_hz, max_hz).detach().numpy())  # 读取最终频率 / Read final frequency
        coeffs = forced_modal_coefficients(mode_fields, frequencies, torch.as_tensor(positions), torch.as_tensor(amplitudes), torch.as_tensor(phases), torch.as_tensor(drive_frequency), float(damping_ratio))  # 重新计算最终系数 / Recompute final coefficients
        loss_value = float(complex_projection_loss(coeffs, target_alpha).detach().numpy())  # 读取最终损失 / Read final loss
        if best is None or loss_value < float(best["projection_loss"]):  # 检查是否刷新最佳 / Check whether best improved
            best = projection_result_dict(candidate_dir, actuator_count, image_size, loss_value, positions, amplitudes, phases, drive_frequency, float(damping_ratio))  # 保存最佳结果 / Store best result
            best["best_restart"] = restart  # 记录最佳重启编号 / Record best restart index
    assert best is not None  # 帮助类型检查确认最佳存在 / Help type checker know best exists
    out_dir = Path(output_dir)  # 转换输出目录 / Convert output directory
    out_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    (out_dir / "actuator_projection.json").write_text(json.dumps(best, indent=2, ensure_ascii=False), encoding="utf-8")  # 写入 JSON 结果 / Write JSON result
    with (out_dir / "actuator_parameters.csv").open("w", encoding="utf-8", newline="") as file_obj:  # 打开激振器 CSV / Open actuator CSV
        writer = csv.DictWriter(file_obj, fieldnames=["id", "x_mm", "y_mm", "amplitude", "phase_deg"])  # 创建 CSV 写入器 / Create CSV writer
        writer.writeheader()  # 写入表头 / Write header
        for actuator in best["actuators"]:  # 遍历激振器结果 / Iterate actuator results
            writer.writerow({key: actuator[key] for key in ["id", "x_mm", "y_mm", "amplitude", "phase_deg"]})  # 写入激振器参数 / Write actuator parameters
    (out_dir / "frequency_parameters.csv").write_text(f"drive_frequency_hz,damping_ratio,force_sigma_mm\n{best['drive_frequency_hz']},{best['damping_ratio']},2.5\n", encoding="utf-8")  # 写入频率参数 / Write frequency parameters
    return best  # 返回最佳结果 / Return best result
