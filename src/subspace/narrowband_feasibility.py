from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import numpy as np  # 导入数值计算库 / Import numerical library

from src.subspace.free_subspace_feasibility import SubspaceResult  # 导入子空间结果结构 / Import subspace result structure
from src.subspace.free_subspace_feasibility import optimise_modal_combination  # 导入组合优化器 / Import combination optimiser
from src.subspace.load_modal_basis import ModalBasis  # 导入模态基底结构 / Import modal-basis structure


DEFAULT_BETAS = (0.05, 0.10, 0.15, 0.20)  # 默认相对频率窗宽 / Default relative bandwidths


def window_indices(freqs: np.ndarray, center_hz: float, beta: float) -> tuple[int, ...]:  # 计算一个频率窗内的模态索引 / Compute modal indices inside one frequency window
    frequency = np.asarray(freqs, dtype=float)  # 转为浮点频率数组 / Convert to float frequency array
    if center_hz <= 0.0:  # 检查中心频率有效性 / Check centre-frequency validity
        return tuple()  # 返回空窗 / Return empty window
    mask = np.abs(frequency - float(center_hz)) / float(center_hz) <= float(beta)  # 计算相对频率窗掩膜 / Compute relative frequency-window mask
    return tuple(int(index) for index in np.flatnonzero(mask))  # 返回索引元组 / Return index tuple


def unique_frequency_windows(freqs: np.ndarray, beta: float, min_modes: int = 2) -> list[tuple[float, tuple[int, ...]]]:  # 构造去重频率窗 / Build de-duplicated frequency windows
    seen: set[tuple[int, ...]] = set()  # 创建已见窗口集合 / Create seen-window set
    windows: list[tuple[float, tuple[int, ...]]] = []  # 创建窗口列表 / Create window list
    for center in np.asarray(freqs, dtype=float):  # 使用已有模态频率作为中心 / Use existing modal frequencies as centres
        indices = window_indices(freqs, float(center), float(beta))  # 计算窗口索引 / Compute window indices
        if len(indices) < int(min_modes):  # 跳过过窄窗口 / Skip too-small window
            continue  # 继续下一个中心 / Continue to next centre
        if indices in seen:  # 检查是否重复 / Check duplicate window
            continue  # 跳过重复窗口 / Skip duplicate window
        seen.add(indices)  # 记录窗口 / Record window
        windows.append((float(center), indices))  # 保存窗口 / Store window
    return windows  # 返回窗口列表 / Return window list


def narrowband_selection_score(result: SubspaceResult) -> float:  # 计算窄频带视觉选择分 / Compute visual selection score for narrowband result
    layout = float(result.metrics.get("layout", 0.0))  # 读取布局分 / Read layout score
    dice = float(result.metrics.get("dice", 0.0))  # 读取 Dice / Read Dice score
    iou = float(result.metrics.get("iou", 0.0))  # 读取 IoU / Read IoU score
    return float(layout + 0.55 * dice + 0.25 * iou - 0.08 * result.loss)  # 合成选择分 / Combine selection score


def optimise_window(basis: ModalBasis, indices: tuple[int, ...], target_binary: np.ndarray, center_frequency_hz: float, beta: float, steps: int, restarts: int, seed: int, image_size_label: str, center_radius_px: int = 0, epsilon: float = 0.045) -> SubspaceResult:  # 优化单个窄频窗口 / Optimise one narrowband window
    fields = basis.Phi[list(indices)]  # 取出窗口模态场 / Select window modal fields
    freqs = basis.freqs[list(indices)]  # 取出窗口频率 / Select window frequencies
    modes = [basis.mode_ids[index] for index in indices]  # 取出窗口模态编号 / Select window mode ids
    result = optimise_modal_combination(fields, freqs, modes, target_binary, steps=int(steps), restarts=int(restarts), center_radius_px=int(center_radius_px), epsilon=float(epsilon), seed=int(seed), label=f"narrowband_{image_size_label}")  # 运行组合优化 / Run combination optimisation
    result.metadata.update({"beta": float(beta), "window_center_frequency_hz": float(center_frequency_hz), "window_mode_ids": modes, "window_indices": list(indices), "selection_score": narrowband_selection_score(result)})  # 写入窗口元数据 / Store window metadata
    return result  # 返回窗口结果 / Return window result


def run_narrowband_scan(basis: ModalBasis, target_binary: np.ndarray, betas: tuple[float, ...] = DEFAULT_BETAS, steps: int = 260, restarts: int = 2, seed: int = 71, min_modes: int = 2, center_radius_px: int = 0, epsilon: float = 0.045) -> dict[str, object]:  # 扫描所有窄频窗 / Scan all narrowband windows
    best_by_beta: dict[float, SubspaceResult] = {}  # 创建每个 beta 的最佳结果 / Create best result per beta
    all_results: list[SubspaceResult] = []  # 创建全部结果列表 / Create all-result list
    for beta_index, beta in enumerate(betas):  # 遍历窗宽 / Iterate bandwidths
        windows = unique_frequency_windows(basis.freqs, float(beta), int(min_modes))  # 构造去重窗口 / Build de-duplicated windows
        beta_best: SubspaceResult | None = None  # 初始化该 beta 最佳结果 / Initialise best result for this beta
        for window_index, (center_hz, indices) in enumerate(windows):  # 遍历当前 beta 的窗口 / Iterate windows for current beta
            result = optimise_window(basis, indices, target_binary, center_hz, float(beta), int(steps), int(restarts), int(seed) + 1000 * beta_index + window_index, f"b{beta:.2f}", int(center_radius_px), float(epsilon))  # 优化当前窗口 / Optimise current window
            all_results.append(result)  # 保存全部结果 / Store full result
            if beta_best is None or float(result.metadata["selection_score"]) > float(beta_best.metadata["selection_score"]):  # 检查是否刷新 beta 最佳 / Check whether beta best improves
                beta_best = result  # 更新 beta 最佳 / Update beta best
        if beta_best is not None:  # 检查该 beta 是否有有效窗口 / Check whether this beta has valid windows
            best_by_beta[float(beta)] = beta_best  # 写入最佳结果 / Store best result
    return {"best_by_beta": best_by_beta, "all_results": all_results, "betas": [float(beta) for beta in betas]}  # 返回扫描结果 / Return scan result
