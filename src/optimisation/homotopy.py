from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
from dataclasses import dataclass, field  # 导入数据类装饰器 / Import dataclass decorator
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值库 / Import numerical library
from scipy.ndimage import distance_transform_edt  # 导入距离变换 / Import distance transform

from src.optimisation.gradient_optimizer import GradientOptimizerConfig  # 复用优化器配置 / Reuse optimiser config
from src.optimisation.gradient_optimizer import run_gradient_optimization  # 复用优化主入口 / Reuse optimisation entry
from src.subspace.manifold_pca import DesignManifold  # 引入设计流形数据类 / Import design-manifold type


@dataclass  # 数据类装饰器 / Dataclass decorator
class HomotopyConfig:  # W5 同伦延拓配置 / W5 homotopy continuation configuration
    lambda_grid: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)  # λ 网格 / Lambda grid
    steps_per_lambda: int = 50  # 每个 λ 的 Adam 步数 / Adam steps per λ
    stall_factor: float = 2.0  # 损失抖动相对历史最低的阈值 / Stall threshold relative to running best
    stall_consecutive: int = 3  # 连续抖动声明次数 / Consecutive stalls before declaring stall
    seed_lambda_steps: int = 80  # λ=0 暖身步数 / Warm-up Adam steps at λ=0
    seed_strategy: str = "natural_amplitude"  # T_0 选取策略 / T_0 selection strategy
    natural_quantile: float = 0.20  # 自然态 T_0 振幅分位 / Quantile for natural T_0 valley band
    explicit_T0_path: Path | None = None  # 显式 T_0 路径 / Explicit T_0 path


@dataclass  # 数据类装饰器 / Dataclass decorator
class HomotopyStepResult:  # 单步 λ 结果 / Per-λ step result
    lambda_value: float  # λ 数值 / λ value
    total_loss: float  # 总损失 / Total loss
    target_loss: float  # 目标项损失 / Target-band loss
    contrast_loss: float  # 对比项损失 / Contrast loss
    compact_loss: float  # 紧凑项损失 / Compactness loss
    smoothness_loss: float  # 平滑项损失 / Smoothness penalty
    h_csv_path: str  # 最终 H.csv 路径 / Final H.csv path
    h_continuous_path: str  # 连续 H 路径 / Continuous H path
    t_lambda_path: str  # 目标 NPY 路径 / Target NPY path
    iou: float  # 当前 λ 目标与振幅低值区的 IoU / IoU of T_λ vs amplitude-valley band
    foreground_ratio: float  # T_λ 前景占比 / Foreground ratio
    drive_frequency_hz: float  # 当前驱动频率 / Drive frequency


def signed_distance_field(binary: np.ndarray) -> np.ndarray:  # 计算二值图的符号距离场 / Compute signed-distance field of binary mask
    mask = np.asarray(binary, dtype=bool)  # 转布尔 / Convert to boolean
    if mask.any() and (~mask).any():  # 检查双区存在 / Check both regions exist
        inside = distance_transform_edt(mask)  # 内部到外部距离 / Inside-to-outside distance
        outside = distance_transform_edt(~mask)  # 外部到内部距离 / Outside-to-inside distance
        return (inside - outside).astype(np.float64)  # 内正外负 / Positive inside, negative outside
    if mask.any():  # 全是前景 / All foreground
        return np.full(mask.shape, float(max(mask.shape)), dtype=np.float64)  # 全正大值 / All-positive large value
    return np.full(mask.shape, -float(max(mask.shape)), dtype=np.float64)  # 全负大值 / All-negative large value


def morph_targets(T0: np.ndarray, T1: np.ndarray, lambda_value: float) -> np.ndarray:  # 用距离场线性插值 morph / Morph by SDF linear blend
    sdf0 = signed_distance_field(T0)  # 起点距离场 / Source SDF
    sdf1 = signed_distance_field(T1)  # 终点距离场 / Target SDF
    sdf_lambda = (1.0 - float(lambda_value)) * sdf0 + float(lambda_value) * sdf1  # SDF 线性插值 / Linear SDF blend
    return sdf_lambda > 0.0  # 重二值化 / Re-binarise


def compute_natural_T0_from_plate(config: dict, proxy_grid_size: int, drive_frequency_hz: float, damping_ratio: float, natural_quantile: float, manifold: DesignManifold | None = None) -> tuple[np.ndarray, np.ndarray]:  # 通过板前向得到自然 T_0 / Derive natural T_0 from plate forward
    import torch  # 延迟导入 / Lazy import
    from src.physics.differentiable_plate import DifferentiablePlate  # 延迟导入板模型 / Lazy import plate model
    thickness_cfg = config["thickness"]  # 读取厚度配置 / Read thickness config
    grid_size = int(config["project"]["grid_size"])  # 设计网格 / Design grid
    image_size = int(config.get("nodal_extraction", {}).get("image_size", 256))  # 输出二值图大小 / Output binary size
    dtype = torch.float64  # 精度 / Precision
    device = torch.device("cpu")  # 设备 / Device
    plate = DifferentiablePlate(config, proxy_grid_size=int(proxy_grid_size), reference_frequency_hz=float(drive_frequency_hz), dtype=dtype, device=device)  # 构造板模型 / Build plate model
    if manifold is not None:  # 走流形均值 / Use manifold mean
        H_design = torch.tensor(manifold.mean.reshape(int(manifold.grid_size), int(manifold.grid_size)), dtype=dtype, device=device)  # 均值厚度 / Mean thickness
    else:  # 走默认厚度 / Default thickness
        H_design = torch.full((grid_size, grid_size), float(thickness_cfg.get("default_mm", 1.0)), dtype=dtype, device=device)  # 默认厚度场 / Default thickness field
    H_design = torch.clamp(H_design, min=float(thickness_cfg["min_mm"]), max=float(thickness_cfg["max_mm"]))  # 裁剪范围 / Clamp range
    with torch.no_grad():  # 关闭梯度 / Disable grad
        result = plate.forward(H_design, drive_frequency_hz=float(drive_frequency_hz), damping_ratio=float(damping_ratio))  # 前向 / Forward
        amp = result.amplitude.detach().cpu().numpy()  # 取振幅 / Get amplitude
    amp_normalised = amp / max(float(amp.max()), 1.0e-12)  # 归一化 / Normalise
    threshold = float(np.quantile(amp_normalised, float(natural_quantile)))  # 分位阈值 / Quantile threshold
    valley = amp_normalised <= threshold  # 振幅最低区 / Lowest-amplitude region
    valley_resized = _resize_binary_nearest(valley, image_size)  # 缩放到目标尺寸 / Resize to target size
    return valley_resized.astype(bool), H_design.detach().cpu().numpy().copy()  # 返回 T_0 与初值厚度 / Return T_0 and initial thickness


def _resize_binary_nearest(binary: np.ndarray, image_size: int) -> np.ndarray:  # 最近邻缩放二值图 / Nearest-neighbour resize for binary mask
    if binary.shape == (int(image_size), int(image_size)):  # 已经是目标大小 / Already target size
        return binary  # 直接返回 / Return as-is
    src_rows, src_cols = binary.shape  # 读取源尺寸 / Read source shape
    row_idx = np.minimum((np.arange(int(image_size)) * src_rows // max(int(image_size), 1)).astype(int), src_rows - 1)  # 行索引 / Row indices
    col_idx = np.minimum((np.arange(int(image_size)) * src_cols // max(int(image_size), 1)).astype(int), src_cols - 1)  # 列索引 / Column indices
    return binary[np.ix_(row_idx, col_idx)]  # 索引缩放 / Index resize


def _build_lambda_T_dir(output_dir: Path, lambda_value: float) -> Path:  # 构造 λ 子目录路径 / Build per-λ subdirectory path
    return Path(output_dir) / f"lambda_{lambda_value:0.3f}"  # 三位小数命名 / Three-decimal naming


def _evaluate_T_lambda_iou(amplitude: np.ndarray, T_lambda: np.ndarray, quantile: float = 0.25) -> float:  # 计算 T_λ 与低振幅区的 IoU / Compute IoU between T_λ and amplitude valley
    amp_resized = _resize_binary_nearest(amplitude, T_lambda.shape[0]) if amplitude.shape != T_lambda.shape else amplitude  # 形状对齐 / Align shapes
    amp_normalised = amp_resized / max(float(amp_resized.max()), 1.0e-12)  # 归一化 / Normalise
    threshold = float(np.quantile(amp_normalised, float(quantile)))  # 分位阈值 / Quantile threshold
    band = amp_normalised <= threshold  # 振幅低值带 / Amplitude-valley band
    inter = int(np.logical_and(band, T_lambda).sum())  # 交集像素 / Intersection
    union = int(np.logical_or(band, T_lambda).sum())  # 并集像素 / Union
    return float(inter) / float(union) if union > 0 else 0.0  # 返回 IoU / Return IoU


def run_homotopy(config: dict, T_1: np.ndarray, opt_config: GradientOptimizerConfig, hom_config: HomotopyConfig, output_dir: Path, verdict: dict | None = None) -> dict:  # 跑 W5 同伦延拓 / Run W5 homotopy continuation
    output_dir = Path(output_dir)  # 转路径 / Convert path
    output_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    manifold = opt_config.manifold  # 读取流形 / Read manifold
    if hom_config.seed_strategy == "explicit_npy" and hom_config.explicit_T0_path is not None:  # 显式 T_0 / Explicit T_0
        T_0 = np.load(hom_config.explicit_T0_path).astype(bool)  # 读取 T_0 / Load T_0
        T_0_resized = _resize_binary_nearest(T_0, int(T_1.shape[0]))  # 缩放到 T_1 尺寸 / Resize to T_1 size
        initial_H = None  # 不设初值 / No initial H
    elif hom_config.seed_strategy == "natural_amplitude":  # 自然振幅策略 / Natural-amplitude strategy
        T_0_resized, initial_H = compute_natural_T0_from_plate(config, proxy_grid_size=int(opt_config.proxy_grid_size), drive_frequency_hz=float(opt_config.drive_frequency_hz), damping_ratio=float(opt_config.damping_ratio), natural_quantile=float(hom_config.natural_quantile), manifold=manifold)  # 计算自然 T_0 / Compute natural T_0
    else:  # 未知策略 / Unknown strategy
        raise ValueError(f"Unknown seed_strategy: {hom_config.seed_strategy}. / 未知 T_0 策略：{hom_config.seed_strategy}。")  # 抛出错误 / Raise error
    if T_0_resized.shape != T_1.shape:  # 检查形状一致 / Check shape consistency
        T_0_resized = _resize_binary_nearest(T_0_resized, int(T_1.shape[0]))  # 二次缩放 / Resize again
    np.save(output_dir / "T_0.npy", T_0_resized)  # 保存 T_0 / Save T_0
    np.save(output_dir / "T_1.npy", np.asarray(T_1, dtype=bool))  # 保存 T_1 / Save T_1
    steps_record: list[HomotopyStepResult] = []  # 创建步骤记录 / Create per-step record
    warm_start_H: np.ndarray | None = initial_H  # 暖启动厚度 / Warm-start thickness
    for lambda_idx, lambda_value in enumerate(hom_config.lambda_grid):  # 遍历 λ 网格 / Iterate λ grid
        T_lambda = morph_targets(T_0_resized, np.asarray(T_1, dtype=bool), float(lambda_value))  # 计算 T_λ / Compute T_λ
        sub_dir = _build_lambda_T_dir(output_dir, float(lambda_value))  # 子目录 / Subdir
        sub_dir.mkdir(parents=True, exist_ok=True)  # 创建子目录 / Create subdir
        np.save(sub_dir / "T_lambda.npy", T_lambda)  # 保存 T_λ / Save T_λ
        steps_for_this_lambda = int(hom_config.seed_lambda_steps) if lambda_idx == 0 else int(hom_config.steps_per_lambda)  # 暖身 vs 续跑 / Warm-up vs continuation
        local_opt_cfg = GradientOptimizerConfig(proxy_grid_size=int(opt_config.proxy_grid_size), drive_frequency_hz=float(opt_config.drive_frequency_hz), damping_ratio=float(opt_config.damping_ratio), epsilon=float(opt_config.epsilon), num_steps=steps_for_this_lambda, learning_rate=float(opt_config.learning_rate), weight_decay=float(opt_config.weight_decay), plateau_patience=int(opt_config.plateau_patience), plateau_min_delta=float(opt_config.plateau_min_delta), snapshot_every=int(max(steps_for_this_lambda, 1)), loss_weights=opt_config.loss_weights, base_accel_m_s2=float(opt_config.base_accel_m_s2), smoothness_weight=float(opt_config.smoothness_weight), smoothness_max_diff_mm=opt_config.smoothness_max_diff_mm, manifold=opt_config.manifold, manifold_coeff_l2_weight=float(opt_config.manifold_coeff_l2_weight))  # 构造每段优化器配置 / Build per-segment optimiser config
        summary = run_gradient_optimization(config, T_lambda.astype(bool), local_opt_cfg, sub_dir, verdict=verdict, initial_H_mm=warm_start_H)  # 调用优化器 / Call optimiser
        h_csv = sub_dir / "H.csv"  # 量化 H 路径 / Quantised H path
        h_continuous = sub_dir / "H_continuous.csv"  # 连续 H 路径 / Continuous H path
        warm_start_H = np.loadtxt(h_continuous, delimiter=",")  # 暖启动从连续厚度继续 / Continue warm-start from continuous H
        amp_path = sorted(sub_dir.glob("snapshot_step_*_amplitude.npy"))  # 找最新振幅快照 / Find latest amplitude snapshot
        amplitude_array = np.load(amp_path[-1]) if amp_path else np.zeros_like(T_lambda, dtype=np.float64)  # 读取振幅 / Load amplitude
        iou = _evaluate_T_lambda_iou(amplitude_array, T_lambda, quantile=0.25)  # 计算 IoU / Compute IoU
        trace_tail = summary["trace"]["losses"][-1]  # 末步损失 / Last-step loss
        step_record = HomotopyStepResult(lambda_value=float(lambda_value), total_loss=float(trace_tail), target_loss=float(summary["trace"]["target_loss"][-1]), contrast_loss=float(summary["trace"]["contrast_loss"][-1]), compact_loss=float(summary["trace"]["compact_loss"][-1]), smoothness_loss=float(summary["trace"]["smoothness_loss"][-1]), h_csv_path=str(h_csv), h_continuous_path=str(h_continuous), t_lambda_path=str(sub_dir / "T_lambda.npy"), iou=float(iou), foreground_ratio=float(T_lambda.mean()), drive_frequency_hz=float(opt_config.drive_frequency_hz))  # 记录单步 / Record single step
        steps_record.append(step_record)  # 追加记录 / Append record
    losses_array = np.array([step.total_loss for step in steps_record], dtype=np.float64)  # 收集损失 / Collect losses
    best_loss_seen = float(losses_array.min())  # 全局最优损失 / Global best loss
    acceptance_threshold = best_loss_seen * float(hom_config.stall_factor)  # 接受阈值 / Acceptance threshold
    acceptable_mask = losses_array <= acceptance_threshold  # 满足接受阈值的 λ / λ within threshold
    lambda_array = np.array([step.lambda_value for step in steps_record], dtype=np.float64)  # λ 数组 / λ array
    lambda_reached = float(lambda_array[acceptable_mask].max()) if acceptable_mask.any() else float(lambda_array[0])  # 最大可达 λ / Highest reached λ
    stall_streak = 0  # 连续抖动计数 / Stall streak counter
    lambda_max_stream: float | None = None  # 流式 λ_max / Streaming λ_max
    rolling_best = float("inf")  # 滚动最优 / Rolling best
    for step_value in losses_array:  # 重放流式判定 / Replay streaming verdict
        if step_value > rolling_best * float(hom_config.stall_factor):  # 损失超阈值 / Loss above threshold
            stall_streak += 1  # 累计抖动 / Accumulate stall
        else:  # 否则刷新滚动最优 / Otherwise refresh rolling best
            rolling_best = min(rolling_best, float(step_value))  # 更新滚动最优 / Update rolling best
            stall_streak = 0  # 重置 / Reset
        if stall_streak >= int(hom_config.stall_consecutive) and lambda_max_stream is None:  # 触发声明 / Trigger declaration
            stall_idx = int(np.argmax(losses_array == step_value))  # 找当前 λ 索引 / Locate current λ index
            lambda_max_stream = float(lambda_array[max(stall_idx - stall_streak, 0)])  # 取前段 λ / Use earlier λ
    lambda_max = float(lambda_max_stream if lambda_max_stream is not None else lambda_reached)  # 综合 λ_max / Combine λ_max
    lambda_max = max(lambda_max, lambda_reached)  # 不低于事后扫描结果 / Not below post-hoc scan
    lambda_curve_rows = []  # CSV 行 / CSV rows
    for record in steps_record:  # 序列化 / Serialise
        lambda_curve_rows.append({"lambda": record.lambda_value, "total_loss": record.total_loss, "target_loss": record.target_loss, "contrast_loss": record.contrast_loss, "compact_loss": record.compact_loss, "smoothness_loss": record.smoothness_loss, "iou_band": record.iou, "T_lambda_foreground_ratio": record.foreground_ratio, "drive_frequency_hz": record.drive_frequency_hz, "h_csv_path": record.h_csv_path})  # 追加行 / Append row
    csv_path = output_dir / "lambda_curve.csv"  # CSV 路径 / CSV path
    columns = ["lambda", "total_loss", "target_loss", "contrast_loss", "compact_loss", "smoothness_loss", "iou_band", "T_lambda_foreground_ratio", "drive_frequency_hz", "h_csv_path"]  # 列名 / Column names
    with csv_path.open("w", encoding="utf-8") as f:  # 写 CSV / Write CSV
        f.write(",".join(columns) + "\n")  # 写表头 / Write header
        for row in lambda_curve_rows:  # 遍历行 / Iterate rows
            f.write(",".join(str(row[col]) for col in columns) + "\n")  # 写一行 / Write one row
    summary = {"lambda_max": float(lambda_max), "lambda_reached_with_quality": float(lambda_reached), "lambda_max_streaming": float(lambda_max_stream) if lambda_max_stream is not None else None, "acceptance_threshold": float(acceptance_threshold), "best_loss_seen": float(best_loss_seen), "final_loss_at_lambda_1": float(steps_record[-1].total_loss), "lambda_grid": list(hom_config.lambda_grid), "steps_per_lambda": int(hom_config.steps_per_lambda), "seed_lambda_steps": int(hom_config.seed_lambda_steps), "seed_strategy": str(hom_config.seed_strategy), "natural_quantile": float(hom_config.natural_quantile), "stall_factor": float(hom_config.stall_factor), "stall_consecutive": int(hom_config.stall_consecutive), "drive_frequency_hz": float(opt_config.drive_frequency_hz), "use_manifold": opt_config.manifold is not None, "T_0_path": str(output_dir / "T_0.npy"), "T_1_path": str(output_dir / "T_1.npy"), "lambda_curve_csv": str(csv_path), "steps": [step.__dict__ for step in steps_record]}  # 构造总结 / Build summary
    summary_path = output_dir / "homotopy_summary.json"  # 摘要路径 / Summary path
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 JSON / Write JSON
    return summary  # 返回摘要 / Return summary
