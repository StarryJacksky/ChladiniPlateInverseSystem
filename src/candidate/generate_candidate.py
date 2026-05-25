from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
import csv  # 导入 CSV 工具 / Import CSV utilities
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


def load_parent_matrices(candidates_dir: Path, limit: int = 6) -> list[np.ndarray]:  # 读取上一轮高分候选矩阵 / Load high-scoring parent matrices
    ranking_path = candidates_dir / "ranked_candidates.csv"  # 构造排行文件路径 / Build ranking file path
    if not ranking_path.exists():  # 检查排行文件是否存在 / Check ranking file existence
        return []  # 没有排行则无父代 / Return no parents without ranking
    parents = []  # 创建父代列表 / Create parent list
    with ranking_path.open("r", encoding="utf-8", newline="") as file_obj:  # 打开排行文件 / Open ranking file
        for row in csv.DictReader(file_obj):  # 遍历排行行 / Iterate ranking rows
            candidate_id = str(row.get("candidate_id", ""))  # 读取候选编号 / Read candidate id
            matrix_path = candidates_dir / candidate_id / "H.csv"  # 构造厚度矩阵路径 / Build thickness matrix path
            if matrix_path.exists():  # 检查矩阵是否存在 / Check matrix existence
                parents.append(np.loadtxt(matrix_path, delimiter=","))  # 读取父代矩阵 / Load parent matrix
            if len(parents) >= limit:  # 检查父代数量上限 / Check parent limit
                break  # 停止读取 / Stop reading
    return parents  # 返回父代矩阵 / Return parent matrices


def random_level_near(value: float, levels: list[float], rng: np.random.Generator) -> float:  # 在邻近厚度等级中采样 / Sample a nearby thickness level
    level_array = np.asarray(levels, dtype=float)  # 转换厚度等级数组 / Convert thickness levels to array
    current = int(np.argmin(np.abs(level_array - value)))  # 找当前最近等级 / Find nearest current level
    low = max(0, current - 1)  # 计算下界索引 / Compute lower index
    high = min(len(level_array) - 1, current + 1)  # 计算上界索引 / Compute upper index
    return float(level_array[int(rng.integers(low, high + 1))])  # 返回邻近随机等级 / Return nearby random level


def generate_evolutionary_H(parents: list[np.ndarray], levels: list[float], default_thickness: float, max_neighbor_diff: float, rng: np.random.Generator) -> np.ndarray:  # 生成进化候选矩阵 / Generate evolutionary candidate matrix
    if len(parents) < 2:  # 检查父代是否足够 / Check whether enough parents exist
        return generate_random_H(parents[0].shape[0], levels, default_thickness, max_neighbor_diff, rng) if parents else generate_random_H(15, levels, default_thickness, max_neighbor_diff, rng)  # 退回随机生成 / Fall back to random generation
    first = parents[int(rng.integers(0, len(parents)))]  # 随机选择第一父代 / Choose first parent randomly
    second = parents[int(rng.integers(0, len(parents)))]  # 随机选择第二父代 / Choose second parent randomly
    mask = rng.random(first.shape) < 0.5  # 创建交叉掩膜 / Build crossover mask
    child = np.where(mask, first, second).astype(float)  # 交叉生成子代 / Build child by crossover
    mutation_rate = 0.10  # 设置变异率 / Set mutation rate
    mutation_mask = rng.random(child.shape) < mutation_rate  # 创建变异掩膜 / Build mutation mask
    for row, col in np.argwhere(mutation_mask):  # 遍历变异单元 / Iterate mutated cells
        child[row, col] = random_level_near(float(child[row, col]), levels, rng)  # 设置邻近变异厚度 / Set nearby mutated thickness
    center_cells = center_cells_for_grid(child.shape[0])  # 获取中心单元 / Get center cells
    child = enforce_center_constraint(child, center_cells, default_thickness)  # 固定中心厚度 / Fix center thickness
    child = repair_neighbor_constraint(child, levels, max_neighbor_diff, fixed_cells=center_cells)  # 修复相邻约束 / Repair neighbour constraint
    child = enforce_center_constraint(child, center_cells, default_thickness)  # 再次固定中心 / Fix centre again
    if not check_neighbor_constraint(child, max_neighbor_diff):  # 检查最终约束 / Check final constraint
        child = repair_neighbor_constraint(child, levels, max_neighbor_diff, passes=24, fixed_cells=center_cells)  # 加强修复 / Run stronger repair
    return child  # 返回子代矩阵 / Return child matrix


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
    method = str(config.get("optimisation", {}).get("method", "random_search"))  # 读取搜索方法 / Read search method
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    rng = np.random.default_rng(generation)  # 创建可复现随机源 / Create reproducible random source
    parents = load_parent_matrices(candidates_dir) if method == "evolutionary_search" and generation > 0 else []  # 读取进化父代 / Load evolutionary parents
    candidate_ids = []  # 创建候选编号列表 / Create candidate id list
    for index in range(population):  # 遍历候选编号 / Iterate candidate index
        candidate_id = f"candidate_{generation:03d}_{index:04d}"  # 构造候选编号 / Build candidate id
        H = generate_evolutionary_H(parents, levels, default, max_diff, rng) if parents else generate_random_H(grid_size, levels, default, max_diff, rng)  # 生成厚度矩阵 / Generate thickness matrix
        metadata = {"candidate_id": candidate_id, "generation": generation, "grid_size": grid_size, "thickness_levels_mm": levels, "center_fixed": True, "created_by": "evolutionary_search" if parents else "random_search"}  # 记录元数据 / Record metadata
        save_candidate(candidates_dir / candidate_id, H, metadata)  # 保存候选 / Save candidate
        candidate_ids.append(candidate_id)  # 添加候选编号 / Add candidate id
    return candidate_ids  # 返回候选编号 / Return candidate ids
