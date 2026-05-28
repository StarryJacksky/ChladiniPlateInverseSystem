from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

"""Sinkhorn divergence (entropic optimal transport) loss for Chladni inverse design.
Sinkhorn 散度（熵正则最优传输）损失，给 Chladni 逆向设计使用。

动机 / Motivation:
- Engquist & Yang (J. Comput. Phys. 2016, SIAM Rev. 2021) 证明：在波形反演里，L² 损失
  对节线/节点的几何错位是非凸的（"cycle skipping"）；W₂ Wasserstein 损失对平移和振幅
  缩放是凸的。
- Cuturi 2013 提出熵正则 Sinkhorn 散度，O(N²) 复杂度，GPU 友好，可微。
- 对 Chladni：节线偏一格就 0 IoU → 优化器没梯度；改用 Sinkhorn → 即使错位也有"往哪挪"
  的梯度。

实现 / Implementation:
- 把模拟撒粉密度 μ_粉(x) 和目标骨架 μ_target(x) 都归一化为概率分布
- 用 geomloss.SamplesLoss('sinkhorn', p=2, blur=ε, scaling=0.9) 算两者间的散度
- 由于 grid 点固定，本质退化为 grid-based OT（fast lapped Sinkhorn）

参考 / References:
- Cuturi 2013 (NIPS, "Sinkhorn Distances: Lightspeed Computation of OT")
- Feydy et al. 2019 (AISTATS, "Interpolating between OT and MMD", geomloss library)
- Engquist & Yang 2018 (Commun. Math. Sci. 14:2018)
- Métivier et al. 2016 (Geophys. J. Int. 205)
"""

import torch  # Torch / Torch

try:  # 尝试导入 geomloss / Try import
    from geomloss import SamplesLoss  # geomloss 入口 / geomloss entry
    HAS_GEOMLOSS = True  # 标志 / Flag
except ImportError:  # 未安装 / Not installed
    HAS_GEOMLOSS = False  # 标志 / Flag


def _make_grid_coords(N: int, dtype: torch.dtype, device: torch.device) -> torch.Tensor:  # 生成 N×N 网格坐标 / Generate N×N grid coordinates
    lin = torch.linspace(0.0, 1.0, int(N), dtype=dtype, device=device)  # 1D 坐标 / 1D coords
    yy, xx = torch.meshgrid(lin, lin, indexing="ij")  # 网格 / Grid
    return torch.stack([xx.flatten(), yy.flatten()], dim=-1)  # (N*N, 2) / (N*N, 2)


def _density_to_distribution(density: torch.Tensor) -> torch.Tensor:  # 把密度归一化为概率分布 / Normalise density to distribution
    flat = density.flatten()  # 扁平 / Flatten
    total = flat.sum() + 1.0e-12  # 总和 / Total
    return flat / total  # 归一 / Normalise


def sinkhorn_density_loss(simulated_density: torch.Tensor, target_density: torch.Tensor, epsilon: float = 0.01, scaling: float = 0.9, p: int = 2) -> torch.Tensor:  # 在两个 2D 密度图之间算 Sinkhorn 散度 / Sinkhorn divergence between two 2D density maps
    """Compute Sinkhorn divergence between two normalised 2D densities on a square grid.
    在方形网格上的两个归一化二维密度之间计算 Sinkhorn 散度。

    Args:
        simulated_density: (N, N) 模拟撒粉密度（>0 区域）/ simulated powder density (>0 regions)
        target_density:    (N, N) 目标骨架密度（>0 区域）/ target skeleton density (>0 regions)
        epsilon: 熵正则强度（小 ε → 接近真 OT，慢；大 ε → 接近 MMD，平滑）/ entropic reg
        scaling: 多尺度 sinkhorn 缩放因子 / multi-scale scaling
        p: 距离阶（2 = W2）/ ground-distance order

    Returns:
        标量损失（散度 ≥ 0，密度相同时为 0）/ scalar divergence (≥ 0, zero when identical)
    """
    if not HAS_GEOMLOSS:  # 检查 / Check
        raise RuntimeError("geomloss not installed; run `pip install geomloss` first. / 未安装 geomloss。")  # 抛错 / Raise
    if simulated_density.shape != target_density.shape:  # 形状检查 / Shape check
        raise ValueError(f"shape mismatch: simulated {simulated_density.shape} vs target {target_density.shape}")  # 抛错 / Raise
    if simulated_density.ndim != 2 or simulated_density.shape[0] != simulated_density.shape[1]:  # 必须方阵 / Must be square
        raise ValueError(f"expected square 2D arrays, got {simulated_density.shape}")  # 抛错 / Raise
    N = int(simulated_density.shape[0])  # 边长 / Side
    dtype = simulated_density.dtype  # 精度 / Dtype
    device = simulated_density.device  # 设备 / Device
    coords = _make_grid_coords(N, dtype=dtype, device=device)  # 网格坐标 / Grid coords
    mu = _density_to_distribution(simulated_density)  # 模拟分布 / Sim distribution
    nu = _density_to_distribution(target_density.to(dtype=dtype, device=device))  # 目标分布 / Target distribution
    sinkhorn = SamplesLoss(loss="sinkhorn", p=int(p), blur=float(epsilon), scaling=float(scaling), backend="tensorized")  # 配置 / Config
    return sinkhorn(mu, coords, nu, coords)  # 计算 / Compute


def sinkhorn_powder_target_loss(simulated_amplitude: torch.Tensor, target_binary: torch.Tensor, sigma_rel: float = 0.05, top_k_frac: float = 0.02, epsilon: float = 0.01, scaling: float = 0.9) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:  # 高斯撒粉 vs 目标骨架的 Sinkhorn / Sinkhorn between Gaussian powder and target skeleton
    """Compute Sinkhorn divergence between predicted powder density and target skeleton.
    在预测撒粉密度和目标骨架之间算 Sinkhorn 散度。

    powder = exp(-(|u|/(σ·peak))²)  (从 src.physics.recognisability_loss 中的模型)
    target = target_binary cast to float
    """
    from src.physics.recognisability_loss import chladni_powder_torch  # 延迟导入 / Lazy
    powder = chladni_powder_torch(simulated_amplitude, sigma_rel=float(sigma_rel), top_k_frac=float(top_k_frac))  # 撒粉密度 / Powder
    target = target_binary.to(dtype=powder.dtype)  # 目标 / Target
    loss = sinkhorn_density_loss(powder, target, epsilon=float(epsilon), scaling=float(scaling), p=2)  # Sinkhorn / Sinkhorn
    return loss, {"powder": powder, "target": target, "sinkhorn": loss}  # 返回 / Return


def sinkhorn_to_irrep_projection(simulated_amplitude: torch.Tensor, target_binary: torch.Tensor, irreps: tuple[str, ...] = ("A1",), sigma_rel: float = 0.05, epsilon: float = 0.01) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:  # 把 target 投到指定 irrep 后做 Sinkhorn / Sinkhorn after projecting target to chosen irrep
    """First project the target onto the union of accessible irreps (centre excitation → A1),
    then compute Sinkhorn between powder and that projection. This avoids "wasting gradient"
    on irrep components the physics cannot reach.

    先把目标投影到可达 irrep 的并集（中心激振 → A1），再算 powder 到该投影的 Sinkhorn。
    避免把梯度浪费在物理不可达的 irrep 分量上。
    """
    from src.physics.recognisability_loss import chladni_powder_torch  # 延迟导入 / Lazy
    from src.symmetry.d4_decomposition import project_to_irrep  # 延迟导入 / Lazy
    import numpy as np  # numpy / numpy
    target_np = target_binary.detach().cpu().numpy().astype(np.float64)  # numpy 副本 / Numpy copy
    projection = np.zeros_like(target_np)  # 累加 / Accumulator
    for irrep in irreps:  # 遍历可达 irrep / Iterate accessible irreps
        projection = projection + project_to_irrep(target_np, irrep)  # 累加投影 / Accumulate projection
    projection = np.clip(projection, 0.0, None)  # 非负化（target 是非负的） / Non-negative
    target_proj = torch.as_tensor(projection, dtype=simulated_amplitude.dtype, device=simulated_amplitude.device)  # 转 tensor / To tensor
    powder = chladni_powder_torch(simulated_amplitude, sigma_rel=float(sigma_rel))  # 撒粉密度 / Powder
    loss = sinkhorn_density_loss(powder, target_proj, epsilon=float(epsilon))  # Sinkhorn / Sinkhorn
    return loss, {"powder": powder, "target_irrep_projection": target_proj, "sinkhorn": loss}  # 返回 / Return
