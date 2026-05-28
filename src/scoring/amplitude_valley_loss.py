from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import torch  # 导入张量计算库 / Import tensor computation library

DEFAULT_AMPLITUDE_VALLEY_WEIGHTS = {"target": 2.0, "extra": 5.0, "contrast": 1.2, "compact": 0.25}  # 定义默认振幅谷线权重 / Define default amplitude-valley weights


def normalised_amplitude(response: torch.Tensor) -> torch.Tensor:  # 计算归一化振幅 / Compute normalised amplitude
    amplitude = torch.abs(response)  # 计算复数响应振幅 / Compute complex-response amplitude
    return amplitude / (torch.amax(amplitude) + 1.0e-8)  # 按最大振幅归一化 / Normalise by maximum amplitude


def amplitude_valley_loss(response: torch.Tensor, target_points: torch.Tensor, distance_to_target: torch.Tensor, valid_mask: torch.Tensor, plus_points: torch.Tensor, minus_points: torch.Tensor, epsilon: float = 0.060, weights: dict[str, float] | None = None) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:  # 计算强迫响应低振幅谷线损失 / Compute forced-response low-amplitude valley loss
    selected_weights = DEFAULT_AMPLITUDE_VALLEY_WEIGHTS if weights is None else {**DEFAULT_AMPLITUDE_VALLEY_WEIGHTS, **weights}  # 合并默认和自定义权重 / Merge default and custom weights
    amplitude = normalised_amplitude(response)  # 计算归一化振幅 / Compute normalised amplitude
    target_amplitude = amplitude[target_points[:, 0], target_points[:, 1]]  # 读取目标线振幅 / Read amplitude on target line
    target_loss = torch.mean(target_amplitude * target_amplitude)  # 惩罚目标线振幅不低 / Penalise non-low amplitude on target
    valley_soft = torch.exp(-((amplitude / float(epsilon)) ** 2)) * valid_mask  # 构造软低振幅区域 / Build soft low-amplitude region
    extra_loss = torch.sum(valley_soft * distance_to_target) / (torch.sum(valley_soft) + 1.0e-8)  # 惩罚远离目标的低振幅区 / Penalise low-amplitude regions far from target
    if plus_points.numel() == 0 or minus_points.numel() == 0:  # 检查是否缺少两侧采样 / Check whether side samples are missing
        contrast_loss = response.real.new_tensor(0.0)  # 无采样则对比项为零 / Use zero contrast loss without samples
    else:  # 处理有两侧采样的情况 / Handle available side samples
        side_plus = amplitude[plus_points[:, 0], plus_points[:, 1]]  # 读取一侧振幅 / Read one-side amplitudes
        side_minus = amplitude[minus_points[:, 0], minus_points[:, 1]]  # 读取另一侧振幅 / Read other-side amplitudes
        side_mean = 0.5 * (torch.mean(side_plus) + torch.mean(side_minus))  # 计算两侧平均振幅 / Compute average side amplitude
        contrast_loss = torch.relu(torch.mean(target_amplitude) - side_mean + 0.12)  # 要求目标线低于两侧 / Require target to be lower than sides
    compact_loss = torch.mean(valley_soft)  # 惩罚整片区域都低振幅 / Penalise broad low-amplitude regions
    total = selected_weights["target"] * target_loss + selected_weights["extra"] * extra_loss + selected_weights["contrast"] * contrast_loss + selected_weights["compact"] * compact_loss  # 合成总损失 / Combine total loss
    parts = {"target": target_loss, "extra": extra_loss, "contrast": contrast_loss, "compact": compact_loss, "total": total}  # 记录分量 / Record components
    return total, parts  # 返回总损失和分量 / Return total loss and components
