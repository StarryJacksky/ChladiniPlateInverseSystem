from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
import math  # 导入数学函数 / Import math helpers
from dataclasses import dataclass, field  # 导入数据类工具 / Import dataclass utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
import torch  # 导入张量计算库 / Import tensor computation library

from src.candidate.constraints import center_cells_for_grid  # 导入中心单元工具 / Import centre-cell helper
from src.candidate.constraints import enforce_center_constraint  # 导入中心约束 / Import centre constraint
from src.candidate.constraints import repair_neighbor_constraint  # 导入相邻修复 / Import neighbour repair
from src.physics.differentiable_plate import DifferentiablePlate  # 导入可微板模型 / Import differentiable plate
from src.physics.plate_loss_adapter import amplitude_valley_loss_on_response  # 导入振幅谷线损失适配 / Import amplitude-valley loss adapter
from src.physics.plate_loss_adapter import build_target_bundle  # 导入目标包构造 / Import target bundle builder
from src.physics.plate_loss_adapter import bundle_to_torch  # 导入目标包张量化 / Import bundle tensor conversion
from src.subspace.manifold_pca import DesignManifold  # 导入流形数据类 / Import manifold data class
from src.subspace.manifold_pca import decode_torch as manifold_decode_torch  # 导入流形 torch 还原 / Import torch decode


@dataclass  # 数据类装饰器 / Dataclass decorator
class GradientOptimizerConfig:  # 梯度优化器配置 / Gradient optimizer configuration
    proxy_grid_size: int = 25  # 代理网格尺寸 / Proxy grid size
    drive_frequency_hz: float = 800.0  # 驱动频率 / Drive frequency
    damping_ratio: float = 0.02  # 模态阻尼比 / Modal damping ratio
    epsilon: float = 0.060  # 谷线判定 epsilon / Valley epsilon
    num_steps: int = 250  # Adam 步数 / Adam steps
    learning_rate: float = 0.05  # Adam 学习率 / Adam learning rate
    weight_decay: float = 0.0  # Adam 权重衰减 / Adam weight decay
    plateau_patience: int = 40  # 平台期容忍步数 / Plateau patience
    plateau_min_delta: float = 1.0e-4  # 平台期最小改善 / Plateau minimum improvement
    snapshot_every: int = 25  # 快照保存间隔 / Snapshot save interval
    dtype: torch.dtype = field(default=torch.float64)  # 浮点精度 / Float precision
    device: str = "cpu"  # 运算设备 / Compute device
    loss_weights: dict[str, float] | None = None  # 自定义损失权重 / Custom loss weights
    base_accel_m_s2: float = 1.0  # 基础激振加速度 / Base-excitation acceleration
    smoothness_weight: float = 4.0  # 相邻约束正则权重 / Neighbour-constraint regularisation weight
    smoothness_max_diff_mm: float | None = None  # 允许的最大相邻差 / Allowed neighbour delta
    manifold: DesignManifold | None = None  # 可选 PCA 流形 / Optional PCA manifold
    manifold_coeff_l2_weight: float = 0.0  # 流形系数 L2 正则 / Manifold-coefficient L2 regularisation
    manifold_initial_coeff: np.ndarray | None = None  # 流形系数初值 / Initial manifold coefficients


def thickness_from_theta(theta: torch.Tensor, h_min_mm: float, h_max_mm: float) -> torch.Tensor:  # 重参化为厚度 / Reparameterise to thickness
    return float(h_min_mm) + (float(h_max_mm) - float(h_min_mm)) * torch.sigmoid(theta)  # 用 sigmoid 限制范围 / Bound by sigmoid


def initial_theta(h_mm: float, h_min_mm: float, h_max_mm: float, grid_size: int, dtype: torch.dtype) -> torch.Tensor:  # 计算初始 theta / Compute initial theta
    span = max(float(h_max_mm) - float(h_min_mm), 1.0e-6)  # 厚度跨度 / Thickness span
    normalised = float(np.clip((float(h_mm) - float(h_min_mm)) / span, 1.0e-3, 1.0 - 1.0e-3))  # 归一化目标 / Normalised target
    theta_value = float(math.log(normalised / (1.0 - normalised)))  # 反 sigmoid / Inverse sigmoid
    return torch.full((int(grid_size), int(grid_size)), float(theta_value), dtype=dtype)  # 返回常数初值 / Return constant init


def apply_center_clamp(thickness: torch.Tensor, fixed_thickness_mm: float, center_cells: list[tuple[int, int]]) -> torch.Tensor:  # 中心区域强制为固定厚度 / Force centre cells to fixed thickness
    if not center_cells:  # 无中心单元 / No centre cells
        return thickness  # 直接返回 / Return as-is
    mask = torch.ones_like(thickness)  # 创建可写掩膜 / Create writable mask
    for row, col in center_cells:  # 遍历中心单元 / Iterate centre cells
        mask[row, col] = 0.0  # 标记中心位置 / Mark centre location
    return thickness * mask + (1.0 - mask) * float(fixed_thickness_mm)  # 替换中心厚度 / Replace centre thickness


def neighbour_smoothness_penalty(thickness: torch.Tensor, max_diff_mm: float) -> torch.Tensor:  # 相邻差超额惩罚 / Neighbour-delta excess penalty
    row_diff = torch.abs(thickness[1:, :] - thickness[:-1, :])  # 行向差 / Vertical differences
    col_diff = torch.abs(thickness[:, 1:] - thickness[:, :-1])  # 列向差 / Horizontal differences
    excess_row = torch.clamp(row_diff - float(max_diff_mm), min=0.0)  # 行向超额 / Row excess
    excess_col = torch.clamp(col_diff - float(max_diff_mm), min=0.0)  # 列向超额 / Column excess
    return excess_row.mean() + excess_col.mean()  # L1 形式相邻惩罚 / L1 neighbour penalty


@dataclass  # 数据类装饰器 / Dataclass decorator
class OptimizationTrace:  # 优化轨迹记录 / Optimisation trace record
    losses: list[float] = field(default_factory=list)  # 总损失序列 / Total-loss sequence
    target_loss: list[float] = field(default_factory=list)  # 目标线损失 / Target-line loss
    extra_loss: list[float] = field(default_factory=list)  # 离目标谷损失 / Off-target valley loss
    contrast_loss: list[float] = field(default_factory=list)  # 对比损失 / Contrast loss
    compact_loss: list[float] = field(default_factory=list)  # 紧凑损失 / Compact loss
    smoothness_loss: list[float] = field(default_factory=list)  # 平滑约束损失 / Neighbour smoothness loss
    step_seconds: list[float] = field(default_factory=list)  # 步骤耗时 / Step time
    snapshots: list[dict] = field(default_factory=list)  # 快照列表 / Snapshot list


def run_gradient_optimization(config: dict, target_binary: np.ndarray, opt_config: GradientOptimizerConfig, output_dir: Path, verdict: dict | None = None, initial_H_mm: np.ndarray | None = None) -> dict:  # 运行梯度优化 / Run gradient optimisation
    output_dir = Path(output_dir)  # 转换输出目录 / Convert output directory
    output_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    device = torch.device(opt_config.device)  # 选择设备 / Select device
    dtype = opt_config.dtype  # 选择精度 / Select precision
    thickness_cfg = config["thickness"]  # 读取厚度配置 / Read thickness config
    h_min_mm = float(thickness_cfg["min_mm"])  # 厚度下限 / Thickness minimum
    h_max_mm = float(thickness_cfg["max_mm"])  # 厚度上限 / Thickness maximum
    default_h_mm = float(thickness_cfg.get("default_mm", h_max_mm))  # 默认厚度 / Default thickness
    grid_size = int(config["project"]["grid_size"])  # 设计网格尺寸 / Design grid size
    center_cells = center_cells_for_grid(grid_size)  # 计算中心单元 / Compute centre cells
    max_neighbour_diff_mm = float(opt_config.smoothness_max_diff_mm if opt_config.smoothness_max_diff_mm is not None else thickness_cfg.get("max_neighbor_difference_mm", 1.0))  # 决定相邻差限 / Resolve neighbour delta limit
    plate = DifferentiablePlate(config, proxy_grid_size=opt_config.proxy_grid_size, base_accel=opt_config.base_accel_m_s2, default_damping=opt_config.damping_ratio, reference_frequency_hz=opt_config.drive_frequency_hz, dtype=dtype, device=device)  # 构造板模型 / Build plate model
    bundle = build_target_bundle(target_binary, plate.N, float(config["project"]["center_clamp_radius_mm"]), float(config["project"]["plate_length_mm"]), verdict=verdict)  # 构造目标包 / Build target bundle
    bundle_tensors = bundle_to_torch(bundle, device, dtype)  # 转张量字典 / Convert to tensor dict
    manifold = opt_config.manifold  # 读取流形 / Read manifold
    use_manifold = manifold is not None  # 是否走流形路径 / Whether to use manifold
    manifold_mean_t: torch.Tensor | None = None  # 占位流形均值张量 / Placeholder mean tensor
    manifold_components_t: torch.Tensor | None = None  # 占位主成分张量 / Placeholder components tensor
    if use_manifold:  # 走 PCA 系数路径 / Use PCA-coefficient path
        if int(manifold.grid_size) != int(grid_size):  # 网格尺寸需要一致 / Grid sizes must match
            raise ValueError(f"Manifold grid {manifold.grid_size} != design grid {grid_size}. / 流形网格 {manifold.grid_size} 与设计网格 {grid_size} 不一致。")  # 抛出错误 / Raise error
        manifold_mean_t = torch.tensor(manifold.mean, dtype=dtype, device=device)  # 均值张量 / Mean tensor
        manifold_components_t = torch.tensor(manifold.components, dtype=dtype, device=device)  # 主成分张量 / Components tensor
        if opt_config.manifold_initial_coeff is not None:  # 提供系数初值 / Coeff initial provided
            coeff_init = torch.tensor(np.asarray(opt_config.manifold_initial_coeff, dtype=np.float64).reshape(-1), dtype=dtype, device=device)  # 系数初值张量 / Coeff init tensor
        elif initial_H_mm is not None:  # 用厚度反推系数 / Encode from thickness
            flat = np.asarray(initial_H_mm, dtype=np.float64).reshape(-1) - manifold.mean  # 去均值 / Centre
            coeff_init = torch.tensor(manifold.components @ flat, dtype=dtype, device=device)  # 投影到主成分 / Project to components
        else:  # 默认从零系数（流形均值）启动 / Default from zero coeffs (mean of manifold)
            coeff_init = torch.zeros(int(manifold.components.shape[0]), dtype=dtype, device=device)  # 零系数 / Zero coeffs
        coeffs = coeff_init.detach().clone().requires_grad_(True)  # 注册可优化系数 / Register optimisable coeffs
        optimiser = torch.optim.Adam([coeffs], lr=float(opt_config.learning_rate), weight_decay=float(opt_config.weight_decay))  # 创建 Adam / Build Adam
        theta = None  # 不再使用 theta / Theta unused
    else:  # 走原始 225 维路径 / Original 225-D path
        if initial_H_mm is not None:  # 提供初值厚度 / Initial thickness provided
            h0 = np.asarray(initial_H_mm, dtype=np.float64)  # 转 numpy / Convert to numpy
            normalised = np.clip((h0 - h_min_mm) / max(h_max_mm - h_min_mm, 1.0e-6), 1.0e-3, 1.0 - 1.0e-3)  # 归一化到 (0,1) / Normalise into (0,1)
            theta_init = torch.tensor(np.log(normalised / (1.0 - normalised)), dtype=dtype, device=device)  # 反 sigmoid 得 theta / Inverse sigmoid to theta
        else:  # 无初值时用默认厚度 / Without initial, use default
            theta_init = initial_theta(default_h_mm, h_min_mm, h_max_mm, grid_size, dtype).to(device)  # 常数 theta / Constant theta
        theta = theta_init.detach().clone().requires_grad_(True)  # 注册可优化参数 / Register optimisable parameter
        optimiser = torch.optim.Adam([theta], lr=float(opt_config.learning_rate), weight_decay=float(opt_config.weight_decay))  # 创建 Adam / Build Adam
        coeffs = None  # 系数模式不使用 / Coeff unused
    trace = OptimizationTrace()  # 创建轨迹 / Build trace
    import time  # 延迟导入 time / Lazy time import
    best_loss = math.inf  # 初始化最佳损失 / Init best loss
    best_H = None  # 初始化最佳厚度 / Init best H
    best_step = 0  # 初始化最佳步号 / Init best step
    stale_steps = 0  # 平台计数 / Plateau counter
    for step in range(int(opt_config.num_steps)):  # 主优化循环 / Main optimisation loop
        start = time.time()  # 计时开始 / Start timer
        optimiser.zero_grad()  # 清零梯度 / Zero gradients
        if use_manifold:  # 流形模式 / Manifold mode
            H_raw = manifold_decode_torch(coeffs, manifold_mean_t, manifold_components_t, grid_size)  # PCA 解码 / PCA decode
            H_continuous = torch.clamp(H_raw, min=float(h_min_mm), max=float(h_max_mm))  # 可微 clamp / Differentiable clamp
        else:  # 原始模式 / Original mode
            H_continuous = thickness_from_theta(theta, h_min_mm, h_max_mm)  # 重参化为厚度 / Reparameterise to thickness
        H_clamped = apply_center_clamp(H_continuous, default_h_mm, center_cells)  # 应用中心夹持 / Apply centre clamp
        result = plate.forward(H_clamped, drive_frequency_hz=opt_config.drive_frequency_hz, damping_ratio=opt_config.damping_ratio)  # 板前向 / Plate forward
        valley_loss, parts = amplitude_valley_loss_on_response(result.response_complex, bundle_tensors, epsilon=opt_config.epsilon, weights=opt_config.loss_weights)  # 计算振幅谷线损失 / Compute amplitude-valley loss
        smoothness = neighbour_smoothness_penalty(H_clamped, max_neighbour_diff_mm)  # 计算相邻差惩罚 / Compute neighbour penalty
        loss = valley_loss + float(opt_config.smoothness_weight) * smoothness  # 合成总损失 / Combine total loss
        if use_manifold and float(opt_config.manifold_coeff_l2_weight) > 0.0:  # 检查系数 L2 / Check coeff L2
            loss = loss + float(opt_config.manifold_coeff_l2_weight) * coeffs.pow(2).mean()  # 加入系数惩罚 / Add coeff penalty
        loss.backward()  # 反传 / Backpropagate
        optimiser.step()  # Adam 更新 / Adam step
        step_time = time.time() - start  # 步骤耗时 / Step time
        trace.losses.append(float(loss.item()))  # 记录总损失 / Record total loss
        trace.target_loss.append(float(parts["target"].item()))  # 记录目标项 / Record target term
        trace.extra_loss.append(float(parts["extra"].item()))  # 记录离目标项 / Record extra term
        trace.contrast_loss.append(float(parts["contrast"].item()))  # 记录对比项 / Record contrast term
        trace.compact_loss.append(float(parts["compact"].item()))  # 记录紧凑项 / Record compact term
        trace.smoothness_loss.append(float(smoothness.item()))  # 记录平滑项 / Record smoothness term
        trace.step_seconds.append(float(step_time))  # 记录耗时 / Record step time
        current_loss = float(loss.item())  # 读取当前损失 / Read current loss
        if current_loss < best_loss - opt_config.plateau_min_delta:  # 检测显著改善 / Detect significant improvement
            best_loss = current_loss  # 更新最佳损失 / Update best loss
            best_step = step  # 更新最佳步号 / Update best step
            with torch.no_grad():  # 拷贝最佳厚度 / Copy best thickness
                best_H = H_clamped.detach().cpu().numpy().copy()  # 缓存最佳厚度 / Cache best thickness
            stale_steps = 0  # 重置平台计数 / Reset plateau counter
        else:  # 否则增加平台计数 / Otherwise increment plateau counter
            stale_steps += 1  # 累计平台 / Accumulate plateau
        if (step + 1) % int(max(1, opt_config.snapshot_every)) == 0 or step == 0:  # 检查是否保存快照 / Check whether to save snapshot
            with torch.no_grad():  # 离开图保存数据 / Detach for save
                amplitude_np = result.amplitude.detach().cpu().numpy()  # 取振幅 / Get amplitude
                H_np = H_clamped.detach().cpu().numpy()  # 取厚度 / Get thickness
            trace.snapshots.append({"step": step, "loss": current_loss, "H_mm": H_np.tolist(), "amplitude_max": float(amplitude_np.max()), "amplitude_mean": float(amplitude_np.mean())})  # 记录快照摘要 / Record snapshot summary
            np.save(output_dir / f"snapshot_step_{step:04d}_H.npy", H_np)  # 保存厚度快照 / Save thickness snapshot
            np.save(output_dir / f"snapshot_step_{step:04d}_amplitude.npy", amplitude_np)  # 保存振幅快照 / Save amplitude snapshot
        if stale_steps >= int(opt_config.plateau_patience):  # 检查平台终止 / Check plateau termination
            break  # 提前结束 / Early stop
    final_H_raw = best_H if best_H is not None else H_clamped.detach().cpu().numpy()  # 选择最终连续厚度 / Select final continuous thickness
    np.savetxt(output_dir / "H_continuous.csv", final_H_raw, delimiter=",", fmt="%.6f")  # 保存连续优化结果 / Save continuous optimisation result
    levels = list(thickness_cfg.get("levels_mm") or [h_min_mm, h_max_mm])  # 读取允许厚度等级 / Read manufacturable levels
    final_H = repair_neighbor_constraint(np.clip(final_H_raw, h_min_mm, h_max_mm), levels, float(max_neighbour_diff_mm), fixed_cells=center_cells)  # 修复相邻约束并量化 / Repair neighbour constraint and quantise
    final_H = enforce_center_constraint(final_H, center_cells, float(default_h_mm))  # 重新固定中心厚度 / Re-fix centre thickness
    np.savetxt(output_dir / "H.csv", final_H, delimiter=",", fmt="%.6f")  # 写最终 H 矩阵 / Write final H matrix
    row_diff_final = float(np.max(np.abs(np.diff(final_H, axis=0))))  # 最终行向最大相邻差 / Final row neighbour delta
    col_diff_final = float(np.max(np.abs(np.diff(final_H, axis=1))))  # 最终列向最大相邻差 / Final column neighbour delta
    manifold_summary: dict | None = None  # 占位流形摘要 / Manifold summary placeholder
    if use_manifold:  # 收集流形信息 / Collect manifold info
        with torch.no_grad():  # 离开图取系数 / Detach to fetch coeffs
            coeffs_final = coeffs.detach().cpu().numpy().copy()  # 最终系数 / Final coefficients
        np.savetxt(output_dir / "manifold_coefficients.csv", coeffs_final, delimiter=",", fmt="%.6f")  # 保存系数 / Save coefficients
        manifold_summary = {"num_components": int(manifold.components.shape[0]), "grid_size": int(manifold.grid_size), "sample_count": int(manifold.sample_count), "explained_variance_ratio_last": float(manifold.explained_variance_ratio[-1]), "coeff_l2_weight": float(opt_config.manifold_coeff_l2_weight), "coefficients_l2_norm": float(np.linalg.norm(coeffs_final))}  # 流形摘要 / Manifold summary
    summary = {"best_loss": float(best_loss) if best_H is not None else float(trace.losses[-1]), "best_step": int(best_step), "executed_steps": int(len(trace.losses)), "drive_frequency_hz": float(opt_config.drive_frequency_hz), "damping_ratio": float(opt_config.damping_ratio), "proxy_grid_size": int(plate.N), "epsilon": float(opt_config.epsilon), "loss_weights": opt_config.loss_weights or {}, "smoothness_weight": float(opt_config.smoothness_weight), "smoothness_max_diff_mm": float(max_neighbour_diff_mm), "final_max_row_neighbour_diff_mm": row_diff_final, "final_max_col_neighbour_diff_mm": col_diff_final, "h_min_mm": h_min_mm, "h_max_mm": h_max_mm, "quantised_levels_mm": levels, "manifold": manifold_summary, "search_mode": "manifold_pca" if use_manifold else "direct_225d", "trace": {"losses": trace.losses, "target_loss": trace.target_loss, "extra_loss": trace.extra_loss, "contrast_loss": trace.contrast_loss, "compact_loss": trace.compact_loss, "smoothness_loss": trace.smoothness_loss, "step_seconds": trace.step_seconds, "snapshots": trace.snapshots}, "verdict_used": verdict}  # 构造摘要 / Build summary
    (output_dir / "w3_optimization_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")  # 写摘要 JSON / Write summary JSON
    return summary  # 返回摘要 / Return summary
