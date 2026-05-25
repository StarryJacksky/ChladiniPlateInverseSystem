from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

from src.candidate.generate_candidate import generate_candidate_batch  # 导入候选生成 / Import candidate generation
from src.comsol.export_parameters import export_candidate_for_comsol  # 导入 COMSOL 参数导出 / Import COMSOL parameter export


RANKING_FIELDNAMES = ["candidate_id", "best_mode", "best_iou", "best_dice", "best_distance_similarity", "best_overlap_balance", "best_layout_similarity", "best_area_similarity", "best_precision", "best_recall", "best_projection_similarity", "best_extent_similarity", "best_complexity_similarity", "frequency_hz", "final_score"]  # 定义排行表字段 / Define ranking table fields


def generate_random_search_batch(config: dict, generation: int = 0) -> list[str]:  # 生成随机搜索批次 / Generate random-search batch
    from src.visualisation.plot_thickness import render_candidate_preview  # 延迟导入候选预览函数 / Lazily import candidate preview function
    candidate_ids = generate_candidate_batch(config, generation)  # 生成候选结构 / Generate candidate designs
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    for candidate_id in candidate_ids:  # 遍历候选编号 / Iterate candidate ids
        export_candidate_for_comsol(candidates_dir / candidate_id, config.get("material"))  # 导出 COMSOL 参数表 / Export COMSOL parameter table
        render_candidate_preview(candidates_dir / candidate_id)  # 生成厚度预览图 / Generate thickness preview
    return candidate_ids  # 返回候选编号 / Return candidate ids


def generate_existing_candidate_previews(config: dict) -> list[Path]:  # 生成已有候选预览 / Generate previews for existing candidates
    from src.visualisation.plot_thickness import render_candidate_preview  # 延迟导入候选预览函数 / Lazily import candidate preview function
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    preview_paths = []  # 创建预览路径列表 / Create preview path list
    for candidate_path in sorted(candidates_dir.glob("candidate_*")):  # 遍历候选目录 / Iterate candidate directories
        if (candidate_path / "H.csv").exists():  # 检查厚度矩阵是否存在 / Check whether thickness matrix exists
            preview_paths.append(render_candidate_preview(candidate_path))  # 生成并记录预览 / Generate and record preview
    return preview_paths  # 返回预览路径 / Return preview paths


def score_available_candidates(config: dict, target_binary, candidate_id: str | None = None, generation: int | None = None):  # 评分已有候选 / Score available candidates
    from src.scoring.score_candidate import score_candidate  # 延迟导入候选评分 / Lazily import candidate scoring
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    exports_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取 COMSOL 导出目录 / Read COMSOL export directory
    rows = []  # 创建结果行列表 / Create result rows
    pattern = f"candidate_{generation:03d}_*" if generation is not None else "candidate_*"  # 构造候选匹配模式 / Build candidate glob pattern
    candidate_paths = [candidates_dir / candidate_id] if candidate_id else sorted(candidates_dir.glob(pattern))  # 选择候选目录 / Select candidate directories
    for candidate_path in candidate_paths:  # 遍历候选目录 / Iterate candidate directories
        if not candidate_path.exists():  # 检查候选目录是否存在 / Check whether candidate directory exists
            continue  # 跳过不存在候选 / Skip missing candidate
        export_path = exports_dir / candidate_path.name  # 构造 COMSOL 导出路径 / Build COMSOL export path
        if not export_path.exists():  # 检查导出目录是否存在 / Check whether export directory exists
            continue  # 跳过未仿真的候选 / Skip unsimulated candidate
        result = score_candidate(candidate_path, export_path, target_binary, config)  # 计算候选分数 / Score candidate
        rows.append({"candidate_id": candidate_path.name, "best_mode": result["best_mode"], "best_iou": result["best_iou"], "best_dice": result["best_dice"], "best_distance_similarity": result.get("best_distance_similarity", ""), "best_overlap_balance": result.get("best_overlap_balance", ""), "best_layout_similarity": result.get("best_layout_similarity", ""), "best_area_similarity": result.get("best_area_similarity", ""), "best_precision": result.get("best_precision", ""), "best_recall": result.get("best_recall", ""), "best_projection_similarity": result.get("best_projection_similarity", ""), "best_extent_similarity": result.get("best_extent_similarity", ""), "best_complexity_similarity": result.get("best_complexity_similarity", ""), "frequency_hz": result["frequency_hz"], "final_score": result["final_score"]})  # 添加排行行 / Add ranking row
    ranking = sorted(rows, key=lambda item: item["final_score"], reverse=True)  # 按最终分数排序 / Sort by final score
    with (candidates_dir / "ranked_candidates.csv").open("w", encoding="utf-8", newline="") as file_obj:  # 打开排行文件 / Open ranking file
        writer = csv.DictWriter(file_obj, fieldnames=RANKING_FIELDNAMES)  # 创建 CSV 写入器 / Create CSV writer
        writer.writeheader()  # 写入表头 / Write header
        writer.writerows(ranking)  # 写入排行数据 / Write ranking rows
    return ranking  # 返回排行列表 / Return ranking list
