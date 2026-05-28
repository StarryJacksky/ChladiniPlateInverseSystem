from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析 / Import argument parsing
import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

import numpy as np  # 导入数值库 / Import numerical library

from src.config import load_config  # 复用配置加载 / Reuse config loader
from src.optimisation.gradient_optimizer import GradientOptimizerConfig  # 复用优化器配置 / Reuse optimiser config
from src.optimisation.homotopy import HomotopyConfig  # 引入同伦配置 / Import homotopy config
from src.optimisation.homotopy import morph_targets  # 引入 morph 函数 / Import morph helper
from src.optimisation.homotopy import run_homotopy  # 引入同伦入口 / Import homotopy entry
from src.optimisation.homotopy import signed_distance_field  # 引入 SDF 函数 / Import SDF helper
from src.physics.plate_loss_adapter import load_target_binary  # 复用目标加载 / Reuse target loader
from src.subspace.manifold_pca import load_manifold  # 复用流形加载 / Reuse manifold loader


def check_morph_endpoints(T0: np.ndarray, T1: np.ndarray) -> bool:  # 检验 λ=0 与 λ=1 端点一致性 / Check λ=0/λ=1 endpoint consistency
    T_at_0 = morph_targets(T0, T1, 0.0)  # λ=0 应≈T_0 / λ=0 should ≈ T_0
    T_at_1 = morph_targets(T0, T1, 1.0)  # λ=1 应≈T_1 / λ=1 should ≈ T_1
    iou_0 = float(np.logical_and(T_at_0, T0).sum()) / max(float(np.logical_or(T_at_0, T0).sum()), 1.0)  # 与 T_0 的 IoU / IoU vs T_0
    iou_1 = float(np.logical_and(T_at_1, T1).sum()) / max(float(np.logical_or(T_at_1, T1).sum()), 1.0)  # 与 T_1 的 IoU / IoU vs T_1
    ok = iou_0 > 0.95 and iou_1 > 0.95  # 端点应高度吻合 / Endpoints should match closely
    print(f"morph endpoint IoU: λ=0 vs T_0 = {iou_0:.4f}, λ=1 vs T_1 = {iou_1:.4f} (ok={ok}) / 端点 IoU：λ=0 与 T_0 = {iou_0:.4f}，λ=1 与 T_1 = {iou_1:.4f}（合格={ok}）")  # 输出 / Print
    return ok  # 返回结果 / Return result


def check_morph_monotone(T0: np.ndarray, T1: np.ndarray) -> bool:  # 检验中间 λ 的距离单调性 / Check monotone distance between T_λ and endpoints
    iou_to_T1 = []  # 记录 IoU 序列 / IoU sequence
    for lam in np.linspace(0.0, 1.0, 6):  # 6 个 λ 抽样 / 6 λ samples
        T_lam = morph_targets(T0, T1, float(lam))  # 计算 T_λ / Compute T_λ
        inter = float(np.logical_and(T_lam, T1).sum())  # 交集 / Intersection
        union = float(np.logical_or(T_lam, T1).sum())  # 并集 / Union
        iou_to_T1.append(inter / max(union, 1.0))  # 追加 IoU / Append IoU
    diffs = np.diff(np.array(iou_to_T1))  # 计算前向差 / Forward diffs
    ok = float(np.percentile(diffs, 50)) >= 0.0 and iou_to_T1[-1] > iou_to_T1[0] - 1.0e-6  # 中位数非负 + 末点≥首点 / Median ≥0 and last ≥ first
    print(f"morph IoU(T_λ, T_1) sequence over λ: {[f'{v:.3f}' for v in iou_to_T1]} (ok={ok}) / λ 序列 IoU(T_λ, T_1)：{[f'{v:.3f}' for v in iou_to_T1]}（合格={ok}）")  # 输出 / Print
    return ok  # 返回结果 / Return result


def check_full_homotopy_loop(config_path: Path, manifold_path: Path | None) -> bool:  # 跑短链路 W5 / Run abbreviated W5 loop
    config = load_config(config_path)  # 读取配置 / Load config
    target = load_target_binary(config, None)  # 读取目标 / Load target
    manifold = load_manifold(manifold_path) if manifold_path is not None else None  # 加载流形 / Load manifold
    opt_cfg = GradientOptimizerConfig(proxy_grid_size=21, drive_frequency_hz=600.0, damping_ratio=0.02, epsilon=0.06, learning_rate=0.20, smoothness_weight=2.0, manifold=manifold, manifold_coeff_l2_weight=1.0e-3)  # 优化器配置 / Optimiser config
    hom_cfg = HomotopyConfig(lambda_grid=(0.0, 0.5, 1.0), steps_per_lambda=10, seed_lambda_steps=15, seed_strategy="natural_amplitude", natural_quantile=0.20)  # 短链路同伦配置 / Short homotopy config
    out_dir = Path("reports/homotopy/_smoke")  # 烟雾输出目录 / Smoke output dir
    summary = run_homotopy(config, np.asarray(target, dtype=bool), opt_cfg, hom_cfg, out_dir, verdict=None)  # 跑同伦 / Run homotopy
    losses = [step["total_loss"] for step in summary["steps"]]  # 提取损失 / Extract losses
    csv_path = Path(summary["lambda_curve_csv"])  # 取 CSV 路径 / Get CSV path
    ok_struct = csv_path.exists() and (out_dir / "homotopy_summary.json").exists() and (out_dir / "T_0.npy").exists() and (out_dir / "T_1.npy").exists()  # 检查关键文件 / Check key files
    ok_finite = all(np.isfinite(v) for v in losses)  # 损失全部有限 / All losses finite
    ok_lambda_max = 0.0 <= float(summary["lambda_max"]) <= 1.0  # λ_max 在合法范围 / λ_max within legal range
    per_lambda_h = all(Path(step["h_csv_path"]).exists() for step in summary["steps"])  # 每 λ 都有 H.csv / H.csv per λ exists
    ok = ok_struct and ok_finite and ok_lambda_max and per_lambda_h  # 综合 / Overall
    print(f"homotopy loop: losses={[f'{v:.3f}' for v in losses]}, lambda_max={summary['lambda_max']:.3f}, struct={ok_struct}, finite={ok_finite}, lambda_range={ok_lambda_max}, per_lambda_H={per_lambda_h} (ok={ok}) / 同伦循环损失 {[f'{v:.3f}' for v in losses]}，λ_max={summary['lambda_max']:.3f}，文件齐={ok_struct}，有限={ok_finite}，λ范围={ok_lambda_max}，每λH={per_lambda_h}（合格={ok}）")  # 输出 / Print
    return ok  # 返回 / Return


def main(argv: list[str] | None = None) -> int:  # 主入口 / Main entry
    parser = argparse.ArgumentParser(description="W5 homotopy smoke tests. / W5 同伦延拓烟雾测试。")  # 解析器 / Parser
    parser.add_argument("--config", type=str, default="config.yaml")  # 配置 / Config
    parser.add_argument("--manifold", type=str, default="reports/design_manifold_pca.npz")  # 流形 / Manifold
    args = parser.parse_args(argv)  # 解析 / Parse
    rng = np.random.default_rng(0)  # 创建 RNG / Build RNG
    T0 = rng.random((96, 96)) > 0.5  # 随机 T_0 / Random T_0
    T1 = rng.random((96, 96)) > 0.7  # 随机 T_1 / Random T_1
    results = [check_morph_endpoints(T0, T1), check_morph_monotone(T0, T1), check_full_homotopy_loop(Path(args.config), Path(args.manifold) if args.manifold else None)]  # 三项检测 / Three checks
    ok = all(results)  # 综合 / Overall
    print(f"smoke result: {'PASS' if ok else 'FAIL'} / 烟雾测试结果：{'通过' if ok else '失败'}")  # 输出综合 / Print overall
    return 0 if ok else 1  # 返回码 / Exit code


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出 / Exit
