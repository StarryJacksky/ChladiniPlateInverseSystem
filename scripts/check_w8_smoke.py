from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import sys  # 系统 / System
from pathlib import Path  # 路径 / Paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 项目根 / Project root
if str(PROJECT_ROOT) not in sys.path:  # 检查 / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加 / Add

import math  # 数学 / Math
import numpy as np  # NumPy / NumPy
import torch  # Torch / Torch

from src.config import load_config  # 配置 / Config
from src.physics.differentiable_plate import DifferentiablePlate  # 板 / Plate
from src.physics.multifreq_amp_valley import frequencies_from_logits  # 频率重参 / Reparam
from src.physics.multifreq_amp_valley import initialise_freq_logits  # 初值 / Init
from src.physics.multifreq_amp_valley import initialise_weight_logits  # 权重初值 / Init
from src.physics.multifreq_amp_valley import weights_from_logits  # 权重重参 / Reparam
from src.physics.plate_loss_adapter import load_target_binary  # 目标 / Target
from src.physics.recognisability_loss import RecognisabilityLossWeights  # 权重 / Weights
from src.physics.recognisability_loss import combined_recognisability_loss  # 损失 / Loss
from src.physics.recognisability_loss import compose_multifreq_amplitude_with_weights  # 合成 / Compose
from src.scoring.geometry_helpers import resize_binary_nearest  # 缩放 / Resize


def check_gradients_finite(config: dict) -> None:  # 梯度有限 / Gradients finite
    dtype = torch.float64  # 精度 / Precision
    device = torch.device("cpu")  # CPU / CPU
    K = 4  # K / K
    plate = DifferentiablePlate(config, proxy_grid_size=21, dtype=dtype, device=device)  # 板 / Plate
    target = load_target_binary(config, None)  # 目标 / Target
    tp = torch.as_tensor(resize_binary_nearest(target, plate.N).astype(np.float64), dtype=dtype, device=device)  # 代理目标 / Proxy
    H = torch.full((int(config["project"]["grid_size"]),) * 2, 1.5, dtype=dtype, device=device, requires_grad=True)  # H / H
    fl = initialise_freq_logits(K, 150.0, 1000.0, dtype=dtype, device=device).requires_grad_(True)  # 频率 / Freqs
    wl = initialise_weight_logits(K, dtype=dtype, device=device).requires_grad_(True)  # 权重 / Weights
    H_proxy = plate.upsample(H)  # 升采样 / Upsample
    K_full, M_diag = plate.assemble_K_M(H_proxy)  # 装配 / Assemble
    free = plate.free_indices  # 自由 / Free
    K_free = K_full.index_select(0, free).index_select(1, free)  # 自由 K / Free K
    M_free = torch.clamp(M_diag.index_select(0, free), min=1.0e-18)  # 自由 M / Free M
    freqs_hz = frequencies_from_logits(fl, 150.0, 1000.0)  # 频率 / Freqs
    weights = weights_from_logits(wl)  # 权重 / Weights
    responses = [plate.expand_to_grid(plate.direct_forced_response(K_free, M_free, 2.0 * math.pi * freqs_hz[k], 0.02)) for k in range(K)]  # 响应 / Responses
    composite = compose_multifreq_amplitude_with_weights(responses, weights)  # 合成 / Compose
    composite_c = composite.to(dtype=torch.complex128) + 0.0j  # 复数 / Complex
    loss, parts = combined_recognisability_loss(composite_c, tp, weights=RecognisabilityLossWeights())  # 损失 / Loss
    loss.backward()  # 反传 / Backprop
    gH = H.grad  # H 梯度 / H grad
    gf = fl.grad  # 频率梯度 / Freq grad
    gw = wl.grad  # 权重梯度 / Weight grad
    assert gH is not None and torch.isfinite(gH).all(), "H grad not finite. / H 梯度非有限。"  # 断言 / Assert
    assert gf is not None and torch.isfinite(gf).all(), "Freq grad not finite. / 频率梯度非有限。"  # 断言 / Assert
    assert gw is not None and torch.isfinite(gw).all(), "Weight grad not finite. / 权重梯度非有限。"  # 断言 / Assert
    enr = float(parts["enrichment"].detach())  # 富集 / Enr
    print(f"[ok] gradients finite | loss={float(loss):.4f}  enrichment={enr:.3f}  ||g_H||={float(gH.norm()):.2e}  ||g_f||={float(gf.norm()):.2e}  ||g_w||={float(gw.norm()):.2e}")  # 打印 / Print


def check_enrichment_increases(config: dict) -> None:  # 富集上升 / Enrichment increases
    dtype = torch.float64  # 精度 / Precision
    device = torch.device("cpu")  # CPU / CPU
    K = 4  # K / K
    plate = DifferentiablePlate(config, proxy_grid_size=21, dtype=dtype, device=device)  # 板 / Plate
    target = load_target_binary(config, None)  # 目标 / Target
    tp = torch.as_tensor(resize_binary_nearest(target, plate.N).astype(np.float64), dtype=dtype, device=device)  # 代理目标 / Proxy
    H = torch.full((int(config["project"]["grid_size"]),) * 2, 1.5, dtype=dtype, device=device, requires_grad=True)  # H / H
    fl = initialise_freq_logits(K, 200.0, 900.0, dtype=dtype, device=device).requires_grad_(True)  # 频率 / Freqs
    wl = initialise_weight_logits(K, dtype=dtype, device=device).requires_grad_(True)  # 权重 / Weights
    opt = torch.optim.Adam([{"params": [H], "lr": 0.05}, {"params": [fl], "lr": 0.10}, {"params": [wl], "lr": 0.10}])  # Adam / Adam
    enrichment_history: list[float] = []  # 历史 / History
    for step in range(15):  # 15 步 / 15 steps
        opt.zero_grad()  # 清零 / Zero
        H_proxy = plate.upsample(H)  # 升采样 / Upsample
        K_full, M_diag = plate.assemble_K_M(H_proxy)  # 装配 / Assemble
        free = plate.free_indices  # 自由 / Free
        K_free = K_full.index_select(0, free).index_select(1, free)  # 自由 K / Free K
        M_free = torch.clamp(M_diag.index_select(0, free), min=1.0e-18)  # 自由 M / Free M
        freqs_hz = frequencies_from_logits(fl, 200.0, 900.0)  # 频率 / Freqs
        weights = weights_from_logits(wl)  # 权重 / Weights
        responses = [plate.expand_to_grid(plate.direct_forced_response(K_free, M_free, 2.0 * math.pi * freqs_hz[k], 0.02)) for k in range(K)]  # 响应 / Responses
        composite = compose_multifreq_amplitude_with_weights(responses, weights)  # 合成 / Compose
        composite_c = composite.to(dtype=torch.complex128) + 0.0j  # 复数 / Complex
        loss, parts = combined_recognisability_loss(composite_c, tp, weights=RecognisabilityLossWeights())  # 损失 / Loss
        loss.backward()  # 反传 / Backprop
        opt.step()  # 更新 / Step
        enrichment_history.append(float(parts["enrichment"].detach()))  # 记录 / Record
    initial_enr = enrichment_history[0]  # 初 / Init
    best_enr = max(enrichment_history)  # 最佳 / Best
    assert best_enr > initial_enr + 0.05, f"Enrichment did not increase meaningfully: init={initial_enr:.3f}, best={best_enr:.3f}. / 富集未显著上升。"  # 断言 / Assert
    print(f"[ok] enrichment increases | init={initial_enr:.3f}  best={best_enr:.3f}  last={enrichment_history[-1]:.3f}")  # 打印 / Print


def main() -> int:  # 主 / Main
    config = load_config("config.yaml")  # 配置 / Config
    print("=== W8 smoke ===")  # 头 / Header
    check_gradients_finite(config)  # 梯度 / Gradients
    check_enrichment_increases(config)  # 上升 / Increase
    print("OK")  # 结束 / Done
    return 0  # 返回 / Return


if __name__ == "__main__":  # 直接 / Direct
    raise SystemExit(main())  # 退出 / Exit
