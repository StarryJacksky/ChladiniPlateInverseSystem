from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析 / Import argument parsing
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

import numpy as np  # 导入数值库 / Import numerical library
import torch  # 导入张量库 / Import tensor library

from src.config import load_config  # 复用配置加载 / Reuse config loader
from src.physics.differentiable_plate import DifferentiablePlate  # 引入可微板 / Import differentiable plate
from src.physics.plate_loss_adapter import amplitude_valley_loss_on_response  # 引入损失函数 / Import loss function
from src.physics.plate_loss_adapter import build_target_bundle  # 引入目标包构造 / Import target bundle builder
from src.physics.plate_loss_adapter import bundle_to_torch  # 引入目标张量化 / Import bundle tensorisation
from src.physics.plate_loss_adapter import load_target_binary  # 引入目标加载 / Import target loader
from src.subspace.manifold_pca import decode  # 引入 numpy 解码 / Import numpy decode
from src.subspace.manifold_pca import decode_torch  # 引入 torch 解码 / Import torch decode
from src.subspace.manifold_pca import encode  # 引入 numpy 编码 / Import numpy encode
from src.subspace.manifold_pca import load_manifold  # 引入流形加载 / Import manifold loader


def check_encode_decode(manifold_path: Path) -> bool:  # 检验编码-解码自洽 / Check encode/decode consistency
    manifold = load_manifold(manifold_path)  # 加载流形 / Load manifold
    rng = np.random.default_rng(42)  # 创建 RNG / Build RNG
    test_H = (rng.uniform(0.6, 2.0, size=(manifold.grid_size, manifold.grid_size))).astype(np.float64)  # 生成测试厚度 / Generate test thickness
    coeffs = encode(test_H, manifold)  # 编码 / Encode
    recon = decode(coeffs, manifold)  # 解码 / Decode
    err = float(np.abs(test_H - recon).max())  # 最大误差 / Max error
    pool_err_bound = 1.5  # 池外样本误差上限 / Pool-external error bound in mm
    ok = err < pool_err_bound  # 随机厚度未必在流形内，仅检查不爆炸 / Random thickness not on manifold, just check not exploded
    print(f"encode/decode max abs reconstruction error on random sample: {err:.4f} mm (ok={ok}) / 随机样本编码-解码最大重建误差 {err:.4f} mm（合格={ok}）")  # 输出信息 / Print info
    train_recon = decode(np.zeros(manifold.components.shape[0]), manifold)  # 零系数解码 / Zero-coeff decode
    mean_recon_err = float(np.abs(train_recon - manifold.mean.reshape(manifold.grid_size, manifold.grid_size)).max())  # 与均值差 / Diff vs mean
    ok = ok and mean_recon_err < 1.0e-9  # 零系数应严格等于均值 / Zero coeff must equal mean
    print(f"zero-coefficient decode matches manifold mean: diff={mean_recon_err:.2e} (ok={ok}) / 零系数解码等于均值，差异 {mean_recon_err:.2e}（合格={ok}）")  # 输出信息 / Print info
    return ok  # 返回结果 / Return result


def check_grad_finite_manifold(config_path: Path, manifold_path: Path) -> bool:  # 检验流形系数梯度有限 / Check coeff-gradient finiteness
    config = load_config(config_path)  # 读取配置 / Load config
    manifold = load_manifold(manifold_path)  # 加载流形 / Load manifold
    target = load_target_binary(config, None)  # 加载目标 / Load target
    dtype = torch.float64  # 选择精度 / Select precision
    device = torch.device("cpu")  # 选择设备 / Select device
    plate = DifferentiablePlate(config, proxy_grid_size=21, dtype=dtype, device=device)  # 构造小代理板 / Build small proxy plate
    bundle = build_target_bundle(target, plate.N, float(config["project"]["center_clamp_radius_mm"]), float(config["project"]["plate_length_mm"]))  # 构造目标包 / Build target bundle
    tensors = bundle_to_torch(bundle, device, dtype)  # 转张量 / Convert to tensors
    mean_t = torch.tensor(manifold.mean, dtype=dtype, device=device)  # 均值张量 / Mean tensor
    comp_t = torch.tensor(manifold.components, dtype=dtype, device=device)  # 主成分张量 / Components tensor
    coeffs = torch.zeros(int(manifold.components.shape[0]), dtype=dtype, device=device, requires_grad=True)  # 零系数 / Zero coeffs
    H = decode_torch(coeffs, mean_t, comp_t, manifold.grid_size)  # 解码厚度 / Decode thickness
    H_c = torch.clamp(H, min=float(config["thickness"]["min_mm"]), max=float(config["thickness"]["max_mm"]))  # 可微 clamp / Differentiable clamp
    response = plate.forward(H_c, drive_frequency_hz=800.0, damping_ratio=0.02).response_complex  # 板前向 / Plate forward
    loss, _ = amplitude_valley_loss_on_response(response, tensors, epsilon=0.06)  # 计算损失 / Compute loss
    loss.backward()  # 反传 / Backpropagate
    grad = coeffs.grad.detach().cpu().numpy()  # 取梯度 / Get gradient
    finite = bool(np.all(np.isfinite(grad)))  # 检查有限 / Check finite
    norm = float(np.linalg.norm(grad))  # 计算范数 / Compute norm
    nonzero = norm > 0.0  # 非零检测 / Non-zero detection
    ok = finite and nonzero  # 合格条件 / OK condition
    print(f"manifold-coeff gradient finite={finite}, norm={norm:.4e}, nonzero={nonzero} (ok={ok}) / 流形系数梯度有限={finite}，范数 {norm:.4e}，非零={nonzero}（合格={ok}）")  # 输出信息 / Print info
    return ok  # 返回结果 / Return result


def check_loss_decreases(config_path: Path, manifold_path: Path, steps: int = 25) -> bool:  # 检验沿系数方向损失下降 / Check loss decreases over coeff steps
    config = load_config(config_path)  # 读取配置 / Load config
    manifold = load_manifold(manifold_path)  # 加载流形 / Load manifold
    target = load_target_binary(config, None)  # 加载目标 / Load target
    dtype = torch.float64  # 精度 / Precision
    device = torch.device("cpu")  # 设备 / Device
    plate = DifferentiablePlate(config, proxy_grid_size=21, dtype=dtype, device=device)  # 小代理板 / Small proxy plate
    bundle = build_target_bundle(target, plate.N, float(config["project"]["center_clamp_radius_mm"]), float(config["project"]["plate_length_mm"]))  # 目标包 / Target bundle
    tensors = bundle_to_torch(bundle, device, dtype)  # 张量化 / Tensorise
    mean_t = torch.tensor(manifold.mean, dtype=dtype, device=device)  # 均值张量 / Mean tensor
    comp_t = torch.tensor(manifold.components, dtype=dtype, device=device)  # 主成分张量 / Components tensor
    coeffs = torch.zeros(int(manifold.components.shape[0]), dtype=dtype, device=device, requires_grad=True)  # 系数初值 / Coeff init
    optim = torch.optim.Adam([coeffs], lr=0.2)  # Adam 优化器 / Adam optimiser
    losses: list[float] = []  # 损失序列 / Loss sequence
    for _ in range(int(steps)):  # 迭代步 / Iterate steps
        optim.zero_grad()  # 清零梯度 / Zero gradients
        H = decode_torch(coeffs, mean_t, comp_t, manifold.grid_size)  # 解码厚度 / Decode thickness
        H_c = torch.clamp(H, min=float(config["thickness"]["min_mm"]), max=float(config["thickness"]["max_mm"]))  # 可微 clamp / Differentiable clamp
        response = plate.forward(H_c, drive_frequency_hz=800.0, damping_ratio=0.02).response_complex  # 板前向 / Plate forward
        loss, _ = amplitude_valley_loss_on_response(response, tensors, epsilon=0.06)  # 计算损失 / Compute loss
        loss.backward()  # 反传 / Backpropagate
        optim.step()  # 更新 / Update
        losses.append(float(loss.item()))  # 记录损失 / Record loss
    min_loss = float(min(losses))  # 最小损失 / Minimum loss
    ok = min_loss < losses[0] - 1.0e-3  # 至少一次显著下降 / At least one significant drop
    print(f"manifold-loss sequence ({steps} steps): first={losses[0]:.4f}, min={min_loss:.4f}, last={losses[-1]:.4f} (ok={ok}) / 流形损失序列：首步 {losses[0]:.4f}，最小 {min_loss:.4f}，末步 {losses[-1]:.4f}（合格={ok}）")  # 输出信息 / Print info
    return ok  # 返回结果 / Return result


def main(argv: list[str] | None = None) -> int:  # 主入口 / Main entry
    parser = argparse.ArgumentParser(description="W4 manifold optimisation smoke tests. / W4 流形优化烟雾测试。")  # 解析器 / Parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config path. / 项目配置路径。")  # 配置 / Config
    parser.add_argument("--manifold", type=str, default="reports/design_manifold_pca.npz", help="PCA manifold NPZ path. / PCA 流形 NPZ 路径。")  # 流形路径 / Manifold path
    args = parser.parse_args(argv)  # 解析 / Parse
    results = [check_encode_decode(Path(args.manifold)), check_grad_finite_manifold(Path(args.config), Path(args.manifold)), check_loss_decreases(Path(args.config), Path(args.manifold))]  # 跑三项检测 / Run three checks
    ok = all(results)  # 综合结果 / Overall result
    print(f"smoke result: {'PASS' if ok else 'FAIL'} / 烟雾测试结果：{'通过' if ok else '失败'}")  # 输出综合 / Print overall
    return 0 if ok else 1  # 返回退出码 / Return exit code


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出 / Exit
