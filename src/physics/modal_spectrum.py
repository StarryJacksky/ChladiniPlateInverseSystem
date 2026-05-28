from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from dataclasses import dataclass  # 导入数据类装饰器 / Import dataclass decorator

import torch  # 导入张量库 / Import tensor library

from src.physics.plate_loss_adapter import amplitude_valley_loss_on_response  # 复用振幅谷线损失 / Reuse amplitude-valley loss


@dataclass  # 数据类装饰器 / Dataclass decorator
class ModalSpectrumResult:  # 模态频谱结果 / Modal-spectrum result
    eigenvalues: torch.Tensor  # 可微本征值 (num_modes,) / Differentiable eigenvalues
    eigenvalues_full: torch.Tensor  # 全部本征值用于诊断 / Full eigenvalues for diagnostics
    eigenvectors_grid: torch.Tensor  # 模式形状网格 / Mode-shape grid on N x N
    target_alignment_loss: torch.Tensor  # 每模态目标契合损失 (num_modes,) 无梯度 / Per-mode target-alignment loss (num_modes,) no grad
    target_alignment_weights: torch.Tensor  # 归一化契合权重 (num_modes,) 无梯度 / Normalised alignment weights (num_modes,) no grad


def _symmetrise_K_M(K_free: torch.Tensor, M_free: torch.Tensor) -> torch.Tensor:  # 构造标准对称问题 / Build symmetric standard problem
    inv_sqrt_M = 1.0 / torch.sqrt(torch.clamp(M_free, min=1.0e-18))  # 质量平方根反 / Inverse mass square root
    K_scaled = K_free * inv_sqrt_M.unsqueeze(0) * inv_sqrt_M.unsqueeze(1)  # 标准化刚度 / Symmetric standard stiffness
    return 0.5 * (K_scaled + K_scaled.T)  # 强制对称 / Force symmetric


def differentiable_eigenvalues(K_free: torch.Tensor, M_free: torch.Tensor, num_modes: int) -> torch.Tensor:  # 可微本征值 / Differentiable eigenvalues
    K_scaled = _symmetrise_K_M(K_free, M_free)  # 标准化 / Symmetrise
    eigvals = torch.linalg.eigvalsh(K_scaled)  # 求实本征值 / Solve real eigenvalues
    eigvals = torch.clamp(eigvals, min=0.0)  # 防数值负值 / Clip numerical negatives
    return eigvals[: int(num_modes)]  # 截取前若干阶 / Slice leading modes


def forward_only_eigenpairs(K_free: torch.Tensor, M_free: torch.Tensor, num_modes: int) -> tuple[torch.Tensor, torch.Tensor]:  # 仅 forward 的本征对 / Forward-only eigenpairs
    with torch.no_grad():  # 关闭梯度 / Disable autograd
        K_scaled = _symmetrise_K_M(K_free.detach(), M_free.detach())  # 已 detach 后再标准化 / Symmetrise after detach
        eigvals, eigvecs = torch.linalg.eigh(K_scaled)  # 求标准本征对 / Solve standard eigenpairs
        inv_sqrt_M = 1.0 / torch.sqrt(torch.clamp(M_free.detach(), min=1.0e-18))  # 质量平方根反 / Inverse mass sqrt
        phi = eigvecs * inv_sqrt_M.unsqueeze(1)  # 还原广义本征向量 / Recover generalised eigenvectors
    return eigvals[: int(num_modes)], phi[:, : int(num_modes)]  # 截取前若干阶 / Slice leading modes


def scatter_mode_to_grid(phi_free: torch.Tensor, free_indices: torch.Tensor, grid_size: int) -> torch.Tensor:  # 把本征向量铺到网格 / Scatter eigenvector to grid
    N = int(grid_size)  # 网格 / Grid
    full = torch.zeros(N * N, dtype=phi_free.dtype, device=phi_free.device)  # 创建零向量 / Create zero vector
    full.index_copy_(0, free_indices, phi_free)  # 写入自由度 / Write free DOFs
    return full.reshape(N, N)  # 返回二维形状 / Return 2-D shape


def per_mode_target_alignment(eigenvectors_free: torch.Tensor, free_indices: torch.Tensor, grid_size: int, bundle_tensors: dict[str, torch.Tensor], epsilon: float = 0.060) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:  # 计算每模态目标契合 / Compute per-mode target alignment
    num_modes = int(eigenvectors_free.shape[1])  # 模态数 / Mode count
    grid_shapes: list[torch.Tensor] = []  # 创建网格列表 / Create grid list
    losses: list[float] = []  # 创建损失列表 / Create loss list
    with torch.no_grad():  # 关闭梯度 / Disable autograd
        for i in range(num_modes):  # 遍历模态 / Iterate modes
            phi_grid = scatter_mode_to_grid(eigenvectors_free[:, i], free_indices, grid_size)  # 铺到网格 / Scatter to grid
            grid_shapes.append(phi_grid.unsqueeze(0))  # 增维收集 / Stack with new axis
            norm = float(torch.norm(phi_grid)) or 1.0  # 计算归一化常数 / Compute normalisation
            phi_unit = phi_grid / norm  # 单位化 / Normalise
            response = phi_unit.to(dtype=torch.complex128 if phi_unit.dtype == torch.float64 else torch.complex64)  # 转伪复数 / Cast to pseudo-complex
            loss_value, _ = amplitude_valley_loss_on_response(response, bundle_tensors, epsilon=float(epsilon))  # 计算契合损失 / Compute alignment loss
            losses.append(float(loss_value.item()))  # 记录损失 / Record loss
    loss_tensor = torch.tensor(losses, dtype=eigenvectors_free.dtype, device=eigenvectors_free.device)  # 转张量 / Convert to tensor
    weights = torch.softmax(-loss_tensor, dim=0)  # softmax 加权 / Softmax weighting
    grids = torch.cat(grid_shapes, dim=0)  # 拼接形状 / Concatenate shapes
    return loss_tensor, weights, grids  # 返回三元组 / Return triple


def compute_modal_spectrum(K_free: torch.Tensor, M_free: torch.Tensor, free_indices: torch.Tensor, grid_size: int, num_modes: int, bundle_tensors: dict[str, torch.Tensor], epsilon: float = 0.060) -> ModalSpectrumResult:  # 统一入口 / Unified entry
    eigvals = differentiable_eigenvalues(K_free, M_free, int(num_modes))  # 可微本征值 / Differentiable eigenvalues
    eigvals_full, eigvecs_free = forward_only_eigenpairs(K_free, M_free, int(num_modes))  # forward-only 本征对 / Forward-only eigenpairs
    losses, weights, grids = per_mode_target_alignment(eigvecs_free, free_indices, int(grid_size), bundle_tensors, epsilon=float(epsilon))  # 每模态契合度 / Per-mode alignment
    return ModalSpectrumResult(eigenvalues=eigvals, eigenvalues_full=eigvals_full, eigenvectors_grid=grids, target_alignment_loss=losses, target_alignment_weights=weights)  # 返回结果 / Return result


def spectral_cluster_loss(eigenvalues: torch.Tensor, target_weights: torch.Tensor, omega_squared: torch.Tensor, normalise_by_omega_sq: bool = True) -> torch.Tensor:  # 模态频率聚簇损失 / Modal-frequency cluster loss
    residual = eigenvalues - omega_squared  # 频率差 / Frequency residual
    if normalise_by_omega_sq:  # 检查是否归一化 / Check normalisation
        scale = torch.clamp(omega_squared, min=1.0e-12)  # 防零 / Avoid zero
        residual = residual / scale  # 归一化 / Normalise
    return torch.sum(target_weights * residual.pow(2))  # 加权平方和 / Weighted squared sum
