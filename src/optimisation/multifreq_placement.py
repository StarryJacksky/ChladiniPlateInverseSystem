from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
import math  # 导入数学函数 / Import math helpers
from dataclasses import dataclass, field  # 导入数据类装饰器 / Import dataclass decorator
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值库 / Import numerical library
import torch  # 导入张量库 / Import tensor library

from src.candidate.constraints import center_cells_for_grid  # 中心单元 / Centre cells
from src.candidate.constraints import enforce_center_constraint  # 中心约束 / Centre constraint
from src.candidate.constraints import repair_neighbor_constraint  # 邻格修复 / Neighbour repair
from src.optimisation.gradient_optimizer import apply_center_clamp  # 中心夹持 / Centre clamp
from src.optimisation.gradient_optimizer import initial_theta  # theta 初值 / Theta init
from src.optimisation.gradient_optimizer import neighbour_smoothness_penalty  # 邻平滑罚 / Smoothness penalty
from src.optimisation.gradient_optimizer import thickness_from_theta  # sigmoid 重参化 / Sigmoid reparameterisation
from src.physics.differentiable_plate import DifferentiablePlate  # 可微板 / Differentiable plate
from src.physics.multifreq_amp_valley import frequencies_from_logits  # 频率重参化 / Frequency reparameterisation
from src.physics.multifreq_amp_valley import frequency_separation_penalty  # 频率间隔罚 / Frequency separation penalty
from src.physics.multifreq_amp_valley import initialise_freq_logits  # 频率初值 / Frequency init
from src.physics.multifreq_amp_valley import initialise_weight_logits  # 权重初值 / Weight init
from src.physics.multifreq_amp_valley import multifreq_amplitude_valley_loss  # 多频损失 / Multi-frequency loss
from src.physics.multifreq_amp_valley import summarise_weight_distribution  # 权重摘要 / Weight summary
from src.physics.multifreq_amp_valley import weight_sparsity_penalty  # 稀疏罚 / Sparsity penalty
from src.physics.multifreq_amp_valley import weights_from_logits  # 权重重参化 / Weight reparameterisation
from src.physics.plate_loss_adapter import build_target_bundle  # 目标包 / Target bundle
from src.physics.plate_loss_adapter import bundle_to_torch  # 张量化 / Tensorise
from src.subspace.manifold_pca import DesignManifold  # 流形数据 / Manifold data
from src.subspace.manifold_pca import decode_torch as manifold_decode_torch  # 流形解码 / Manifold decode


@dataclass  # 数据类装饰器 / Dataclass decorator
class MultiFrequencyPlacementConfig:  # W7 多频联合优化配置 / W7 multi-frequency joint config
    proxy_grid_size: int = 25  # 代理网格 / Proxy grid
    num_frequencies: int = 6  # 联合频率数 K / Number of joint frequencies
    f_min_hz: float = 150.0  # 频率下限 / Frequency lower bound
    f_max_hz: float = 1000.0  # 频率上限 / Frequency upper bound
    damping_ratio: float = 0.02  # Rayleigh 阻尼比 / Damping ratio
    epsilon: float = 0.060  # 谷线 epsilon / Valley epsilon
    num_steps: int = 250  # Adam 步数 / Adam steps
    learning_rate_H: float = 0.05  # H/coeffs 学习率 / H/coeffs LR
    learning_rate_freq: float = 0.10  # 频率 logits 学习率 / Frequency logits LR
    learning_rate_weight: float = 0.10  # 权重 logits 学习率 / Weight logits LR
    weight_decay: float = 0.0  # 权重衰减 / Weight decay
    plateau_patience: int = 40  # 平台容忍 / Plateau patience
    plateau_min_delta: float = 1.0e-4  # 最小改善 / Min delta
    snapshot_every: int = 25  # 快照间隔 / Snapshot interval
    dtype: torch.dtype = field(default=torch.float64)  # 精度 / Precision
    device: str = "cpu"  # 设备 / Device
    base_accel_m_s2: float = 1.0  # 基础加速度 / Base accel
    smoothness_weight: float = 4.0  # 邻平滑权重 / Smoothness weight
    smoothness_max_diff_mm: float | None = None  # 邻差上限 / Max neighbour diff
    manifold: DesignManifold | None = None  # 可选流形 / Optional manifold
    manifold_coeff_l2_weight: float = 0.0  # 流形 L2 / Manifold L2
    manifold_initial_coeff: np.ndarray | None = None  # 流形初值 / Manifold init
    freq_separation_min_hz: float = 30.0  # 频率最小间隔 / Frequency min gap
    freq_separation_weight: float = 0.5  # 间隔罚权重 / Separation penalty weight
    sparsity_target_active: int = 0  # 0 = 不启用稀疏 / 0 disables sparsity guide
    sparsity_weight: float = 0.0  # 稀疏罚权重 / Sparsity weight
    freeze_freq_first_steps: int = 50  # 前 N 步冻结 freq/weight / Freeze freq/weight for first N steps
    initial_frequencies_hz: list[float] | None = None  # 显式频率初值 / Explicit frequency init


@dataclass  # 数据类装饰器 / Dataclass decorator
class MultiFrequencyTrace:  # 优化轨迹 / Optimisation trace
    total_loss: list[float] = field(default_factory=list)  # 总损失 / Total
    amp_loss: list[float] = field(default_factory=list)  # 振幅项 / Amplitude
    target_part: list[float] = field(default_factory=list)  # target 子项 / target part
    extra_part: list[float] = field(default_factory=list)  # extra 子项 / extra part
    contrast_part: list[float] = field(default_factory=list)  # contrast 子项 / contrast part
    compact_part: list[float] = field(default_factory=list)  # compact 子项 / compact part
    smoothness_loss: list[float] = field(default_factory=list)  # 平滑项 / Smoothness
    freq_sep_loss: list[float] = field(default_factory=list)  # 间隔项 / Separation
    sparsity_loss: list[float] = field(default_factory=list)  # 稀疏项 / Sparsity
    frequencies_history: list[list[float]] = field(default_factory=list)  # 频率历史 / Frequency history
    weights_history: list[list[float]] = field(default_factory=list)  # 权重历史 / Weight history


def _build_thickness(theta: torch.Tensor | None, coeffs: torch.Tensor | None, manifold: DesignManifold | None, mean_t: torch.Tensor | None, comp_t: torch.Tensor | None, grid_size: int, h_min: float, h_max: float, default_h: float, centre_cells: list[tuple[int, int]]) -> torch.Tensor:  # 构造受约束厚度 / Build constrained thickness
    if manifold is not None and coeffs is not None and mean_t is not None and comp_t is not None:  # 流形模式 / Manifold mode
        H_raw = manifold_decode_torch(coeffs, mean_t, comp_t, int(grid_size))  # 解码 / Decode
        H_clipped = torch.clamp(H_raw, min=float(h_min), max=float(h_max))  # clamp / Clamp
    elif theta is not None:  # sigmoid 模式 / Sigmoid mode
        H_clipped = thickness_from_theta(theta, float(h_min), float(h_max))  # 重参化 / Reparameterise
    else:  # 不应出现 / Should not happen
        raise RuntimeError("Either theta or coeffs must be provided. / theta 与 coeffs 必须至少有一个。")  # 抛出 / Raise
    return apply_center_clamp(H_clipped, float(default_h), centre_cells)  # 中心夹持 / Centre clamp


def run_multifreq_placement(config: dict, target_binary: np.ndarray, opt_config: MultiFrequencyPlacementConfig, output_dir: Path, verdict: dict | None = None, initial_H_mm: np.ndarray | None = None) -> dict:  # 运行 W7 多频联合优化 / Run W7 multi-frequency joint optimisation
    output_dir = Path(output_dir)  # 转路径 / Convert
    output_dir.mkdir(parents=True, exist_ok=True)  # 建目录 / Create dir
    device = torch.device(opt_config.device)  # 设备 / Device
    dtype = opt_config.dtype  # 精度 / Precision
    thickness_cfg = config["thickness"]  # 厚度配置 / Thickness cfg
    h_min = float(thickness_cfg["min_mm"])  # 厚度下限 / H min
    h_max = float(thickness_cfg["max_mm"])  # 厚度上限 / H max
    default_h = float(thickness_cfg.get("default_mm", h_max))  # 默认厚度 / Default
    grid_size = int(config["project"]["grid_size"])  # 设计网格 / Design grid
    centre_cells = center_cells_for_grid(grid_size)  # 中心单元 / Centre cells
    max_neighbour_diff_mm = float(opt_config.smoothness_max_diff_mm if opt_config.smoothness_max_diff_mm is not None else thickness_cfg.get("max_neighbor_difference_mm", 1.0))  # 邻差上限 / Neighbour diff cap
    K = int(opt_config.num_frequencies)  # 频率数 / Number of frequencies
    plate = DifferentiablePlate(config, proxy_grid_size=int(opt_config.proxy_grid_size), base_accel=float(opt_config.base_accel_m_s2), default_damping=float(opt_config.damping_ratio), reference_frequency_hz=0.5 * (float(opt_config.f_min_hz) + float(opt_config.f_max_hz)), dtype=dtype, device=device)  # 板模型 / Plate
    bundle = build_target_bundle(target_binary, plate.N, float(config["project"]["center_clamp_radius_mm"]), float(config["project"]["plate_length_mm"]), verdict=verdict)  # 目标包 / Target bundle
    bundle_tensors = bundle_to_torch(bundle, device, dtype)  # 张量化 / Tensorise
    if opt_config.initial_frequencies_hz is not None and len(opt_config.initial_frequencies_hz) == K:  # 提供显式初值 / Explicit init provided
        clamp = lambda x: float(min(max(x, float(opt_config.f_min_hz) + 1.0e-3), float(opt_config.f_max_hz) - 1.0e-3))  # 内夹 / Clamp inside
        fractions = torch.tensor([(clamp(x) - float(opt_config.f_min_hz)) / max(float(opt_config.f_max_hz) - float(opt_config.f_min_hz), 1.0e-9) for x in opt_config.initial_frequencies_hz], dtype=dtype, device=device)  # 反映射 / Inverse map
        freq_logits_init = torch.log(fractions / (1.0 - fractions))  # 反 sigmoid / Inverse sigmoid
    else:  # 均匀初值 / Uniform init
        freq_logits_init = initialise_freq_logits(K, float(opt_config.f_min_hz), float(opt_config.f_max_hz), dtype=dtype, device=device)  # 频率 logits / Frequency logits
    weight_logits_init = initialise_weight_logits(K, dtype=dtype, device=device)  # 权重 logits / Weight logits
    freq_logits = freq_logits_init.detach().clone().requires_grad_(True)  # 注册频率 / Register freq
    weight_logits = weight_logits_init.detach().clone().requires_grad_(True)  # 注册权重 / Register weight
    manifold = opt_config.manifold  # 流形 / Manifold
    use_manifold = manifold is not None  # 是否启用 / Manifold on
    mean_t = torch.tensor(manifold.mean, dtype=dtype, device=device) if use_manifold else None  # 均值 / Mean
    comp_t = torch.tensor(manifold.components, dtype=dtype, device=device) if use_manifold else None  # 主成分 / Components
    theta: torch.Tensor | None = None  # 占位 / Placeholder
    coeffs: torch.Tensor | None = None  # 占位 / Placeholder
    if use_manifold:  # 流形模式 / Manifold
        if opt_config.manifold_initial_coeff is not None:  # 系数初值 / Coeff init
            coeff_init = torch.tensor(np.asarray(opt_config.manifold_initial_coeff, dtype=np.float64).reshape(-1), dtype=dtype, device=device)  # 张量化 / Tensorise
        elif initial_H_mm is not None:  # 厚度初值反推 / From thickness
            flat = np.asarray(initial_H_mm, dtype=np.float64).reshape(-1) - manifold.mean  # 去均值 / Centre
            coeff_init = torch.tensor(manifold.components @ flat, dtype=dtype, device=device)  # 投影 / Project
        else:  # 零系数 / Zero coeffs
            coeff_init = torch.zeros(int(manifold.components.shape[0]), dtype=dtype, device=device)  # 全零 / Zeros
        coeffs = coeff_init.detach().clone().requires_grad_(True)  # 注册 / Register
        H_params = [coeffs]  # H 参数组 / H param group
    else:  # 225 维模式 / 225-D
        if initial_H_mm is not None:  # 厚度初值 / Thickness init
            h0 = np.asarray(initial_H_mm, dtype=np.float64)  # 转 numpy / Convert
            normalised = np.clip((h0 - h_min) / max(h_max - h_min, 1.0e-6), 1.0e-3, 1.0 - 1.0e-3)  # 归一化 / Normalise
            theta_init = torch.tensor(np.log(normalised / (1.0 - normalised)), dtype=dtype, device=device)  # 反 sigmoid / Inverse sigmoid
        else:  # 常数 / Constant
            theta_init = initial_theta(default_h, h_min, h_max, grid_size, dtype).to(device)  # 默认 / Default
        theta = theta_init.detach().clone().requires_grad_(True)  # 注册 / Register
        H_params = [theta]  # H 参数组 / H param group
    optimiser = torch.optim.Adam([{"params": H_params, "lr": float(opt_config.learning_rate_H)}, {"params": [freq_logits], "lr": float(opt_config.learning_rate_freq)}, {"params": [weight_logits], "lr": float(opt_config.learning_rate_weight)}], weight_decay=float(opt_config.weight_decay))  # 多参数组 Adam / Multi-group Adam
    trace = MultiFrequencyTrace()  # 轨迹 / Trace
    best_loss = math.inf  # 最佳损失 / Best
    best_step = 0  # 最佳步号 / Best step
    best_H_continuous: np.ndarray | None = None  # 缓存 H / Cache H
    best_freqs: list[float] | None = None  # 缓存频率 / Cache freqs
    best_weights: list[float] | None = None  # 缓存权重 / Cache weights
    best_composite: np.ndarray | None = None  # 缓存合成图 / Cache composite
    stale = 0  # 平台计数 / Plateau counter
    for step in range(int(opt_config.num_steps)):  # 主循环 / Main loop
        optimiser.zero_grad()  # 清零 / Zero grads
        H_clamped = _build_thickness(theta, coeffs, manifold, mean_t, comp_t, grid_size, h_min, h_max, default_h, centre_cells)  # 厚度 / Thickness
        H_proxy = plate.upsample(H_clamped)  # 升采样 / Upsample
        K_full, M_diag = plate.assemble_K_M(H_proxy)  # 装配 K/M / Assemble K/M
        free = plate.free_indices  # 自由度 / Free indices
        K_free = K_full.index_select(0, free).index_select(1, free)  # 自由 K / Free K
        M_free = torch.clamp(M_diag.index_select(0, free), min=1.0e-18)  # 自由 M / Free M
        if step < int(opt_config.freeze_freq_first_steps):  # 冻结 freq/weight / Freeze freq/weight
            freq_logits_use = freq_logits.detach()  # 冻结频率 / Detach freq
            weight_logits_use = weight_logits.detach()  # 冻结权重 / Detach weight
        else:  # 解冻 / Unfreeze
            freq_logits_use = freq_logits  # 用梯度版 / Use gradient version
            weight_logits_use = weight_logits  # 用梯度版 / Use gradient version
        frequencies_hz = frequencies_from_logits(freq_logits_use, float(opt_config.f_min_hz), float(opt_config.f_max_hz))  # 频率重参化 / Reparam freqs
        weights = weights_from_logits(weight_logits_use)  # 权重重参化 / Reparam weights
        per_freq_responses = []  # 每频响应列表 / Per-freq responses
        for k in range(K):  # 遍历 K 个频率 / Iterate K freqs
            omega_k = 2.0 * math.pi * frequencies_hz[k]  # 角频率 / Angular frequency
            u_free = plate.direct_forced_response(K_free, M_free, omega_k, float(opt_config.damping_ratio))  # 强迫响应 / Forced response
            u_grid = plate.expand_to_grid(u_free)  # 网格化 / Scatter
            per_freq_responses.append(u_grid)  # 加入列表 / Append
        amp_loss, composite_amp, parts = multifreq_amplitude_valley_loss(per_freq_responses, weights, bundle_tensors, epsilon=float(opt_config.epsilon))  # 多频损失 / Multi-freq loss
        smoothness = neighbour_smoothness_penalty(H_clamped, max_neighbour_diff_mm)  # 平滑 / Smoothness
        freq_sep = frequency_separation_penalty(frequencies_hz, float(opt_config.freq_separation_min_hz)) if step >= int(opt_config.freeze_freq_first_steps) else frequencies_hz.new_tensor(0.0)  # 间隔罚 / Separation
        sparsity = weight_sparsity_penalty(weights, int(opt_config.sparsity_target_active)) if int(opt_config.sparsity_target_active) > 0 and step >= int(opt_config.freeze_freq_first_steps) else weights.new_tensor(0.0)  # 稀疏罚 / Sparsity
        loss = amp_loss + float(opt_config.smoothness_weight) * smoothness + float(opt_config.freq_separation_weight) * freq_sep + float(opt_config.sparsity_weight) * sparsity  # 总损失 / Total
        if use_manifold and float(opt_config.manifold_coeff_l2_weight) > 0.0 and coeffs is not None:  # 系数 L2 / Coeff L2
            loss = loss + float(opt_config.manifold_coeff_l2_weight) * coeffs.pow(2).mean()  # 加入 L2 / Add L2
        loss.backward()  # 反传 / Backprop
        optimiser.step()  # 更新 / Step
        trace.total_loss.append(float(loss.item()))  # 记录 / Record
        trace.amp_loss.append(float(amp_loss.item()))  # 记录 / Record
        trace.target_part.append(float(parts["target"].item()))  # 记录 / Record
        trace.extra_part.append(float(parts["extra"].item()))  # 记录 / Record
        trace.contrast_part.append(float(parts["contrast"].item()))  # 记录 / Record
        trace.compact_part.append(float(parts["compact"].item()))  # 记录 / Record
        trace.smoothness_loss.append(float(smoothness.item()))  # 记录 / Record
        trace.freq_sep_loss.append(float(freq_sep.item()))  # 记录 / Record
        trace.sparsity_loss.append(float(sparsity.item()))  # 记录 / Record
        trace.frequencies_history.append([float(v) for v in frequencies_hz.detach().cpu().numpy().tolist()])  # 记录频率 / Record freqs
        trace.weights_history.append([float(v) for v in weights.detach().cpu().numpy().tolist()])  # 记录权重 / Record weights
        current = float(loss.item())  # 当前损失 / Current
        if current < best_loss - float(opt_config.plateau_min_delta):  # 改善 / Improvement
            best_loss = current  # 更新 / Update best
            best_step = step  # 步号 / Step
            best_H_continuous = H_clamped.detach().cpu().numpy().copy()  # 缓存 H / Cache H
            best_freqs = [float(v) for v in frequencies_hz.detach().cpu().numpy().tolist()]  # 缓存频率 / Cache freqs
            best_weights = [float(v) for v in weights.detach().cpu().numpy().tolist()]  # 缓存权重 / Cache weights
            best_composite = composite_amp.detach().cpu().numpy().copy()  # 缓存合成图 / Cache composite
            stale = 0  # 重置 / Reset
        else:  # 平台 / Plateau
            stale += 1  # 累计 / Accumulate
        if (step + 1) % int(max(1, opt_config.snapshot_every)) == 0 or step == 0:  # 快照 / Snapshot
            with torch.no_grad():  # 取数据 / Take data
                np.save(output_dir / f"snapshot_step_{step:04d}_H.npy", H_clamped.detach().cpu().numpy())  # 保存 H / Save H
                np.save(output_dir / f"snapshot_step_{step:04d}_composite.npy", composite_amp.detach().cpu().numpy())  # 保存合成图 / Save composite
        if stale >= int(opt_config.plateau_patience):  # 平台终止 / Plateau early stop
            break  # 跳出 / Break
    final_H = best_H_continuous if best_H_continuous is not None else H_clamped.detach().cpu().numpy()  # 最终 H / Final H
    final_freqs = best_freqs if best_freqs is not None else trace.frequencies_history[-1]  # 最终频率 / Final freqs
    final_weights = best_weights if best_weights is not None else trace.weights_history[-1]  # 最终权重 / Final weights
    np.savetxt(output_dir / "H_continuous.csv", final_H, delimiter=",", fmt="%.6f")  # 保存连续 H / Save continuous H
    levels = list(thickness_cfg.get("levels_mm") or [h_min, h_max])  # 等级 / Levels
    repaired = repair_neighbor_constraint(np.clip(final_H, h_min, h_max), levels, float(max_neighbour_diff_mm), fixed_cells=centre_cells)  # 修复 / Repair
    repaired = enforce_center_constraint(repaired, centre_cells, float(default_h))  # 固定中心 / Fix centre
    np.savetxt(output_dir / "H.csv", repaired, delimiter=",", fmt="%.6f")  # 保存 H / Save H
    np.savetxt(output_dir / "frequencies_hz.csv", np.asarray(final_freqs).reshape(-1, 1), delimiter=",", fmt="%.4f", header="frequency_hz", comments="")  # 保存频率 / Save freqs
    np.savetxt(output_dir / "weights.csv", np.asarray(final_weights).reshape(-1, 1), delimiter=",", fmt="%.6f", header="weight", comments="")  # 保存权重 / Save weights
    if best_composite is not None:  # 保存合成图 / Save composite
        np.save(output_dir / "composite_amplitude.npy", best_composite)  # 保存 / Save
    row_diff = float(np.max(np.abs(np.diff(repaired, axis=0))))  # 行差 / Row diff
    col_diff = float(np.max(np.abs(np.diff(repaired, axis=1))))  # 列差 / Col diff
    summary_weights = summarise_weight_distribution(torch.tensor(final_weights), torch.tensor(final_freqs))  # 权重摘要 / Weights summary
    summary = {"best_loss": float(best_loss) if best_H_continuous is not None else float(trace.total_loss[-1]), "best_step": int(best_step), "executed_steps": int(len(trace.total_loss)), "num_frequencies": int(K), "frequencies_hz": [float(v) for v in final_freqs], "weights": [float(v) for v in final_weights], "weight_distribution": summary_weights, "damping_ratio": float(opt_config.damping_ratio), "proxy_grid_size": int(plate.N), "f_min_hz": float(opt_config.f_min_hz), "f_max_hz": float(opt_config.f_max_hz), "smoothness_weight": float(opt_config.smoothness_weight), "smoothness_max_diff_mm": float(max_neighbour_diff_mm), "h_min_mm": h_min, "h_max_mm": h_max, "final_max_row_neighbour_diff_mm": row_diff, "final_max_col_neighbour_diff_mm": col_diff, "quantised_levels_mm": levels, "search_mode": "manifold_pca" if use_manifold else "direct_225d", "manifold": {"num_components": int(manifold.components.shape[0]), "sample_count": int(manifold.sample_count)} if use_manifold else None, "trace": {"total_loss": trace.total_loss, "amp_loss": trace.amp_loss, "target_part": trace.target_part, "extra_part": trace.extra_part, "contrast_part": trace.contrast_part, "compact_part": trace.compact_part, "smoothness_loss": trace.smoothness_loss, "freq_sep_loss": trace.freq_sep_loss, "sparsity_loss": trace.sparsity_loss, "frequencies_history": trace.frequencies_history, "weights_history": trace.weights_history}, "verdict_used": verdict}  # 汇总 / Summary
    (output_dir / "w7_optimization_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 JSON / Write JSON
    return summary  # 返回 / Return
