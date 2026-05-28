from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import math  # 导入数学函数 / Import math helpers
from dataclasses import dataclass  # 导入数据类装饰器 / Import dataclass decorator

import torch  # 导入张量库 / Import tensor library

from src.scoring.amplitude_valley_loss import amplitude_valley_loss  # 复用 W2 单频损失 / Reuse W2 single-frequency loss


@dataclass  # 数据类装饰器 / Dataclass decorator
class MultiFrequencyComposite:  # 多频复合振幅结果 / Multi-frequency composite result
    composite_amplitude: torch.Tensor  # 加权 RMS 振幅图（实数） / Weighted RMS amplitude (real)
    per_freq_amplitudes: list[torch.Tensor]  # 每个频率的振幅图 / Per-frequency amplitude maps
    weights_normalised: torch.Tensor  # 归一化权重 / Normalised weights
    frequencies_hz: torch.Tensor  # 频率值（Hz） / Frequencies in Hz


def weights_from_logits(weight_logits: torch.Tensor) -> torch.Tensor:  # 用 softmax 把 logits 转成凸组合权重 / Convert logits to a simplex via softmax
    return torch.softmax(weight_logits, dim=0)  # 单纯形归一化 / Simplex normalisation


def frequencies_from_logits(freq_logits: torch.Tensor, f_min: float, f_max: float) -> torch.Tensor:  # 用 sigmoid 把 logits 映射到 [f_min, f_max] / Map logits to [f_min, f_max] via sigmoid
    return float(f_min) + (float(f_max) - float(f_min)) * torch.sigmoid(freq_logits)  # 区间内插 / Interpolate inside range


def compose_multifreq_amplitude(per_freq_responses: list[torch.Tensor], weights: torch.Tensor) -> torch.Tensor:  # 把 K 个复数响应加权合成 RMS 振幅图 / Weighted RMS composition of K complex responses
    if len(per_freq_responses) == 0:  # 没有频率则报错 / Empty input is invalid
        raise ValueError("per_freq_responses must contain at least one frequency. / per_freq_responses 至少要有一个频率。")  # 抛出错误 / Raise error
    if weights.numel() != len(per_freq_responses):  # 检查权重维度 / Check weight length
        raise ValueError(f"weights length {weights.numel()} != number of responses {len(per_freq_responses)}. / 权重数量与响应数量不一致。")  # 抛出错误 / Raise error
    amp_squared_sum = None  # 累加器 / Accumulator
    for w, u in zip(weights, per_freq_responses):  # 遍历频率 / Iterate per-frequency
        amp_sq = torch.abs(u) ** 2  # |u(ω_k)|² / Energy density
        weighted = w * amp_sq  # 加权能量 / Weighted energy
        amp_squared_sum = weighted if amp_squared_sum is None else amp_squared_sum + weighted  # 累加 / Accumulate
    return torch.sqrt(amp_squared_sum + 1.0e-18)  # 取 sqrt 得到 RMS 振幅 / Take sqrt for RMS amplitude


def multifreq_amplitude_valley_loss(per_freq_responses: list[torch.Tensor], weights: torch.Tensor, bundle_tensors: dict[str, torch.Tensor], epsilon: float = 0.060, loss_weights: dict[str, float] | None = None) -> tuple[torch.Tensor, torch.Tensor, dict[str, torch.Tensor]]:  # 多频加权振幅谷线损失 / Multi-frequency weighted amplitude-valley loss
    composite_amp = compose_multifreq_amplitude(per_freq_responses, weights)  # 合成 RMS 振幅图 / Compose RMS amplitude
    response_as_complex = composite_amp.to(dtype=torch.complex128 if composite_amp.dtype == torch.float64 else torch.complex64) + 0.0j  # 包装成复数（损失内部只用 abs） / Wrap as complex (loss only uses abs)
    total, parts = amplitude_valley_loss(response_as_complex, bundle_tensors["target_points"], bundle_tensors["distance_to_target"], bundle_tensors["valid_mask"], bundle_tensors["plus_points"], bundle_tensors["minus_points"], epsilon=float(epsilon), weights=loss_weights)  # 复用 W2 损失 / Reuse W2 loss
    return total, composite_amp, parts  # 返回损失、合成图、分量 / Return loss, composite, parts


def frequency_separation_penalty(frequencies_hz: torch.Tensor, min_gap_hz: float = 30.0) -> torch.Tensor:  # 惩罚频率过近 / Penalise frequencies that are too close
    if frequencies_hz.numel() < 2:  # 单频不惩罚 / Single freq has no separation
        return frequencies_hz.new_tensor(0.0)  # 返回零 / Return zero
    sorted_freqs, _ = torch.sort(frequencies_hz)  # 排序 / Sort
    gaps = sorted_freqs[1:] - sorted_freqs[:-1]  # 相邻间隔 / Adjacent gaps
    deficit = torch.clamp(float(min_gap_hz) - gaps, min=0.0)  # 不足部分 / Deficit below threshold
    return torch.mean(deficit ** 2) / (float(min_gap_hz) ** 2 + 1.0e-9)  # 归一化平方惩罚 / Normalised squared penalty


def weight_sparsity_penalty(weights: torch.Tensor, target_active: int) -> torch.Tensor:  # 引导有效频率数量接近 target_active / Encourage active count near target_active
    effective = 1.0 / (torch.sum(weights ** 2) + 1.0e-9)  # 有效数 = 1/Σwk² / Effective number = 1/Σwk²
    target = float(target_active)  # 目标有效数 / Target effective count
    return (effective - target) ** 2 / (target ** 2 + 1.0e-9)  # 归一化平方惩罚 / Normalised squared penalty


def initialise_freq_logits(num_freqs: int, f_min: float, f_max: float, dtype: torch.dtype = torch.float64, device: torch.device | str = "cpu") -> torch.Tensor:  # 等间距初始化频率 logits / Initialise frequency logits evenly
    fractions = torch.linspace(0.1, 0.9, int(num_freqs), dtype=dtype, device=device)  # 均匀分位 / Even quantiles
    eps = 1.0e-6  # 避免边界 / Avoid edges
    clamped = torch.clamp(fractions, eps, 1.0 - eps)  # 夹到开区间 / Clip to open interval
    return torch.log(clamped / (1.0 - clamped))  # 反 sigmoid / Inverse sigmoid


def initialise_weight_logits(num_freqs: int, dtype: torch.dtype = torch.float64, device: torch.device | str = "cpu") -> torch.Tensor:  # 等权初始化（softmax 后均匀） / Initialise to uniform weights after softmax
    return torch.zeros(int(num_freqs), dtype=dtype, device=device)  # 全零 / All zeros


def summarise_weight_distribution(weights: torch.Tensor, frequencies_hz: torch.Tensor) -> dict[str, float]:  # 汇总权重分布（仅 forward，无梯度） / Summarise weight distribution (forward only)
    with torch.no_grad():  # 取数据 / No grad
        w = weights.detach().cpu().numpy()  # 权重 / Weights
        f = frequencies_hz.detach().cpu().numpy()  # 频率 / Frequencies
        effective = float(1.0 / (float((w ** 2).sum()) + 1.0e-9))  # 有效数 / Effective count
        top_idx = int(w.argmax())  # 最大权重位置 / Argmax index
        return {"effective_count": effective, "top_weight": float(w[top_idx]), "top_frequency_hz": float(f[top_idx]), "freq_min_hz": float(f.min()), "freq_max_hz": float(f.max()), "weight_min": float(w.min()), "weight_max": float(w.max())}  # 返回字典 / Return dict
