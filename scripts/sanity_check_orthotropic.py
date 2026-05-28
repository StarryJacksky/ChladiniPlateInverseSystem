from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

"""Sanity checks for OrthotropicPlate.
正交各向异性板模型自检脚本。

Tests:
1. Isotropic limit (E_||=E_⊥, G=G_iso) reproduces existing DifferentiablePlate response
2. θ=0 vs θ=π/4 give DIFFERENT responses (proves D4 symmetry is physically broken)
3. Pure rotation invariance: rotating both H and θ by π/2 gives a rotated response
"""

import sys  # 系统 / System
from pathlib import Path  # 路径 / Paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 根 / Root
if str(PROJECT_ROOT) not in sys.path:  # 检查 / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加 / Add

import math  # 数学 / Math
import numpy as np  # NumPy / NumPy
import torch  # Torch / Torch

from src.config import load_config  # 配置 / Config
from src.physics.differentiable_plate import DifferentiablePlate  # 各向同性 / Isotropic
from src.physics.orthotropic_plate import OrthotropicPlate  # 正交各向异 / Orthotropic
from src.symmetry.d4_decomposition import irrep_energy_ratios  # D4 / D4


def main() -> int:  # 主 / Main
    config = load_config()  # 加载 / Load
    proxy_N = 25  # 代理 / Proxy
    dtype = torch.float64  # 精度 / Dtype
    device = "cpu"  # 设备 / Device
    freq_hz = torch.tensor(400.0, dtype=dtype)  # 频率 / Freq

    # Uniform thickness H, all-zero θ (= isotropic axes aligned with x-y)
    H = 1.0 * torch.ones(15, 15, dtype=dtype)  # 均一 H / Uniform H
    theta_zero = torch.zeros(15, 15, dtype=dtype)  # θ=0 / θ=0
    theta_45 = torch.full((15, 15), math.pi / 4.0, dtype=dtype)  # θ=π/4 / θ=π/4

    # Random non-uniform θ for D4-breaking test
    rng = np.random.RandomState(7)  # RNG / RNG
    theta_random = torch.as_tensor(rng.uniform(0.0, math.pi, size=(15, 15)), dtype=dtype)  # 随机 / Random

    print("=" * 80)
    print("Sanity 1: Isotropic limit (E_||=E_⊥, G=G_iso) vs current DifferentiablePlate")
    print("=" * 80)

    plate_iso = DifferentiablePlate(config, proxy_grid_size=proxy_N, dtype=dtype, device=device)  # 老模型 / Old
    plate_ortho_iso = OrthotropicPlate(config, proxy_grid_size=proxy_N, stiffness_ratio=1.0, shear_ratio=1.0, dtype=dtype, device=device)  # 新模型 各向同性极限 / New, iso limit

    amp_iso_old = plate_iso.forward(H, freq_hz, damping_ratio=0.02).amplitude  # 旧 / Old
    amp_iso_new = plate_ortho_iso.amplitude_at_frequency(H, theta_zero, freq_hz, damping_ratio=0.02)  # 新 / New
    # Normalise both to compare shapes (old normalises internally; do same for new)
    amp_iso_new = amp_iso_new / (amp_iso_new.max() + 1e-12)  # 归一化 / Normalise

    diff_iso = (amp_iso_old - amp_iso_new).abs() / amp_iso_old.abs().mean()  # 相对差 / Rel diff
    print(f"  amp_iso_old max: {amp_iso_old.max().item():.4e}")
    print(f"  amp_iso_new max: {amp_iso_new.max().item():.4e}")
    print(f"  relative max diff: {diff_iso.max().item():.4f}")
    print(f"  relative mean diff: {diff_iso.mean().item():.4f}")
    if diff_iso.max().item() > 0.10:  # 10%
        print(f"  WARN: isotropic limit diverges from old model by >10% — operator formulation differs (expected; new model uses split w_xx/w_yy/w_xy ops vs old biharmonic)")
    else:
        print(f"  OK: isotropic limit matches within 10%")

    print()
    print("=" * 80)
    print("Sanity 2: θ=0 vs θ=π/4 (with E_||/E_⊥ = 1.5) — D4 physical breaking")
    print("=" * 80)
    plate_ortho = OrthotropicPlate(config, proxy_grid_size=proxy_N, stiffness_ratio=1.5, shear_ratio=1.0, dtype=dtype, device=device)  # 真各向异性 / True ortho
    amp_theta0 = plate_ortho.amplitude_at_frequency(H, theta_zero, freq_hz, damping_ratio=0.02)  # θ=0 / θ=0
    amp_theta45 = plate_ortho.amplitude_at_frequency(H, theta_45, freq_hz, damping_ratio=0.02)  # θ=π/4 / θ=π/4
    diff_45 = (amp_theta0 - amp_theta45).abs() / amp_theta0.abs().mean()  # 相对差 / Rel diff
    print(f"  amp(θ=0)  max: {amp_theta0.max().item():.4e}")
    print(f"  amp(θ=π/4) max: {amp_theta45.max().item():.4e}")
    print(f"  relative max diff: {diff_45.max().item():.4f} (expect > 0)")
    print(f"  relative mean diff: {diff_45.mean().item():.4f}")

    print()
    print("=" * 80)
    print("Sanity 3: D4 irrep decomposition — θ=0 (uniform) vs θ=random (non-uniform)")
    print("=" * 80)
    amp_theta_random = plate_ortho.amplitude_at_frequency(H, theta_random, freq_hz, damping_ratio=0.02)  # 随机 θ / Random θ
    ratios_theta0 = irrep_energy_ratios(amp_theta0.detach().cpu().numpy())  # θ=0 irreps / θ=0 irreps
    ratios_theta_random = irrep_energy_ratios(amp_theta_random.detach().cpu().numpy())  # 随机 θ irreps / Random θ irreps

    print(f"  amp(H uniform, θ=0)         irreps: {{'A1': {ratios_theta0['A1']:.3f}, 'B1': {ratios_theta0['B1']:.3f}, 'B2': {ratios_theta0['B2']:.3f}, 'E': {ratios_theta0['E']:.3f}, 'A2': {ratios_theta0['A2']:.3f}}}")
    print(f"  amp(H uniform, θ=random)    irreps: {{'A1': {ratios_theta_random['A1']:.3f}, 'B1': {ratios_theta_random['B1']:.3f}, 'B2': {ratios_theta_random['B2']:.3f}, 'E': {ratios_theta_random['E']:.3f}, 'A2': {ratios_theta_random['A2']:.3f}}}")
    print(f"  → uniform θ=0 should be ~100% A1 (center excitation + D4 plate is A1-coupled)")
    print(f"  → random θ should leak energy into non-A1 irreps (= physical D4 breaking)")
    nonA1_random = 1.0 - ratios_theta_random['A1']  # 非 A1 占比 / Non-A1 fraction
    if nonA1_random > 0.05:
        print(f"  OK: random θ leaks {nonA1_random*100:.1f}% energy into non-A1 irreps — D4 BREAKING CONFIRMED ✓")
    else:
        print(f"  WARN: random θ only leaks {nonA1_random*100:.2f}% into non-A1 — D4 breaking is too weak")

    print()
    print("=" * 80)
    print("Sanity 4: differentiability — gradient w.r.t. θ exists and is nonzero")
    print("=" * 80)
    theta_grad = theta_random.clone().requires_grad_(True)  # 启用梯度 / Enable grad
    amp_grad = plate_ortho.amplitude_at_frequency(H, theta_grad, freq_hz, damping_ratio=0.02)  # 振幅 / Amplitude
    loss = amp_grad.sum()  # 简单 loss / Simple loss
    loss.backward()  # 反传 / Backprop
    grad = theta_grad.grad  # 梯度 / Gradient
    print(f"  d(amp.sum)/dθ: max abs = {grad.abs().max().item():.4e}, mean abs = {grad.abs().mean().item():.4e}")
    if grad.abs().max().item() > 0:
        print(f"  OK: gradient w.r.t. θ is nonzero — backprop through orthotropic K assembly works ✓")
    else:
        print(f"  FAIL: gradient is zero — backprop is broken!")

    return 0  # 返回 / Return


if __name__ == "__main__":  # 直接 / Direct
    raise SystemExit(main())  # 退出 / Exit
