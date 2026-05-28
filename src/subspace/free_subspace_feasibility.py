from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from dataclasses import dataclass  # 导入数据类工具 / Import dataclass helper

import numpy as np  # 导入数值计算库 / Import numerical library
import torch  # 导入张量优化库 / Import tensor optimisation library

from src.nodal.extract_nodal import extract_nodal_region  # 导入零线提取 / Import zero-line extraction
from src.nodal.extract_nodal import postprocess_nodal_region  # 导入零线后处理 / Import zero-line postprocessing
from src.nodal.extract_nodal import remove_center_region  # 导入中心区移除 / Import centre-region removal
from src.scoring.signed_distance_loss import zero_contour_loss  # 导入可微零线损失 / Import differentiable zero-contour loss
from src.subspace.mosaic_z import build_target_data  # 复用目标几何张量构造 / Reuse target-geometry tensor builder
from src.subspace.mosaic_z import response_metrics  # 复用零线指标计算 / Reuse zero-line metric computation


@dataclass  # 声明子空间优化结果 / Declare subspace optimisation result
class SubspaceResult:  # 保存一次模态组合可行性结果 / Store one modal-combination feasibility result
    alpha: np.ndarray  # 归一化模态系数 / Normalised modal coefficients
    response: np.ndarray  # 组合响应场 / Combined response field
    nodal: np.ndarray  # 从响应提取的零线图 / Extracted zero-contour map
    metrics: dict[str, float]  # IoU、Dice、Layout 等指标 / IoU, Dice, Layout, and related metrics
    loss: float  # 零等值线损失 / Zero-contour loss
    loss_parts: dict[str, float]  # 损失分量 / Loss components
    mode_ids: list[int]  # 参与优化的模态编号 / Participating mode identifiers
    freqs: np.ndarray  # 参与优化的模态频率 / Participating modal frequencies
    frequency_mean_hz: float  # 系数加权平均频率 / Coefficient-weighted mean frequency
    frequency_spread: float  # 归一化频率离散度 / Normalised frequency spread
    effective_modal_count: float  # 有效模态数 / Effective modal count
    participating_modes: list[dict[str, float]]  # 主导模态摘要 / Dominant-mode summary
    metadata: dict[str, object]  # 额外元数据 / Extra metadata


def extract_response_nodal(response: np.ndarray, epsilon_ratio: float, center_radius_px: int) -> np.ndarray:  # 提取组合响应零线图 / Extract zero-contour map from combined response
    nodal = extract_nodal_region(response, float(epsilon_ratio))  # 提取近零和符号翻转区域 / Extract near-zero and sign-crossing region
    nodal = postprocess_nodal_region(nodal)  # 清理零线图 / Clean zero-contour map
    return remove_center_region(nodal, int(center_radius_px)) if int(center_radius_px) > 0 else nodal  # 可选移除中心区 / Optionally remove centre region


def modal_weight_statistics(alpha: np.ndarray, freqs: np.ndarray, mode_ids: list[int], top_n: int = 8) -> dict[str, object]:  # 计算模态权重统计 / Compute modal-weight statistics
    coeff = np.asarray(alpha, dtype=float).reshape(-1)  # 转成一维系数 / Convert to one-dimensional coefficients
    frequency = np.asarray(freqs, dtype=float).reshape(-1)  # 转成一维频率 / Convert to one-dimensional frequencies
    weights = np.square(np.abs(coeff))  # 计算能量权重 / Compute energy weights
    weights = weights / max(float(weights.sum()), 1.0e-12)  # 归一化权重 / Normalise weights
    f_bar = float(np.sum(weights * frequency)) if len(frequency) else 0.0  # 计算加权平均频率 / Compute weighted mean frequency
    spread = float(np.sqrt(np.sum(weights * np.square(frequency - f_bar))) / max(f_bar, 1.0e-12)) if len(frequency) else 0.0  # 计算相对频率离散度 / Compute relative frequency spread
    n_eff = float(1.0 / max(float(np.sum(np.square(weights))), 1.0e-12))  # 计算有效模态数 / Compute effective modal count
    order = np.argsort(-np.abs(coeff))[: int(top_n)]  # 找到主导模态索引 / Find dominant modal indices
    dominant = [{"mode": float(mode_ids[index]), "frequency_hz": float(frequency[index]), "alpha": float(coeff[index]), "weight": float(weights[index])} for index in order]  # 构造主导模态表 / Build dominant-mode table
    return {"weights": weights, "frequency_mean_hz": f_bar, "frequency_spread": spread, "effective_modal_count": n_eff, "participating_modes": dominant}  # 返回统计结果 / Return statistics


def optimise_modal_combination(fields: np.ndarray, freqs: np.ndarray, mode_ids: list[int], target_binary: np.ndarray, steps: int = 420, restarts: int = 3, learning_rate: float = 0.035, center_radius_px: int = 0, epsilon: float = 0.045, seed: int = 17, loss_weights: dict[str, float] | None = None, label: str = "free") -> SubspaceResult:  # 优化给定模态集合的线性组合 / Optimise linear combination for a given modal set
    if fields.ndim != 3:  # 检查模态场维度 / Check modal-field rank
        raise ValueError("fields must have shape [num_modes, height, width]. / fields 必须是 [模态数, 高, 宽]。")  # 抛出维度错误 / Raise shape error
    if fields.shape[0] != len(mode_ids) or fields.shape[0] != len(freqs):  # 检查模态数量一致性 / Check modal-count consistency
        raise ValueError("fields, freqs, and mode_ids must have matching lengths. / fields、freqs 和 mode_ids 长度必须一致。")  # 抛出一致性错误 / Raise consistency error
    torch.manual_seed(int(seed))  # 固定 Torch 随机种子 / Fix Torch random seed
    np.random.seed(int(seed))  # 固定 NumPy 随机种子 / Fix NumPy random seed
    device = torch.device("cpu")  # 使用 CPU 保证部署兼容 / Use CPU for deployment compatibility
    image_size = int(fields.shape[1])  # 读取图像尺寸 / Read image size
    basis_np = np.asarray(fields, dtype=np.float32).reshape(fields.shape[0], -1).T  # 转为 [pixel, mode] 矩阵 / Convert to [pixel, mode] matrix
    basis = torch.as_tensor(basis_np, dtype=torch.float32, device=device)  # 转成 Torch 张量 / Convert to Torch tensor
    target_data = build_target_data(target_binary, image_size, int(center_radius_px), device)  # 构造目标数据 / Build target data
    best: dict[str, object] | None = None  # 初始化最佳记录 / Initialise best record
    for restart in range(max(1, int(restarts))):  # 多起点优化 / Run multi-start optimisation
        alpha = torch.randn(fields.shape[0], dtype=torch.float32, device=device, requires_grad=True)  # 初始化系数 / Initialise coefficients
        optimiser = torch.optim.Adam([alpha], lr=float(learning_rate))  # 创建 Adam 优化器 / Create Adam optimiser
        for _step in range(max(1, int(steps))):  # 迭代优化 / Iterate optimisation
            coeff = alpha / (torch.linalg.norm(alpha) + 1.0e-8)  # 归一化系数 / Normalise coefficients
            response = torch.matmul(basis, coeff).reshape(image_size, image_size)  # 合成响应 / Compose response
            loss, parts = zero_contour_loss(response, target_data["target_points"], target_data["distance_to_target"], target_data["valid_mask"], target_data["plus_points"], target_data["minus_points"], epsilon=float(epsilon), weights=loss_weights)  # 计算零线损失 / Compute zero-contour loss
            optimiser.zero_grad()  # 清空梯度 / Clear gradients
            loss.backward()  # 反向传播 / Backpropagate
            optimiser.step()  # 更新系数 / Update coefficients
        coeff = alpha / (torch.linalg.norm(alpha) + 1.0e-8)  # 读取最终归一化系数 / Read final normalised coefficients
        response = torch.matmul(basis, coeff).reshape(image_size, image_size)  # 生成最终响应 / Build final response
        loss, parts = zero_contour_loss(response, target_data["target_points"], target_data["distance_to_target"], target_data["valid_mask"], target_data["plus_points"], target_data["minus_points"], epsilon=float(epsilon), weights=loss_weights)  # 重新计算损失 / Recompute loss
        loss_value = float(loss.detach().cpu())  # 读取损失浮点值 / Read scalar loss value
        if best is None or loss_value < float(best["loss"]):  # 判断是否刷新最佳 / Decide whether best improves
            best = {"loss": loss_value, "parts": {key: float(value.detach().cpu()) for key, value in parts.items()}, "alpha": coeff.detach().cpu().numpy(), "response": response.detach().cpu().numpy(), "restart": int(restart)}  # 保存最佳结果 / Store best result
    assert best is not None  # 帮助类型检查确认最佳存在 / Help type checker know best exists
    response_np = np.asarray(best["response"], dtype=np.float32)  # 读取最佳响应 / Read best response
    nodal = extract_response_nodal(response_np, float(epsilon), int(center_radius_px))  # 提取零线 / Extract zero contour
    metrics = response_metrics(response_np, np.asarray(target_data["target"], dtype=bool), float(epsilon), int(center_radius_px))  # 计算指标 / Compute metrics
    stats = modal_weight_statistics(np.asarray(best["alpha"], dtype=float), np.asarray(freqs, dtype=float), [int(mode) for mode in mode_ids])  # 计算模态统计 / Compute modal statistics
    return SubspaceResult(alpha=np.asarray(best["alpha"], dtype=np.float32), response=response_np, nodal=nodal.astype(bool), metrics=metrics, loss=float(best["loss"]), loss_parts=dict(best["parts"]), mode_ids=[int(mode) for mode in mode_ids], freqs=np.asarray(freqs, dtype=np.float32), frequency_mean_hz=float(stats["frequency_mean_hz"]), frequency_spread=float(stats["frequency_spread"]), effective_modal_count=float(stats["effective_modal_count"]), participating_modes=list(stats["participating_modes"]), metadata={"label": label, "image_size": image_size, "steps": int(steps), "restarts": int(restarts), "epsilon": float(epsilon), "best_restart": int(best["restart"])})  # 返回结构化结果 / Return structured result


def result_to_flat_record(result: SubspaceResult, prefix: str) -> dict[str, object]:  # 将结果转成 CSV 友好记录 / Convert result into CSV-friendly record
    return {f"{prefix}_iou": float(result.metrics.get("iou", 0.0)), f"{prefix}_dice": float(result.metrics.get("dice", 0.0)), f"{prefix}_layout": float(result.metrics.get("layout", 0.0)), f"{prefix}_zero_loss": float(result.loss), f"{prefix}_frequency_mean_hz": float(result.frequency_mean_hz), f"{prefix}_frequency_spread": float(result.frequency_spread), f"{prefix}_N_eff": float(result.effective_modal_count)}  # 返回扁平记录 / Return flat record
