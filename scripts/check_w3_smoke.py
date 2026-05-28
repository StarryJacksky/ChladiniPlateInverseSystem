from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

import numpy as np  # 导入数值库 / Import numerical library
import torch  # 导入张量库 / Import tensor library

from src.config import load_config  # 复用配置加载 / Reuse config loader
from src.optimisation.gradient_optimizer import GradientOptimizerConfig  # 引入优化器配置 / Import optimiser config
from src.optimisation.gradient_optimizer import run_gradient_optimization  # 引入优化入口 / Import optimisation entry
from src.physics.differentiable_plate import DifferentiablePlate  # 引入可微板 / Import differentiable plate
from src.physics.plate_loss_adapter import amplitude_valley_loss_on_response  # 引入振幅谷线损失 / Import loss adapter
from src.physics.plate_loss_adapter import build_target_bundle  # 引入目标包构造 / Import target bundle
from src.physics.plate_loss_adapter import bundle_to_torch  # 引入目标包张量化 / Import bundle tensor conversion


def check_grad_finite(config: dict, target_binary: np.ndarray) -> None:  # 检查梯度有限 / Check gradient is finite
    plate = DifferentiablePlate(config, proxy_grid_size=21)  # 小网格快速测试 / Small grid for quick test
    bundle = build_target_bundle(target_binary, plate.N, float(config["project"]["center_clamp_radius_mm"]), float(config["project"]["plate_length_mm"]))  # 构造目标包 / Build target bundle
    bundle_tensors = bundle_to_torch(bundle, plate.device, plate.dtype)  # 转张量 / Convert to tensors
    H = torch.full((15, 15), 1.5, dtype=plate.dtype, requires_grad=True)  # 创建可优化厚度 / Create optimisable thickness
    result = plate.forward(H, drive_frequency_hz=750.0)  # 板前向 / Plate forward
    loss, _ = amplitude_valley_loss_on_response(result.response_complex, bundle_tensors)  # 计算损失 / Compute loss
    loss.backward()  # 反传 / Backpropagate
    assert H.grad is not None, "Gradient is None. / 梯度为空。"  # 必须有梯度 / Must have gradient
    assert torch.isfinite(H.grad).all().item(), "Gradient has non-finite entries. / 梯度含非有限值。"  # 必须有限 / Must be finite
    assert float(H.grad.abs().max().item()) > 1.0e-8, "Gradient is degenerate. / 梯度退化。"  # 不能退化 / Cannot be degenerate
    print(f"grad check OK / 梯度检查通过: norm={float(H.grad.norm().item()):.4e}, max-abs={float(H.grad.abs().max().item()):.4e}")  # 打印通过 / Print pass


def check_loss_decreases(config: dict, target_binary: np.ndarray, output_dir: Path) -> None:  # 检查 8 步下降 / Check 8-step descent
    opt = GradientOptimizerConfig(proxy_grid_size=21, drive_frequency_hz=750.0, num_steps=8, learning_rate=0.1, snapshot_every=4, plateau_patience=999)  # 配置短优化 / Configure short optimisation
    summary = run_gradient_optimization(config, target_binary, opt, output_dir)  # 跑优化 / Run optimiser
    losses = summary["trace"]["losses"]  # 读取损失 / Read losses
    assert len(losses) == 8, f"Expected 8 steps, got {len(losses)}. / 预期 8 步，实际 {len(losses)}。"  # 步数校验 / Step count check
    assert losses[-1] < losses[0], f"Loss did not decrease: first={losses[0]:.4f} last={losses[-1]:.4f}. / 损失未下降。"  # 下降校验 / Descent check
    print(f"descent check OK / 下降检查通过: losses[0]={losses[0]:.4f} -> losses[-1]={losses[-1]:.4f}")  # 打印通过 / Print pass


def main() -> int:  # 主入口 / Main entry
    config = load_config("config.yaml")  # 读取配置 / Load config
    target_path = Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 拼接目标路径 / Build target path
    if not target_path.exists():  # 检查目标 / Check target
        print(f"Target binary missing: {target_path}. / 目标二值图缺失。", file=sys.stderr)  # 打印缺失 / Print missing
        return 2  # 返回失败 / Return failure
    target_binary = np.load(target_path).astype(bool)  # 读取目标 / Load target
    output_dir = Path("reports/w3_smoke")  # 输出目录 / Output dir
    check_grad_finite(config, target_binary)  # 检查梯度 / Check gradient
    check_loss_decreases(config, target_binary, output_dir)  # 检查下降 / Check descent
    print("W3 smoke check passed. / W3 烟测通过。")  # 总结打印 / Print summary
    return 0  # 返回成功 / Return success


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出 / Exit
