from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

"""W9 — Surrogate-COMSOL trust-region calibration loop (Pollock homotopy).
W9 —— 代理-COMSOL 信赖域校正回路。

动机 / Motivation:
Sprint 1 实验明确显示：surrogate (Kirchhoff plate) 上的优化胜利 (+SBS, +13%)
**没有传递到 COMSOL (Mindlin plate)**。Surrogate-COMSOL gap 是真正的瓶颈，
而不是优化算法本身。

Sprint 1 experiments revealed that surrogate-side optimisation gains DO NOT transfer
to COMSOL. Fixing this gap is the highest-leverage engineering task.

方法 / Method:
1. Outer iterations alternate between W8 surrogate optimisation and COMSOL eval.
2. After each COMSOL eval at H_k, store residual r_k(x) = y_COMSOL(x) - y_surrogate(x).
3. Next W8 inner uses CALIBRATED surrogate: y_calibrated(H) = y_surr(H) + w(H, H_k) * r_k
   where w(H, H_k) = exp(-|H - H_k|² / σ²) fades to 0 far from anchor.
4. Trust region adapts: if surrogate's predicted improvement matched COMSOL's actual
   improvement, expand (more aggressive next iter); otherwise shrink.

This is the formal version of Pollock (2010) trust-region homotopy adapted for
the differentiable plate / COMSOL Multiphysics inverse-design pipeline.

参考 / References:
- Hammond et al. 2022 Opt. Express 30:4467 (photonic large-scale trust-region adjoint)
- Conn, Gould & Toint 2000 (Trust-Region Methods)
- Allaire & Jouve 2008 (structural optimisation trust-region)
"""

import json  # JSON / JSON
import math  # 数学 / Math
import shutil  # shutil / shutil
import time  # 时间 / Time
from dataclasses import dataclass, field  # 数据类 / Dataclass
from pathlib import Path  # 路径 / Paths

import numpy as np  # NumPy / NumPy


@dataclass  # 数据类 / Dataclass
class TrustRegionAnchor:  # 信赖域锚点 / Trust-region anchor
    iteration: int  # 第几轮 / Iteration
    H_grid: np.ndarray  # H 厚度场 (15x15) / Thickness field
    residual_amp: np.ndarray  # COMSOL - surrogate 的 256x256 振幅残差 / Amplitude residual
    comsol_amp: np.ndarray  # COMSOL RMS 合成 / COMSOL RMS composite
    surrogate_amp: np.ndarray  # 该 H 下 surrogate 的 RMS 合成 / Surrogate RMS composite
    comsol_enrichment: float  # 真 enrichment / True enrichment
    surrogate_enrichment: float  # 代理 enrichment / Surrogate enrichment
    freqs_hz: list[float]  # 该轮频率 / Frequencies
    weights: list[float]  # 该轮权重 / Weights


@dataclass  # 数据类 / Dataclass
class TrustRegionConfig:  # 信赖域配置 / Trust-region config
    outer_iterations: int = 4  # 外层迭代 / Outer iters
    inner_w8_steps: int = 80  # W8 内层步数 / W8 inner steps
    inner_w8_lr_H: float = 0.05  # W8 内层 H LR / Inner LR
    inner_w8_lr_freq: float = 0.10  # 频率 LR / Freq LR
    inner_w8_lr_weight: float = 0.10  # 权重 LR / Weight LR
    num_frequencies: int = 6  # 频率数 / Freq count
    f_min_hz: float = 120.0  # 频率下限 / Freq min
    f_max_hz: float = 1200.0  # 频率上限 / Freq max
    initial_trust_radius_mm: float = 0.5  # 初始信赖半径（H 空间欧氏距离 mm）/ Initial trust radius
    trust_radius_min_mm: float = 0.05  # 最小信赖半径 / Min radius
    trust_radius_max_mm: float = 2.0  # 最大信赖半径 / Max radius
    trust_radius_expand: float = 1.5  # 扩张因子 / Expansion
    trust_radius_shrink: float = 0.5  # 收缩因子 / Shrinkage
    ratio_expand_threshold: float = 0.75  # 比率扩张阈值 / Expand threshold
    ratio_shrink_threshold: float = 0.25  # 比率收缩阈值 / Shrink threshold
    calibration_sigma_factor: float = 1.0  # 高斯衰减 σ = trust_radius × factor / σ factor
    freeze_freqs_after_iter: int = 1  # 第几轮后冻结 freq/weight / Freeze after iter
    sbs_seed_path: str | None = None  # 可选 SBS 种子 / Optional SBS seed
    proxy_grid_size: int = 25  # 代理网格 / Proxy grid
    damping_ratio: float = 0.02  # 阻尼 / Damping
    smoothness_weight: float = 4.0  # 平滑罚 / Smoothness


def make_calibration_npz(anchors: list[TrustRegionAnchor], trust_radius_mm: float, sigma_factor: float, output_path: Path) -> dict:  # 把锚点序列化为 NPZ 给 W8 inner 用 / Serialise anchors to NPZ for W8 inner
    sigma = float(trust_radius_mm) * float(sigma_factor)  # σ / Sigma
    data: dict[str, np.ndarray] = {}  # 数据 / Data
    if anchors:  # 有锚点 / Has anchors
        H_stack = np.stack([a.H_grid for a in anchors], axis=0)  # (N, 15, 15)
        resid_stack = np.stack([a.residual_amp for a in anchors], axis=0)  # (N, 256, 256)
        data["H_anchors"] = H_stack.astype(np.float64)  # 厚度锚点 / H anchors
        data["residual_anchors"] = resid_stack.astype(np.float64)  # 残差锚点 / Residual anchors
        data["sigma_mm"] = np.float64(sigma)  # σ / Sigma
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 建目录 / Mkdir
    np.savez(output_path, **data)  # 保存 / Save
    return {"num_anchors": len(anchors), "sigma_mm": sigma, "path": str(output_path)}  # 元信息 / Meta


def trust_region_ratio(comsol_history: list[float], surrogate_history: list[float]) -> float:  # 计算 actual/predicted 改善比率 / Compute actual/predicted ratio
    if len(comsol_history) < 2 or len(surrogate_history) < 2:  # 数据不够 / Not enough
        return 1.0  # 中性 / Neutral
    actual_imp = comsol_history[-1] - comsol_history[-2]  # 真实改善 / Actual improvement
    predicted_imp = surrogate_history[-1] - surrogate_history[-2]  # 预测改善 / Predicted improvement
    if abs(predicted_imp) < 1.0e-6:  # 预测改善太小 / Predicted ~0
        return 1.0 if abs(actual_imp) < 1.0e-3 else (1.0 if actual_imp > 0 else -1.0)  # 退化 / Degenerate
    return float(actual_imp / predicted_imp)  # 比率 / Ratio


def update_trust_radius(ratio: float, trust_radius_mm: float, cfg: TrustRegionConfig) -> tuple[float, str]:  # 根据比率更新信赖半径 / Update trust radius
    if ratio > cfg.ratio_expand_threshold:  # 好 / Good
        new_radius = min(trust_radius_mm * cfg.trust_radius_expand, cfg.trust_radius_max_mm)  # 扩 / Expand
        decision = f"expand (ratio={ratio:.2f} > {cfg.ratio_expand_threshold})"  # 决策 / Decision
    elif ratio > cfg.ratio_shrink_threshold:  # 一般 / OK
        new_radius = trust_radius_mm  # 不变 / Keep
        decision = f"keep (ratio={ratio:.2f})"  # 决策 / Decision
    else:  # 差 / Bad
        new_radius = max(trust_radius_mm * cfg.trust_radius_shrink, cfg.trust_radius_min_mm)  # 缩 / Shrink
        decision = f"shrink (ratio={ratio:.2f} < {cfg.ratio_shrink_threshold})"  # 决策 / Decision
    return new_radius, decision  # 返回 / Return


def summarise_iteration(iteration: int, anchor: TrustRegionAnchor, trust_radius_mm: float, decision: str) -> dict:  # 单次迭代摘要 / One-iter summary
    return {"iteration": int(iteration), "comsol_enrichment": float(anchor.comsol_enrichment), "surrogate_enrichment": float(anchor.surrogate_enrichment), "gap_comsol_minus_surrogate": float(anchor.comsol_enrichment - anchor.surrogate_enrichment), "trust_radius_mm": float(trust_radius_mm), "trust_decision": str(decision), "frequencies_hz": [float(f) for f in anchor.freqs_hz], "weights": [float(w) for w in anchor.weights], "residual_rms": float(np.sqrt((anchor.residual_amp ** 2).mean())), "residual_max": float(np.abs(anchor.residual_amp).max())}  # 字典 / Dict
