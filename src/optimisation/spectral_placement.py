from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
import math  # 导入数学函数 / Import math helpers
from dataclasses import dataclass, field  # 导入数据类装饰器 / Import dataclass decorator
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值库 / Import numerical library
import torch  # 导入张量库 / Import tensor library

from src.candidate.constraints import center_cells_for_grid  # 导入中心单元 / Import centre cells
from src.candidate.constraints import enforce_center_constraint  # 导入中心约束 / Import centre constraint
from src.candidate.constraints import repair_neighbor_constraint  # 导入相邻修复 / Import neighbour repair
from src.optimisation.gradient_optimizer import apply_center_clamp  # 复用中心夹持 / Reuse centre clamp
from src.optimisation.gradient_optimizer import initial_theta  # 复用 theta 初值 / Reuse theta init
from src.optimisation.gradient_optimizer import neighbour_smoothness_penalty  # 复用平滑罚 / Reuse smoothness penalty
from src.optimisation.gradient_optimizer import thickness_from_theta  # 复用 sigmoid 重参化 / Reuse sigmoid reparameterisation
from src.physics.differentiable_plate import DifferentiablePlate  # 导入可微板 / Import differentiable plate
from src.physics.modal_spectrum import compute_modal_spectrum  # 导入频谱入口 / Import spectrum entry
from src.physics.modal_spectrum import spectral_cluster_loss  # 导入聚簇损失 / Import cluster loss
from src.physics.plate_loss_adapter import amplitude_valley_loss_on_response  # 复用振幅谷线 / Reuse amplitude-valley
from src.physics.plate_loss_adapter import build_target_bundle  # 复用目标包构造 / Reuse target bundle builder
from src.physics.plate_loss_adapter import bundle_to_torch  # 复用目标张量化 / Reuse bundle tensorisation
from src.subspace.manifold_pca import DesignManifold  # 复用流形数据类 / Reuse manifold class
from src.subspace.manifold_pca import decode_torch as manifold_decode_torch  # 复用流形可微解码 / Reuse manifold decode


@dataclass  # 数据类装饰器 / Dataclass decorator
class SpectralPlacementConfig:  # W6 频谱聚簇优化配置 / W6 spectral-placement configuration
    proxy_grid_size: int = 25  # 代理网格尺寸 / Proxy grid size
    drive_frequency_hz: float = 800.0  # 驱动频率 / Drive frequency
    damping_ratio: float = 0.02  # Rayleigh 阻尼比 / Rayleigh damping ratio
    epsilon: float = 0.060  # 谷线 epsilon / Valley epsilon
    num_modes: int = 12  # 监测模态数 / Modes monitored
    num_steps: int = 200  # Adam 步数 / Adam steps
    learning_rate: float = 0.05  # Adam 学习率 / Adam learning rate
    weight_decay: float = 0.0  # 权重衰减 / Weight decay
    plateau_patience: int = 40  # 平台容忍步 / Plateau patience
    plateau_min_delta: float = 1.0e-4  # 平台最小改善 / Plateau min delta
    snapshot_every: int = 25  # 快照间隔 / Snapshot interval
    dtype: torch.dtype = field(default=torch.float64)  # 浮点精度 / Float precision
    device: str = "cpu"  # 设备 / Device
    base_accel_m_s2: float = 1.0  # 基础激振加速度 / Base-excitation acceleration
    smoothness_weight: float = 4.0  # 相邻平滑权重 / Neighbour-smoothness weight
    smoothness_max_diff_mm: float | None = None  # 邻格差上限 / Max neighbour delta
    manifold: DesignManifold | None = None  # 可选 PCA 流形 / Optional PCA manifold
    manifold_coeff_l2_weight: float = 0.0  # 流形系数 L2 / Manifold-coeff L2
    manifold_initial_coeff: np.ndarray | None = None  # 流形系数初值 / Manifold coeff init
    cluster_weight: float = 1.0  # 聚簇项权重 / Cluster-term weight
    amplitude_weight: float = 1.0  # 振幅谷线项权重 / Amplitude-valley weight
    cluster_realignment_every: int = 10  # 每多少步刷新一次模态契合权重 / Refresh alignment every N steps
    cluster_normalise: bool = True  # 是否按 ω² 归一化聚簇项 / Normalise cluster by ω²


@dataclass  # 数据类装饰器 / Dataclass decorator
class SpectralOptimisationTrace:  # 优化轨迹 / Optimisation trace
    total_loss: list[float] = field(default_factory=list)  # 总损失 / Total loss
    cluster_loss: list[float] = field(default_factory=list)  # 聚簇损失 / Cluster loss
    amplitude_loss: list[float] = field(default_factory=list)  # 振幅项 / Amplitude term
    smoothness_loss: list[float] = field(default_factory=list)  # 平滑项 / Smoothness term
    eigenvalues_first: list[list[float]] = field(default_factory=list)  # 前若干阶本征值 / Leading eigenvalues
    omega_squared: list[float] = field(default_factory=list)  # 驱动频率平方 / Drive ω² values
    weights_top1_mode_index: list[int] = field(default_factory=list)  # 最契合模态索引 / Top-1 alignment mode index


def _build_thickness(theta: torch.Tensor | None, coeffs: torch.Tensor | None, manifold: DesignManifold | None, mean_t: torch.Tensor | None, comp_t: torch.Tensor | None, grid_size: int, h_min: float, h_max: float, default_h: float, centre_cells: list[tuple[int, int]]) -> torch.Tensor:  # 构造受约束厚度 / Build constrained thickness
    if manifold is not None and coeffs is not None and mean_t is not None and comp_t is not None:  # 流形模式 / Manifold mode
        H_raw = manifold_decode_torch(coeffs, mean_t, comp_t, int(grid_size))  # PCA 解码 / PCA decode
        H_clipped = torch.clamp(H_raw, min=float(h_min), max=float(h_max))  # 可微 clamp / Differentiable clamp
    elif theta is not None:  # sigmoid 模式 / Sigmoid mode
        H_clipped = thickness_from_theta(theta, float(h_min), float(h_max))  # sigmoid 重参化 / Sigmoid reparameterisation
    else:  # 不应出现 / Should not happen
        raise RuntimeError("Either theta or coeffs must be provided. / theta 与 coeffs 必须至少有一个。")  # 抛出错误 / Raise error
    return apply_center_clamp(H_clipped, float(default_h), centre_cells)  # 应用中心夹持 / Apply centre clamp


def run_spectral_placement(config: dict, target_binary: np.ndarray, opt_config: SpectralPlacementConfig, output_dir: Path, verdict: dict | None = None, initial_H_mm: np.ndarray | None = None) -> dict:  # 运行 W6 频谱聚簇 / Run W6 spectral placement
    output_dir = Path(output_dir)  # 转路径 / Convert path
    output_dir.mkdir(parents=True, exist_ok=True)  # 创建目录 / Create directory
    device = torch.device(opt_config.device)  # 设备 / Device
    dtype = opt_config.dtype  # 精度 / Precision
    thickness_cfg = config["thickness"]  # 厚度配置 / Thickness config
    h_min = float(thickness_cfg["min_mm"])  # 厚度下限 / Thickness min
    h_max = float(thickness_cfg["max_mm"])  # 厚度上限 / Thickness max
    default_h = float(thickness_cfg.get("default_mm", h_max))  # 默认厚度 / Default thickness
    grid_size = int(config["project"]["grid_size"])  # 设计网格 / Design grid
    centre_cells = center_cells_for_grid(grid_size)  # 中心单元 / Centre cells
    max_neighbour_diff_mm = float(opt_config.smoothness_max_diff_mm if opt_config.smoothness_max_diff_mm is not None else thickness_cfg.get("max_neighbor_difference_mm", 1.0))  # 邻格差限 / Neighbour-diff limit
    plate = DifferentiablePlate(config, proxy_grid_size=int(opt_config.proxy_grid_size), base_accel=float(opt_config.base_accel_m_s2), default_damping=float(opt_config.damping_ratio), reference_frequency_hz=float(opt_config.drive_frequency_hz), dtype=dtype, device=device)  # 板模型 / Plate model
    bundle = build_target_bundle(target_binary, plate.N, float(config["project"]["center_clamp_radius_mm"]), float(config["project"]["plate_length_mm"]), verdict=verdict)  # 目标包 / Target bundle
    bundle_tensors = bundle_to_torch(bundle, device, dtype)  # 张量化 / Tensorise
    omega_squared = torch.tensor((2.0 * math.pi * float(opt_config.drive_frequency_hz)) ** 2, dtype=dtype, device=device)  # ω² / Drive ω²
    manifold = opt_config.manifold  # 流形 / Manifold
    use_manifold = manifold is not None  # 是否启用流形 / Manifold on
    mean_t = torch.tensor(manifold.mean, dtype=dtype, device=device) if use_manifold else None  # 均值张量 / Mean tensor
    comp_t = torch.tensor(manifold.components, dtype=dtype, device=device) if use_manifold else None  # 主成分张量 / Components tensor
    theta: torch.Tensor | None = None  # 占位 theta / Placeholder theta
    coeffs: torch.Tensor | None = None  # 占位 coeffs / Placeholder coeffs
    if use_manifold:  # 流形模式 / Manifold mode
        if opt_config.manifold_initial_coeff is not None:  # 提供系数初值 / Coeff init provided
            coeff_init = torch.tensor(np.asarray(opt_config.manifold_initial_coeff, dtype=np.float64).reshape(-1), dtype=dtype, device=device)  # 初值张量 / Init tensor
        elif initial_H_mm is not None:  # 用厚度反推 / Encode from thickness
            flat = np.asarray(initial_H_mm, dtype=np.float64).reshape(-1) - manifold.mean  # 去均值 / Centre
            coeff_init = torch.tensor(manifold.components @ flat, dtype=dtype, device=device)  # 投影 / Project
        else:  # 默认零系数 / Default zero coeffs
            coeff_init = torch.zeros(int(manifold.components.shape[0]), dtype=dtype, device=device)  # 零系数 / Zero coeffs
        coeffs = coeff_init.detach().clone().requires_grad_(True)  # 注册系数 / Register coeffs
        optimiser = torch.optim.Adam([coeffs], lr=float(opt_config.learning_rate), weight_decay=float(opt_config.weight_decay))  # Adam / Adam
    else:  # 225 维模式 / 225-D mode
        if initial_H_mm is not None:  # 提供厚度初值 / Thickness init provided
            h0 = np.asarray(initial_H_mm, dtype=np.float64)  # 转 numpy / Convert
            normalised = np.clip((h0 - h_min) / max(h_max - h_min, 1.0e-6), 1.0e-3, 1.0 - 1.0e-3)  # 归一化 / Normalise
            theta_init = torch.tensor(np.log(normalised / (1.0 - normalised)), dtype=dtype, device=device)  # 反 sigmoid / Inverse sigmoid
        else:  # 默认厚度 / Default thickness
            theta_init = initial_theta(default_h, h_min, h_max, grid_size, dtype).to(device)  # 常数 theta / Constant theta
        theta = theta_init.detach().clone().requires_grad_(True)  # 注册 theta / Register theta
        optimiser = torch.optim.Adam([theta], lr=float(opt_config.learning_rate), weight_decay=float(opt_config.weight_decay))  # Adam / Adam
    trace = SpectralOptimisationTrace()  # 创建轨迹 / Build trace
    best_loss = math.inf  # 初始化最佳 / Init best
    best_step = 0  # 最佳步号 / Best step
    best_H_continuous: np.ndarray | None = None  # 最佳连续厚度 / Best continuous thickness
    stale = 0  # 平台计数 / Plateau counter
    last_spectrum = None  # 上次频谱 / Last spectrum
    for step in range(int(opt_config.num_steps)):  # 主循环 / Main loop
        optimiser.zero_grad()  # 清零梯度 / Zero grads
        H_clamped = _build_thickness(theta, coeffs, manifold, mean_t, comp_t, grid_size, h_min, h_max, default_h, centre_cells)  # 构造厚度 / Build thickness
        H_proxy = plate.upsample(H_clamped)  # 升采样 / Upsample
        K_full, M_diag = plate.assemble_K_M(H_proxy)  # 组装 K M / Assemble K M
        free = plate.free_indices  # 自由度 / Free indices
        K_free = K_full.index_select(0, free).index_select(1, free)  # 截取自由刚度 / Slice free stiffness
        M_free = torch.clamp(M_diag.index_select(0, free), min=1.0e-18)  # 截取自由质量 / Slice free mass
        u_free = plate.direct_forced_response(K_free, M_free, torch.sqrt(omega_squared), float(opt_config.damping_ratio))  # 强迫响应 / Forced response
        response = plate.expand_to_grid(u_free)  # 铺到网格 / Scatter to grid
        if (step % int(max(1, opt_config.cluster_realignment_every))) == 0 or last_spectrum is None:  # 检查是否刷新契合权重 / Whether to refresh alignment
            last_spectrum = compute_modal_spectrum(K_free, M_free, free, plate.N, int(opt_config.num_modes), bundle_tensors, epsilon=float(opt_config.epsilon))  # 更新频谱 / Refresh spectrum
        else:  # 否则仅刷新可微本征值 / Otherwise only refresh diff eigvals
            from src.physics.modal_spectrum import differentiable_eigenvalues  # 延迟导入 / Lazy import
            eigvals = differentiable_eigenvalues(K_free, M_free, int(opt_config.num_modes))  # 重算可微本征值 / Recompute differentiable eigenvalues
            last_spectrum = type(last_spectrum)(eigenvalues=eigvals, eigenvalues_full=last_spectrum.eigenvalues_full, eigenvectors_grid=last_spectrum.eigenvectors_grid, target_alignment_loss=last_spectrum.target_alignment_loss, target_alignment_weights=last_spectrum.target_alignment_weights)  # 重构频谱结果 / Rebuild spectrum result
        cluster = spectral_cluster_loss(last_spectrum.eigenvalues, last_spectrum.target_alignment_weights, omega_squared, normalise_by_omega_sq=bool(opt_config.cluster_normalise))  # 聚簇损失 / Cluster loss
        amp_loss, amp_parts = amplitude_valley_loss_on_response(response, bundle_tensors, epsilon=float(opt_config.epsilon))  # 振幅损失 / Amplitude loss
        smoothness = neighbour_smoothness_penalty(H_clamped, max_neighbour_diff_mm)  # 平滑罚 / Smoothness penalty
        loss = float(opt_config.cluster_weight) * cluster + float(opt_config.amplitude_weight) * amp_loss + float(opt_config.smoothness_weight) * smoothness  # 总损失 / Total loss
        if use_manifold and float(opt_config.manifold_coeff_l2_weight) > 0.0 and coeffs is not None:  # 系数 L2 / Coeff L2
            loss = loss + float(opt_config.manifold_coeff_l2_weight) * coeffs.pow(2).mean()  # 加入 L2 / Add L2
        loss.backward()  # 反传 / Backpropagate
        optimiser.step()  # 更新 / Update
        trace.total_loss.append(float(loss.item()))  # 记录总损失 / Record total loss
        trace.cluster_loss.append(float(cluster.item()))  # 记录聚簇 / Record cluster
        trace.amplitude_loss.append(float(amp_loss.item()))  # 记录振幅 / Record amplitude
        trace.smoothness_loss.append(float(smoothness.item()))  # 记录平滑 / Record smoothness
        trace.eigenvalues_first.append([float(v) for v in last_spectrum.eigenvalues.detach().cpu().numpy().tolist()])  # 记录本征值 / Record eigenvalues
        trace.omega_squared.append(float(omega_squared.item()))  # 记录 ω² / Record ω²
        trace.weights_top1_mode_index.append(int(torch.argmax(last_spectrum.target_alignment_weights).item()))  # 记录最契合模态 / Record top-1 mode
        current = float(loss.item())  # 当前损失 / Current loss
        if current < best_loss - float(opt_config.plateau_min_delta):  # 显著改善 / Significant improvement
            best_loss = current  # 更新最佳 / Update best
            best_step = step  # 更新步号 / Update step
            best_H_continuous = H_clamped.detach().cpu().numpy().copy()  # 缓存厚度 / Cache thickness
            stale = 0  # 重置 / Reset
        else:  # 平台累积 / Accumulate plateau
            stale += 1  # 累计 / Accumulate
        if (step + 1) % int(max(1, opt_config.snapshot_every)) == 0 or step == 0:  # 快照 / Snapshot
            with torch.no_grad():  # 取数据 / Take data
                amp_np = torch.abs(response).detach().cpu().numpy()  # 振幅 / Amplitude
                np.save(output_dir / f"snapshot_step_{step:04d}_H.npy", H_clamped.detach().cpu().numpy())  # 保存厚度 / Save thickness
                np.save(output_dir / f"snapshot_step_{step:04d}_amplitude.npy", amp_np)  # 保存振幅 / Save amplitude
        if stale >= int(opt_config.plateau_patience):  # 平台终止 / Plateau exit
            break  # 提前结束 / Early stop
    final_H = best_H_continuous if best_H_continuous is not None else H_clamped.detach().cpu().numpy()  # 最终连续厚度 / Final continuous
    np.savetxt(output_dir / "H_continuous.csv", final_H, delimiter=",", fmt="%.6f")  # 保存连续 H / Save continuous H
    levels = list(thickness_cfg.get("levels_mm") or [h_min, h_max])  # 制造等级 / Manufacturable levels
    repaired = repair_neighbor_constraint(np.clip(final_H, h_min, h_max), levels, float(max_neighbour_diff_mm), fixed_cells=centre_cells)  # 修复邻格差 / Repair neighbour
    repaired = enforce_center_constraint(repaired, centre_cells, float(default_h))  # 再次固定中心 / Re-fix centre
    np.savetxt(output_dir / "H.csv", repaired, delimiter=",", fmt="%.6f")  # 保存最终 H / Save final H
    row_diff = float(np.max(np.abs(np.diff(repaired, axis=0))))  # 行向最大邻差 / Row max neighbour
    col_diff = float(np.max(np.abs(np.diff(repaired, axis=1))))  # 列向最大邻差 / Column max neighbour
    eig_first = last_spectrum.eigenvalues_full.detach().cpu().numpy().tolist() if last_spectrum is not None else []  # 末步本征值 / Final eigenvalues
    distance_to_omega2 = [float(abs(v - omega_squared.item())) for v in last_spectrum.eigenvalues.detach().cpu().numpy().tolist()] if last_spectrum is not None else []  # 末步频差 / Final frequency residuals
    summary = {"best_loss": float(best_loss) if best_H_continuous is not None else float(trace.total_loss[-1]), "best_step": int(best_step), "executed_steps": int(len(trace.total_loss)), "drive_frequency_hz": float(opt_config.drive_frequency_hz), "damping_ratio": float(opt_config.damping_ratio), "proxy_grid_size": int(plate.N), "num_modes_tracked": int(opt_config.num_modes), "cluster_weight": float(opt_config.cluster_weight), "amplitude_weight": float(opt_config.amplitude_weight), "smoothness_weight": float(opt_config.smoothness_weight), "smoothness_max_diff_mm": float(max_neighbour_diff_mm), "h_min_mm": h_min, "h_max_mm": h_max, "final_max_row_neighbour_diff_mm": row_diff, "final_max_col_neighbour_diff_mm": col_diff, "quantised_levels_mm": levels, "search_mode": "manifold_pca" if use_manifold else "direct_225d", "manifold": {"num_components": int(manifold.components.shape[0]), "sample_count": int(manifold.sample_count)} if use_manifold else None, "trace": {"total_loss": trace.total_loss, "cluster_loss": trace.cluster_loss, "amplitude_loss": trace.amplitude_loss, "smoothness_loss": trace.smoothness_loss, "omega_squared": trace.omega_squared, "top1_mode_index": trace.weights_top1_mode_index, "eigenvalues_history": trace.eigenvalues_first}, "final_eigenvalues_tracked": eig_first, "final_residuals_omega2": distance_to_omega2, "verdict_used": verdict}  # 总结 / Summary
    (output_dir / "w6_optimization_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 JSON / Write JSON
    return summary  # 返回 / Return
