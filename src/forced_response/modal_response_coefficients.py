from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import torch  # 导入张量优化库 / Import tensor optimisation library


def bilinear_sample_modes(mode_fields: torch.Tensor, positions: torch.Tensor) -> torch.Tensor:  # 双线性采样模态值 / Bilinearly sample modal values
    num_modes, height, width = mode_fields.shape  # 读取模态场尺寸 / Read modal-field shape
    y = torch.clamp(positions[:, 0], 0.0, float(height - 1))  # 限制 y 坐标 / Clamp y coordinate
    x = torch.clamp(positions[:, 1], 0.0, float(width - 1))  # 限制 x 坐标 / Clamp x coordinate
    y0 = torch.floor(y).long()  # 计算上方像素索引 / Compute upper pixel index
    x0 = torch.floor(x).long()  # 计算左侧像素索引 / Compute left pixel index
    y1 = torch.clamp(y0 + 1, max=height - 1)  # 计算下方像素索引 / Compute lower pixel index
    x1 = torch.clamp(x0 + 1, max=width - 1)  # 计算右侧像素索引 / Compute right pixel index
    wy = (y - y0.float()).unsqueeze(0)  # 计算 y 插值权重 / Compute y interpolation weight
    wx = (x - x0.float()).unsqueeze(0)  # 计算 x 插值权重 / Compute x interpolation weight
    f00 = mode_fields[:, y0, x0]  # 读取左上采样值 / Read upper-left values
    f01 = mode_fields[:, y0, x1]  # 读取右上采样值 / Read upper-right values
    f10 = mode_fields[:, y1, x0]  # 读取左下采样值 / Read lower-left values
    f11 = mode_fields[:, y1, x1]  # 读取右下采样值 / Read lower-right values
    top = f00 * (1.0 - wx) + f01 * wx  # 插值上边 / Interpolate top edge
    bottom = f10 * (1.0 - wx) + f11 * wx  # 插值下边 / Interpolate bottom edge
    return top * (1.0 - wy) + bottom * wy  # 返回双线性采样结果 / Return bilinear samples


def modal_denominator(frequencies_hz: torch.Tensor, drive_frequency_hz: torch.Tensor, damping_ratio: float) -> torch.Tensor:  # 计算模态频响分母 / Compute modal response denominator
    omega_modes = 2.0 * torch.pi * frequencies_hz  # 模态角频率 / Modal angular frequencies
    omega_drive = 2.0 * torch.pi * drive_frequency_hz  # 驱动角频率 / Drive angular frequency
    real = omega_modes * omega_modes - omega_drive * omega_drive  # 计算实部分母 / Compute real denominator
    imag = 2.0 * float(damping_ratio) * omega_modes * omega_drive  # 计算阻尼虚部 / Compute damping imaginary part
    return torch.complex(real, imag)  # 返回复数分母 / Return complex denominator


def forced_modal_coefficients(mode_fields: torch.Tensor, frequencies_hz: torch.Tensor, positions: torch.Tensor, amplitudes: torch.Tensor, phases: torch.Tensor, drive_frequency_hz: torch.Tensor, damping_ratio: float, modal_scale: torch.Tensor | None = None) -> torch.Tensor:  # 计算强迫响应模态系数 / Compute forced-response modal coefficients
    samples = bilinear_sample_modes(mode_fields, positions)  # 采样每个激振点处的模态值 / Sample mode values at actuator points
    complex_drive = torch.complex(amplitudes * torch.cos(phases), amplitudes * torch.sin(phases))  # 构造复数激励幅值 / Build complex actuator amplitudes
    numerator = torch.sum(samples.to(torch.complex64) * complex_drive.unsqueeze(0), dim=1)  # 计算每个模态的激励投影 / Compute modal force projections
    denominator = modal_denominator(frequencies_hz, drive_frequency_hz, damping_ratio).to(torch.complex64)  # 计算复数频响分母 / Compute complex response denominator
    coeffs = numerator / (denominator + torch.complex(torch.tensor(1.0e-8, device=denominator.device), torch.tensor(0.0, device=denominator.device)))  # 计算模态响应系数 / Compute modal response coefficients
    if modal_scale is not None:  # 检查是否使用真实 COMSOL 校准 / Check whether real-COMSOL calibration is used
        coeffs = coeffs * modal_scale.to(coeffs.device).to(torch.complex64)  # 应用模态参与修正 / Apply modal participation correction
    return coeffs / (torch.linalg.norm(coeffs) + 1.0e-12)  # 返回归一化系数 / Return normalised coefficients


def complex_projection_loss(response_coeffs: torch.Tensor, target_alpha: torch.Tensor) -> torch.Tensor:  # 计算忽略全局复比例的投影损失 / Compute projection loss ignoring global complex scale
    target = target_alpha.to(torch.complex64)  # 转换目标系数为复数 / Convert target coefficients to complex
    response = response_coeffs / (torch.linalg.norm(response_coeffs) + 1.0e-12)  # 归一化响应系数 / Normalise response coefficients
    target = target / (torch.linalg.norm(target) + 1.0e-12)  # 归一化目标系数 / Normalise target coefficients
    scale = torch.sum(torch.conj(response) * target) / (torch.sum(torch.conj(response) * response) + 1.0e-12)  # 求最佳全局复比例 / Solve best global complex scale
    residual = response * scale - target  # 计算残差 / Compute residual
    return torch.real(torch.sum(torch.conj(residual) * residual))  # 返回实数平方误差 / Return real squared error
