from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import torch  # 导入张量优化库 / Import tensor optimisation library

DEFAULT_ZERO_CONTOUR_WEIGHTS = {"target": 1.15, "extra": 1.35, "cross": 0.55, "sharp": 0.12}  # 定义零线损失默认权重 / Define default zero-contour loss weights


def normalise_field(u: torch.Tensor) -> torch.Tensor:  # 归一化位移场 / Normalise displacement field
    return u / (torch.amax(torch.abs(u)) + 1.0e-8)  # 按最大绝对值缩放 / Scale by maximum absolute value


def compute_grad_norm(u: torch.Tensor) -> torch.Tensor:  # 计算位移场梯度幅值 / Compute displacement-field gradient magnitude
    dy = torch.zeros_like(u)  # 创建 y 梯度数组 / Create y-gradient array
    dx = torch.zeros_like(u)  # 创建 x 梯度数组 / Create x-gradient array
    dy[1:-1, :] = 0.5 * (u[2:, :] - u[:-2, :])  # 中心差分计算 y 梯度 / Compute y gradient with centred differences
    dx[:, 1:-1] = 0.5 * (u[:, 2:] - u[:, :-2])  # 中心差分计算 x 梯度 / Compute x gradient with centred differences
    dy[0, :] = u[1, :] - u[0, :]  # 前向差分处理上边界 / Use forward difference on top edge
    dy[-1, :] = u[-1, :] - u[-2, :]  # 后向差分处理下边界 / Use backward difference on bottom edge
    dx[:, 0] = u[:, 1] - u[:, 0]  # 前向差分处理左边界 / Use forward difference on left edge
    dx[:, -1] = u[:, -1] - u[:, -2]  # 后向差分处理右边界 / Use backward difference on right edge
    return torch.sqrt(dx * dx + dy * dy + 1.0e-12)  # 返回稳定梯度幅值 / Return stable gradient magnitude


def zero_contour_loss(u: torch.Tensor, target_points: torch.Tensor, distance_to_target: torch.Tensor, valid_mask: torch.Tensor, plus_points: torch.Tensor, minus_points: torch.Tensor, epsilon: float = 0.045, weights: dict[str, float] | None = None) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:  # 计算可微零等值线损失 / Compute differentiable zero-contour loss
    selected_weights = DEFAULT_ZERO_CONTOUR_WEIGHTS if weights is None else {**DEFAULT_ZERO_CONTOUR_WEIGHTS, **weights}  # 合并默认和自定义权重 / Merge default and custom weights
    u_norm = normalise_field(u)  # 归一化响应场 / Normalise response field
    target_values = u_norm[target_points[:, 0], target_points[:, 1]]  # 读取目标骨架位移 / Read displacement on target skeleton
    target_loss = torch.mean((target_values / float(epsilon)) ** 2)  # 惩罚目标线上不为零 / Penalise nonzero displacement on target line
    zero_soft = torch.exp(-((u_norm / float(epsilon)) ** 2)) * valid_mask  # 生成软零线权重 / Build soft zero-line weights
    extra_loss = torch.sum(zero_soft * distance_to_target) / (torch.sum(zero_soft) + 1.0e-8)  # 惩罚远离目标的额外零线 / Penalise extra zero contours far from target
    if plus_points.numel() == 0 or minus_points.numel() == 0:  # 检查是否缺少法向采样点 / Check whether normal samples are missing
        cross_loss = u_norm.new_tensor(0.0)  # 缺样本时交叉项为零 / Use zero crossing loss when samples are missing
    else:  # 处理存在法向采样的情况 / Handle available normal samples
        plus_values = u_norm[plus_points[:, 0], plus_points[:, 1]]  # 读取目标线一侧位移 / Read displacement on one target side
        minus_values = u_norm[minus_points[:, 0], minus_points[:, 1]]  # 读取目标线另一侧位移 / Read displacement on the other target side
        cross_loss = torch.mean(torch.nn.functional.softplus(10.0 * plus_values * minus_values))  # 惩罚两侧同号 / Penalise same-sign values across the target
    grad_norm = compute_grad_norm(u_norm)  # 计算归一化梯度幅值 / Compute normalised gradient magnitude
    sharp_loss = torch.mean(torch.exp(-((grad_norm[target_points[:, 0], target_points[:, 1]] ** 2) / 0.020)))  # 惩罚宽糊低振幅区 / Penalise broad flat near-zero patches
    total = selected_weights["target"] * target_loss + selected_weights["extra"] * extra_loss + selected_weights["cross"] * cross_loss + selected_weights["sharp"] * sharp_loss  # 合成总损失 / Combine total loss
    parts = {"target": target_loss, "extra": extra_loss, "cross": cross_loss, "sharp": sharp_loss, "total": total}  # 记录损失分量 / Record loss components
    return total, parts  # 返回总损失和分量 / Return total loss and parts
