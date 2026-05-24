from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.candidate.constraints import center_cells_for_grid  # 导入中心单元函数 / Import center-cell helper
from src.candidate.constraints import check_neighbor_constraint  # 导入约束检查函数 / Import constraint checker
from src.candidate.constraints import enforce_center_constraint  # 导入中心约束函数 / Import center constraint helper
from src.candidate.constraints import repair_neighbor_constraint  # 导入约束修复函数 / Import constraint repair helper


def generate_random_H(grid_size: int, levels: list[float], default_thickness: float, max_neighbor_diff: float, rng: np.random.Generator | None = None) -> np.ndarray:  # 生成随机厚度矩阵 / Generate random thickness matrix
    random_gen = rng or np.random.default_rng()  # 创建随机数生成器 / Create random generator
    H = random_gen.choice(np.asarray(levels, dtype=float), size=(grid_size, grid_size))  # 随机选择厚度等级 / Randomly choose thickness levels
    center_cells = center_cells_for_grid(grid_size)  # 获取中心单元 / Get center cells
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 固定中心厚度 / Fix center thickness
    H = repair_neighbor_constraint(H, levels, max_neighbor_diff, fixed_cells=center_cells)  # 修复相邻厚度约束 / Repair neighbour constraint
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 再次固定中心厚度 / Fix center thickness again
    H = repair_neighbor_constraint(H, levels, max_neighbor_diff, fixed_cells=center_cells)  # 修复中心固定后的邻居 / Repair neighbours after centre fixing
    if not check_neighbor_constraint(H, max_neighbor_diff):  # 检查最终约束 / Check final constraint
        raise ValueError("Generated matrix violates neighbour constraint. / 生成矩阵不满足相邻约束。")  # 抛出错误 / Raise error
    return H  # 返回厚度矩阵 / Return thickness matrix


def save_H_csv(H: np.ndarray, path: str | Path) -> None:  # 保存厚度矩阵 CSV / Save thickness matrix CSV
    output_path = Path(path)  # 转换为路径对象 / Convert to path object
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    np.savetxt(output_path, H, delimiter=",", fmt="%.3f")  # 保存 CSV 文件 / Save CSV file


def save_candidate(candidate_dir: str | Path, H: np.ndarray, metadata: dict) -> None:  # 保存候选结构 / Save candidate design
    path = Path(candidate_dir)  # 转换为路径对象 / Convert to path object
    path.mkdir(parents=True, exist_ok=True)  # 创建候选目录 / Create candidate directory
    save_H_csv(H, path / "H.csv")  # 保存厚度矩阵 / Save thickness matrix
    with (path / "metadata.json").open("w", encoding="utf-8") as file_obj:  # 打开元数据文件 / Open metadata file
        json.dump(metadata, file_obj, indent=2, ensure_ascii=False)  # 写入元数据 / Write metadata


def generate_candidate_batch(config: dict, generation: int = 0) -> list[str]:  # 生成一批候选 / Generate a batch of candidates
    grid_size = int(config["project"]["grid_size"])  # 读取网格尺寸 / Read grid size
    levels = list(config["thickness"]["levels_mm"])  # 读取厚度等级 / Read thickness levels
    default = float(config["thickness"]["default_mm"])  # 读取默认厚度 / Read default thickness
    max_diff = float(config["thickness"]["max_neighbor_difference_mm"])  # 读取最大相邻差 / Read max neighbour difference
    population = int(config["optimisation"]["population_size"])  # 读取候选数量 / Read population size
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    rng = np.random.default_rng(generation)  # 创建可复现随机源 / Create reproducible random source
    candidate_ids = []  # 创建候选编号列表 / Create candidate id list
    for index in range(population):  # 遍历候选编号 / Iterate candidate index
        candidate_id = f"candidate_{generation:03d}_{index:04d}"  # 构造候选编号 / Build candidate id
        H = generate_random_H(grid_size, levels, default, max_diff, rng)  # 生成厚度矩阵 / Generate thickness matrix
        metadata = {"candidate_id": candidate_id, "generation": generation, "grid_size": grid_size, "thickness_levels_mm": levels, "center_fixed": True, "created_by": "random_search"}  # 记录元数据 / Record metadata
        save_candidate(candidates_dir / candidate_id, H, metadata)  # 保存候选 / Save candidate
        candidate_ids.append(candidate_id)  # 添加候选编号 / Add candidate id
    return candidate_ids  # 返回候选编号 / Return candidate ids
