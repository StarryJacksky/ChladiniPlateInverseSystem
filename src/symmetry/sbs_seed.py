from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

"""Symmetry-breaking seed (SBS) for D4-equivariant optimisers.
对 D4 等变优化器的对称破坏种子。

理论依据 / Theoretical basis:
- Xie & Smidt 2024 (arXiv 2402.02681, "Equivariant Symmetry Breaking Sets")
- Kaba & Ravanbakhsh 2023 (arXiv 2312.09016, "Symmetry Breaking and Equivariant Neural Networks")

核心结论：D4-等变映射作用在 D4-对称输入上必然输出 D4-对称结果。
若想让优化器找到非 D4 解，必须注入一个固定的（非可学）"对称破坏种子" H_seed，
让 H_total = H_seed + δH，只对 δH 做优化。

For square-plate inverse design, this lets gradient descent escape D4 fixed points
that would otherwise trap the optimisation when targets contain B/E irrep components.

Usage / 用法：
    seed = load_sbs_seed("data/sbs_seed.npy", grid_size=15)
    H_total = apply_sbs_seed(H_optimised, seed)
"""

from pathlib import Path  # 路径 / Paths

import numpy as np  # NumPy / NumPy

try:  # 尝试导入 torch / Try import torch
    import torch  # Torch / Torch
    HAS_TORCH = True  # 标志 / Flag
except ImportError:  # 没安装 / Not installed
    HAS_TORCH = False  # 标志 / Flag


def generate_sbs_seed(grid_size: int, amplitude_mm: float = 0.03, seed: int = 42, center_cells: list[tuple[int, int]] | None = None) -> np.ndarray:  # 生成固定 SBS 种子 / Generate fixed SBS seed
    """生成一个固定（基于种子）、低幅度、非 D4 对称的厚度扰动。
    Generate a fixed (seeded), low-amplitude, non-D4-symmetric thickness perturbation.

    Args:
        grid_size: 网格尺寸 / grid size (typically 15)
        amplitude_mm: 扰动幅值（mm），应远小于约束 max_neighbour_diff (1.0 mm) / amplitude in mm
        seed: 随机种子保证可复现 / RNG seed for reproducibility
        center_cells: 中心夹固单元，这些位置 seed 强制为 0 / centre clamp cells (forced to 0)

    Returns:
        (grid_size, grid_size) numpy array of float64
    """
    rng = np.random.RandomState(int(seed))  # 固定 RNG / Fixed RNG
    raw = rng.standard_normal(size=(int(grid_size), int(grid_size)))  # 高斯噪声 / Gaussian noise
    std = float(raw.std())  # 标准差 / Std
    if std > 1.0e-9:  # 防零除 / Guard div-by-zero
        raw = raw / std  # 归一化 / Normalise
    seed_array = float(amplitude_mm) * raw  # 缩放到目标幅值 / Scale to amplitude
    if center_cells is not None:  # 中心夹固清零 / Centre clamp zero-out
        for row, col in center_cells:  # 遍历 / Iterate
            seed_array[int(row), int(col)] = 0.0  # 清零 / Zero
    return seed_array.astype(np.float64)  # 返回 / Return


def save_sbs_seed(seed_array: np.ndarray, path: str | Path) -> Path:  # 保存 / Save
    out = Path(path)  # 路径 / Path
    out.parent.mkdir(parents=True, exist_ok=True)  # 建目录 / Mkdir
    np.save(out, np.asarray(seed_array, dtype=np.float64))  # 保存 / Save
    return out  # 返回 / Return


def load_sbs_seed(path: str | Path, grid_size: int | None = None) -> np.ndarray:  # 加载 / Load
    p = Path(path)  # 路径 / Path
    if not p.exists():  # 不存在 / Missing
        raise FileNotFoundError(f"SBS seed not found: {p}. Use generate_sbs_seed() first. / 未找到 SBS 种子。")  # 抛错 / Raise
    arr = np.load(p).astype(np.float64)  # 加载 / Load
    if grid_size is not None and arr.shape != (int(grid_size), int(grid_size)):  # 形状检查 / Shape check
        raise ValueError(f"SBS seed shape {arr.shape} mismatch expected ({grid_size}, {grid_size}). / SBS 种子形状不匹配。")  # 抛错 / Raise
    return arr  # 返回 / Return


def apply_sbs_seed_numpy(H: np.ndarray, seed: np.ndarray, h_min_mm: float | None = None, h_max_mm: float | None = None) -> np.ndarray:  # NumPy 版本应用 / NumPy version
    out = H.astype(np.float64) + seed.astype(np.float64)  # 加种子 / Add seed
    if h_min_mm is not None and h_max_mm is not None:  # clamp / Clamp
        out = np.clip(out, float(h_min_mm), float(h_max_mm))  # clamp / Clamp
    return out  # 返回 / Return


def apply_sbs_seed_torch(H: "torch.Tensor", seed: np.ndarray | "torch.Tensor", h_min_mm: float | None = None, h_max_mm: float | None = None) -> "torch.Tensor":  # Torch 版本应用 / Torch version
    if not HAS_TORCH:  # 检查 / Check
        raise RuntimeError("torch not available; install PyTorch to use apply_sbs_seed_torch. / 未安装 torch。")  # 抛错 / Raise
    if isinstance(seed, np.ndarray):  # numpy → tensor / Convert
        seed_t = torch.as_tensor(seed, dtype=H.dtype, device=H.device)  # 转 tensor / To tensor
    else:  # 已是 tensor / Already tensor
        seed_t = seed.to(dtype=H.dtype, device=H.device)  # 对齐 / Align
    out = H + seed_t  # 加种子（保留梯度） / Add (preserve gradient)
    if h_min_mm is not None and h_max_mm is not None:  # clamp / Clamp
        out = torch.clamp(out, min=float(h_min_mm), max=float(h_max_mm))  # clamp / Clamp
    return out  # 返回 / Return


def measure_seed_d4_symmetry(seed: np.ndarray) -> dict[str, float]:  # 验证种子的"非 D4"程度 / Verify non-D4 quality
    from src.symmetry.d4_decomposition import irrep_energy_ratios  # 延迟导入 / Lazy
    ratios = irrep_energy_ratios(seed)  # 占比 / Ratios
    a1_fraction = float(ratios.get("A1", 0.0))  # A1 占比 / A1 fraction
    non_a1_fraction = float(1.0 - a1_fraction)  # 非 A1 / Non-A1
    return {"a1_fraction": a1_fraction, "non_a1_fraction": non_a1_fraction, "amplitude_max_mm": float(np.abs(seed).max()), "amplitude_rms_mm": float(np.sqrt((seed ** 2).mean())), "irrep_ratios": {k: float(v) for k, v in ratios.items()}}  # 返回 / Return
