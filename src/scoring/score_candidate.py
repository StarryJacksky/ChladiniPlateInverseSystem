from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.candidate.constraints import mass_penalty  # 导入质量惩罚 / Import mass penalty
from src.candidate.constraints import roughness_penalty  # 导入粗糙度惩罚 / Import roughness penalty
from src.comsol.import_results import interpolate_to_grid  # 导入插值函数 / Import interpolation function
from src.comsol.import_results import load_frequencies  # 导入频率读取 / Import frequency loader
from src.comsol.import_results import load_mode_csv  # 导入模态读取 / Import mode loader
from src.nodal.extract_nodal import extract_nodal_region  # 导入节点线提取 / Import nodal extraction
from src.nodal.extract_nodal import postprocess_nodal_region  # 导入节点线后处理 / Import nodal postprocessing
from src.nodal.extract_nodal import remove_center_region  # 导入中心区域移除 / Import centre-region removal
from src.scoring.metrics import compute_dice  # 导入 Dice 指标 / Import Dice metric
from src.scoring.metrics import compute_iou  # 导入 IoU 指标 / Import IoU metric
from src.scoring.metrics import compute_overlap_balance  # 导入覆盖平衡分数 / Import overlap balance score
from src.scoring.metrics import chamfer_similarity  # 导入距离相似度 / Import distance similarity
from src.scoring.metrics import frequency_penalty  # 导入频率惩罚 / Import frequency penalty
from src.scoring.metrics import pattern_similarity  # 导入相似度合成 / Import similarity combiner


def resize_binary_to_shape(binary: np.ndarray, shape: tuple[int, int]) -> np.ndarray:  # 缩放二值图到指定尺寸 / Resize binary map to target shape
    if binary.shape == shape:  # 检查尺寸是否已匹配 / Check whether shape already matches
        return binary.astype(bool)  # 返回布尔图 / Return boolean map
    y_index = np.rint(np.linspace(0, binary.shape[0] - 1, shape[0])).astype(int)  # 生成 y 采样索引 / Build y sampling indices
    x_index = np.rint(np.linspace(0, binary.shape[1] - 1, shape[1])).astype(int)  # 生成 x 采样索引 / Build x sampling indices
    resized = binary[np.ix_(y_index, x_index)]  # 最近邻重采样 / Nearest-neighbour resampling
    return resized.astype(bool)  # 返回布尔结果 / Return boolean result


def score_candidate_modes(target_binary: np.ndarray, mode_files: list[Path], image_size: int, epsilon_ratio: float, center_radius_px: int = 0) -> dict:  # 对候选所有模态评分 / Score all candidate modes
    best = {"best_mode": None, "best_iou": -1.0, "best_dice": -1.0, "best_similarity": -1.0, "all_modes": []}  # 初始化最佳结果 / Initialise best result
    for mode_file in mode_files:  # 遍历模态文件 / Iterate mode files
        mode_number = int(mode_file.stem.split("_")[-1])  # 从文件名读取模态编号 / Read mode number from filename
        x, y, w = load_mode_csv(mode_file)  # 读取 COMSOL 位移数据 / Load COMSOL displacement data
        W = interpolate_to_grid(x, y, w, image_size)  # 插值到统一网格 / Interpolate to unified grid
        nodal = extract_nodal_region(W, epsilon_ratio)  # 提取节点线 / Extract nodal region
        nodal = postprocess_nodal_region(nodal)  # 后处理节点线 / Postprocess nodal region
        nodal = remove_center_region(nodal, center_radius_px) if center_radius_px > 0 else nodal  # 移除中心夹持区 / Remove centre clamp region
        target = resize_binary_to_shape(target_binary, nodal.shape)  # 对齐目标图尺寸 / Align target map shape
        iou = compute_iou(nodal, target)  # 计算 IoU / Compute IoU
        dice = compute_dice(nodal, target)  # 计算 Dice / Compute Dice
        distance = chamfer_similarity(nodal, target)  # 计算距离相似度 / Compute distance similarity
        overlap = compute_overlap_balance(nodal, target)  # 计算覆盖平衡 / Compute overlap balance
        similarity = pattern_similarity(iou, dice, distance, overlap)  # 合成相似度 / Combine similarity
        best["all_modes"].append({"mode": mode_number, "iou": iou, "dice": dice, "distance_similarity": distance, "overlap_balance": overlap, "similarity": similarity})  # 记录该模态结果 / Record this mode result
        if similarity > best["best_similarity"]:  # 检查是否是新最佳 / Check whether this is new best
            best.update({"best_mode": mode_number, "best_iou": iou, "best_dice": dice, "best_distance_similarity": distance, "best_overlap_balance": overlap, "best_similarity": similarity})  # 更新最佳结果 / Update best result
    return best  # 返回评分结果 / Return scoring result


def compute_final_score(H: np.ndarray, mode_score: dict, frequency: float, config: dict) -> dict:  # 计算最终分数 / Compute final score
    levels = config["thickness"]["levels_mm"]  # 读取厚度等级 / Read thickness levels
    rough = roughness_penalty(H)  # 计算粗糙度惩罚 / Compute roughness penalty
    mass = mass_penalty(H, min(levels), max(levels))  # 计算质量惩罚 / Compute mass penalty
    freq = frequency_penalty(frequency, float(config["simulation"]["frequency_min_hz"]), float(config["simulation"]["frequency_max_hz"]))  # 计算频率惩罚 / Compute frequency penalty
    score = mode_score["best_similarity"] - config["optimisation"]["roughness_weight"] * rough - config["optimisation"]["mass_weight"] * mass - config["optimisation"]["frequency_weight"] * freq  # 合成最终分数 / Combine final score
    return {"roughness_penalty": rough, "mass_penalty": mass, "frequency_penalty": freq, "final_score": float(score)}  # 返回最终分数字典 / Return final score dictionary


def score_candidate(candidate_dir: str | Path, export_dir: str | Path, target_binary: np.ndarray, config: dict) -> dict:  # 对单个候选评分 / Score one candidate
    candidate_path = Path(candidate_dir)  # 转换候选路径 / Convert candidate path
    export_path = Path(export_dir)  # 转换导出路径 / Convert export path
    H = np.loadtxt(candidate_path / "H.csv", delimiter=",")  # 读取厚度矩阵 / Load thickness matrix
    mode_files = sorted(export_path.glob("mode_*.csv"))  # 查找模态文件 / Find mode files
    if not mode_files:  # 检查是否存在模态文件 / Check whether mode files exist
        raise FileNotFoundError(f"No mode_*.csv files found in {export_path}. / 未找到模态文件。")  # 抛出缺失文件错误 / Raise missing-file error
    frequencies = load_frequencies(export_path / "frequencies.csv")  # 读取频率文件 / Load frequency file
    center_radius_px = int(int(config["nodal_extraction"]["image_size"]) * float(config["project"]["center_clamp_radius_mm"]) / float(config["project"]["plate_length_mm"])) if config["nodal_extraction"].get("remove_center_region", True) else 0  # 计算中心掩膜半径 / Compute centre mask radius
    mode_score = score_candidate_modes(target_binary, mode_files, int(config["nodal_extraction"]["image_size"]), float(config["nodal_extraction"]["epsilon_ratio"]), center_radius_px)  # 计算模态评分 / Compute mode scores
    best_frequency = frequencies.get(int(mode_score["best_mode"]), 0.0)  # 获取最佳模态频率 / Get best-mode frequency
    final_score = compute_final_score(H, mode_score, best_frequency, config)  # 计算最终分数 / Compute final score
    result = {**mode_score, "frequency_hz": best_frequency, **final_score}  # 合并结果 / Merge results
    with (candidate_path / "score.json").open("w", encoding="utf-8") as file_obj:  # 打开评分文件 / Open score file
        json.dump(result, file_obj, indent=2, ensure_ascii=False)  # 写入评分结果 / Write score result
    return result  # 返回结果 / Return result
