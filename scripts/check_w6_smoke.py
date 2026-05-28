from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析 / Import argument parsing
import math  # 导入数学函数 / Import math helpers
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

import numpy as np  # 导入数值库 / Import numerical library
import torch  # 导入张量库 / Import tensor library

from src.config import load_config  # 复用配置加载 / Reuse config loader
from src.physics.differentiable_plate import DifferentiablePlate  # 引入板模型 / Import plate model
from src.physics.modal_spectrum import compute_modal_spectrum  # 引入频谱入口 / Import spectrum entry
from src.physics.modal_spectrum import differentiable_eigenvalues  # 引入可微本征值 / Import diff eigvals
from src.physics.modal_spectrum import spectral_cluster_loss  # 引入聚簇损失 / Import cluster loss
from src.physics.plate_loss_adapter import build_target_bundle  # 复用目标包 / Reuse target bundle
from src.physics.plate_loss_adapter import bundle_to_torch  # 复用张量化 / Reuse tensorise
from src.physics.plate_loss_adapter import load_target_binary  # 复用目标加载 / Reuse target loader


def check_eigvals_finite_gradient(config_path: Path) -> bool:  # 检验可微本征值梯度有限 / Check finite gradient through eigvalsh
    config = load_config(config_path)  # 读取配置 / Load config
    dtype = torch.float64  # 精度 / Precision
    device = torch.device("cpu")  # 设备 / Device
    plate = DifferentiablePlate(config, proxy_grid_size=21, dtype=dtype, device=device)  # 板模型 / Plate model
    grid_size = int(config["project"]["grid_size"])  # 设计网格 / Design grid
    H_design = torch.full((grid_size, grid_size), 1.5, dtype=dtype, device=device, requires_grad=True)  # 设计厚度 / Design thickness
    H_proxy = plate.upsample(H_design)  # 升采样 / Upsample
    K, M = plate.assemble_K_M(H_proxy)  # K M / K M
    free = plate.free_indices  # 自由度 / Free DOF
    K_free = K.index_select(0, free).index_select(1, free)  # 自由 K / Free K
    M_free = torch.clamp(M.index_select(0, free), min=1.0e-18)  # 自由 M / Free M
    eigvals = differentiable_eigenvalues(K_free, M_free, num_modes=8)  # 可微本征值 / Diff eigvals
    omega_squared = torch.tensor((2.0 * math.pi * 600.0) ** 2, dtype=dtype, device=device)  # ω² / ω²
    loss = (eigvals - omega_squared).pow(2).mean()  # 平均偏差 / Mean residual
    loss.backward()  # 反传 / Backprop
    grad = H_design.grad.detach().cpu().numpy()  # 取梯度 / Take grad
    finite = bool(np.all(np.isfinite(grad)))  # 有限性 / Finite
    norm = float(np.linalg.norm(grad))  # 范数 / Norm
    nonzero = norm > 0.0  # 非零 / Non-zero
    ok = finite and nonzero  # 综合 / Combined
    print(f"eigvalsh-gradient finite={finite}, norm={norm:.4e}, nonzero={nonzero} (ok={ok}) / eigvalsh 梯度有限={finite}，范数 {norm:.4e}，非零={nonzero}（合格={ok}）")  # 输出 / Print
    return ok  # 返回 / Return


def check_cluster_loss_decreases(config_path: Path) -> bool:  # 检验聚簇损失下降 / Check cluster loss decreases
    config = load_config(config_path)  # 配置 / Config
    target = load_target_binary(config, None)  # 目标 / Target
    dtype = torch.float64  # 精度 / Precision
    device = torch.device("cpu")  # 设备 / Device
    plate = DifferentiablePlate(config, proxy_grid_size=21, dtype=dtype, device=device)  # 板模型 / Plate model
    bundle = build_target_bundle(target, plate.N, float(config["project"]["center_clamp_radius_mm"]), float(config["project"]["plate_length_mm"]))  # 目标包 / Bundle
    tensors = bundle_to_torch(bundle, device, dtype)  # 张量化 / Tensorise
    grid_size = int(config["project"]["grid_size"])  # 网格 / Grid
    H_min = float(config["thickness"]["min_mm"])  # 厚度下限 / H min
    H_max = float(config["thickness"]["max_mm"])  # 厚度上限 / H max
    H_design = torch.full((grid_size, grid_size), (H_min + H_max) / 2.0, dtype=dtype, device=device, requires_grad=True)  # 厚度初值 / Initial H
    optim = torch.optim.Adam([H_design], lr=0.05)  # Adam / Adam
    omega_squared = torch.tensor((2.0 * math.pi * 600.0) ** 2, dtype=dtype, device=device)  # ω² / ω²
    losses: list[float] = []  # 损失序列 / Loss sequence
    for step in range(20):  # 20 步 / 20 steps
        optim.zero_grad()  # 清零 / Zero
        H_clamped = torch.clamp(H_design, min=H_min, max=H_max)  # 可微 clamp / Clamp
        H_proxy = plate.upsample(H_clamped)  # 升采样 / Upsample
        K, M = plate.assemble_K_M(H_proxy)  # K M / K M
        free = plate.free_indices  # 自由度 / Free
        K_free = K.index_select(0, free).index_select(1, free)  # 自由 K / Free K
        M_free = torch.clamp(M.index_select(0, free), min=1.0e-18)  # 自由 M / Free M
        spectrum = compute_modal_spectrum(K_free, M_free, free, plate.N, num_modes=8, bundle_tensors=tensors, epsilon=0.06)  # 频谱 / Spectrum
        loss = spectral_cluster_loss(spectrum.eigenvalues, spectrum.target_alignment_weights, omega_squared, normalise_by_omega_sq=True)  # 聚簇损失 / Cluster loss
        loss.backward()  # 反传 / Backprop
        optim.step()  # 更新 / Update
        losses.append(float(loss.item()))  # 记录 / Record
    ok = min(losses) < losses[0] - 1.0e-3 and bool(np.all(np.isfinite(losses)))  # 单调有限 / Monotone finite
    print(f"cluster-loss sequence (20 steps): first={losses[0]:.4f}, min={min(losses):.4f}, last={losses[-1]:.4f}, finite={bool(np.all(np.isfinite(losses)))} (ok={ok}) / 聚簇损失序列：首步 {losses[0]:.4f}，最低 {min(losses):.4f}，末 {losses[-1]:.4f}，有限={bool(np.all(np.isfinite(losses)))}（合格={ok}）")  # 输出 / Print
    return ok  # 返回 / Return


def check_alignment_weights_normalised(config_path: Path) -> bool:  # 检验契合权重为概率分布 / Check alignment weights form a probability distribution
    config = load_config(config_path)  # 配置 / Config
    target = load_target_binary(config, None)  # 目标 / Target
    dtype = torch.float64  # 精度 / Precision
    device = torch.device("cpu")  # 设备 / Device
    plate = DifferentiablePlate(config, proxy_grid_size=21, dtype=dtype, device=device)  # 板 / Plate
    bundle = build_target_bundle(target, plate.N, float(config["project"]["center_clamp_radius_mm"]), float(config["project"]["plate_length_mm"]))  # 包 / Bundle
    tensors = bundle_to_torch(bundle, device, dtype)  # 张量化 / Tensorise
    grid_size = int(config["project"]["grid_size"])  # 网格 / Grid
    H_design = torch.full((grid_size, grid_size), 1.5, dtype=dtype, device=device)  # 厚度 / H
    H_proxy = plate.upsample(H_design)  # 升采样 / Upsample
    K, M = plate.assemble_K_M(H_proxy)  # K M / K M
    free = plate.free_indices  # 自由度 / Free
    K_free = K.index_select(0, free).index_select(1, free)  # 自由 K / Free K
    M_free = torch.clamp(M.index_select(0, free), min=1.0e-18)  # 自由 M / Free M
    spectrum = compute_modal_spectrum(K_free, M_free, free, plate.N, num_modes=12, bundle_tensors=tensors, epsilon=0.06)  # 频谱 / Spectrum
    weights = spectrum.target_alignment_weights.detach().cpu().numpy()  # 权重 / Weights
    sum_close_to_1 = abs(float(weights.sum()) - 1.0) < 1.0e-6  # 总和 ≈ 1 / Sums to 1
    non_negative = bool(np.all(weights >= 0.0))  # 非负 / Non-negative
    has_signal = float(weights.max()) > 0.05  # 信号显著 / Has signal
    ok = sum_close_to_1 and non_negative and has_signal  # 综合 / Combined
    print(f"alignment weights: sum={float(weights.sum()):.6f}, max={float(weights.max()):.4f}, min={float(weights.min()):.4f}, non_neg={non_negative} (ok={ok}) / 契合权重：和 {float(weights.sum()):.6f}，max {float(weights.max()):.4f}，min {float(weights.min()):.4f}，非负={non_negative}（合格={ok}）")  # 输出 / Print
    return ok  # 返回 / Return


def main(argv: list[str] | None = None) -> int:  # 主入口 / Main entry
    parser = argparse.ArgumentParser(description="W6 spectral-placement smoke tests. / W6 频谱聚簇烟雾测试。")  # 解析器 / Parser
    parser.add_argument("--config", type=str, default="config.yaml")  # 配置 / Config
    args = parser.parse_args(argv)  # 解析 / Parse
    results = [check_eigvals_finite_gradient(Path(args.config)), check_alignment_weights_normalised(Path(args.config)), check_cluster_loss_decreases(Path(args.config))]  # 三项检测 / Three checks
    ok = all(results)  # 综合 / Combined
    print(f"smoke result: {'PASS' if ok else 'FAIL'} / 烟雾测试结果：{'通过' if ok else '失败'}")  # 综合 / Overall
    return 0 if ok else 1  # 返回码 / Exit code


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出 / Exit
