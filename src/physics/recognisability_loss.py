from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import math  # 数学函数 / Math
from dataclasses import dataclass  # 数据类 / Dataclass

import torch  # 张量库 / Torch


def _soft_peak(amp: torch.Tensor, top_k_frac: float = 0.02) -> torch.Tensor:  # 用 top-k 均值替代 amax，平滑可微 / Differentiable peak via top-k mean
    n = int(max(int(top_k_frac * amp.numel()), 1))  # 选个数 / Pick count
    flat = amp.flatten()  # 扁平 / Flatten
    topk = torch.topk(flat, n, sorted=False).values  # top-k / Top-k
    return topk.mean()  # 均值 / Mean


def chladni_powder_torch(amp: torch.Tensor, sigma_rel: float = 0.05, top_k_frac: float = 0.02) -> torch.Tensor:  # 可微 Chladni 撒粉密度 / Differentiable Chladni powder density
    peak = _soft_peak(amp, top_k_frac=float(top_k_frac))  # 峰值估计 / Peak estimate
    norm = amp / (peak + 1.0e-9)  # 归一化 / Normalised
    return torch.exp(-((norm / float(sigma_rel)) ** 2))  # 高斯密度 / Gaussian density


def gaussian_contrast_loss(response_complex: torch.Tensor, target_mask: torch.Tensor, sigma_rel: float = 0.05, top_k_frac: float = 0.02) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:  # 高斯对比损失 / Gaussian-contrast loss
    amp = torch.abs(response_complex)  # 振幅 / Amplitude
    powder = chladni_powder_torch(amp, sigma_rel=float(sigma_rel), top_k_frac=float(top_k_frac))  # 撒粉密度 / Powder density
    target = target_mask.to(dtype=powder.dtype)  # 目标 / Target
    bg = 1.0 - target  # 背景 / Background
    n_t = target.sum() + 1.0e-9  # 目标像素 / Target pixels
    n_b = bg.sum() + 1.0e-9  # 背景像素 / Background pixels
    mean_target = (powder * target).sum() / n_t  # 目标均值 / Target mean
    mean_bg = (powder * bg).sum() / n_b  # 背景均值 / Background mean
    contrast = mean_target / (mean_bg + 1.0e-9)  # 对比度 / Contrast
    loss = -torch.log(contrast + 1.0e-9)  # 取 -log / Take -log
    return loss, {"mean_target": mean_target, "mean_bg": mean_bg, "contrast": contrast, "powder": powder}  # 返回 / Return


def recall_soft_loss(response_complex: torch.Tensor, target_mask: torch.Tensor, percentile_frac: float = 0.20, beta: float = 30.0) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:  # 软 recall 损失 / Soft recall loss
    amp = torch.abs(response_complex)  # 振幅 / Amplitude
    n_pixels = int(amp.numel())  # 像素数 / Pixel count
    k = int(max(int(percentile_frac * n_pixels), 1))  # 分位个数 / Percentile count
    flat = amp.flatten()  # 扁平 / Flatten
    threshold = torch.kthvalue(flat, k).values  # 分位值 / Percentile value
    valley_soft = torch.sigmoid(beta * (threshold - amp) / (threshold + 1.0e-9))  # 软掩码 / Soft mask
    target = target_mask.to(dtype=valley_soft.dtype)  # 目标 / Target
    recall = (valley_soft * target).sum() / (target.sum() + 1.0e-9)  # 软 recall / Soft recall
    loss = -torch.log(recall + 1.0e-9)  # -log / -log
    return loss, {"recall": recall, "valley_soft": valley_soft, "threshold": threshold}  # 返回 / Return


def enrichment_loss(response_complex: torch.Tensor, target_mask: torch.Tensor, sigma_rel: float = 0.05, top_k_frac: float = 0.02) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:  # 可微富集损失 / Differentiable enrichment loss
    amp = torch.abs(response_complex)  # 振幅 / Amplitude
    powder = chladni_powder_torch(amp, sigma_rel=float(sigma_rel), top_k_frac=float(top_k_frac))  # 撒粉 / Powder
    target = target_mask.to(dtype=powder.dtype)  # 目标 / Target
    target_powder = (powder * target).sum()  # 目标粉 / Target powder
    total_powder = powder.sum() + 1.0e-9  # 总粉 / Total powder
    target_area_frac = target.sum() / float(target.numel())  # 占地比 / Area frac
    enrichment = (target_powder / total_powder) / (target_area_frac + 1.0e-9)  # 富集 / Enrichment
    loss = -torch.log(enrichment + 1.0e-9)  # -log / -log
    return loss, {"enrichment": enrichment, "target_powder": target_powder, "total_powder": total_powder, "powder": powder}  # 返回 / Return


@dataclass  # 数据类 / Dataclass
class RecognisabilityLossWeights:  # 可识别度损失权重 / Recognisability loss weights
    enrichment: float = 1.0  # 富集 / Enrichment
    contrast: float = 1.0  # 对比 / Contrast
    recall: float = 0.5  # recall / Recall
    sigma_rel: float = 0.05  # sigma / Sigma
    top_k_frac: float = 0.02  # top-k 分位 / Top-k frac
    percentile_frac: float = 0.20  # recall 分位 / Recall percentile


def combined_recognisability_loss(response_complex: torch.Tensor, target_mask: torch.Tensor, weights: RecognisabilityLossWeights | None = None) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:  # 综合可识别度损失 / Combined recognisability loss
    w = weights or RecognisabilityLossWeights()  # 默认权重 / Default weights
    enr_loss, enr_parts = enrichment_loss(response_complex, target_mask, sigma_rel=float(w.sigma_rel), top_k_frac=float(w.top_k_frac))  # 富集 / Enrichment
    ct_loss, ct_parts = gaussian_contrast_loss(response_complex, target_mask, sigma_rel=float(w.sigma_rel), top_k_frac=float(w.top_k_frac))  # 对比 / Contrast
    rc_loss, rc_parts = recall_soft_loss(response_complex, target_mask, percentile_frac=float(w.percentile_frac))  # recall / Recall
    total = float(w.enrichment) * enr_loss + float(w.contrast) * ct_loss + float(w.recall) * rc_loss  # 总损失 / Total
    parts = {"enrichment_loss": enr_loss, "contrast_loss": ct_loss, "recall_loss": rc_loss, "enrichment": enr_parts["enrichment"], "contrast": ct_parts["contrast"], "recall": rc_parts["recall"], "total": total}  # 分量 / Parts
    return total, parts  # 返回 / Return


def compose_multifreq_amplitude_with_weights(per_freq_responses: list[torch.Tensor], weights: torch.Tensor) -> torch.Tensor:  # 多频加权 RMS 合成 / Multi-frequency weighted RMS composition
    if len(per_freq_responses) == 0:  # 空保护 / Empty guard
        raise ValueError("per_freq_responses must contain at least one frequency. / 至少要有一个频率响应。")  # 抛错 / Raise
    if weights.numel() != len(per_freq_responses):  # 检查 / Check
        raise ValueError(f"weights length {weights.numel()} != number of responses {len(per_freq_responses)}. / 权重维度不一致。")  # 抛错 / Raise
    amp_sq_sum = None  # 累加 / Accumulator
    for w, u in zip(weights, per_freq_responses):  # 遍历 / Iterate
        contrib = w * (torch.abs(u) ** 2)  # 加权能量 / Weighted energy
        amp_sq_sum = contrib if amp_sq_sum is None else amp_sq_sum + contrib  # 累加 / Accumulate
    return torch.sqrt(amp_sq_sum + 1.0e-18)  # sqrt / Sqrt
