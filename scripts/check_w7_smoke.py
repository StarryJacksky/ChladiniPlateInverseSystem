from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

import math  # 数学函数 / Math
import numpy as np  # 数值库 / NumPy
import torch  # 张量库 / Torch

from src.config import load_config  # 配置加载 / Config loader
from src.physics.differentiable_plate import DifferentiablePlate  # 可微板 / Plate
from src.physics.multifreq_amp_valley import compose_multifreq_amplitude  # 多频合成 / Composition
from src.physics.multifreq_amp_valley import frequencies_from_logits  # 频率重参 / Frequency reparam
from src.physics.multifreq_amp_valley import initialise_freq_logits  # 频率初值 / Init
from src.physics.multifreq_amp_valley import initialise_weight_logits  # 权重初值 / Init
from src.physics.multifreq_amp_valley import multifreq_amplitude_valley_loss  # 多频损失 / Loss
from src.physics.multifreq_amp_valley import weights_from_logits  # 权重重参 / Weight reparam
from src.physics.plate_loss_adapter import build_target_bundle  # 目标包 / Bundle
from src.physics.plate_loss_adapter import bundle_to_torch  # 张量化 / Tensorise
from src.physics.plate_loss_adapter import load_target_binary  # 目标加载 / Target loader


def check_gradients_finite(config: dict) -> None:  # 检查多频联合梯度有限 / Check joint gradients are finite
    dtype = torch.float64  # 精度 / Precision
    device = torch.device("cpu")  # CPU / CPU
    K = 4  # 频率数 / K
    plate = DifferentiablePlate(config, proxy_grid_size=21, dtype=dtype, device=device)  # 板 / Plate
    target = load_target_binary(config, None)  # 目标 / Target
    bundle = build_target_bundle(target, plate.N, float(config["project"]["center_clamp_radius_mm"]), float(config["project"]["plate_length_mm"]))  # 目标包 / Bundle
    bt = bundle_to_torch(bundle, device, dtype)  # 张量化 / Tensorise
    H = torch.full((int(config["project"]["grid_size"]),) * 2, 1.5, dtype=dtype, device=device, requires_grad=True)  # H 初值 / H init
    freq_logits = initialise_freq_logits(K, 150.0, 1000.0, dtype=dtype, device=device).requires_grad_(True)  # 频率 / Freqs
    weight_logits = initialise_weight_logits(K, dtype=dtype, device=device).requires_grad_(True)  # 权重 / Weights
    H_proxy = plate.upsample(H)  # 升采样 / Upsample
    K_full, M_diag = plate.assemble_K_M(H_proxy)  # 装配 / Assemble
    free = plate.free_indices  # 自由度 / Free
    K_free = K_full.index_select(0, free).index_select(1, free)  # 自由 K / Free K
    M_free = torch.clamp(M_diag.index_select(0, free), min=1.0e-18)  # 自由 M / Free M
    freqs_hz = frequencies_from_logits(freq_logits, 150.0, 1000.0)  # 频率 / Freqs
    weights = weights_from_logits(weight_logits)  # 权重 / Weights
    responses = [plate.expand_to_grid(plate.direct_forced_response(K_free, M_free, 2.0 * math.pi * freqs_hz[k], 0.02)) for k in range(K)]  # K 次求解 / K solves
    loss, _, parts = multifreq_amplitude_valley_loss(responses, weights, bt, epsilon=0.060)  # 损失 / Loss
    loss.backward()  # 反传 / Backprop
    grads_H = H.grad  # H 梯度 / H grad
    grads_freq = freq_logits.grad  # 频率梯度 / Freq grad
    grads_w = weight_logits.grad  # 权重梯度 / Weight grad
    assert grads_H is not None and torch.isfinite(grads_H).all(), "H gradient not finite. / H 梯度含非有限值。"  # 断言 / Assert
    assert grads_freq is not None and torch.isfinite(grads_freq).all(), "Freq gradient not finite. / 频率梯度含非有限值。"  # 断言 / Assert
    assert grads_w is not None and torch.isfinite(grads_w).all(), "Weight gradient not finite. / 权重梯度含非有限值。"  # 断言 / Assert
    print(f"[ok] gradients finite | loss={float(loss):.4f}  ||grad_H||={float(grads_H.norm()):.3e}  ||grad_freq||={float(grads_freq.norm()):.3e}  ||grad_w||={float(grads_w.norm()):.3e}")  # 打印 / Print


def check_loss_decreases(config: dict) -> None:  # 用 Adam 跑 12 步验证 loss 下降 / Run 12 Adam steps to verify decrease
    dtype = torch.float64  # 精度 / Precision
    device = torch.device("cpu")  # CPU / CPU
    K = 4  # K / K
    plate = DifferentiablePlate(config, proxy_grid_size=21, dtype=dtype, device=device)  # 板 / Plate
    target = load_target_binary(config, None)  # 目标 / Target
    bundle = build_target_bundle(target, plate.N, float(config["project"]["center_clamp_radius_mm"]), float(config["project"]["plate_length_mm"]))  # 目标包 / Bundle
    bt = bundle_to_torch(bundle, device, dtype)  # 张量化 / Tensorise
    H = torch.full((int(config["project"]["grid_size"]),) * 2, 1.5, dtype=dtype, device=device, requires_grad=True)  # H / H
    freq_logits = initialise_freq_logits(K, 200.0, 900.0, dtype=dtype, device=device).requires_grad_(True)  # 频率 / Freqs
    weight_logits = initialise_weight_logits(K, dtype=dtype, device=device).requires_grad_(True)  # 权重 / Weights
    opt = torch.optim.Adam([{"params": [H], "lr": 0.05}, {"params": [freq_logits], "lr": 0.10}, {"params": [weight_logits], "lr": 0.10}])  # Adam / Adam
    losses: list[float] = []  # 记录 / Record
    for step in range(12):  # 12 步 / 12 steps
        opt.zero_grad()  # 清零 / Zero
        H_proxy = plate.upsample(H)  # 升采样 / Upsample
        K_full, M_diag = plate.assemble_K_M(H_proxy)  # 装配 / Assemble
        free = plate.free_indices  # 自由 / Free
        K_free = K_full.index_select(0, free).index_select(1, free)  # 自由 K / Free K
        M_free = torch.clamp(M_diag.index_select(0, free), min=1.0e-18)  # 自由 M / Free M
        freqs_hz = frequencies_from_logits(freq_logits, 200.0, 900.0)  # 频率 / Freqs
        weights = weights_from_logits(weight_logits)  # 权重 / Weights
        responses = [plate.expand_to_grid(plate.direct_forced_response(K_free, M_free, 2.0 * math.pi * freqs_hz[k], 0.02)) for k in range(K)]  # 响应 / Responses
        loss, _, _ = multifreq_amplitude_valley_loss(responses, weights, bt, epsilon=0.060)  # 损失 / Loss
        loss.backward()  # 反传 / Backprop
        opt.step()  # 更新 / Step
        losses.append(float(loss.item()))  # 记录 / Record
    best = min(losses)  # 最小 / Min
    first = losses[0]  # 首步 / First
    assert best < first - 1.0e-3, f"Loss did not decrease meaningfully: first={first:.4f}, best={best:.4f}. / 损失下降不显著。"  # 断言 / Assert
    print(f"[ok] loss decreases | first={first:.4f}  best={best:.4f}  last={losses[-1]:.4f}")  # 打印 / Print


def main() -> int:  # 主入口 / Main entry
    config = load_config("config.yaml")  # 配置 / Config
    print("=== W7 smoke ===")  # 头 / Header
    check_gradients_finite(config)  # 梯度 / Gradients
    check_loss_decreases(config)  # 下降 / Decrease
    print("OK")  # 结束 / Done
    return 0  # 返回 / Return


if __name__ == "__main__":  # 直接运行 / Direct run
    raise SystemExit(main())  # 退出 / Exit
