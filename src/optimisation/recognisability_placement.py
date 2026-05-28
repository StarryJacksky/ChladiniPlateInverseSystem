from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # JSON / JSON
import math  # 数学 / Math
from dataclasses import dataclass, field  # 数据类 / Dataclass
from pathlib import Path  # 路径 / Paths

import numpy as np  # NumPy / NumPy
import torch  # Torch / Torch

from src.candidate.constraints import center_cells_for_grid  # 中心单元 / Centre cells
from src.candidate.constraints import enforce_center_constraint  # 中心约束 / Centre constraint
from src.candidate.constraints import repair_neighbor_constraint  # 邻格修复 / Neighbour repair
from src.optimisation.gradient_optimizer import apply_center_clamp  # 中心夹持 / Centre clamp
from src.optimisation.gradient_optimizer import initial_theta  # theta 初值 / Theta init
from src.optimisation.gradient_optimizer import neighbour_smoothness_penalty  # 邻平滑 / Smoothness
from src.optimisation.gradient_optimizer import thickness_from_theta  # sigmoid 重参化 / Sigmoid
from src.physics.differentiable_plate import DifferentiablePlate  # 可微板 / Plate
from src.physics.multifreq_amp_valley import frequencies_from_logits  # 频率重参 / Freq reparam
from src.physics.multifreq_amp_valley import frequency_separation_penalty  # 间隔罚 / Separation
from src.physics.multifreq_amp_valley import initialise_freq_logits  # 频率初值 / Init
from src.physics.multifreq_amp_valley import initialise_weight_logits  # 权重初值 / Init
from src.physics.multifreq_amp_valley import summarise_weight_distribution  # 权重摘要 / Summary
from src.physics.multifreq_amp_valley import weights_from_logits  # 权重重参 / Reparam
from src.physics.recognisability_loss import RecognisabilityLossWeights  # 损失权重 / Loss weights
from src.physics.recognisability_loss import combined_recognisability_loss  # 综合损失 / Combined loss
from src.physics.recognisability_loss import compose_multifreq_amplitude_with_weights  # 多频合成 / Composition
from src.subspace.manifold_pca import DesignManifold  # 流形 / Manifold
from src.subspace.manifold_pca import decode_torch as manifold_decode_torch  # 流形解码 / Decode


@dataclass  # 数据类 / Dataclass
class RecognisabilityPlacementConfig:  # W8 可识别度联合优化配置 / W8 recognisability joint config
    proxy_grid_size: int = 25  # 代理网格 / Proxy grid
    num_frequencies: int = 6  # 频率数 K / K
    f_min_hz: float = 120.0  # 频率下限 / Freq lower
    f_max_hz: float = 1200.0  # 频率上限 / Freq upper
    damping_ratio: float = 0.02  # 阻尼 / Damping
    num_steps: int = 250  # Adam 步数 / Adam steps
    learning_rate_H: float = 0.05  # H 学习率 / H LR
    learning_rate_freq: float = 0.10  # 频率学习率 / Freq LR
    learning_rate_weight: float = 0.10  # 权重学习率 / Weight LR
    weight_decay: float = 0.0  # 权重衰减 / Weight decay
    plateau_patience: int = 50  # 平台容忍 / Plateau patience
    plateau_min_delta: float = 1.0e-4  # 最小改善 / Min delta
    snapshot_every: int = 25  # 快照间隔 / Snapshot interval
    dtype: torch.dtype = field(default=torch.float64)  # 精度 / Precision
    device: str = "cpu"  # 设备 / Device
    base_accel_m_s2: float = 1.0  # 基础加速度 / Accel
    smoothness_weight: float = 4.0  # 平滑罚 / Smoothness weight
    smoothness_max_diff_mm: float | None = None  # 邻差上限 / Neighbour diff cap
    manifold: DesignManifold | None = None  # 流形 / Manifold
    manifold_coeff_l2_weight: float = 0.0  # 流形 L2 / Manifold L2
    manifold_initial_coeff: np.ndarray | None = None  # 流形初值 / Manifold init
    freq_separation_min_hz: float = 30.0  # 频率间隔 / Freq gap
    freq_separation_weight: float = 0.5  # 间隔罚 / Separation
    freeze_freq_first_steps: int = 60  # 冻结 freq/weight 步数 / Freeze
    initial_frequencies_hz: list[float] | None = None  # 频率初值 / Init freqs
    enrichment_weight: float = 1.0  # 富集权重 / Enrichment weight
    contrast_weight: float = 1.0  # 对比权重 / Contrast weight
    recall_weight: float = 0.5  # recall 权重 / Recall weight
    sigma_rel: float = 0.05  # 高斯 sigma / Gaussian sigma
    recall_percentile_frac: float = 0.20  # recall 分位 / Recall percentile
    sbs_seed_path: str | None = None  # 对称破坏种子路径（Xie-Smidt 2024） / Symmetry-breaking seed path
    sinkhorn_weight: float = 0.0  # Sinkhorn loss 权重，0 关闭 / Sinkhorn loss weight, 0 disables
    sinkhorn_epsilon: float = 0.01  # Sinkhorn 熵正则 / Sinkhorn entropic reg
    sinkhorn_target_irreps: list[str] | None = None  # 在哪些 irrep 投影上算 Sinkhorn / Project target to these irreps before Sinkhorn
    calibration_npz_path: str | None = None  # W9 信赖域校正锚点 NPZ 路径 / W9 trust-region calibration anchors NPZ


@dataclass  # 数据类 / Dataclass
class RecognisabilityTrace:  # 优化轨迹 / Trace
    total_loss: list[float] = field(default_factory=list)  # 总损失 / Total
    recognisability_loss: list[float] = field(default_factory=list)  # 可识别度 / Recog
    enrichment: list[float] = field(default_factory=list)  # 富集 / Enrichment
    contrast: list[float] = field(default_factory=list)  # 对比 / Contrast
    recall: list[float] = field(default_factory=list)  # recall / Recall
    smoothness_loss: list[float] = field(default_factory=list)  # 平滑 / Smoothness
    freq_sep_loss: list[float] = field(default_factory=list)  # 间隔 / Separation
    frequencies_history: list[list[float]] = field(default_factory=list)  # 频率 / Freqs
    weights_history: list[list[float]] = field(default_factory=list)  # 权重 / Weights


def _build_thickness(theta: torch.Tensor | None, coeffs: torch.Tensor | None, manifold: DesignManifold | None, mean_t: torch.Tensor | None, comp_t: torch.Tensor | None, grid_size: int, h_min: float, h_max: float, default_h: float, centre_cells: list[tuple[int, int]], sbs_seed: torch.Tensor | None = None) -> torch.Tensor:  # 厚度构造（可加 SBS 种子） / Build thickness (optional SBS seed)
    if manifold is not None and coeffs is not None and mean_t is not None and comp_t is not None:  # 流形 / Manifold
        H_raw = manifold_decode_torch(coeffs, mean_t, comp_t, int(grid_size))  # 解码 / Decode
    elif theta is not None:  # sigmoid / Sigmoid
        H_raw = thickness_from_theta(theta, float(h_min), float(h_max))  # 重参化 / Reparam
    else:  # 错误 / Error
        raise RuntimeError("Either theta or coeffs must be provided. / theta 与 coeffs 至少要有一个。")  # 抛错 / Raise
    if sbs_seed is not None:  # 注入对称破坏种子 / Inject SBS
        H_raw = H_raw + sbs_seed  # 加固定非 D4 扰动 / Add fixed non-D4 perturbation
    H_clipped = torch.clamp(H_raw, min=float(h_min), max=float(h_max))  # clamp / Clamp
    return apply_center_clamp(H_clipped, float(default_h), centre_cells)  # 中心夹持 / Clamp


def _build_target_mask_proxy(target_binary_full: np.ndarray, proxy_grid_size: int, device: torch.device, dtype: torch.dtype) -> torch.Tensor:  # 把目标降采样到代理网格 / Downsample target to proxy grid
    from src.scoring.geometry_helpers import resize_binary_nearest  # 延迟导入 / Lazy import
    resized = resize_binary_nearest(target_binary_full.astype(bool), int(proxy_grid_size))  # 调整 / Resize
    return torch.as_tensor(resized.astype(np.float64), dtype=dtype, device=device)  # 张量 / Tensor


def run_recognisability_placement(config: dict, target_binary: np.ndarray, opt_config: RecognisabilityPlacementConfig, output_dir: Path, verdict: dict | None = None, initial_H_mm: np.ndarray | None = None) -> dict:  # W8 主入口 / W8 main
    output_dir = Path(output_dir)  # 转路径 / Path
    output_dir.mkdir(parents=True, exist_ok=True)  # 建目录 / Mkdir
    device = torch.device(opt_config.device)  # 设备 / Device
    dtype = opt_config.dtype  # 精度 / Precision
    thickness_cfg = config["thickness"]  # 厚度配置 / Thickness
    h_min = float(thickness_cfg["min_mm"])  # 下限 / Min
    h_max = float(thickness_cfg["max_mm"])  # 上限 / Max
    default_h = float(thickness_cfg.get("default_mm", h_max))  # 默认 / Default
    grid_size = int(config["project"]["grid_size"])  # 网格 / Grid
    centre_cells = center_cells_for_grid(grid_size)  # 中心 / Centre
    max_neighbour_diff_mm = float(opt_config.smoothness_max_diff_mm if opt_config.smoothness_max_diff_mm is not None else thickness_cfg.get("max_neighbor_difference_mm", 1.0))  # 邻差 / Diff cap
    K = int(opt_config.num_frequencies)  # K / K
    plate = DifferentiablePlate(config, proxy_grid_size=int(opt_config.proxy_grid_size), base_accel=float(opt_config.base_accel_m_s2), default_damping=float(opt_config.damping_ratio), reference_frequency_hz=0.5 * (float(opt_config.f_min_hz) + float(opt_config.f_max_hz)), dtype=dtype, device=device)  # 板 / Plate
    target_proxy = _build_target_mask_proxy(target_binary, plate.N, device=device, dtype=dtype)  # 代理目标 / Proxy target
    if opt_config.initial_frequencies_hz is not None and len(opt_config.initial_frequencies_hz) == K:  # 显式频率初值 / Explicit init
        clamp = lambda x: float(min(max(x, float(opt_config.f_min_hz) + 1.0e-3), float(opt_config.f_max_hz) - 1.0e-3))  # clamp / Clamp
        fractions = torch.tensor([(clamp(x) - float(opt_config.f_min_hz)) / max(float(opt_config.f_max_hz) - float(opt_config.f_min_hz), 1.0e-9) for x in opt_config.initial_frequencies_hz], dtype=dtype, device=device)  # 比例 / Fractions
        freq_logits_init = torch.log(fractions / (1.0 - fractions))  # 反 sigmoid / Inverse sigmoid
    else:  # 均匀 / Uniform
        freq_logits_init = initialise_freq_logits(K, float(opt_config.f_min_hz), float(opt_config.f_max_hz), dtype=dtype, device=device)  # 均匀 / Even
    weight_logits_init = initialise_weight_logits(K, dtype=dtype, device=device)  # 权重 / Weight
    freq_logits = freq_logits_init.detach().clone().requires_grad_(True)  # 频率 / Freq
    weight_logits = weight_logits_init.detach().clone().requires_grad_(True)  # 权重 / Weight
    manifold = opt_config.manifold  # 流形 / Manifold
    use_manifold = manifold is not None  # 启用 / Enabled
    mean_t = torch.tensor(manifold.mean, dtype=dtype, device=device) if use_manifold else None  # 均值 / Mean
    comp_t = torch.tensor(manifold.components, dtype=dtype, device=device) if use_manifold else None  # 主成分 / Components
    theta: torch.Tensor | None = None  # 占位 / Placeholder
    coeffs: torch.Tensor | None = None  # 占位 / Placeholder
    if use_manifold:  # 流形 / Manifold
        if opt_config.manifold_initial_coeff is not None:  # 提供 / Provided
            coeff_init = torch.tensor(np.asarray(opt_config.manifold_initial_coeff, dtype=np.float64).reshape(-1), dtype=dtype, device=device)  # 张量 / Tensor
        elif initial_H_mm is not None:  # 厚度反推 / From H
            flat = np.asarray(initial_H_mm, dtype=np.float64).reshape(-1) - manifold.mean  # 去均值 / Centre
            coeff_init = torch.tensor(manifold.components @ flat, dtype=dtype, device=device)  # 投影 / Project
        else:  # 零 / Zero
            coeff_init = torch.zeros(int(manifold.components.shape[0]), dtype=dtype, device=device)  # 零 / Zero
        coeffs = coeff_init.detach().clone().requires_grad_(True)  # 系数 / Coeffs
        H_params = [coeffs]  # H 参数 / H params
    else:  # 225 维 / 225-D
        if initial_H_mm is not None:  # 厚度初值 / H init
            h0 = np.asarray(initial_H_mm, dtype=np.float64)  # numpy / NumPy
            normalised = np.clip((h0 - h_min) / max(h_max - h_min, 1.0e-6), 1.0e-3, 1.0 - 1.0e-3)  # 归一 / Normalise
            theta_init = torch.tensor(np.log(normalised / (1.0 - normalised)), dtype=dtype, device=device)  # 反 sigmoid / Inverse
        else:  # 常数 / Constant
            theta_init = initial_theta(default_h, h_min, h_max, grid_size, dtype).to(device)  # 默认 / Default
        theta = theta_init.detach().clone().requires_grad_(True)  # theta / Theta
        H_params = [theta]  # H 参数 / H params
    sbs_seed_tensor: torch.Tensor | None = None  # SBS 种子张量 / SBS seed tensor
    if opt_config.sbs_seed_path:  # 启用 SBS / Enable SBS
        from src.symmetry.sbs_seed import load_sbs_seed  # 延迟导入 / Lazy
        seed_arr = load_sbs_seed(opt_config.sbs_seed_path, grid_size=grid_size)  # 加载 / Load
        sbs_seed_tensor = torch.as_tensor(seed_arr, dtype=dtype, device=device)  # 转 tensor / To tensor
        print(f"  SBS seed loaded from {opt_config.sbs_seed_path}: max={float(np.abs(seed_arr).max()):.4f} mm, rms={float(np.sqrt((seed_arr**2).mean())):.4f} mm")  # 打印 / Print
    calib_H_anchors: torch.Tensor | None = None  # 校正锚点 H / Calib H
    calib_residual_anchors: torch.Tensor | None = None  # 校正锚点残差 / Calib residual
    calib_sigma_mm: float = 0.5  # 默认 σ / Default σ
    if opt_config.calibration_npz_path:  # 启用 W9 校正 / Enable W9 calibration
        calib_data = np.load(opt_config.calibration_npz_path)  # 加载 / Load
        if "H_anchors" in calib_data.files and "residual_anchors" in calib_data.files:  # 有锚点 / Has anchors
            calib_H_anchors = torch.as_tensor(calib_data["H_anchors"], dtype=dtype, device=device)  # H 锚 / H anchors
            calib_residual_anchors = torch.as_tensor(calib_data["residual_anchors"], dtype=dtype, device=device)  # 残差锚 / Residual anchors
            if "sigma_mm" in calib_data.files:  # σ / Sigma
                calib_sigma_mm = float(calib_data["sigma_mm"])  # σ / Sigma
            print(f"  W9 calibration loaded: {calib_H_anchors.shape[0]} anchors, sigma={calib_sigma_mm:.3f} mm")  # 打印 / Print
    optimiser = torch.optim.Adam([{"params": H_params, "lr": float(opt_config.learning_rate_H)}, {"params": [freq_logits], "lr": float(opt_config.learning_rate_freq)}, {"params": [weight_logits], "lr": float(opt_config.learning_rate_weight)}], weight_decay=float(opt_config.weight_decay))  # Adam / Adam
    loss_weights = RecognisabilityLossWeights(enrichment=float(opt_config.enrichment_weight), contrast=float(opt_config.contrast_weight), recall=float(opt_config.recall_weight), sigma_rel=float(opt_config.sigma_rel), percentile_frac=float(opt_config.recall_percentile_frac))  # 损失权重 / Loss weights
    trace = RecognisabilityTrace()  # 轨迹 / Trace
    best_loss = math.inf  # 最佳 / Best
    best_step = 0  # 步号 / Step
    best_H_continuous: np.ndarray | None = None  # 缓存 H / Cache H
    best_freqs: list[float] | None = None  # 缓存频率 / Cache freqs
    best_weights: list[float] | None = None  # 缓存权重 / Cache weights
    best_composite: np.ndarray | None = None  # 缓存合成图 / Cache composite
    best_metrics: dict[str, float] | None = None  # 缓存指标 / Cache metrics
    stale = 0  # 平台计数 / Plateau counter
    for step in range(int(opt_config.num_steps)):  # 主循环 / Main loop
        optimiser.zero_grad()  # 清零 / Zero
        H_clamped = _build_thickness(theta, coeffs, manifold, mean_t, comp_t, grid_size, h_min, h_max, default_h, centre_cells, sbs_seed=sbs_seed_tensor)  # 厚度（带 SBS） / Thickness (with SBS)
        H_proxy = plate.upsample(H_clamped)  # 升采样 / Upsample
        K_full, M_diag = plate.assemble_K_M(H_proxy)  # 装配 / Assemble
        free = plate.free_indices  # 自由度 / Free
        K_free = K_full.index_select(0, free).index_select(1, free)  # 自由 K / Free K
        M_free = torch.clamp(M_diag.index_select(0, free), min=1.0e-18)  # 自由 M / Free M
        if step < int(opt_config.freeze_freq_first_steps):  # 冻结 / Freeze
            freq_logits_use = freq_logits.detach()  # 冻结 freq / Detach freq
            weight_logits_use = weight_logits.detach()  # 冻结 weight / Detach weight
        else:  # 解冻 / Unfreeze
            freq_logits_use = freq_logits  # 启用 / Enable
            weight_logits_use = weight_logits  # 启用 / Enable
        frequencies_hz = frequencies_from_logits(freq_logits_use, float(opt_config.f_min_hz), float(opt_config.f_max_hz))  # 频率 / Freqs
        weights = weights_from_logits(weight_logits_use)  # 权重 / Weights
        per_freq_responses = []  # 响应列表 / Responses
        for k in range(K):  # 遍历 / Iterate
            omega_k = 2.0 * math.pi * frequencies_hz[k]  # 角频率 / ω
            u_free = plate.direct_forced_response(K_free, M_free, omega_k, float(opt_config.damping_ratio))  # 响应 / Response
            u_grid = plate.expand_to_grid(u_free)  # 网格化 / Scatter
            per_freq_responses.append(u_grid)  # 加入 / Append
        composite_amp = compose_multifreq_amplitude_with_weights(per_freq_responses, weights)  # 合成 / Compose
        if calib_H_anchors is not None and calib_residual_anchors is not None:  # W9 校正 / W9 calibration
            distances = ((H_clamped.unsqueeze(0) - calib_H_anchors) ** 2).flatten(1).sum(dim=1).sqrt()  # 欧氏距离 / Euclidean distance
            anchor_weights = torch.exp(-(distances / float(calib_sigma_mm)) ** 2)  # 高斯权重 / Gaussian weights
            calibration = (anchor_weights.unsqueeze(-1).unsqueeze(-1) * calib_residual_anchors).sum(dim=0) / (anchor_weights.sum() + 1.0e-9)  # 加权平均残差 / Weighted residual
            if calibration.shape != composite_amp.shape:  # 形状不一致 / Shape mismatch
                calib_resized = torch.nn.functional.interpolate(calibration.unsqueeze(0).unsqueeze(0), size=composite_amp.shape, mode="bilinear", align_corners=False).squeeze(0).squeeze(0)  # 双线性 / Bilinear
                composite_amp = composite_amp + calib_resized  # 校正 / Calibrate
            else:  # 同样形状 / Same shape
                composite_amp = composite_amp + calibration  # 校正 / Calibrate
            composite_amp = torch.clamp(composite_amp, min=0.0)  # 非负 / Non-negative
        composite_complex = composite_amp.to(dtype=torch.complex128 if composite_amp.dtype == torch.float64 else torch.complex64) + 0.0j  # 包装 / Wrap
        recog_loss, parts = combined_recognisability_loss(composite_complex, target_proxy, weights=loss_weights)  # 综合损失 / Combined
        sinkhorn_part = composite_amp.new_tensor(0.0)  # Sinkhorn 默认 0 / Sinkhorn default 0
        if float(opt_config.sinkhorn_weight) > 0.0:  # 启用 Sinkhorn / Enable Sinkhorn
            from src.physics.sinkhorn_loss import sinkhorn_powder_target_loss  # 延迟导入 / Lazy
            from src.physics.sinkhorn_loss import sinkhorn_to_irrep_projection  # 延迟导入 / Lazy
            if opt_config.sinkhorn_target_irreps:  # irrep 投影 / irrep projection
                sinkhorn_part, _ = sinkhorn_to_irrep_projection(composite_amp, target_proxy, irreps=tuple(opt_config.sinkhorn_target_irreps), sigma_rel=float(opt_config.sigma_rel), epsilon=float(opt_config.sinkhorn_epsilon))  # 投影后 Sinkhorn / Project then Sinkhorn
            else:  # 原始目标 / Raw target
                sinkhorn_part, _ = sinkhorn_powder_target_loss(composite_amp, target_proxy, sigma_rel=float(opt_config.sigma_rel), epsilon=float(opt_config.sinkhorn_epsilon))  # 直接 Sinkhorn / Direct Sinkhorn
            parts["sinkhorn_loss"] = sinkhorn_part  # 记录 / Record
        smoothness = neighbour_smoothness_penalty(H_clamped, max_neighbour_diff_mm)  # 平滑 / Smoothness
        freq_sep = frequency_separation_penalty(frequencies_hz, float(opt_config.freq_separation_min_hz)) if step >= int(opt_config.freeze_freq_first_steps) else frequencies_hz.new_tensor(0.0)  # 间隔罚 / Separation
        loss = recog_loss + float(opt_config.smoothness_weight) * smoothness + float(opt_config.freq_separation_weight) * freq_sep + float(opt_config.sinkhorn_weight) * sinkhorn_part  # 总损失（含 Sinkhorn） / Total (with Sinkhorn)
        if use_manifold and float(opt_config.manifold_coeff_l2_weight) > 0.0 and coeffs is not None:  # L2 / L2
            loss = loss + float(opt_config.manifold_coeff_l2_weight) * coeffs.pow(2).mean()  # 加入 / Add
        loss.backward()  # 反传 / Backprop
        optimiser.step()  # 更新 / Step
        trace.total_loss.append(float(loss.item()))  # 总 / Total
        trace.recognisability_loss.append(float(recog_loss.item()))  # 可识别 / Recog
        trace.enrichment.append(float(parts["enrichment"].item()))  # 富集 / Enrichment
        trace.contrast.append(float(parts["contrast"].item()))  # 对比 / Contrast
        trace.recall.append(float(parts["recall"].item()))  # recall / Recall
        trace.smoothness_loss.append(float(smoothness.item()))  # 平滑 / Smoothness
        trace.freq_sep_loss.append(float(freq_sep.item()))  # 间隔 / Separation
        if not hasattr(trace, "sinkhorn_loss"):  # 兼容旧 trace / Backward compat
            trace.sinkhorn_loss = []  # 初始化 / Init
        trace.sinkhorn_loss.append(float(sinkhorn_part.item()))  # 记录 Sinkhorn / Record Sinkhorn
        trace.frequencies_history.append([float(v) for v in frequencies_hz.detach().cpu().numpy().tolist()])  # 频率 / Freqs
        trace.weights_history.append([float(v) for v in weights.detach().cpu().numpy().tolist()])  # 权重 / Weights
        current = float(loss.item())  # 当前 / Current
        if current < best_loss - float(opt_config.plateau_min_delta):  # 改善 / Improvement
            best_loss = current  # 更新 / Update
            best_step = step  # 步 / Step
            best_H_continuous = H_clamped.detach().cpu().numpy().copy()  # 缓存 / Cache
            best_freqs = [float(v) for v in frequencies_hz.detach().cpu().numpy().tolist()]  # 频率 / Freqs
            best_weights = [float(v) for v in weights.detach().cpu().numpy().tolist()]  # 权重 / Weights
            best_composite = composite_amp.detach().cpu().numpy().copy()  # 合成 / Composite
            best_metrics = {"enrichment": float(parts["enrichment"].item()), "contrast": float(parts["contrast"].item()), "recall": float(parts["recall"].item())}  # 指标 / Metrics
            stale = 0  # 重置 / Reset
        else:  # 平台 / Plateau
            stale += 1  # 累计 / Accumulate
        if (step + 1) % int(max(1, opt_config.snapshot_every)) == 0 or step == 0:  # 快照 / Snapshot
            with torch.no_grad():  # 取数据 / No grad
                np.save(output_dir / f"snapshot_step_{step:04d}_H.npy", H_clamped.detach().cpu().numpy())  # 保存 H / Save
                np.save(output_dir / f"snapshot_step_{step:04d}_composite.npy", composite_amp.detach().cpu().numpy())  # 保存合成 / Save
        if stale >= int(opt_config.plateau_patience):  # 平台 / Plateau
            break  # 跳出 / Break
    final_H = best_H_continuous if best_H_continuous is not None else H_clamped.detach().cpu().numpy()  # 最终 H / Final H
    final_freqs = best_freqs if best_freqs is not None else trace.frequencies_history[-1]  # 频率 / Freqs
    final_weights = best_weights if best_weights is not None else trace.weights_history[-1]  # 权重 / Weights
    np.savetxt(output_dir / "H_continuous.csv", final_H, delimiter=",", fmt="%.6f")  # 保存 / Save
    levels = list(thickness_cfg.get("levels_mm") or [h_min, h_max])  # 等级 / Levels
    repaired = repair_neighbor_constraint(np.clip(final_H, h_min, h_max), levels, float(max_neighbour_diff_mm), fixed_cells=centre_cells)  # 修复 / Repair
    repaired = enforce_center_constraint(repaired, centre_cells, float(default_h))  # 固定 / Fix
    np.savetxt(output_dir / "H.csv", repaired, delimiter=",", fmt="%.6f")  # 保存 / Save
    np.savetxt(output_dir / "frequencies_hz.csv", np.asarray(final_freqs).reshape(-1, 1), delimiter=",", fmt="%.4f", header="frequency_hz", comments="")  # 频率 / Freqs
    np.savetxt(output_dir / "weights.csv", np.asarray(final_weights).reshape(-1, 1), delimiter=",", fmt="%.6f", header="weight", comments="")  # 权重 / Weights
    if best_composite is not None:  # 合成 / Composite
        np.save(output_dir / "composite_amplitude.npy", best_composite)  # 保存 / Save
    row_diff = float(np.max(np.abs(np.diff(repaired, axis=0))))  # 行差 / Row diff
    col_diff = float(np.max(np.abs(np.diff(repaired, axis=1))))  # 列差 / Col diff
    summary_weights = summarise_weight_distribution(torch.tensor(final_weights), torch.tensor(final_freqs))  # 权重摘要 / Summary
    summary = {"best_loss": float(best_loss) if best_H_continuous is not None else float(trace.total_loss[-1]), "best_step": int(best_step), "executed_steps": int(len(trace.total_loss)), "num_frequencies": int(K), "frequencies_hz": [float(v) for v in final_freqs], "weights": [float(v) for v in final_weights], "weight_distribution": summary_weights, "best_surrogate_metrics": best_metrics, "damping_ratio": float(opt_config.damping_ratio), "proxy_grid_size": int(plate.N), "f_min_hz": float(opt_config.f_min_hz), "f_max_hz": float(opt_config.f_max_hz), "smoothness_weight": float(opt_config.smoothness_weight), "smoothness_max_diff_mm": float(max_neighbour_diff_mm), "h_min_mm": h_min, "h_max_mm": h_max, "final_max_row_neighbour_diff_mm": row_diff, "final_max_col_neighbour_diff_mm": col_diff, "quantised_levels_mm": levels, "search_mode": "manifold_pca" if use_manifold else "direct_225d", "manifold": {"num_components": int(manifold.components.shape[0]), "sample_count": int(manifold.sample_count)} if use_manifold else None, "loss_weights": {"enrichment": float(opt_config.enrichment_weight), "contrast": float(opt_config.contrast_weight), "recall": float(opt_config.recall_weight), "sigma_rel": float(opt_config.sigma_rel)}, "trace": {"total_loss": trace.total_loss, "recognisability_loss": trace.recognisability_loss, "enrichment": trace.enrichment, "contrast": trace.contrast, "recall": trace.recall, "smoothness_loss": trace.smoothness_loss, "freq_sep_loss": trace.freq_sep_loss, "frequencies_history": trace.frequencies_history, "weights_history": trace.weights_history}, "verdict_used": verdict}  # 汇总 / Summary
    (output_dir / "w8_optimization_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 JSON / Write
    return summary  # 返回 / Return
