from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

from src.candidate.generate_candidate import generate_candidate_batch  # 导入候选生成 / Import candidate generation
from src.comsol.export_parameters import export_candidate_for_comsol  # 导入 COMSOL 参数导出 / Import COMSOL parameter export


def generate_random_search_batch(config: dict, generation: int = 0) -> list[str]:  # 生成随机搜索批次 / Generate random-search batch
    candidate_ids = generate_candidate_batch(config, generation)  # 生成候选结构 / Generate candidate designs
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    for candidate_id in candidate_ids:  # 遍历候选编号 / Iterate candidate ids
        export_candidate_for_comsol(candidates_dir / candidate_id)  # 导出 COMSOL 参数表 / Export COMSOL parameter table
    return candidate_ids  # 返回候选编号 / Return candidate ids


def score_available_candidates(config: dict, target_binary):  # 评分已有候选 / Score available candidates
    from src.scoring.score_candidate import score_candidate  # 延迟导入候选评分 / Lazily import candidate scoring
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    exports_dir = Path(config["paths"]["comsol_exports_dir"])  # 读取 COMSOL 导出目录 / Read COMSOL export directory
    rows = []  # 创建结果行列表 / Create result rows
    for candidate_path in sorted(candidates_dir.glob("candidate_*")):  # 遍历候选目录 / Iterate candidate directories
        export_path = exports_dir / candidate_path.name  # 构造 COMSOL 导出路径 / Build COMSOL export path
        if not export_path.exists():  # 检查导出目录是否存在 / Check whether export directory exists
            continue  # 跳过未仿真的候选 / Skip unsimulated candidate
        result = score_candidate(candidate_path, export_path, target_binary, config)  # 计算候选分数 / Score candidate
        rows.append({"candidate_id": candidate_path.name, "best_mode": result["best_mode"], "best_iou": result["best_iou"], "best_dice": result["best_dice"], "frequency_hz": result["frequency_hz"], "final_score": result["final_score"]})  # 添加排行行 / Add ranking row
    ranking = sorted(rows, key=lambda item: item["final_score"], reverse=True)  # 按最终分数排序 / Sort by final score
    with (candidates_dir / "ranked_candidates.csv").open("w", encoding="utf-8", newline="") as file_obj:  # 打开排行文件 / Open ranking file
        writer = csv.DictWriter(file_obj, fieldnames=["candidate_id", "best_mode", "best_iou", "best_dice", "frequency_hz", "final_score"])  # 创建 CSV 写入器 / Create CSV writer
        writer.writeheader()  # 写入表头 / Write header
        writer.writerows(ranking)  # 写入排行数据 / Write ranking rows
    return ranking  # 返回排行列表 / Return ranking list
