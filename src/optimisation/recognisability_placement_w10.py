"""W10 — joint H + ω optimisation on orthotropic Kirchhoff plate.
W10：H + ω 在正交各向异性 Kirchhoff 板上的联合优化。

历史与现状 / History & current state:
W10 originally optimised three groups of variables jointly — per-cell thickness
H, per-cell fibre orientation θ, and the K drive frequencies ω. Empirical work
in 2026-05 (`reports/_battery/BATTERY_FINDINGS.md`) showed θ is a parasitic
dimension under this surrogate: at the off-resonance frequencies W10 actually
probes, ω²M dominates K by ~5 orders of magnitude, so θ (which only enters
through K) has near-zero gradient. The optimiser ended up drifting θ randomly,
and that drift then perturbed the COMSOL anisotropic eigenmodes downstream
into worse configurations. A 10-run battery (5 targets × 2 materials) confirmed
that isotropic PLA (θ trivially uniform) beats anisotropic CF-PETG with
"optimised" θ on 4/6 targets, ties 1, loses only IC.

This file therefore optimises only H + ω. θ is kept as a fixed (zero) field
that still flows into the OrthotropicPlate stiffness assembly — the material
remains genuinely orthotropic (sr / gr from config), but every cell has the
same principal axis aligned with the global x-axis. The all-zero θ field is
also written to `theta_continuous_*.csv` for backwards compatibility with the
downstream COMSOL pipeline which expects those files. /
W10 现在只优化 H + ω。θ 作为全零常量字段仍流过正交板装配，材料 sr/gr
保留各向异性效果，只是每格主轴对齐全局 x 轴。零 θ CSV 仍写给下游 COMSOL。

关键参数 / Key knobs:
- material.stiffness_ratio (E_||/E_⊥) 仍生效：板物理本身仍是正交各向异性
  · SLA grey resin ≈ 1.05  ≈ 各向同性
  · FDM PLA          ≈ 1.0  → 推荐
  · FDM CF-PETG      ≈ 3.0  → 沿打印方向偏强；不再做 per-cell 旋转
"""
from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # JSON / JSON
import math  # 数学 / Math
from dataclasses import dataclass, field  # 数据类 / Dataclass
from pathlib import Path  # 路径 / Paths

import numpy as np  # NumPy / NumPy
import torch  # Torch / Torch

from src.candidate.constraints import center_cells_for_grid  # 中心 / Centre
from src.candidate.constraints import enforce_center_constraint  # 中心约束 / Centre constraint
from src.candidate.constraints import repair_neighbor_constraint  # 邻格修复 / Neighbour repair
from src.optimisation.gradient_optimizer import apply_center_clamp  # 中心夹持 / Centre clamp
from src.optimisation.gradient_optimizer import initial_theta as initial_h_logit  # H 重参化初值 / H logit init
from src.optimisation.gradient_optimizer import neighbour_smoothness_penalty  # 邻平滑 / Smoothness
from src.optimisation.gradient_optimizer import thickness_from_theta  # sigmoid 重参化 / Sigmoid reparam
from src.physics.multifreq_amp_valley import frequencies_from_logits  # 频率 / Freqs
from src.physics.multifreq_amp_valley import frequency_separation_penalty  # 间隔 / Separation
from src.physics.multifreq_amp_valley import initialise_freq_logits  # 频率初值 / Freq init
from src.physics.multifreq_amp_valley import initialise_weight_logits  # 权重初值 / Weight init
from src.physics.multifreq_amp_valley import summarise_weight_distribution  # 摘要 / Summary
from src.physics.multifreq_amp_valley import weights_from_logits  # 权重 / Weights
from src.physics.orthotropic_plate import OrthotropicPlate  # 正交板 / Ortho plate
from src.physics.recognisability_loss import RecognisabilityLossWeights  # 损失权重 / Loss weights
from src.physics.recognisability_loss import combined_recognisability_loss  # 综合 / Combined
from src.physics.recognisability_loss import compose_multifreq_amplitude_with_weights  # 合成 / Compose


@dataclass  # 数据类 / Dataclass
class W10AnisotropyConfig:  # W10 配置 / W10 config
    proxy_grid_size: int = 25  # 代理网格 / Proxy grid
    num_frequencies: int = 6  # 频率数 / K
    f_min_hz: float = 120.0  # 频率下限 / Freq lower
    f_max_hz: float = 1200.0  # 频率上限 / Freq upper
    damping_ratio: float = 0.02  # 阻尼 / Damping
    num_steps: int = 250  # Adam 步数 / Adam steps
    learning_rate_H: float = 0.05  # H 学习率 / H LR
    learning_rate_freq: float = 0.10  # 频率 / Freq LR
    learning_rate_weight: float = 0.10  # 权重 / Weight LR
    weight_decay: float = 0.0  # 衰减 / Weight decay
    plateau_patience: int = 60  # 平台容忍 / Plateau
    plateau_min_delta: float = 1.0e-4  # 最小改善 / Min delta
    snapshot_every: int = 25  # 快照间隔 / Snapshot
    dtype: torch.dtype = field(default=torch.float64)  # 精度 / Precision
    device: str = "cpu"  # 设备 / Device
    base_accel_m_s2: float = 1.0  # 加速度 / Accel
    smoothness_weight: float = 4.0  # H 邻平滑 / H smoothness weight
    smoothness_max_diff_mm: float | None = None  # H 邻差上限 / H neighbour diff cap
    freq_separation_min_hz: float = 30.0  # 频率间隔 / Freq gap
    freq_separation_weight: float = 0.5  # 间隔罚 / Separation
    freeze_freq_first_steps: int = 60  # 冻结 / Freeze
    initial_frequencies_hz: list[float] | None = None  # 频率初值 / Init freqs
    enrichment_weight: float = 1.0  # 富集权重 / Enrichment
    contrast_weight: float = 1.0  # 对比权重 / Contrast
    # recall_weight bumped 0.5 → 1.5 (2026-05) — for thin / sparse / 4-fold
    # symmetric targets, low recall was the dominant failure mode: high
    # enrichment + 30% recall = "right pattern, only 1/3 of outline covered".
    # Higher recall pressure forces the optimiser to spread powder across
    # more of the target outline, even at the cost of some enrichment. /
    # recall 加权从 0.5 提到 1.5：细线/4 重对称 target 的主要短板是 recall 太低
    recall_weight: float = 1.5  # recall 权重 / Recall
    # Weight entropy regulariser (2026-05). Without it, W10 routinely
    # collapses to a single dominant frequency (effective_count ≈ 1 of K=6),
    # losing the multi-frequency composite capability that's the whole
    # point of the algorithm. Adds  -λ · H(softmax(weights))  to the loss;
    # since H is maximised when weights are uniform, this pulls toward
    # effective_count → K when nothing else differentiates the freqs. /
    # 权重熵正则：防 weights 坍缩到单一频率（effective_count → 1）
    weight_entropy_weight: float = 0.10  # 权重熵正则强度 / Entropy regularizer
    sigma_rel: float = 0.05  # 高斯 σ / Gaussian σ
    # Sigma annealing: start with a broader Gaussian powder window and linearly
    # shrink to ``sigma_rel`` over the first ``sigma_anneal_steps`` steps. The
    # default loss with sigma_rel=0.05 is so sharp that initial enrichment for
    # thin/sparse targets underflows to ~1e-40 and the gradient cliff
    # (-log(x + 1e-9)) zeroes out — Adam never gets a useful signal. Starting
    # sigma at e.g. 0.20 keeps initial enrichment near O(1), so the optimiser
    # can actually move H in a meaningful direction before tightening. /
    # Sigma 退火：起步用宽 powder（粗），训练前 N 步线性收紧到 sigma_rel；
    # 防止细线/稀疏目标在 sigma=0.05 下 enrichment 起步即 1e-40、梯度被 epsilon 削平
    sigma_anneal_start: float | None = None  # None = 关闭 / None disables
    sigma_anneal_steps: int = 100  # 退火步数 / Anneal steps
    # Target dilation (on proxy grid). For thin-curve targets (1-2 px wide
    # outlines), even a 25×25 proxy preserves the sharpness — leaving the
    # optimiser with too little overlap area for the gradient signal. /
    # 目标膨胀（proxy 网格上）：细线 target 在 25×25 proxy 上仍是 1-2 像素宽，
    # 几乎没有 powder 重叠区域；膨胀 1-2 像素能给优化提供有效梯度
    target_dilation_px: int = 0  # 0 = 不膨胀 / 0 disables
    recall_percentile_frac: float = 0.20  # recall 分位 / Recall percentile
    sinkhorn_weight: float = 0.0  # Sinkhorn 权重 / Sinkhorn weight
    sinkhorn_epsilon: float = 0.01  # Sinkhorn ε / Sinkhorn ε
    sinkhorn_target_irreps: list[str] | None = None  # irrep 投影 / irrep projection
    stiffness_ratio: float | None = None  # 各向异性比覆盖 / Override anisotropy ratio
    shear_ratio: float | None = None  # 剪切比覆盖 / Override shear ratio
    # H init thickness for the sigmoid reparam. Defaults to None → use the
    # midpoint of (h_min, h_max) so Adam starts in the linear region of the
    # sigmoid where the gradient signal is strong. Set explicitly to override.
    # Why this is NOT bound to thickness.default_mm: that field is the
    # center-clamp value (a physical design constraint), which is currently
    # 2.0 mm = h_max. Initialising every H cell there puts the optimiser deep
    # in the sigmoid saturation zone (dsig/dx ≈ 0), so Adam can't move H —
    # a smoke test confirmed default_mm=2.0 → best_enrichment ≈ 0,
    # default_mm=1.3 → best_enrichment ≈ 0.72 with the same number of steps.
    # H 初值厚度。默认 None = (h_min+h_max)/2 中点，避开 sigmoid 饱和区。
    # 不绑定 default_mm（中心夹持的物理值，目前=h_max，会卡死优化）。
    h_init_mm: float | None = None  # H init thickness / H 初始厚度


@dataclass  # 数据类 / Dataclass
class W10Trace:  # W10 轨迹 / Trace
    total_loss: list[float] = field(default_factory=list)  # / Total
    recognisability_loss: list[float] = field(default_factory=list)  # / Recog
    enrichment: list[float] = field(default_factory=list)  # / Enrichment
    contrast: list[float] = field(default_factory=list)  # / Contrast
    recall: list[float] = field(default_factory=list)  # / Recall
    smoothness_loss: list[float] = field(default_factory=list)  # H 平滑 / H smoothness
    freq_sep_loss: list[float] = field(default_factory=list)  # / Separation
    sinkhorn_loss: list[float] = field(default_factory=list)  # / Sinkhorn
    frequencies_history: list[list[float]] = field(default_factory=list)  # / Freqs
    weights_history: list[list[float]] = field(default_factory=list)  # / Weights


def _build_thickness(h_logit: torch.Tensor, grid_size: int, h_min: float, h_max: float, default_h: float, centre_cells: list[tuple[int, int]]) -> torch.Tensor:  # H 重参化 / Build thickness
    H_raw = thickness_from_theta(h_logit, float(h_min), float(h_max))  # sigmoid 重参 / Reparam
    H_clipped = torch.clamp(H_raw, min=float(h_min), max=float(h_max))  # clamp / Clamp
    return apply_center_clamp(H_clipped, float(default_h), centre_cells)  # 中心夹持 / Clamp


def _build_target_mask_proxy(target_binary_full: np.ndarray, proxy_grid_size: int, device: torch.device, dtype: torch.dtype, dilation_px: int = 0) -> torch.Tensor:  # 目标降采样 / Downsample target
    from src.scoring.geometry_helpers import resize_binary_nearest  # 延迟导入 / Lazy
    resized = resize_binary_nearest(target_binary_full.astype(bool), int(proxy_grid_size))  # 调整 / Resize
    if int(dilation_px) > 0:  # 膨胀 / Dilation
        try:
            from scipy.ndimage import binary_dilation  # 延迟导入 / Lazy
            from scipy.ndimage import generate_binary_structure  # 延迟导入 / Lazy
            struct = generate_binary_structure(2, 2)  # 8-邻接 / 8-connectivity
            resized = binary_dilation(resized, structure=struct, iterations=int(dilation_px))  # 多次膨胀 / Iterate
        except ImportError:
            print(f"[W10] scipy.ndimage unavailable; skipping target dilation (requested {dilation_px} px). / scipy 不可用，跳过目标膨胀")
    return torch.as_tensor(resized.astype(np.float64), dtype=dtype, device=device)  # 张量 / Tensor


def run_w10_anisotropy_placement(config: dict, target_binary: np.ndarray, opt_config: W10AnisotropyConfig, output_dir: Path, verdict: dict | None = None, initial_H_mm: np.ndarray | None = None) -> dict:  # W10 主入口 / W10 main
    output_dir = Path(output_dir)  # 路径 / Path
    output_dir.mkdir(parents=True, exist_ok=True)  # 建目录 / Mkdir
    device = torch.device(opt_config.device)  # 设备 / Device
    dtype = opt_config.dtype  # 精度 / Precision
    thickness_cfg = config["thickness"]  # 厚度配置 / Thickness
    h_min = float(thickness_cfg["min_mm"])  # 下限 / Min
    h_max = float(thickness_cfg["max_mm"])  # 上限 / Max
    default_h = float(thickness_cfg.get("default_mm", h_max))  # 中心夹持 / Centre clamp
    # H init thickness: defaults to (h_min+h_max)/2 unless opt_config.h_init_mm
    # is explicitly provided. Crucially decoupled from default_h (which is the
    # physical center-clamp value, currently sitting at h_max=2.0 mm). Initing
    # at h_max puts every cell deep in sigmoid saturation, so Adam can't move
    # H; midpoint init keeps the gradient signal strong.
    # H 初值厚度：跟中心夹持解耦，默认中点；避免 sigmoid 饱和区。
    init_h = float(opt_config.h_init_mm) if opt_config.h_init_mm is not None else 0.5 * (h_min + h_max)
    init_h = float(max(h_min + 1.0e-3, min(h_max - 1.0e-3, init_h)))  # 安全夹紧 / Safety clamp
    grid_size = int(config["project"]["grid_size"])  # 网格 / Grid
    centre_cells = center_cells_for_grid(grid_size)  # 中心单元 / Centre cells
    max_neighbour_diff_mm = float(opt_config.smoothness_max_diff_mm if opt_config.smoothness_max_diff_mm is not None else thickness_cfg.get("max_neighbor_difference_mm", 1.0))  # 邻差 / Diff cap
    K = int(opt_config.num_frequencies)  # K / K
    plate = OrthotropicPlate(config, proxy_grid_size=int(opt_config.proxy_grid_size), base_accel=float(opt_config.base_accel_m_s2), default_damping=float(opt_config.damping_ratio), reference_frequency_hz=0.5 * (float(opt_config.f_min_hz) + float(opt_config.f_max_hz)), stiffness_ratio=opt_config.stiffness_ratio, shear_ratio=opt_config.shear_ratio, dtype=dtype, device=device)  # 正交板 / Ortho plate
    print(f"[W10] OrthotropicPlate ready: N={plate.N}, stiffness_ratio={plate.stiffness_ratio:.3f}, shear_ratio={plate.shear_ratio:.3f}")  # 打印 / Print
    print(f"[W10] E_||={plate.E_parallel_pa:.3e} Pa, E_⊥={plate.E_perp_pa:.3e} Pa, G={plate.G_pp_pa:.3e} Pa")  # 打印 / Print
    target_proxy = _build_target_mask_proxy(target_binary, plate.N, device=device, dtype=dtype, dilation_px=int(opt_config.target_dilation_px))  # 代理目标 / Proxy target
    target_area_frac = float(target_proxy.sum().item()) / float(target_proxy.numel())  # 占地比 / Area frac
    print(f"[W10] target_proxy: {int(target_proxy.sum().item())}/{int(target_proxy.numel())} pixels (area_frac={target_area_frac:.3%}), dilation_px={int(opt_config.target_dilation_px)}")  # / Print
    if target_area_frac < 0.01:  # 极稀疏目标 / Very sparse target
        print(f"[W10] WARNING: target_proxy area_frac={target_area_frac:.3%} is extremely sparse — consider raising --target-dilation-px to give the loss gradient a chance. / 目标过稀疏，建议 --target-dilation-px 加大")  # / Warn

    # === 决策变量初始化 / Initialise decision variables ===
    # H logit / H logit
    if initial_H_mm is not None:  # 提供初值 / Provided
        h0 = np.asarray(initial_H_mm, dtype=np.float64)  # numpy / NumPy
        normalised = np.clip((h0 - h_min) / max(h_max - h_min, 1.0e-6), 1.0e-3, 1.0 - 1.0e-3)  # 归一 / Normalise
        h_logit_init = torch.tensor(np.log(normalised / (1.0 - normalised)), dtype=dtype, device=device)  # 反 sigmoid / Inverse
    else:  # 默认 / Default
        h_logit_init = initial_h_logit(init_h, h_min, h_max, grid_size, dtype).to(device)  # 中点初值 / Mid-range init
        print(f"[W10] H init: {init_h:.3f} mm  (center clamp stays at {default_h:.3f} mm) / H 初值 / 中心夹持")
    h_logit = h_logit_init.detach().clone().requires_grad_(True)  # 优化变量 / Decision variable

    # θ field: held constant at zero. Material remains orthotropic via sr/gr
    # in OrthotropicPlate; per-cell θ rotation was empirically shown to be a
    # parasitic optimisation variable in the ω²M ≫ K regime W10 probes, so it
    # is no longer optimised. The zero field still flows through assemble_K_M
    # so the physics path is unchanged. /
    # θ 字段恒为 0；材料各向异性通过 sr/gr 保留，per-cell 旋转优化已撤
    theta_design = torch.zeros((grid_size, grid_size), dtype=dtype, device=device)

    # 频率 + 权重 / Freqs + weights
    if opt_config.initial_frequencies_hz is not None and len(opt_config.initial_frequencies_hz) == K:  # 显式初值 / Explicit init
        clamp = lambda x: float(min(max(x, float(opt_config.f_min_hz) + 1.0e-3), float(opt_config.f_max_hz) - 1.0e-3))  # clamp / Clamp
        fractions = torch.tensor([(clamp(x) - float(opt_config.f_min_hz)) / max(float(opt_config.f_max_hz) - float(opt_config.f_min_hz), 1.0e-9) for x in opt_config.initial_frequencies_hz], dtype=dtype, device=device)  # 比例 / Fractions
        freq_logits_init = torch.log(fractions / (1.0 - fractions))  # 反 sigmoid / Inverse
    else:  # 均匀 / Uniform
        freq_logits_init = initialise_freq_logits(K, float(opt_config.f_min_hz), float(opt_config.f_max_hz), dtype=dtype, device=device)  # 均匀 / Even
    weight_logits_init = initialise_weight_logits(K, dtype=dtype, device=device)  # 权重 / Weight
    freq_logits = freq_logits_init.detach().clone().requires_grad_(True)  # 优化 / Decision
    weight_logits = weight_logits_init.detach().clone().requires_grad_(True)  # 优化 / Decision

    # Adam param groups: H + freq + weight (θ is fixed, see init above). /
    # Adam 参数组：H + freq + weight；θ 固定不入优化
    param_groups = [
        {"params": [h_logit], "lr": float(opt_config.learning_rate_H)},  # H / H
        {"params": [freq_logits], "lr": float(opt_config.learning_rate_freq)},  # f / f
        {"params": [weight_logits], "lr": float(opt_config.learning_rate_weight)},  # w / w
    ]
    optimiser = torch.optim.Adam(param_groups, weight_decay=float(opt_config.weight_decay))  # Adam / Adam

    sigma_end = float(opt_config.sigma_rel)  # 末态 σ / Final sigma
    sigma_start = float(opt_config.sigma_anneal_start) if opt_config.sigma_anneal_start is not None else sigma_end  # 起态 σ / Initial sigma
    sigma_anneal_steps = max(1, int(opt_config.sigma_anneal_steps))  # 退火步数 / Anneal steps
    if sigma_start != sigma_end:  # 退火生效 / Annealing on
        print(f"[W10] sigma annealing: {sigma_start:.3f} → {sigma_end:.3f} over first {sigma_anneal_steps} steps / Sigma 退火")  # / Print
    def _current_sigma(step: int) -> float:  # 线性退火 / Linear anneal
        if sigma_start == sigma_end:  # 关闭 / Off
            return sigma_end  # / Return
        frac = min(1.0, max(0.0, float(step) / float(sigma_anneal_steps)))  # 比例 / Fraction
        return float(sigma_start + (sigma_end - sigma_start) * frac)  # 插值 / Lerp

    loss_weights = RecognisabilityLossWeights(enrichment=float(opt_config.enrichment_weight), contrast=float(opt_config.contrast_weight), recall=float(opt_config.recall_weight), sigma_rel=float(sigma_start), percentile_frac=float(opt_config.recall_percentile_frac))  # 损失权重 / Loss weights

    trace = W10Trace()  # 轨迹 / Trace
    best_loss = math.inf  # 最佳 / Best
    best_step = 0  # 步号 / Step
    best_H: np.ndarray | None = None  # 缓存 / Cache
    best_freqs: list[float] | None = None  # 缓存 / Cache
    best_weights: list[float] | None = None  # 缓存 / Cache
    best_composite: np.ndarray | None = None  # 缓存 / Cache
    best_metrics: dict[str, float] | None = None  # 缓存 / Cache
    stale = 0  # 平台 / Plateau

    for step in range(int(opt_config.num_steps)):  # 主循环 / Main loop
        optimiser.zero_grad()  # 清零 / Zero
        H_clamped = _build_thickness(h_logit, grid_size, h_min, h_max, default_h, centre_cells)  # H 设计 / H design
        H_proxy = plate.upsample(H_clamped)  # 升采样 H / Upsample H
        theta_proxy = plate.upsample(theta_design)  # 升采样 θ / Upsample θ
        K_full, M_diag = plate.assemble_K_M(H_proxy, theta_proxy)  # 装配 / Assemble
        free = plate.free_indices  # 自由 / Free
        K_free = K_full.index_select(0, free).index_select(1, free)  # 自由 K / Free K
        M_free = torch.clamp(M_diag.index_select(0, free), min=1.0e-18)  # 自由 M / Free M

        if step < int(opt_config.freeze_freq_first_steps):  # 冻结频率/权重 / Freeze
            freq_logits_use = freq_logits.detach()  # / Detach
            weight_logits_use = weight_logits.detach()  # / Detach
        else:  # 解冻 / Unfreeze
            freq_logits_use = freq_logits  # / Enable
            weight_logits_use = weight_logits  # / Enable
        frequencies_hz = frequencies_from_logits(freq_logits_use, float(opt_config.f_min_hz), float(opt_config.f_max_hz))  # 频率 / Freqs
        weights = weights_from_logits(weight_logits_use)  # 权重 / Weights

        per_freq_responses = []  # 响应列表 / Responses
        for k in range(K):  # 遍历频率 / Iterate freq
            omega_k = 2.0 * math.pi * frequencies_hz[k]  # ω / ω
            u_free = plate.direct_forced_response(K_free, M_free, omega_k, float(opt_config.damping_ratio))  # 响应 / Response
            u_grid = plate.expand_to_grid(u_free)  # 网格化 / Scatter
            per_freq_responses.append(u_grid)  # 加入 / Append
        composite_amp = compose_multifreq_amplitude_with_weights(per_freq_responses, weights)  # 合成 / Compose
        composite_complex = composite_amp.to(dtype=torch.complex128 if composite_amp.dtype == torch.float64 else torch.complex64) + 0.0j  # 包装 / Wrap
        loss_weights.sigma_rel = _current_sigma(step)  # 当步 σ / Current sigma (annealed)
        recog_loss, parts = combined_recognisability_loss(composite_complex, target_proxy, weights=loss_weights)  # 综合损失 / Combined

        sinkhorn_part = composite_amp.new_tensor(0.0)  # Sinkhorn 默认 0 / Default 0
        if float(opt_config.sinkhorn_weight) > 0.0:  # 启用 / Enable
            from src.physics.sinkhorn_loss import sinkhorn_powder_target_loss  # 延迟导入 / Lazy
            from src.physics.sinkhorn_loss import sinkhorn_to_irrep_projection  # 延迟导入 / Lazy
            if opt_config.sinkhorn_target_irreps:  # 投影 / Projection
                sinkhorn_part, _ = sinkhorn_to_irrep_projection(composite_amp, target_proxy, irreps=tuple(opt_config.sinkhorn_target_irreps), sigma_rel=float(opt_config.sigma_rel), epsilon=float(opt_config.sinkhorn_epsilon))  # / Sinkhorn
            else:  # 原始 / Raw
                sinkhorn_part, _ = sinkhorn_powder_target_loss(composite_amp, target_proxy, sigma_rel=float(opt_config.sigma_rel), epsilon=float(opt_config.sinkhorn_epsilon))  # / Sinkhorn

        smoothness = neighbour_smoothness_penalty(H_clamped, max_neighbour_diff_mm)  # H 邻平滑 / H smoothness
        freq_sep = frequency_separation_penalty(frequencies_hz, float(opt_config.freq_separation_min_hz)) if step >= int(opt_config.freeze_freq_first_steps) else frequencies_hz.new_tensor(0.0)  # 间隔 / Separation
        # Weight-entropy regulariser. H(w) = -Σ w log(w + 1e-12), max at
        # uniform distribution (H = log K). Subtracting it from the loss
        # pulls weights toward uniform when nothing else discriminates the
        # frequencies, preventing collapse to a single dominant mode. Only
        # active after freq/weights unfreeze. /
        # 权重熵正则：仅在 freq/weight 解冻后启用；H 在均匀时最大
        if step >= int(opt_config.freeze_freq_first_steps) and float(opt_config.weight_entropy_weight) > 0.0:
            weight_entropy = -(weights * torch.log(weights + 1.0e-12)).sum()  # 熵 / Entropy
        else:
            weight_entropy = weights.new_tensor(0.0)  # 冻结期间不算 / Skip while frozen

        loss = (
            recog_loss
            + float(opt_config.smoothness_weight) * smoothness
            + float(opt_config.freq_separation_weight) * freq_sep
            + float(opt_config.sinkhorn_weight) * sinkhorn_part
            - float(opt_config.weight_entropy_weight) * weight_entropy  # 减熵 = 鼓励均匀 / Subtract entropy = encourage uniform
        )  # 总损失 / Total loss

        loss.backward()  # 反传 / Backprop
        optimiser.step()  # 更新 / Step

        # 记录 / Record
        trace.total_loss.append(float(loss.item()))  # / Total
        trace.recognisability_loss.append(float(recog_loss.item()))  # / Recog
        trace.enrichment.append(float(parts["enrichment"].item()))  # / Enrichment
        trace.contrast.append(float(parts["contrast"].item()))  # / Contrast
        trace.recall.append(float(parts["recall"].item()))  # / Recall
        trace.smoothness_loss.append(float(smoothness.item()))  # / Smoothness
        trace.freq_sep_loss.append(float(freq_sep.item()))  # / Separation
        trace.sinkhorn_loss.append(float(sinkhorn_part.item()))  # / Sinkhorn
        trace.frequencies_history.append([float(v) for v in frequencies_hz.detach().cpu().numpy().tolist()])  # / Freqs
        trace.weights_history.append([float(v) for v in weights.detach().cpu().numpy().tolist()])  # / Weights

        # 缓存最佳 / Cache best
        current = float(loss.item())  # / Current
        if current < best_loss - float(opt_config.plateau_min_delta):  # 改善 / Improved
            best_loss = current  # / Update
            best_step = step  # / Step
            best_H = H_clamped.detach().cpu().numpy().copy()  # / Cache
            best_freqs = [float(v) for v in frequencies_hz.detach().cpu().numpy().tolist()]  # / Freqs
            best_weights = [float(v) for v in weights.detach().cpu().numpy().tolist()]  # / Weights
            best_composite = composite_amp.detach().cpu().numpy().copy()  # / Composite
            best_metrics = {"enrichment": float(parts["enrichment"].item()), "contrast": float(parts["contrast"].item()), "recall": float(parts["recall"].item())}  # / Metrics
            stale = 0  # / Reset
        else:  # 平台 / Plateau
            stale += 1  # / Accumulate

        if (step + 1) % int(max(1, opt_config.snapshot_every)) == 0 or step == 0:  # 快照 / Snapshot
            with torch.no_grad():  # / No grad
                np.save(output_dir / f"snapshot_step_{step:04d}_H.npy", H_clamped.detach().cpu().numpy())  # / Save H
                np.save(output_dir / f"snapshot_step_{step:04d}_composite.npy", composite_amp.detach().cpu().numpy())  # / Save composite
            print(f"  step {step:4d}  loss {current:.4e}  enr {parts['enrichment'].item():.3f}  ctr {parts['contrast'].item():.3f}  rec {parts['recall'].item():.3f}")  # 进度 / Progress

        if stale >= int(opt_config.plateau_patience):  # 平台 / Plateau
            print(f"  early stop at step {step} (plateau {stale} >= {opt_config.plateau_patience})")  # / Print
            break  # / Break

    final_H = best_H if best_H is not None else H_clamped.detach().cpu().numpy()  # 最终 H / Final H
    final_theta = theta_design.detach().cpu().numpy()  # 全 0 θ / Zero θ
    final_freqs = best_freqs if best_freqs is not None else trace.frequencies_history[-1]  # / Freqs
    final_weights = best_weights if best_weights is not None else trace.weights_history[-1]  # / Weights

    # 保存连续 / Save continuous. θ stays zero but the CSVs are still written
    # for backward compat with downstream COMSOL pipeline (validation /
    # eigfreq calibration scripts both read theta_continuous_rad.csv). /
    # θ 全 0 仍写 CSV，下游 COMSOL 脚本依赖
    np.savetxt(output_dir / "H_continuous.csv", final_H, delimiter=",", fmt="%.6f")  # / Save
    np.savetxt(output_dir / "theta_continuous_rad.csv", final_theta, delimiter=",", fmt="%.6f")  # / Save θ rad
    np.savetxt(output_dir / "theta_continuous_deg.csv", np.rad2deg(final_theta) % 180.0, delimiter=",", fmt="%.3f")  # / Save θ deg

    # H 量化和修复 / Quantise + repair H
    levels = list(thickness_cfg.get("levels_mm") or [h_min, h_max])  # 等级 / Levels
    repaired = repair_neighbor_constraint(np.clip(final_H, h_min, h_max), levels, float(max_neighbour_diff_mm), fixed_cells=centre_cells)  # 修复 / Repair
    repaired = enforce_center_constraint(repaired, centre_cells, float(default_h))  # 固定 / Fix
    np.savetxt(output_dir / "H.csv", repaired, delimiter=",", fmt="%.6f")  # / Save
    np.savetxt(output_dir / "frequencies_hz.csv", np.asarray(final_freqs).reshape(-1, 1), delimiter=",", fmt="%.4f", header="frequency_hz", comments="")  # / Freqs
    np.savetxt(output_dir / "weights.csv", np.asarray(final_weights).reshape(-1, 1), delimiter=",", fmt="%.6f", header="weight", comments="")  # / Weights
    if best_composite is not None:  # 合成 / Composite
        np.save(output_dir / "composite_amplitude.npy", best_composite)  # / Save

    row_diff = float(np.max(np.abs(np.diff(repaired, axis=0))))  # / Row diff
    col_diff = float(np.max(np.abs(np.diff(repaired, axis=1))))  # / Col diff
    summary_weights = summarise_weight_distribution(torch.tensor(final_weights), torch.tensor(final_freqs))  # / Summary

    summary = {
        "version": "w10_anisotropy_v2_theta_removed",
        "best_loss": float(best_loss) if best_H is not None else float(trace.total_loss[-1]),
        "best_step": int(best_step),
        "executed_steps": int(len(trace.total_loss)),
        "num_frequencies": int(K),
        "frequencies_hz": [float(v) for v in final_freqs],
        "weights": [float(v) for v in final_weights],
        "weight_distribution": summary_weights,
        "best_surrogate_metrics": best_metrics,
        "damping_ratio": float(opt_config.damping_ratio),
        "proxy_grid_size": int(plate.N),
        "stiffness_ratio_used": float(plate.stiffness_ratio),
        "shear_ratio_used": float(plate.shear_ratio),
        "E_parallel_pa": float(plate.E_parallel_pa),
        "E_perp_pa": float(plate.E_perp_pa),
        "G_pp_pa": float(plate.G_pp_pa),
        "f_min_hz": float(opt_config.f_min_hz),
        "f_max_hz": float(opt_config.f_max_hz),
        "smoothness_weight": float(opt_config.smoothness_weight),
        "smoothness_max_diff_mm": float(max_neighbour_diff_mm),
        "h_min_mm": h_min,
        "h_max_mm": h_max,
        "final_max_row_neighbour_diff_mm": row_diff,
        "final_max_col_neighbour_diff_mm": col_diff,
        "quantised_levels_mm": levels,
        "theta_optimisation": "removed",
        "loss_weights": {"enrichment": float(opt_config.enrichment_weight), "contrast": float(opt_config.contrast_weight), "recall": float(opt_config.recall_weight), "sigma_rel": float(opt_config.sigma_rel), "sinkhorn_weight": float(opt_config.sinkhorn_weight)},
        "trace": {
            "total_loss": trace.total_loss,
            "recognisability_loss": trace.recognisability_loss,
            "enrichment": trace.enrichment,
            "contrast": trace.contrast,
            "recall": trace.recall,
            "smoothness_loss": trace.smoothness_loss,
            "freq_sep_loss": trace.freq_sep_loss,
            "sinkhorn_loss": trace.sinkhorn_loss,
            "frequencies_history": trace.frequencies_history,
            "weights_history": trace.weights_history,
        },
        "verdict_used": verdict,
    }  # 汇总 / Summary
    (output_dir / "w10_optimization_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 JSON / Write
    return summary  # 返回 / Return
