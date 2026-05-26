from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
import csv  # 导入 CSV 工具 / Import CSV utilities
import hashlib  # 导入稳定哈希工具 / Import stable hashing helper
import math  # 导入数学函数 / Import math functions
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.candidate.constraints import center_cells_for_grid  # 导入中心单元函数 / Import center-cell helper
from src.candidate.constraints import check_neighbor_constraint  # 导入约束检查函数 / Import constraint checker
from src.candidate.constraints import enforce_center_constraint  # 导入中心约束函数 / Import center constraint helper
from src.candidate.constraints import repair_continuous_neighbor_constraint  # 导入连续约束修复 / Import continuous constraint repair helper
from src.scoring.metrics import SCORING_VERSION  # 导入当前评分版本 / Import current scoring version


def generate_random_H(grid_size: int, levels: list[float], default_thickness: float, max_neighbor_diff: float, rng: np.random.Generator | None = None) -> np.ndarray:  # 生成随机厚度矩阵 / Generate random thickness matrix
    random_gen = rng or np.random.default_rng()  # 创建随机数生成器 / Create random generator
    H = random_gen.uniform(float(min(levels)), float(max(levels)), size=(grid_size, grid_size))  # 随机生成连续厚度 / Randomly generate continuous thicknesses
    center_cells = center_cells_for_grid(grid_size)  # 获取中心单元 / Get center cells
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 固定中心厚度 / Fix center thickness
    H = repair_candidate_matrix(H, levels, max_neighbor_diff, center_cells)  # 修复连续相邻厚度约束 / Repair continuous neighbour constraint
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 再次固定中心厚度 / Fix center thickness again
    H = repair_candidate_matrix(H, levels, max_neighbor_diff, center_cells)  # 修复中心固定后的邻居 / Repair neighbours after centre fixing
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


def random_continuous_near(value: float, levels: list[float], rng: np.random.Generator) -> float:  # 在邻近连续厚度中采样 / Sample a nearby continuous thickness
    low = float(min(levels))  # 读取最小厚度 / Read minimum thickness
    high = float(max(levels))  # 读取最大厚度 / Read maximum thickness
    span = max(high - low, 1.0e-9)  # 计算厚度跨度 / Compute thickness span
    return float(np.clip(value + rng.normal(0.0, 0.10 * span), low, high))  # 返回连续扰动厚度 / Return continuously perturbed thickness


def repair_candidate_matrix(H: np.ndarray, levels: list[float], max_neighbor_diff: float, fixed_cells: list[tuple[int, int]], passes: int = 24) -> np.ndarray:  # 修复连续候选厚度矩阵 / Repair continuous candidate thickness matrix
    return repair_continuous_neighbor_constraint(H, float(min(levels)), float(max(levels)), max_neighbor_diff, passes=passes, fixed_cells=fixed_cells)  # 调用连续约束修复 / Call continuous constraint repair


def generate_evolutionary_H(parents: list[np.ndarray], levels: list[float], default_thickness: float, max_neighbor_diff: float, rng: np.random.Generator, mutation_rate: float = 0.10) -> np.ndarray:  # 生成遗传算法候选矩阵 / Generate genetic algorithm candidate matrix
    if len(parents) < 2:  # 检查父代是否足够 / Check whether enough parents exist
        return generate_random_H(parents[0].shape[0], levels, default_thickness, max_neighbor_diff, rng) if parents else generate_random_H(15, levels, default_thickness, max_neighbor_diff, rng)  # 退回随机生成 / Fall back to random generation
    first = parents[int(rng.integers(0, len(parents)))]  # 随机选择第一父代 / Choose first parent randomly
    second = parents[int(rng.integers(0, len(parents)))]  # 随机选择第二父代 / Choose second parent randomly
    mask = rng.random(first.shape) < 0.5  # 创建交叉掩膜 / Build crossover mask
    child = np.where(mask, first, second).astype(float)  # 交叉生成子代 / Build child by crossover
    mutation_mask = rng.random(child.shape) < mutation_rate  # 创建变异掩膜 / Build mutation mask
    for row, col in np.argwhere(mutation_mask):  # 遍历变异单元 / Iterate mutated cells
        child[row, col] = random_continuous_near(float(child[row, col]), levels, rng)  # 设置连续邻近变异厚度 / Set nearby continuous mutated thickness
    center_cells = center_cells_for_grid(child.shape[0])  # 获取中心单元 / Get center cells
    child = enforce_center_constraint(child, center_cells, default_thickness)  # 固定中心厚度 / Fix center thickness
    child = repair_candidate_matrix(child, levels, max_neighbor_diff, center_cells)  # 修复连续相邻约束 / Repair continuous neighbour constraint
    child = enforce_center_constraint(child, center_cells, default_thickness)  # 再次固定中心 / Fix centre again
    if not check_neighbor_constraint(child, max_neighbor_diff):  # 检查最终约束 / Check final constraint
        child = repair_candidate_matrix(child, levels, max_neighbor_diff, center_cells, passes=32)  # 加强连续修复 / Run stronger continuous repair
    return child  # 返回子代矩阵 / Return child matrix


def load_target_binary_grid(config: dict, grid_size: int) -> np.ndarray | None:  # 读取目标图并压缩到厚度网格 / Load target image and compress to thickness grid
    target_path = Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 构造目标数组路径 / Build target array path
    if not target_path.exists():  # 检查目标数组是否存在 / Check whether target array exists
        return None  # 没有目标时返回空 / Return none without target
    binary = np.load(target_path).astype(bool)  # 读取目标二值图 / Load target binary image
    return downsample_binary_to_grid(binary, grid_size)  # 返回网格占用图 / Return grid occupancy map


def downsample_binary_to_grid(binary: np.ndarray, grid_size: int) -> np.ndarray:  # 将目标图降采样到候选网格 / Downsample target image to candidate grid
    rows, cols = binary.shape  # 读取图像尺寸 / Read image shape
    row_edges = np.linspace(0, rows, grid_size + 1).astype(int)  # 构造行边界 / Build row edges
    col_edges = np.linspace(0, cols, grid_size + 1).astype(int)  # 构造列边界 / Build column edges
    occupancy = np.zeros((grid_size, grid_size), dtype=float)  # 创建占用矩阵 / Create occupancy matrix
    for row in range(grid_size):  # 遍历目标网格行 / Iterate target-grid rows
        for col in range(grid_size):  # 遍历目标网格列 / Iterate target-grid columns
            block = binary[row_edges[row]:row_edges[row + 1], col_edges[col]:col_edges[col + 1]]  # 读取当前图像块 / Read current image block
            occupancy[row, col] = float(block.mean()) if block.size else 0.0  # 保存前景比例 / Store foreground ratio
    return occupancy  # 返回占用矩阵 / Return occupancy matrix


def normalise_design_map(values: np.ndarray) -> np.ndarray:  # 归一化设计引导图 / Normalize design guidance map
    low = float(values.min())  # 读取最小值 / Read minimum value
    high = float(values.max())  # 读取最大值 / Read maximum value
    if high - low < 1.0e-9:  # 检查是否近似常量 / Check whether nearly constant
        return np.zeros_like(values, dtype=float)  # 常量图返回零图 / Return zero map for constant input
    return (values - low) / (high - low)  # 返回 0-1 归一化图 / Return 0-1 normalized map


def smooth_design_map(values: np.ndarray, passes: int = 2) -> np.ndarray:  # 平滑设计引导图 / Smooth design guidance map
    smoothed = values.astype(float)  # 转为浮点矩阵 / Convert to float matrix
    for _ in range(passes):  # 遍历平滑轮次 / Iterate smoothing passes
        padded = np.pad(smoothed, 1, mode="edge")  # 边缘复制填充 / Pad by edge values
        smoothed = 0.40 * padded[1:-1, 1:-1] + 0.15 * padded[:-2, 1:-1] + 0.15 * padded[2:, 1:-1] + 0.15 * padded[1:-1, :-2] + 0.15 * padded[1:-1, 2:]  # 五点模板平滑 / Smooth with five-point stencil
    return smoothed  # 返回平滑结果 / Return smoothed map


def target_edge_guidance(target_grid: np.ndarray) -> np.ndarray:  # 计算目标边缘引导图 / Compute target-edge guidance map
    padded = np.pad(target_grid, 1, mode="edge")  # 边缘复制填充 / Pad by edge values
    vertical = np.abs(padded[:-2, 1:-1] - padded[2:, 1:-1])  # 计算上下梯度 / Compute vertical gradient
    horizontal = np.abs(padded[1:-1, :-2] - padded[1:-1, 2:])  # 计算左右梯度 / Compute horizontal gradient
    return normalise_design_map(vertical + horizontal)  # 返回归一化边缘图 / Return normalized edge map


def radial_design_bias(grid_size: int) -> np.ndarray:  # 生成径向破缺引导图 / Build radial design-bias map
    axis = np.linspace(-1.0, 1.0, grid_size)  # 创建归一化坐标轴 / Create normalized axis
    yy, xx = np.meshgrid(axis, axis, indexing="ij")  # 创建二维坐标网格 / Create two-dimensional coordinate grid
    radius = np.sqrt(xx * xx + yy * yy)  # 计算半径 / Compute radius
    return normalise_design_map(radius)  # 返回径向图 / Return radial map


def angular_design_bias(grid_size: int, phase: float) -> np.ndarray:  # 生成角向破缺引导图 / Build angular design-bias map
    axis = np.linspace(-1.0, 1.0, grid_size)  # 创建归一化坐标轴 / Create normalized axis
    yy, xx = np.meshgrid(axis, axis, indexing="ij")  # 创建二维坐标网格 / Create two-dimensional coordinate grid
    angle = np.arctan2(yy, xx)  # 计算极角 / Compute polar angle
    return normalise_design_map(np.sin(3.0 * angle + phase))  # 返回三瓣角向图 / Return three-lobed angular map


def laplacian_design_map(values: np.ndarray) -> np.ndarray:  # 计算设计图拉普拉斯 / Compute design-map Laplacian
    padded = np.pad(values.astype(float), 1, mode="edge")  # 边缘复制填充 / Pad by edge values
    return padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2] + padded[1:-1, 2:] - 4.0 * padded[1:-1, 1:-1]  # 返回五点拉普拉斯 / Return five-point Laplacian


def target_crossing_sign_field(target_grid: np.ndarray, axis: int) -> np.ndarray:  # 根据目标笔画构造符号翻转场 / Build sign-flip field from target strokes
    stroke = target_grid > 0.12  # 二值化目标笔画 / Binarize target strokes
    transitions = np.cumsum(stroke.astype(int), axis=axis) % 2  # 沿指定方向累积穿越次数 / Accumulate crossing parity along chosen axis
    return np.where(transitions == 0, 1.0, -1.0)  # 返回正负符号场 / Return signed parity field


def desired_modal_field(target_grid: np.ndarray, variant_index: int, rng: np.random.Generator) -> np.ndarray:  # 将目标编译为期望模态场 / Compile target into desired modal field
    from src.scoring.metrics import chamfer_distance  # 局部导入距离场工具 / Locally import distance-field helper
    stroke = target_grid > 0.12  # 二值化目标线 / Binarize target line
    distance = chamfer_distance(stroke)  # 计算到目标线的距离 / Compute distance to target line
    x_sign = target_crossing_sign_field(target_grid, axis=1)  # 构造横向穿越符号 / Build horizontal-crossing sign
    y_sign = target_crossing_sign_field(target_grid, axis=0)  # 构造纵向穿越符号 / Build vertical-crossing sign
    radial = 2.0 * radial_design_bias(target_grid.shape[0]) - 1.0  # 构造有符号径向场 / Build signed radial field
    angular = 2.0 * angular_design_bias(target_grid.shape[0], float(rng.uniform(0.0, 2.0 * np.pi))) - 1.0  # 构造有符号角向场 / Build signed angular field
    sign_variants = [x_sign, y_sign, x_sign * y_sign, np.sign(0.65 * x_sign + 0.35 * angular), np.sign(0.65 * y_sign + 0.35 * radial), np.sign(x_sign * y_sign + 0.45 * angular)]  # 组合多种符号翻转假设 / Combine sign-flip hypotheses
    sign = np.where(sign_variants[variant_index % len(sign_variants)] >= 0.0, 1.0, -1.0)  # 选择当前符号场 / Select current sign field
    field = sign * np.tanh(distance / 1.6)  # 让目标线成为期望零线 / Make target line the desired zero contour
    field = field + 0.16 * radial + 0.10 * angular  # 注入非对称低频背景 / Inject asymmetric low-frequency background
    field[stroke] = 0.0  # 强制目标笔画处为零位移 / Force zero displacement on target strokes
    return field - float(field.mean())  # 去除常量漂移 / Remove constant drift


def inverse_pde_thickness_guidance(mode_field: np.ndarray, target_grid: np.ndarray, variant_index: int) -> np.ndarray:  # 从期望模态反推厚度引导 / Infer thickness guidance from desired mode
    laplacian = laplacian_design_map(mode_field)  # 计算一阶曲率近似 / Compute curvature proxy
    bilaplacian = laplacian_design_map(laplacian)  # 计算双调和项近似 / Compute biharmonic proxy
    modal_mass = np.abs(mode_field) + 0.08  # 构造模态质量项 / Build modal mass term
    curvature = np.abs(bilaplacian) + 0.08 * np.abs(laplacian) + 0.03  # 构造曲率需求项 / Build curvature-demand term
    inferred = np.sqrt(modal_mass / curvature)  # 根据 h^2 近似反推厚度趋势 / Infer thickness trend from h-squared proxy
    stroke = normalise_design_map(target_grid)  # 归一化目标笔画 / Normalize target strokes
    edge = target_edge_guidance(stroke)  # 计算目标边缘引导 / Compute target-edge guidance
    channel = smooth_design_map(stroke, 2)  # 平滑目标通道 / Smooth target channel
    if variant_index % 4 == 0:  # 变体一：目标线附近变薄 / Variant one: thin around target line
        guidance = normalise_design_map(inferred) - 0.55 * channel + 0.25 * edge  # 合成薄节点引导 / Combine thin-node guidance
    elif variant_index % 4 == 1:  # 变体二：目标线附近变厚 / Variant two: thicken around target line
        guidance = normalise_design_map(inferred) + 0.50 * channel - 0.15 * edge  # 合成厚节点引导 / Combine thick-node guidance
    elif variant_index % 4 == 2:  # 变体三：反曲率场 / Variant three: inverse curvature field
        guidance = 1.0 - normalise_design_map(inferred) + 0.35 * edge - 0.25 * channel  # 合成反曲率引导 / Combine inverse-curvature guidance
    else:  # 变体四：曲率和目标双通道 / Variant four: curvature-plus-target dual channel
        guidance = 0.55 * normalise_design_map(curvature) + 0.25 * edge + 0.20 * (1.0 - channel)  # 合成双通道引导 / Combine dual-channel guidance
    return normalise_design_map(guidance)  # 返回归一化厚度引导 / Return normalized thickness guidance


def generate_modal_compiler_H(target_grid: np.ndarray, index: int, parents: list[np.ndarray], levels: list[float], default_thickness: float, max_neighbor_diff: float, rng: np.random.Generator) -> tuple[np.ndarray, str]:  # 生成模态编译器候选 / Generate modal-compiler candidate
    field = desired_modal_field(target_grid, index, rng)  # 构造期望模态场 / Build desired modal field
    guidance = inverse_pde_thickness_guidance(field, target_grid, index)  # 反推厚度引导 / Infer thickness guidance
    if parents and index % 3 == 2:  # 周期性混合真实高分父代 / Periodically blend real high-score parent
        guidance = normalise_design_map(0.58 * guidance + 0.42 * matrix_to_guidance(parents[int(rng.integers(0, len(parents)))], levels))  # 混合父代和编译器引导 / Blend parent and compiler guidance
    H = guidance_to_continuous_thickness(guidance, levels)  # 映射为连续厚度 / Map to continuous thicknesses
    center_cells = center_cells_for_grid(H.shape[0])  # 获取中心固定单元 / Get centre fixed cells
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 固定中心厚度 / Fix centre thickness
    H = repair_candidate_matrix(H, levels, max_neighbor_diff, center_cells, passes=40)  # 强化修复制造约束 / Strongly repair manufacturing constraints
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 再次固定中心 / Fix centre again
    return H, f"modal_compiler_inverse_pde_{index % 8}"  # 返回候选和来源 / Return candidate and source


def generate_modal_compiler_proposals(config: dict, target_grid: np.ndarray | None, parents: list[np.ndarray], levels: list[float], default_thickness: float, max_neighbor_diff: float, population: int, rng: np.random.Generator) -> list[tuple[np.ndarray, str]]:  # 生成目标模态编译提案 / Generate target-modal compiler proposals
    if target_grid is None:  # 检查目标是否存在 / Check whether target exists
        return []  # 无目标时返回空 / Return empty without target
    count = min(population, int(config.get("optimisation", {}).get("modal_compiler_count", 4)))  # 读取编译器候选数量 / Read compiler proposal count
    proposals = []  # 创建提案列表 / Create proposal list
    for index in range(max(0, count)):  # 遍历编译器变体 / Iterate compiler variants
        H, name = generate_modal_compiler_H(target_grid, index, parents, levels, default_thickness, max_neighbor_diff, rng)  # 生成一个编译器候选 / Generate one compiler candidate
        if is_diverse_candidate(H, proposals, levels, threshold=0.030):  # 检查本批多样性 / Check batch diversity
            proposals.append((H, name))  # 保存提案 / Store proposal
    return proposals  # 返回编译器提案 / Return compiler proposals


def lightly_mutate_physics_base(H: np.ndarray, levels: list[float], default_thickness: float, max_neighbor_diff: float, rng: np.random.Generator, rate: float = 0.035) -> np.ndarray:  # 轻微扰动辅助物理基底厚度 / Lightly mutate an auxiliary-physics base thickness
    proposal = H.copy().astype(float)  # 复制候选矩阵 / Copy candidate matrix
    center_cells = center_cells_for_grid(proposal.shape[0])  # 获取中心固定单元 / Get fixed centre cells
    fixed_cells = set(center_cells)  # 创建固定单元集合 / Create fixed-cell set
    mutation_mask = rng.random(proposal.shape) < rate  # 创建轻微变异掩膜 / Build light mutation mask
    for row, col in np.argwhere(mutation_mask):  # 遍历变异单元 / Iterate mutated cells
        if (int(row), int(col)) not in fixed_cells:  # 跳过中心固定单元 / Skip centre fixed cells
            proposal[row, col] = random_continuous_near(float(proposal[row, col]), levels, rng)  # 应用局部厚度扰动 / Apply local thickness perturbation
    proposal = enforce_center_constraint(proposal, center_cells, default_thickness)  # 恢复中心固定 / Restore centre constraint
    proposal = repair_candidate_matrix(proposal, levels, max_neighbor_diff, center_cells, passes=20)  # 修复制造相邻约束 / Repair manufacturable neighbour constraint
    return enforce_center_constraint(proposal, center_cells, default_thickness)  # 返回最终候选 / Return final candidate


def auxiliary_physics_variant_names() -> list[str]:  # 列出辅助物理场强策略 / List strong auxiliary-physics strategies
    return ["aux_mass_target_heavy", "aux_mass_target_light", "aux_loss_outer_suppress", "aux_inertia_edge_heavy", "aux_inertia_ring_break", "aux_low_loss_target_channel", "aux_heavy_loss_balanced", "aux_target_edge_bridge", "aux_recall_outer_trim", "aux_precision_channel_guard"]  # 返回策略名称 / Return strategy names


def auxiliary_physics_local_plan(bases: list[tuple[np.ndarray, str]], variants: list[str]) -> list[tuple[np.ndarray, str, str, int]]:  # 构建辅助物理局部测试计划 / Build auxiliary-physics local test plan
    primary_count = min(4, len(bases))  # 限制局部基底数量 / Limit local base count
    plan = []  # 创建计划列表 / Create plan list
    for base_index, (base_H, base_name) in enumerate(bases[:primary_count]):  # 遍历高分基底 / Iterate high-score bases
        for variant in variants:  # 遍历每个辅助物理策略 / Iterate each auxiliary-physics strategy
            plan.append((base_H, base_name, variant, base_index))  # 添加同厚度不同物理场测试 / Add same-thickness different-field test
    return plan  # 返回计划 / Return plan


def generate_auxiliary_physics_proposals(config: dict, candidates_dir: Path, target_grid: np.ndarray | None, response_records: list[dict], parents: list[np.ndarray], levels: list[float], default_thickness: float, max_neighbor_diff: float, population: int, generation: int, rng: np.random.Generator) -> list[tuple[np.ndarray, str]]:  # 生成独立质量阻尼提案 / Generate independent mass-damping proposals
    if target_grid is None or not config.get("design_variables", {}).get("export_auxiliary_fields", True):  # 检查辅助物理场是否可用 / Check whether auxiliary physics is available
        return []  # 无目标或未导出辅助场时返回空 / Return empty without target or auxiliary export
    count = min(population, int(config.get("optimisation", {}).get("auxiliary_physics_count", max(2, population // 3))))  # 读取辅助候选数量 / Read auxiliary proposal count
    history = filter_history_by_shape(load_surrogate_history(candidates_dir, config, limit=48), target_grid.shape)  # 读取真实评分历史 / Load real scored history
    bases = [(item["H"], item["candidate_id"]) for item in history[:10]]  # 使用高分历史作为基底 / Use high-score history as bases
    bases.extend((record["H"], record["candidate_id"]) for record in response_records)  # 追加真实响应失败记忆 / Add real-response failure memories
    bases.extend((parent, f"parent_{index}") for index, parent in enumerate(parents[:6]))  # 追加遗传父代 / Add genetic parents
    variants = auxiliary_physics_variant_names()  # 读取强策略名称 / Read strong strategy names
    local_plan = auxiliary_physics_local_plan(bases, variants)  # 构建赢家附近局部物理场计划 / Build local field plan around winners
    proposals = []  # 创建提案列表 / Create proposal list
    reference_designs = [(item["H"], item["candidate_id"]) for item in history[:18]]  # 创建历史参考设计 / Create historical reference designs
    used_names = set()  # 记录已用变体名 / Track used variant names
    attempt_count = max(count * 4, len(variants), len(local_plan))  # 设置尝试次数 / Set attempt count
    for index in range(attempt_count):  # 遍历辅助物理尝试 / Iterate auxiliary-physics attempts
        if index < len(local_plan):  # 优先测试同厚度不同物理场 / First test same thickness with different physical fields
            base_H, base_name, variant, base_index = local_plan[index]  # 读取局部计划项 / Read local plan item
            H = base_H.copy().astype(float) if index < len(variants) else lightly_mutate_physics_base(base_H, levels, default_thickness, max_neighbor_diff, rng, rate=0.012 + 0.006 * (base_index % 3))  # 保持赢家厚度或轻微扰动 / Keep winner thickness or lightly perturb
            variant_name = f"{variant}_from_{base_name}_aux_local_g{generation:03d}_{index:02d}"  # 构造局部物理场变体名 / Build local physical-field variant name
        elif bases:  # 检查是否有真实基底 / Check whether real bases exist
            base_H, base_name = bases[index % len(bases)]  # 选择基底 / Select base
            H = lightly_mutate_physics_base(base_H, levels, default_thickness, max_neighbor_diff, rng, rate=0.025 + 0.01 * (index % 3))  # 轻微扰动基底 / Lightly mutate base
            variant_name = f"{variants[index % len(variants)]}_from_{base_name}_explore_g{generation:03d}_{index:02d}"  # 构造探索变体名 / Build exploration variant name
        else:  # 无基底时使用模态编译器 / Use modal compiler without bases
            H, base_name = generate_modal_compiler_H(target_grid, index, parents, levels, default_thickness, max_neighbor_diff, rng)  # 构建模态基底 / Build modal base
            variant_name = f"{variants[index % len(variants)]}_from_{base_name}_bootstrap_g{generation:03d}_{index:02d}"  # 构造启动变体名 / Build bootstrap variant name
        if variant_name in used_names:  # 检查变体名是否重复 / Check duplicate variant name
            continue  # 跳过重复变体 / Skip duplicate variant
        keep_same_base = "_aux_local_" in variant_name  # 判断是否为同厚度局部测试 / Decide whether this is same-base local test
        thickness_ok = keep_same_base or (is_diverse_candidate(H, reference_designs, levels, threshold=0.006) and is_diverse_candidate(H, proposals, levels, threshold=0.008))  # 检查厚度多样性或局部物理例外 / Check thickness diversity or local-physics exception
        if thickness_ok:  # 检查是否保留该提案 / Check whether to keep proposal
            proposals.append((H, variant_name))  # 保存辅助提案 / Store auxiliary proposal
            used_names.add(variant_name)  # 记录已用变体名 / Record used variant name
        if len(proposals) >= count:  # 检查是否达到数量 / Check proposal count
            break  # 停止生成 / Stop generation
    return proposals  # 返回辅助物理提案 / Return auxiliary-physics proposals


def guidance_to_continuous_thickness(guidance: np.ndarray, levels: list[float]) -> np.ndarray:  # 将引导图映射为连续厚度 / Map guidance map to continuous thicknesses
    low = float(min(levels))  # 读取最小厚度 / Read minimum thickness
    high = float(max(levels))  # 读取最大厚度 / Read maximum thickness
    scaled = low + normalise_design_map(guidance) * (high - low)  # 缩放到连续厚度范围 / Scale to continuous thickness range
    return np.round(np.clip(scaled, low, high), 3)  # 返回三位小数厚度矩阵 / Return thickness matrix rounded to 0.001 mm


def build_target_guidance_variants(target_grid: np.ndarray, rng: np.random.Generator) -> list[tuple[str, np.ndarray]]:  # 构建目标感知设计变体 / Build target-aware design variants
    stroke = normalise_design_map(target_grid)  # 归一化目标笔画 / Normalize target strokes
    blurred = normalise_design_map(smooth_design_map(stroke, 3))  # 构建模糊目标图 / Build blurred target map
    edge = target_edge_guidance(stroke)  # 构建边缘引导图 / Build edge guidance map
    radial = radial_design_bias(stroke.shape[0])  # 构建径向引导图 / Build radial guidance map
    angular = angular_design_bias(stroke.shape[0], float(rng.uniform(0.0, 2.0 * np.pi)))  # 构建角向引导图 / Build angular guidance map
    variants = []  # 创建变体列表 / Create variant list
    variants.append(("target_high", 0.75 * stroke + 0.25 * edge))  # 添加目标区域偏厚变体 / Add target-thick variant
    variants.append(("target_low", 1.0 - (0.75 * stroke + 0.25 * edge)))  # 添加目标区域偏薄变体 / Add target-thin variant
    variants.append(("edge_high", 0.65 * edge + 0.35 * blurred))  # 添加边缘偏厚变体 / Add edge-thick variant
    variants.append(("edge_low", 1.0 - (0.65 * edge + 0.35 * blurred)))  # 添加边缘偏薄变体 / Add edge-thin variant
    variants.append(("stroke_radial", 0.60 * stroke + 0.25 * radial + 0.15 * angular))  # 添加径向破缺目标变体 / Add radial target-breaking variant
    variants.append(("inverse_radial", 0.55 * (1.0 - stroke) + 0.30 * radial + 0.15 * (1.0 - angular)))  # 添加反相径向变体 / Add inverse radial variant
    return [(name, normalise_design_map(values)) for name, values in variants]  # 返回归一化变体 / Return normalized variants


def blend_parent_with_guidance(parent: np.ndarray, guidance: np.ndarray, levels: list[float], rng: np.random.Generator) -> np.ndarray:  # 将父代与目标引导混合 / Blend parent design with target guidance
    guided = guidance_to_continuous_thickness(guidance, levels)  # 映射目标引导到连续厚度 / Map target guidance to continuous thickness
    blend = float(rng.uniform(0.35, 0.70))  # 随机选择引导强度 / Randomly choose guidance strength
    mixed = (1.0 - blend) * parent + blend * guided  # 混合父代和引导图 / Mix parent and guidance map
    return np.round(np.clip(mixed, float(min(levels)), float(max(levels))), 3)  # 返回连续混合矩阵 / Return continuous mixed matrix


def matrix_to_guidance(H: np.ndarray, levels: list[float]) -> np.ndarray:  # 将厚度矩阵转为 0-1 引导图 / Convert thickness matrix to 0-1 guidance map
    low = float(min(levels))  # 读取最小厚度 / Read minimum thickness
    high = float(max(levels))  # 读取最大厚度 / Read maximum thickness
    return np.clip((H.astype(float) - low) / max(high - low, 1.0e-9), 0.0, 1.0)  # 返回归一化厚度 / Return normalized thickness


def candidate_generation_number(candidate_id: str) -> int:  # 从候选编号读取代数 / Read generation number from candidate id
    parts = candidate_id.split("_")  # 拆分候选编号 / Split candidate id
    try:  # 捕获异常编号 / Catch malformed ids
        return int(parts[1])  # 返回第二段代数 / Return second-part generation
    except Exception:  # 兼容无法解析的编号 / Support unparseable ids
        return -1  # 返回最低优先级 / Return lowest priority


def safe_float(value: object, default: float = 0.0) -> float:  # 安全转换浮点数 / Safely convert to float
    try:  # 尝试转换 / Try conversion
        return float(value)  # 返回浮点值 / Return float value
    except Exception:  # 捕获空值或非法字符串 / Catch empty or invalid values
        return default  # 返回默认值 / Return default value


def score_row_from_score_file(score_path: Path) -> dict | None:  # 从评分文件构造候选行 / Build candidate row from score file
    try:  # 捕获 JSON 读取失败 / Catch JSON read failures
        with score_path.open("r", encoding="utf-8") as file_obj:  # 打开评分文件 / Open score file
            score = json.load(file_obj)  # 读取评分数据 / Read score data
    except Exception:  # 评分文件损坏时跳过 / Skip broken score files
        return None  # 返回空 / Return none
    if score.get("scoring_version") != SCORING_VERSION:  # 只使用当前评分版本 / Use only current scoring version
        return None  # 跳过旧评分 / Skip stale score
    candidate_id = score_path.parent.name  # 读取候选编号 / Read candidate id
    if not score.get("best_mode"):  # 检查是否有最佳模态 / Check best-mode presence
        return None  # 无最佳模态则跳过 / Skip without best mode
    return {"candidate_id": candidate_id, "best_mode": score.get("best_mode"), "final_score": score.get("final_score", 0.0), "best_precision": score.get("best_precision", 0.0), "best_recall": score.get("best_recall", 0.0), "source": "score_json"}  # 返回候选行 / Return candidate row


def source_performance_record(score_path: Path) -> dict | None:  # 从评分和元数据构造算法家族表现记录 / Build algorithm-family performance record from score and metadata
    metadata_path = score_path.parent / "metadata.json"  # 构造元数据路径 / Build metadata path
    if not metadata_path.exists():  # 检查元数据是否存在 / Check metadata existence
        return None  # 无元数据则跳过 / Skip without metadata
    row = score_row_from_score_file(score_path)  # 读取评分行 / Read score row
    if row is None:  # 检查评分是否可用 / Check score usability
        return None  # 不可用则跳过 / Skip unusable score
    try:  # 捕获元数据读取失败 / Catch metadata read failures
        with metadata_path.open("r", encoding="utf-8") as file_obj:  # 打开元数据文件 / Open metadata file
            metadata = json.load(file_obj)  # 读取元数据 / Read metadata
    except Exception:  # 元数据损坏时跳过 / Skip broken metadata
        return None  # 返回空 / Return none
    created_by = str(metadata.get("created_by", "unknown"))  # 读取创建来源 / Read creation source
    optimizer = str(metadata.get("latent_optimizer", ""))  # 读取潜变量优化器 / Read latent optimizer
    family = f"{created_by}:{optimizer}" if optimizer else created_by  # 构造算法家族键 / Build algorithm-family key
    return {"candidate_id": row["candidate_id"], "generation": candidate_generation_number(row["candidate_id"]), "family": family, "score": safe_float(row.get("final_score", 0.0), 0.0)}  # 返回表现记录 / Return performance record


def load_source_performance(candidates_dir: Path, limit: int) -> list[dict]:  # 读取最近算法家族真实表现 / Load recent real performance by algorithm family
    records = []  # 创建记录列表 / Create record list
    for score_path in sorted(candidates_dir.glob("candidate_*_*/score.json")):  # 遍历评分文件 / Iterate score files
        record = source_performance_record(score_path)  # 构造家族表现记录 / Build family performance record
        if record is not None:  # 检查记录是否有效 / Check record validity
            records.append(record)  # 保存记录 / Store record
    ordered = sorted(records, key=lambda item: (int(item["generation"]), float(item["score"])), reverse=True)  # 最近且高分优先排序 / Sort by recency and score
    return ordered[:max(1, limit)]  # 返回限制后的记录 / Return limited records


def top_family_mean(records: list[dict], token: str, count: int = 6) -> float:  # 计算算法家族顶部均分 / Compute top-score mean for an algorithm family
    scores = sorted([float(record["score"]) for record in records if token in str(record.get("family", ""))], reverse=True)  # 提取家族分数 / Extract family scores
    return float(np.mean(scores[:count])) if scores else -1.0e9  # 返回顶部均分或极小值 / Return top mean or tiny sentinel


def adaptive_frontload_counts(config: dict, candidates_dir: Path, latent_default: int, auxiliary_default: int, population: int) -> tuple[int, int]:  # 自适应分配候选家族前置名额 / Adaptively allocate front-loaded slots by candidate family
    optimisation = config.get("optimisation", {})  # 读取优化配置 / Read optimisation settings
    if not optimisation.get("adaptive_family_scheduling", True):  # 检查是否关闭自适应调度 / Check whether adaptive scheduling is disabled
        return latent_default, auxiliary_default  # 返回配置默认值 / Return configured defaults
    limit = int(optimisation.get("adaptive_family_history_limit", 96))  # 读取历史窗口数量 / Read history-window size
    records = load_source_performance(candidates_dir, limit)  # 读取最近真实表现 / Load recent real performance
    latent_scores = [record for record in records if "latent_physics_inverse_search" in str(record.get("family", ""))]  # 提取潜变量家族记录 / Extract latent-family records
    auxiliary_scores = [record for record in records if "auxiliary_physics_inverse_search" in str(record.get("family", ""))]  # 提取辅助物理家族记录 / Extract auxiliary-family records
    if len(latent_scores) < 4 or len(auxiliary_scores) < 4:  # 检查是否样本不足 / Check whether samples are insufficient
        return latent_default, auxiliary_default  # 样本不足时保持默认 / Keep defaults with insufficient samples
    margin = float(optimisation.get("adaptive_family_margin", 0.0012))  # 读取切换优势阈值 / Read switching margin
    min_latent = min(latent_default, int(optimisation.get("adaptive_min_latent_frontload", 2)))  # 读取潜变量最小名额 / Read minimum latent slots
    latent_mean = top_family_mean(records, "latent_physics_inverse_search")  # 计算潜变量顶部均分 / Compute latent top mean
    auxiliary_mean = top_family_mean(records, "auxiliary_physics_inverse_search")  # 计算辅助物理顶部均分 / Compute auxiliary top mean
    latent_count = latent_default  # 初始化潜变量名额 / Initialize latent slot count
    auxiliary_count = auxiliary_default  # 初始化辅助物理名额 / Initialize auxiliary slot count
    if auxiliary_mean > latent_mean + margin:  # 检查辅助物理是否显著更好 / Check whether auxiliary physics is clearly better
        shift = min(max(0, latent_default - min_latent), max(1, latent_default // 2))  # 计算从潜变量转出的名额 / Compute slots shifted away from latent family
        latent_count = max(min_latent, latent_default - shift)  # 降低潜变量名额 / Reduce latent slots
        auxiliary_count = auxiliary_default + shift  # 增加辅助物理名额 / Increase auxiliary slots
    elif latent_mean > auxiliary_mean + margin:  # 检查潜变量是否显著更好 / Check whether latent family is clearly better
        shift = max(1, auxiliary_default // 4)  # 计算转给潜变量的名额 / Compute slots shifted to latent family
        latent_count = min(population, latent_default + shift)  # 增加潜变量名额 / Increase latent slots
        auxiliary_count = max(0, auxiliary_default - shift)  # 降低辅助物理名额 / Reduce auxiliary slots
    return min(population, latent_count), min(max(0, population - min(population, latent_count)), auxiliary_count)  # 返回受人口约束的名额 / Return population-constrained slots


def load_response_guidance_rows(candidates_dir: Path, pool_limit: int) -> list[dict]:  # 读取可用于闭环的候选行 / Load candidate rows usable for closed-loop guidance
    rows = {}  # 创建候选行字典 / Create candidate-row dictionary
    ranking_path = candidates_dir / "ranked_candidates.csv"  # 构造排行文件路径 / Build ranking file path
    if ranking_path.exists():  # 检查排行是否存在 / Check ranking existence
        with ranking_path.open("r", encoding="utf-8", newline="") as file_obj:  # 打开排行文件 / Open ranking file
            for row in csv.DictReader(file_obj):  # 遍历排行候选 / Iterate ranked candidates
                candidate_id = str(row.get("candidate_id", ""))  # 读取候选编号 / Read candidate id
                if candidate_id:  # 检查编号是否有效 / Check id validity
                    rows[candidate_id] = dict(row)  # 保存排行行 / Store ranking row
    for score_path in sorted(candidates_dir.glob("candidate_*_*/score.json")):  # 遍历所有评分文件 / Iterate all score files
        row = score_row_from_score_file(score_path)  # 从评分文件构造行 / Build row from score file
        if row is not None:  # 检查是否可用 / Check row usability
            rows[row["candidate_id"]] = row  # 评分文件优先覆盖排行 / Let score file override ranking row
    ordered = sorted(rows.values(), key=lambda row: (candidate_generation_number(str(row.get("candidate_id", ""))), safe_float(row.get("final_score", 0.0))), reverse=True)  # 最新且较高分优先 / Prefer recent and higher-score rows
    return ordered[:max(1, pool_limit)]  # 返回候选池 / Return candidate-row pool


def response_record_priority(record: dict) -> float:  # 计算失败记忆优先级 / Compute failure-memory priority
    precision = float(record.get("precision", 0.0))  # 读取精度 / Read precision
    recall = float(record.get("recall", 0.0))  # 读取召回 / Read recall
    extra_ratio = float(record.get("extra_ratio", 0.0))  # 读取多余响应比例 / Read extra-response ratio
    missing_ratio = float(record.get("missing_ratio", 0.0))  # 读取缺失比例 / Read missing ratio
    generation = max(candidate_generation_number(str(record.get("candidate_id", ""))), 0)  # 读取候选代数 / Read candidate generation
    recency = min(generation / 200.0, 1.0)  # 归一化新近程度 / Normalize recency
    badness = (1.0 - precision) * 0.34 + max(0.0, recall - precision) * 0.24 + extra_ratio * 0.22 + missing_ratio * 0.10 + recency * 0.10  # 合成坏样本优先级 / Combine bad-sample priority
    return float(badness)  # 返回优先级 / Return priority


def load_response_guidance_records(config: dict, candidates_dir: Path, target_grid: np.ndarray, limit: int = 4) -> list[dict]:  # 读取上一轮真实响应作为闭环引导 / Load previous real responses as closed-loop guidance
    optimisation = config.get("optimisation", {})  # 读取优化设置 / Read optimisation settings
    record_limit = int(optimisation.get("response_guidance_limit", limit))  # 读取闭环记录数量 / Read response-guidance record count
    pool_limit = int(optimisation.get("response_guidance_pool_limit", max(record_limit * 4, 16)))  # 读取闭环候选池数量 / Read response-guidance pool size
    records = []  # 创建响应记录列表 / Create response record list
    for row in load_response_guidance_rows(candidates_dir, pool_limit):  # 遍历可用候选行 / Iterate usable candidate rows
        record = build_response_guidance_record(config, candidates_dir, row, target_grid)  # 构建单个响应记录 / Build one response record
        if record is not None:  # 检查记录是否可用 / Check whether record is usable
            records.append(record)  # 保存响应记录 / Store response record
    records = sorted(records, key=response_record_priority, reverse=True)  # 失败记忆优先 / Prioritize failure memories
    return records[:max(1, record_limit)]  # 返回响应记录 / Return response records


def build_response_guidance_record(config: dict, candidates_dir: Path, ranking_row: dict, target_grid: np.ndarray) -> dict | None:  # 构建响应闭环记录 / Build response closed-loop record
    from src.comsol.import_results import interpolate_to_grid  # 局部导入插值函数 / Locally import interpolation helper
    from src.comsol.import_results import load_mode_csv  # 局部导入模态读取 / Locally import mode CSV loader
    from src.nodal.extract_nodal import extract_nodal_region  # 局部导入节点线提取 / Locally import nodal extraction
    from src.nodal.extract_nodal import postprocess_nodal_region  # 局部导入节点线后处理 / Locally import nodal postprocessing
    from src.nodal.extract_nodal import remove_center_region  # 局部导入中心移除 / Locally import centre removal
    candidate_id = str(ranking_row.get("candidate_id", ""))  # 读取候选编号 / Read candidate id
    if not candidate_id:  # 检查候选编号 / Check candidate id
        return None  # 无编号则跳过 / Skip without id
    candidate_path = candidates_dir / candidate_id  # 构造候选路径 / Build candidate path
    matrix_path = candidate_path / "H.csv"  # 构造厚度矩阵路径 / Build thickness matrix path
    if not matrix_path.exists():  # 检查厚度矩阵是否存在 / Check whether thickness matrix exists
        return None  # 缺失矩阵则跳过 / Skip missing matrix
    try:  # 捕获响应读取失败 / Catch response-loading failures
        best_mode = int(float(ranking_row.get("best_mode", 0)))  # 读取最佳模态号 / Read best mode number
    except ValueError:  # 处理模态号异常 / Handle bad mode number
        return None  # 模态号无效则跳过 / Skip invalid mode number
    mode_file = Path(config["paths"]["comsol_exports_dir"]) / candidate_id / f"mode_{best_mode:02d}.csv"  # 构造最佳模态文件 / Build best-mode file
    if not mode_file.exists():  # 检查最佳模态文件 / Check best-mode file
        return None  # 缺失模态则跳过 / Skip missing mode file
    image_size = int(config["nodal_extraction"]["image_size"])  # 读取图像尺寸 / Read image size
    epsilon_ratio = float(config["nodal_extraction"]["epsilon_ratio"])  # 读取节点阈值比例 / Read nodal threshold ratio
    center_radius_px = int(image_size * float(config["project"]["center_clamp_radius_mm"]) / float(config["project"]["plate_length_mm"])) if config["nodal_extraction"].get("remove_center_region", True) else 0  # 计算中心移除半径 / Compute centre-removal radius
    x, y, w = load_mode_csv(mode_file)  # 读取模态位移数据 / Load mode displacement data
    W = interpolate_to_grid(x, y, w, image_size)  # 插值到图像网格 / Interpolate to image grid
    nodal = extract_nodal_region(W, epsilon_ratio)  # 提取节点线区域 / Extract nodal-line region
    nodal = postprocess_nodal_region(nodal)  # 后处理节点线 / Postprocess nodal lines
    nodal = remove_center_region(nodal, center_radius_px) if center_radius_px > 0 else nodal  # 移除中心夹持区 / Remove centre clamp area
    H = np.loadtxt(matrix_path, delimiter=",")  # 读取候选厚度矩阵 / Load candidate thickness matrix
    if tuple(H.shape) != tuple(target_grid.shape):  # 检查候选网格是否匹配当前项目 / Check whether candidate grid matches current project
        return None  # 跳过旧网格候选 / Skip old-grid candidate
    simulated_grid = downsample_binary_to_grid(nodal, target_grid.shape[0])  # 将仿真节点线压到厚度网格 / Compress simulated nodal lines to thickness grid
    missing = np.clip(target_grid - simulated_grid, 0.0, 1.0)  # 计算目标有而仿真缺失区域 / Compute target-present simulation-missing area
    extra = np.clip(simulated_grid - target_grid, 0.0, 1.0)  # 计算仿真多余区域 / Compute simulation-extra area
    score = safe_float(ranking_row.get("final_score", 0.0), 0.0)  # 读取最终分数 / Read final score
    precision = safe_float(ranking_row.get("best_precision", 0.0), 0.0)  # 读取精度 / Read precision
    recall = safe_float(ranking_row.get("best_recall", 0.0), 0.0)  # 读取召回 / Read recall
    avoid = np.clip(0.70 * extra + 0.30 * simulated_grid, 0.0, 1.0)  # 构造坏响应规避图 / Build bad-response avoidance map
    return {"candidate_id": candidate_id, "H": H, "target": target_grid, "simulated": simulated_grid, "missing": missing, "extra": extra, "avoid": avoid, "score": score, "precision": precision, "recall": recall, "extra_ratio": float(extra.mean()), "missing_ratio": float(missing.mean()), "mode": best_mode}  # 返回闭环记录 / Return closed-loop record


def response_error_guidance(record: dict, variant_index: int, levels: list[float], rng: np.random.Generator) -> tuple[np.ndarray, str]:  # 根据真实响应误差生成引导图 / Build guidance from real response error
    parent = matrix_to_guidance(record["H"], levels)  # 读取父代归一化厚度 / Read normalized parent thickness
    target = normalise_design_map(record["target"])  # 读取目标占用图 / Read target occupancy map
    simulated = normalise_design_map(record["simulated"])  # 读取仿真占用图 / Read simulated occupancy map
    missing = smooth_design_map(record["missing"], 2)  # 平滑缺失区域 / Smooth missing area
    extra = smooth_design_map(record["extra"], 2)  # 平滑多余区域 / Smooth extra area
    avoid = smooth_design_map(record.get("avoid", record["extra"]), 2)  # 平滑失败规避区域 / Smooth failure-avoidance area
    edge = target_edge_guidance(target)  # 构建目标边缘图 / Build target edge map
    radial = radial_design_bias(parent.shape[0])  # 构建径向破缺图 / Build radial breaking map
    angular = angular_design_bias(parent.shape[0], float(rng.uniform(0.0, 2.0 * np.pi)))  # 构建角向破缺图 / Build angular breaking map
    kind = variant_index % 8  # 选择闭环变体类型 / Select closed-loop variant type
    if kind == 0:  # 第一类：缺失区增厚、多余区减薄 / Type one: thicken missing and thin extra
        return normalise_design_map(0.35 * parent + 0.60 * target + 0.70 * missing - 0.70 * avoid), "error_push_positive"  # 返回正向误差推动 / Return positive error push
    if kind == 1:  # 第二类：反向符号探索 / Type two: opposite-sign exploration
        return normalise_design_map(0.38 * parent + 0.52 * (1.0 - target) + 0.30 * angular - 0.55 * avoid), "error_push_negative"  # 返回反向误差推动 / Return negative error push
    if kind == 2:  # 第三类：目标边缘和缺失区优先 / Type three: target edge and missing area first
        return normalise_design_map(0.32 * parent + 0.46 * edge + 0.70 * missing - 0.48 * avoid), "missing_edge_focus"  # 返回缺失边缘聚焦 / Return missing-edge focus
    if kind == 3:  # 第四类：强力压制多余星形臂 / Type four: strongly suppress extra star arms
        return normalise_design_map(0.45 * parent + 0.48 * target - 0.95 * avoid + 0.28 * angular), "extra_suppression"  # 返回多余响应压制 / Return extra-response suppression
    if kind == 4:  # 第五类：反相目标和径向破缺 / Type five: inverse target and radial breaking
        return normalise_design_map(0.30 * parent + 0.46 * (1.0 - target) + 0.34 * radial - 0.62 * avoid), "inverse_breaking"  # 返回反相破缺 / Return inverse breaking
    if kind == 5:  # 第六类：父代保持加非对称扰动 / Type six: parent keeping with asymmetric perturbation
        return normalise_design_map(0.58 * parent + 0.28 * target + 0.45 * angular - 0.45 * avoid), "asymmetric_parent"  # 返回非对称父代引导 / Return asymmetric parent guidance
    if kind == 6:  # 第七类：缺失区和反星形共同驱动 / Type seven: missing area and anti-star jointly drive
        return normalise_design_map(0.34 * parent + 0.62 * missing + 0.52 * (1.0 - simulated) + 0.28 * edge - 0.38 * avoid), "anti_star_missing"  # 返回反星形缺失引导 / Return anti-star missing guidance
    return normalise_design_map(0.26 * parent + 0.42 * target + 0.24 * radial + 0.30 * angular - 0.44 * avoid + rng.normal(0.0, 0.12, size=parent.shape)), "noisy_surrogate"  # 返回噪声代理探索 / Return noisy surrogate exploration


def generate_response_guided_H(records: list[dict], index: int, levels: list[float], default_thickness: float, max_neighbor_diff: float, rng: np.random.Generator) -> tuple[np.ndarray, str]:  # 生成闭环响应引导厚度矩阵 / Generate closed-loop response-guided thickness matrix
    record = records[index % len(records)]  # 选择响应记录 / Select response record
    guidance, variant = response_error_guidance(record, index, levels, rng)  # 生成误差引导图 / Build error guidance map
    H = guidance_to_continuous_thickness(guidance, levels)  # 映射为连续厚度 / Map to continuous thicknesses
    center_cells = center_cells_for_grid(H.shape[0])  # 获取中心单元 / Get center cells
    fixed_cells = set(center_cells)  # 创建固定中心集合 / Create fixed center set
    mutation_mask = rng.random(H.shape) < 0.08  # 创建闭环探索变异掩膜 / Build closed-loop exploration mutation mask
    for row, col in np.argwhere(mutation_mask):  # 遍历变异单元 / Iterate mutated cells
        if (int(row), int(col)) not in fixed_cells:  # 跳过固定中心单元 / Skip fixed centre cells
            H[row, col] = random_continuous_near(float(H[row, col]), levels, rng)  # 执行连续邻近变异 / Apply nearby continuous mutation
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 固定中心厚度 / Fix centre thickness
    H = repair_candidate_matrix(H, levels, max_neighbor_diff, center_cells, passes=32)  # 强化修复连续相邻约束 / Strongly repair continuous neighbour constraints
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 再次固定中心 / Fix centre again
    return H, f"{variant}_from_{record['candidate_id']}"  # 返回矩阵和来源 / Return matrix and source


def generate_response_closed_loop_proposals(config: dict, response_records: list[dict], levels: list[float], default_thickness: float, max_neighbor_diff: float, population: int, rng: np.random.Generator) -> list[tuple[np.ndarray, str]]:  # 生成真实响应闭环提案 / Generate real-response closed-loop proposals
    if not response_records:  # 检查是否存在真实响应记录 / Check whether real-response records exist
        return []  # 无真实记录则返回空 / Return empty without real records
    optimisation = config.get("optimisation", {})  # 读取优化配置 / Read optimisation config
    proposal_count = min(population, int(optimisation.get("response_closed_loop_count", max(4, population // 3))))  # 读取闭环提案数量 / Read closed-loop proposal count
    reference_designs = [(record["H"], str(record["candidate_id"])) for record in response_records]  # 构造真实响应参考设计 / Build real-response reference designs
    proposals = []  # 创建提案列表 / Create proposal list
    for index in range(max(0, proposal_count * 2)):  # 多试几次以通过多样性过滤 / Try extra times to pass diversity filtering
        H, name = generate_response_guided_H(response_records, index, levels, default_thickness, max_neighbor_diff, rng)  # 生成真实响应闭环候选 / Generate real-response closed-loop candidate
        proposal_name = f"response_closed_loop_{name}"  # 构造闭环来源名 / Build closed-loop source name
        if is_diverse_candidate(H, reference_designs, levels, threshold=0.014) and is_diverse_candidate(H, proposals, levels, threshold=0.026):  # 检查与真实历史和本批的差异 / Check diversity against real history and batch
            proposals.append((H, proposal_name))  # 保存提案 / Store proposal
        if len(proposals) >= proposal_count:  # 检查是否达到数量 / Check whether enough proposals exist
            break  # 停止生成 / Stop generation
    return proposals  # 返回闭环提案 / Return closed-loop proposals


def generate_target_guided_H(target_grid: np.ndarray, index: int, parents: list[np.ndarray], levels: list[float], default_thickness: float, max_neighbor_diff: float, rng: np.random.Generator) -> tuple[np.ndarray, str]:  # 生成目标感知厚度矩阵 / Generate target-aware thickness matrix
    variants = build_target_guidance_variants(target_grid, rng)  # 构建目标引导变体 / Build target guidance variants
    variant_name, guidance = variants[index % len(variants)]  # 选择当前变体 / Select current variant
    noise = rng.normal(0.0, 0.08, size=guidance.shape)  # 生成小幅探索噪声 / Generate small exploration noise
    guided = normalise_design_map(guidance + noise)  # 合成带噪引导图 / Combine guidance with noise
    if parents and index >= len(variants):  # 判断是否进入父代混合阶段 / Check whether to blend with parents
        parent = parents[int(rng.integers(0, len(parents)))]  # 随机选择父代 / Choose parent randomly
        H = blend_parent_with_guidance(parent, guided, levels, rng)  # 混合父代和目标引导 / Blend parent and target guidance
        variant_name = f"parent_{variant_name}"  # 标记父代混合变体 / Mark parent-blended variant
    else:  # 处理无父代或早期候选 / Handle no-parent or early candidate
        H = guidance_to_continuous_thickness(guided, levels)  # 直接映射连续引导图 / Directly map continuous guidance map
    center_cells = center_cells_for_grid(H.shape[0])  # 获取中心单元 / Get center cells
    mutation_rate = 0.06 if parents else 0.10  # 设置变异率 / Set mutation rate
    mutation_mask = rng.random(H.shape) < mutation_rate  # 创建变异掩膜 / Build mutation mask
    fixed_cells = set(center_cells)  # 创建中心固定集合 / Create fixed center-cell set
    for row, col in np.argwhere(mutation_mask):  # 遍历变异单元 / Iterate mutated cells
        if (int(row), int(col)) not in fixed_cells:  # 跳过中心固定单元 / Skip fixed center cells
            H[row, col] = random_continuous_near(float(H[row, col]), levels, rng)  # 执行连续邻近厚度变异 / Apply nearby continuous thickness mutation
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 固定中心厚度 / Fix center thickness
    H = repair_candidate_matrix(H, levels, max_neighbor_diff, center_cells, passes=24)  # 修复连续相邻厚度约束 / Repair continuous neighbour thickness constraint
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 再次固定中心 / Fix centre again
    return H, variant_name  # 返回矩阵和变体名 / Return matrix and variant name


def auxiliary_bounds(config: dict | None) -> dict[str, tuple[float, float, float]]:  # 读取辅助变量边界 / Read auxiliary-variable bounds
    settings = (config or {}).get("design_variables", {})  # 读取配置分区 / Read config section
    return {"density_scale": (float(settings.get("density_scale_min", 0.85)), float(settings.get("density_scale_max", 1.25)), 1.0), "loss_factor": (float(settings.get("loss_factor_min", 0.0)), float(settings.get("loss_factor_max", 0.08)), 0.0)}  # 返回边界和默认值 / Return bounds and defaults


def load_auxiliary_field(candidate_path: Path, name: str, shape: tuple[int, int], config: dict | None) -> np.ndarray:  # 读取或补齐辅助场 / Load or fill an auxiliary field
    low, high, default = auxiliary_bounds(config)[name]  # 读取字段边界 / Read field bounds
    path = candidate_path / f"{name}.csv"  # 构造字段路径 / Build field path
    if path.exists():  # 检查字段文件是否存在 / Check whether field file exists
        values = np.loadtxt(path, delimiter=",").astype(float)  # 读取字段矩阵 / Load field matrix
        if tuple(values.shape) == tuple(shape):  # 检查形状匹配 / Check shape match
            return np.clip(values, low, high)  # 返回裁剪字段 / Return clipped field
    return np.full(shape, default, dtype=float)  # 返回默认字段 / Return default field


def load_auxiliary_fields(candidate_path: Path, shape: tuple[int, int], config: dict | None) -> dict[str, np.ndarray]:  # 读取辅助变量集合 / Load auxiliary-variable set
    return {name: load_auxiliary_field(candidate_path, name, shape, config) for name in auxiliary_bounds(config)}  # 返回字段字典 / Return field dictionary


def load_surrogate_history(candidates_dir: Path, config: dict | None = None, limit: int = 120) -> list[dict]:  # 读取历史评分样本 / Load historical scored samples
    history = []  # 创建历史样本列表 / Create history sample list
    for score_path in sorted(candidates_dir.glob("candidate_*_*/score.json")):  # 遍历候选评分文件 / Iterate candidate score files
        matrix_path = score_path.parent / "H.csv"  # 构造厚度矩阵路径 / Build thickness matrix path
        if not matrix_path.exists():  # 检查厚度矩阵是否存在 / Check whether thickness matrix exists
            continue  # 跳过缺失矩阵 / Skip missing matrix
        with score_path.open("r", encoding="utf-8") as file_obj:  # 打开评分文件 / Open score file
            score = json.load(file_obj)  # 读取评分 JSON / Read score JSON
        if score.get("scoring_version") != SCORING_VERSION:  # 检查评分版本是否匹配 / Check whether scoring version matches
            continue  # 跳过旧评分样本 / Skip old-score samples
        if "best_area_similarity" not in score or "best_precision" not in score:  # 检查是否为新版评分 / Check whether score uses current metrics
            continue  # 跳过旧评分样本 / Skip old-score samples
        final_score = float(score.get("final_score", -999.0))  # 读取最终评分 / Read final score
        if np.isfinite(final_score):  # 检查评分是否有效 / Check whether score is finite
            H = np.loadtxt(matrix_path, delimiter=",")  # 读取厚度矩阵 / Load thickness matrix
            auxiliary_fields = load_auxiliary_fields(score_path.parent, tuple(H.shape), config)  # 读取辅助物理场 / Load auxiliary physical fields
            history.append({"candidate_id": score_path.parent.name, "H": H, "auxiliary_fields": auxiliary_fields, "score": final_score})  # 保存历史样本 / Store historical sample
    return sorted(history, key=lambda item: item["score"], reverse=True)[:limit]  # 返回高分优先历史 / Return high-score-first history


def filter_history_by_shape(history: list[dict], shape: tuple[int, int]) -> list[dict]:  # 按厚度矩阵形状过滤历史 / Filter history by thickness-matrix shape
    return [item for item in history if tuple(item["H"].shape) == tuple(shape)]  # 只保留当前网格样本 / Keep only current-grid samples


def normalise_auxiliary_field(values: np.ndarray, name: str, config: dict | None) -> np.ndarray:  # 归一化辅助变量场 / Normalize auxiliary-variable field
    low, high, default = auxiliary_bounds(config)[name]  # 读取字段边界 / Read field bounds
    if high - low < 1.0e-9:  # 检查范围是否退化 / Check degenerate range
        return np.full_like(values, default, dtype=float)  # 返回默认归一化场 / Return default normalized field
    return np.clip((values.astype(float) - low) / (high - low), 0.0, 1.0)  # 返回归一化字段 / Return normalized field


def surrogate_vector(H: np.ndarray, levels: list[float], auxiliary_fields: dict[str, np.ndarray] | None = None, config: dict | None = None) -> np.ndarray:  # 构建代理模型输入向量 / Build surrogate-model input vector
    fields = auxiliary_fields or {name: np.full(H.shape, default, dtype=float) for name, (_low, _high, default) in auxiliary_bounds(config).items()}  # 补齐辅助场 / Fill auxiliary fields
    parts = [matrix_to_guidance(H, levels).ravel()]  # 创建厚度向量部分 / Create thickness vector part
    parts.extend(normalise_auxiliary_field(fields[name], name, config).ravel() for name in ("density_scale", "loss_factor"))  # 添加辅助变量部分 / Add auxiliary-variable parts
    return np.concatenate(parts)  # 返回联合设计向量 / Return joint design vector


def fit_score_surrogate(history: list[dict], levels: list[float], config: dict | None = None) -> dict | None:  # 拟合轻量岭回归代理模型 / Fit lightweight ridge-regression surrogate model
    if len(history) < 6:  # 检查样本数量是否足够 / Check whether enough samples exist
        return None  # 样本太少时不使用代理 / Do not use surrogate with too few samples
    X = np.vstack([surrogate_vector(item["H"], levels, item.get("auxiliary_fields"), config) for item in history])  # 构建输入矩阵 / Build input matrix
    y = np.asarray([float(item["score"]) for item in history], dtype=float)  # 构建评分向量 / Build score vector
    x_mean = X.mean(axis=0)  # 计算输入均值 / Compute input mean
    y_mean = float(y.mean())  # 计算评分均值 / Compute score mean
    Xc = X - x_mean  # 中心化输入 / Center input matrix
    yc = y - y_mean  # 中心化评分 / Center score vector
    alpha = 0.08 + 0.02 * X.shape[1] / max(X.shape[0], 1)  # 设置岭回归正则 / Set ridge regularization
    kernel = Xc @ Xc.T + alpha * np.eye(Xc.shape[0])  # 构造对偶岭回归矩阵 / Build dual ridge matrix
    weights = np.linalg.solve(kernel, yc)  # 求解对偶权重 / Solve dual weights
    coef = Xc.T @ weights  # 还原空间系数 / Recover feature-space coefficients
    return {"x_mean": x_mean, "y_mean": y_mean, "y_min": float(y.min()), "y_max": float(y.max()), "coef": coef, "history_vectors": X, "history": history}  # 返回代理模型 / Return surrogate model


def fit_bayesian_surrogate_ensemble(history: list[dict], levels: list[float], ensemble_size: int, rng: np.random.Generator, config: dict | None = None) -> list[dict]:  # 拟合贝叶斯式自助集成代理 / Fit Bayesian-style bootstrap surrogate ensemble
    if len(history) < 6:  # 检查历史样本数量 / Check historical sample count
        return []  # 样本太少则返回空集成 / Return empty ensemble with too few samples
    ensemble = []  # 创建代理模型集成 / Create surrogate-model ensemble
    base = fit_score_surrogate(history, levels, config)  # 拟合全量基准代理 / Fit full-data baseline surrogate
    if base is not None:  # 检查基准模型是否可用 / Check whether baseline model is usable
        ensemble.append(base)  # 加入基准模型 / Add baseline model
    for _ in range(max(0, ensemble_size - len(ensemble))):  # 生成自助采样模型 / Generate bootstrap models
        sample = [history[int(rng.integers(0, len(history)))] for _ in range(len(history))]  # 有放回采样历史 / Sample history with replacement
        model = fit_score_surrogate(sample, levels, config)  # 拟合采样代理模型 / Fit sampled surrogate model
        if model is not None:  # 检查模型是否有效 / Check whether model is valid
            ensemble.append(model)  # 加入集成 / Add to ensemble
    return ensemble  # 返回集成代理 / Return surrogate ensemble


def predict_surrogate_score(surrogate: dict, H: np.ndarray, levels: list[float], auxiliary_fields: dict[str, np.ndarray] | None = None, config: dict | None = None) -> float:  # 预测代理评分 / Predict surrogate score
    vector = surrogate_vector(H, levels, auxiliary_fields, config)  # 构建候选向量 / Build candidate vector
    raw = float(surrogate["y_mean"] + np.dot(vector - surrogate["x_mean"], surrogate["coef"]))  # 计算原始预测 / Compute raw prediction
    return float(np.clip(raw, surrogate["y_min"] - 0.15, surrogate["y_max"] + 0.15))  # 裁剪到合理外推范围 / Clip to reasonable extrapolation range


def predict_bayesian_surrogate_stats(ensemble: list[dict], H: np.ndarray, levels: list[float], auxiliary_fields: dict[str, np.ndarray] | None = None, config: dict | None = None) -> tuple[float, float]:  # 预测贝叶斯集成均值和不确定性 / Predict Bayesian ensemble mean and uncertainty
    predictions = np.asarray([predict_surrogate_score(model, H, levels, auxiliary_fields, config) for model in ensemble], dtype=float)  # 计算所有代理预测 / Compute all surrogate predictions
    if predictions.size == 0:  # 检查是否无预测 / Check whether predictions are empty
        return 0.0, 0.0  # 无代理时返回零 / Return zeros without surrogate
    return float(predictions.mean()), float(predictions.std())  # 返回均值和标准差 / Return mean and standard deviation


def expected_improvement(mean: float, std: float, best_score: float) -> float:  # 计算贝叶斯期望改进 / Compute Bayesian expected improvement
    if std < 1.0e-9:  # 检查不确定性是否过小 / Check whether uncertainty is tiny
        return max(0.0, mean - best_score)  # 退化为正改进 / Fall back to positive improvement
    z_value = (mean - best_score) / std  # 计算标准化改进 / Compute normalized improvement
    cdf = 0.5 * (1.0 + math.erf(z_value / math.sqrt(2.0)))  # 计算标准正态 CDF / Compute standard normal CDF
    pdf = math.exp(-0.5 * z_value * z_value) / math.sqrt(2.0 * math.pi)  # 计算标准正态 PDF / Compute standard normal PDF
    return float((mean - best_score) * cdf + std * pdf)  # 返回期望改进 / Return expected improvement


def surrogate_novelty(surrogate: dict, H: np.ndarray, levels: list[float], auxiliary_fields: dict[str, np.ndarray] | None = None, config: dict | None = None) -> float:  # 计算候选新颖度 / Compute candidate novelty
    vector = surrogate_vector(H, levels, auxiliary_fields, config)  # 构建候选向量 / Build candidate vector
    distances = np.sqrt(np.mean(np.square(surrogate["history_vectors"] - vector), axis=1))  # 计算到历史样本距离 / Compute distances to history samples
    return float(np.clip(distances.min() / 0.35, 0.0, 1.0))  # 返回归一化新颖度 / Return normalized novelty


def target_alignment_score(H: np.ndarray, target_grid: np.ndarray, levels: list[float]) -> float:  # 计算厚度场与目标的弱对齐分 / Compute weak alignment between thickness field and target
    field = normalise_design_map(matrix_to_guidance(H, levels))  # 归一化厚度场 / Normalize thickness field
    target = normalise_design_map(target_grid)  # 归一化目标图 / Normalize target map
    inverse = 1.0 - target  # 构造反相目标 / Build inverse target
    field_norm = max(float(np.linalg.norm(field.ravel())), 1.0e-9)  # 计算厚度范数 / Compute field norm
    target_score = float(np.dot(field.ravel(), target.ravel()) / max(field_norm * float(np.linalg.norm(target.ravel())), 1.0e-9))  # 计算正相余弦 / Compute positive cosine
    inverse_score = float(np.dot(field.ravel(), inverse.ravel()) / max(field_norm * float(np.linalg.norm(inverse.ravel())), 1.0e-9))  # 计算反相余弦 / Compute inverse cosine
    return max(target_score, inverse_score)  # 返回两者较好值 / Return better alignment


def auxiliary_alignment_score(auxiliary_fields: dict[str, np.ndarray], target_grid: np.ndarray, config: dict | None = None) -> float:  # 计算辅助变量目标对齐 / Compute auxiliary-variable target alignment
    target = normalise_design_map(target_grid)  # 归一化目标图 / Normalize target map
    edge = target_edge_guidance(target)  # 计算目标边缘 / Compute target edge
    density = normalise_auxiliary_field(auxiliary_fields["density_scale"], "density_scale", config)  # 归一化密度倍率 / Normalize density scale
    loss = normalise_auxiliary_field(auxiliary_fields["loss_factor"], "loss_factor", config)  # 归一化损耗因子 / Normalize loss factor
    density_score = float(np.mean(density * target + (1.0 - density) * (1.0 - target)))  # 计算密度目标同向分 / Compute density-target agreement
    loss_score = float(np.mean(loss * edge + (1.0 - loss) * (1.0 - edge)))  # 计算损耗边缘同向分 / Compute loss-edge agreement
    return float(np.clip(0.55 * density_score + 0.45 * loss_score, 0.0, 1.0))  # 返回辅助变量对齐分 / Return auxiliary alignment score


def surrogate_gradient_candidate(parent: np.ndarray, surrogate: dict, levels: list[float], default_thickness: float, max_neighbor_diff: float, rng: np.random.Generator) -> tuple[np.ndarray, str]:  # 沿代理模型梯度生成候选 / Generate candidate along surrogate-model gradient
    guidance = matrix_to_guidance(parent, levels)  # 读取父代厚度引导 / Read parent thickness guidance
    gradient = surrogate["coef"][: parent.size].reshape(parent.shape)  # 读取厚度部分代理梯度 / Read thickness part of surrogate gradient
    gradient = normalise_design_map(gradient) - 0.5  # 归一化梯度到正负范围 / Normalize gradient to signed range
    signed = 1.0 if rng.random() < 0.65 else -1.0  # 随机选择正向或反向探索 / Randomly choose forward or reverse exploration
    guidance = normalise_design_map(guidance + signed * rng.uniform(0.25, 0.55) * gradient + rng.normal(0.0, 0.08, size=parent.shape))  # 合成代理梯度引导 / Combine surrogate-gradient guidance
    H = guidance_to_continuous_thickness(guidance, levels)  # 映射为连续厚度 / Map to continuous thicknesses
    center_cells = center_cells_for_grid(H.shape[0])  # 获取中心单元 / Get center cells
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 固定中心厚度 / Fix center thickness
    H = repair_candidate_matrix(H, levels, max_neighbor_diff, center_cells, passes=32)  # 修复连续相邻约束 / Repair continuous neighbour constraints
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 再次固定中心 / Fix centre again
    return H, "surrogate_gradient" if signed > 0 else "surrogate_reverse_gradient"  # 返回候选和名称 / Return candidate and name


def choose_pool_parent(history: list[dict], parents: list[np.ndarray], rng: np.random.Generator) -> np.ndarray:  # 选择代理池父代 / Choose parent for surrogate pool
    if history and rng.random() < 0.75:  # 优先使用高分历史样本 / Prefer high-scoring history samples
        return history[int(rng.integers(0, min(len(history), 8)))]["H"]  # 返回高分历史矩阵 / Return high-score history matrix
    if parents:  # 检查是否有进化父代 / Check whether evolutionary parents exist
        return parents[int(rng.integers(0, len(parents)))]  # 返回进化父代 / Return evolutionary parent
    return generate_random_H(15, levels=[0.6, 0.8, 0.9, 1.0, 1.3, 1.4, 1.8, 2.0], default_thickness=1.0, max_neighbor_diff=0.7, rng=rng)  # 返回兜底随机矩阵 / Return fallback random matrix


def build_surrogate_pool_candidate(pool_index: int, surrogate: dict, history: list[dict], response_records: list[dict], parents: list[np.ndarray], target_grid: np.ndarray, levels: list[float], default_thickness: float, max_neighbor_diff: float, mutation_rate: float, rng: np.random.Generator) -> tuple[np.ndarray, str]:  # 构建代理候选池成员 / Build one surrogate candidate-pool member
    kind = pool_index % 6  # 选择候选来源类型 / Select candidate source type
    if response_records and kind in {0, 1}:  # 优先使用真实响应闭环候选 / Prefer real-response closed-loop candidates
        return generate_response_guided_H(response_records, pool_index, levels, default_thickness, max_neighbor_diff, rng)  # 返回闭环候选 / Return closed-loop candidate
    if kind == 2:  # 使用目标感知候选 / Use target-aware candidate
        return generate_target_guided_H(target_grid, pool_index, parents, levels, default_thickness, max_neighbor_diff, rng)  # 返回目标感知候选 / Return target-aware candidate
    if kind in {3, 4}:  # 使用代理梯度候选 / Use surrogate-gradient candidate
        return surrogate_gradient_candidate(choose_pool_parent(history, parents, rng), surrogate, levels, default_thickness, max_neighbor_diff, rng)  # 返回代理梯度候选 / Return surrogate-gradient candidate
    return generate_evolutionary_H([item["H"] for item in history[:8]], levels, default_thickness, max_neighbor_diff, rng, mutation_rate), "surrogate_genetic_pool"  # 返回代理池遗传候选 / Return surrogate-pool genetic candidate


def proposal_matrix(proposal: tuple) -> np.ndarray:  # 读取提案厚度矩阵 / Read proposal thickness matrix
    return proposal[0]  # 返回第一项厚度矩阵 / Return first tuple item as thickness matrix


def proposal_name(proposal: tuple) -> str:  # 读取提案名称 / Read proposal name
    return str(proposal[1])  # 返回第二项名称 / Return second tuple item as name


def proposal_auxiliary_fields(proposal: tuple) -> dict[str, np.ndarray] | None:  # 读取提案自带辅助场 / Read proposal-owned auxiliary fields
    return proposal[2] if len(proposal) > 2 else None  # 三元提案返回辅助场 / Return auxiliary fields for three-part proposals


def proposal_metadata(proposal: tuple) -> dict:  # 读取提案自带元数据 / Read proposal-owned metadata
    return dict(proposal[3]) if len(proposal) > 3 else {}  # 四元提案返回元数据副本 / Return metadata copy for four-part proposals


def is_diverse_candidate(H: np.ndarray, selected: list[tuple], levels: list[float], threshold: float = 0.055) -> bool:  # 判断候选是否足够多样 / Decide whether candidate is diverse enough
    if not selected:  # 检查是否尚无已选候选 / Check whether no candidates are selected yet
        return True  # 第一个候选总是保留 / Always keep first candidate
    vector = matrix_to_guidance(H, levels).ravel()  # 构建厚度多样性向量 / Build thickness diversity vector
    distances = [float(np.sqrt(np.mean(np.square(vector - matrix_to_guidance(proposal_matrix(item), levels).ravel())))) for item in selected]  # 计算到已选候选距离 / Compute distances to selected candidates
    return min(distances) >= threshold  # 返回是否超过阈值 / Return whether distance exceeds threshold


def proposal_source_key(name: str) -> str:  # 提取代理提案来源类型 / Extract surrogate proposal source type
    return name.split("_from_")[0].split("_pred_")[0]  # 返回去掉来源和预测后缀的名称 / Return name without source and prediction suffix


def kl_proxy_candidate_score(H: np.ndarray, target_grid: np.ndarray, config: dict) -> float:  # 计算 KL 代理候选分 / Compute KL proxy candidate score
    from src.physics.kirchhoff_love import score_thickness_with_kl_proxy  # 局部导入 KL 代理评分 / Locally import KL proxy scoring
    mode_count = int(config.get("optimisation", {}).get("kl_proxy_num_modes", 10))  # 读取 KL 代理模态数量 / Read KL proxy mode count
    return float(score_thickness_with_kl_proxy(H, target_grid, config, num_modes=mode_count)["kl_proxy_score"])  # 返回 KL 代理分数 / Return KL proxy score


def nearest_history_item(H: np.ndarray, history: list[dict], levels: list[float]) -> tuple[dict | None, float]:  # 查找最近真实历史样本 / Find nearest real-history sample
    if not history:  # 检查历史是否为空 / Check whether history is empty
        return None, 1.0e9  # 返回空和大距离 / Return none and large distance
    vector = matrix_to_guidance(H, levels).ravel()  # 构建候选厚度向量 / Build candidate thickness vector
    best_item = None  # 初始化最近样本 / Initialize nearest sample
    best_distance = 1.0e9  # 初始化最近距离 / Initialize nearest distance
    for item in history:  # 遍历真实历史样本 / Iterate real-history samples
        other = matrix_to_guidance(item["H"], levels).ravel()  # 构建历史厚度向量 / Build historical thickness vector
        distance = float(np.sqrt(np.mean(np.square(vector - other))))  # 计算均方根距离 / Compute root-mean-square distance
        if distance < best_distance:  # 检查是否更近 / Check whether this sample is nearer
            best_item = item  # 更新最近样本 / Update nearest sample
            best_distance = distance  # 更新最近距离 / Update nearest distance
    return best_item, best_distance  # 返回最近样本和距离 / Return nearest sample and distance


def real_history_proxy_adjustment(H: np.ndarray, history: list[dict], levels: list[float], config: dict) -> float:  # 基于真实历史校准代理分 / Calibrate proxy score from real history
    if not history:  # 检查历史是否为空 / Check whether history is empty
        return 0.0  # 无历史则不调整 / Do not adjust without history
    optimisation = config.get("optimisation", {})  # 读取优化配置 / Read optimisation config
    radius = float(optimisation.get("kl_proxy_real_history_radius", 0.10))  # 读取真实历史影响半径 / Read real-history influence radius
    penalty_weight = float(optimisation.get("kl_proxy_real_penalty_weight", 0.18))  # 读取坏历史惩罚权重 / Read bad-history penalty weight
    reward_weight = float(optimisation.get("kl_proxy_real_reward_weight", 0.045))  # 读取好历史奖励权重 / Read good-history reward weight
    scores = [float(item["score"]) for item in history]  # 提取真实分数 / Extract real scores
    best_score = max(scores)  # 读取历史最佳真实分 / Read best real score
    score_span = max(best_score - min(scores), 0.025)  # 计算稳定分数跨度 / Compute stable score span
    nearest, distance = nearest_history_item(H, history, levels)  # 查找最近历史样本 / Find nearest history sample
    if nearest is None:  # 检查是否无最近样本 / Check whether no nearest sample exists
        return 0.0  # 无样本则不调整 / Do not adjust without a sample
    closeness = math.exp(-float(distance * distance) / max(radius * radius, 1.0e-9))  # 计算距离权重 / Compute distance weight
    nearest_score = float(nearest["score"])  # 读取最近样本分数 / Read nearest sample score
    bad_gap = float(np.clip((best_score - nearest_score) / score_span, 0.0, 1.0))  # 计算坏样本差距 / Compute bad-sample gap
    good_gain = float(np.clip((nearest_score - (best_score - 0.25 * score_span)) / max(0.25 * score_span, 1.0e-9), 0.0, 1.0))  # 计算好样本奖励 / Compute good-sample reward
    return reward_weight * closeness * good_gain - penalty_weight * closeness * bad_gap  # 返回净调整 / Return net adjustment


def calibrated_kl_proxy_candidate_score(H: np.ndarray, target_grid: np.ndarray, config: dict, levels: list[float], history: list[dict]) -> float:  # 计算真实历史校准后的 KL 分 / Compute real-history-calibrated KL score
    raw_score = kl_proxy_candidate_score(H, target_grid, config)  # 计算原始 KL 代理分 / Compute raw KL proxy score
    adjustment = real_history_proxy_adjustment(H, history, levels, config)  # 计算真实历史校准量 / Compute real-history calibration
    return float(np.clip(raw_score + adjustment, 0.0, 1.0))  # 返回校准后分数 / Return calibrated score


def free_design_cells(shape: tuple[int, int], fixed_cells: list[tuple[int, int]]) -> list[tuple[int, int]]:  # 构建可优化单元列表 / Build optimisable cell list
    fixed = set(fixed_cells)  # 创建固定单元集合 / Create fixed-cell set
    return [(row, col) for row in range(shape[0]) for col in range(shape[1]) if (row, col) not in fixed]  # 返回非固定单元 / Return non-fixed cells


def perturb_proxy_candidate(H: np.ndarray, levels: list[float], default_thickness: float, max_neighbor_diff: float, fixed_cells: list[tuple[int, int]], free_cells: list[tuple[int, int]], step_scale: float, mutation_cells: int, rng: np.random.Generator) -> np.ndarray:  # 扰动 KL 代理候选 / Perturb KL proxy candidate
    proposal = H.copy()  # 复制当前厚度场 / Copy current thickness field
    low = float(min(levels))  # 读取最小厚度 / Read minimum thickness
    high = float(max(levels))  # 读取最大厚度 / Read maximum thickness
    for _ in range(max(1, mutation_cells)):  # 遍历扰动单元数量 / Iterate mutation-cell count
        row, col = free_cells[int(rng.integers(0, len(free_cells)))]  # 随机选择可优化单元 / Choose a random optimisable cell
        proposal[row, col] = float(np.clip(proposal[row, col] + rng.normal(0.0, step_scale), low, high))  # 应用连续厚度扰动 / Apply continuous thickness perturbation
    proposal = enforce_center_constraint(proposal, fixed_cells, default_thickness)  # 恢复中心固定 / Restore centre constraint
    proposal = repair_candidate_matrix(proposal, levels, max_neighbor_diff, fixed_cells, passes=18)  # 修复制造相邻约束 / Repair manufacturable neighbour constraint
    return enforce_center_constraint(proposal, fixed_cells, default_thickness)  # 返回中心固定后的提案 / Return proposal after centre fixing


def optimise_kl_proxy_seed(seed: np.ndarray, target_grid: np.ndarray, levels: list[float], default_thickness: float, max_neighbor_diff: float, config: dict, rng: np.random.Generator, history: list[dict] | None = None) -> tuple[np.ndarray, float]:  # 用 KL 代理直接优化种子 / Directly optimise a seed with KL proxy
    fixed_cells = center_cells_for_grid(seed.shape[0])  # 读取中心固定单元 / Read centre fixed cells
    free_cells = free_design_cells(seed.shape, fixed_cells)  # 读取可优化单元 / Read optimisable cells
    current = repair_candidate_matrix(enforce_center_constraint(seed, fixed_cells, default_thickness), levels, max_neighbor_diff, fixed_cells, passes=32)  # 修复初始种子 / Repair initial seed
    real_history = history or []  # 读取真实历史样本 / Read real-history samples
    current_score = calibrated_kl_proxy_candidate_score(current, target_grid, config, levels, real_history)  # 计算当前校准 KL 分 / Compute current calibrated KL score
    best = current.copy()  # 保存最佳厚度场 / Store best thickness field
    best_score = current_score  # 保存最佳分数 / Store best score
    optimisation = config.get("optimisation", {})  # 读取优化配置 / Read optimisation config
    steps = int(optimisation.get("kl_proxy_local_steps", 72))  # 读取局部搜索步数 / Read local-search steps
    start_temperature = float(optimisation.get("kl_proxy_start_temperature", 0.035))  # 读取初始退火温度 / Read initial annealing temperature
    end_temperature = float(optimisation.get("kl_proxy_end_temperature", 0.004))  # 读取末端退火温度 / Read final annealing temperature
    span = max(float(max(levels)) - float(min(levels)), 1.0e-9)  # 计算厚度范围 / Compute thickness span
    for step in range(max(1, steps)):  # 遍历局部搜索步 / Iterate local-search steps
        progress = step / max(steps - 1, 1)  # 计算退火进度 / Compute annealing progress
        step_scale = span * (0.34 * (1.0 - progress) + 0.045)  # 计算当前扰动尺度 / Compute current perturbation scale
        global_fraction = 0.12 * (1.0 - progress) + 0.025  # 计算全局扰动比例 / Compute global mutation fraction
        mutation_cells = max(2, int(round(len(free_cells) * global_fraction)))  # 选择本步扰动单元数 / Choose mutation-cell count for this step
        mutation_cells = min(len(free_cells), mutation_cells * (3 if step % 11 == 0 else 1))  # 周期性执行大跳跃 / Periodically run large jumps
        proposal = perturb_proxy_candidate(current, levels, default_thickness, max_neighbor_diff, fixed_cells, free_cells, step_scale, mutation_cells, rng)  # 生成局部提案 / Build local proposal
        proposal_score = calibrated_kl_proxy_candidate_score(proposal, target_grid, config, levels, real_history)  # 计算提案校准 KL 分 / Compute proposal calibrated KL score
        temperature = max(1.0e-6, start_temperature * (1.0 - progress) + end_temperature * progress)  # 计算当前温度 / Compute current temperature
        accept = proposal_score >= current_score or rng.random() < math.exp((proposal_score - current_score) / temperature)  # 判断是否接受提案 / Decide whether to accept proposal
        if accept:  # 检查是否接受 / Check acceptance
            current = proposal  # 更新当前厚度场 / Update current thickness field
            current_score = proposal_score  # 更新当前分数 / Update current score
        if proposal_score > best_score:  # 检查是否刷新最佳 / Check whether best improves
            best = proposal.copy()  # 保存最佳厚度场 / Store best thickness field
            best_score = proposal_score  # 保存最佳分数 / Store best score
    return best, best_score  # 返回最佳厚度场和 KL 分 / Return best thickness field and KL score


def build_kl_proxy_seed(index: int, history: list[dict], response_records: list[dict], parents: list[np.ndarray], target_grid: np.ndarray, levels: list[float], default_thickness: float, max_neighbor_diff: float, rng: np.random.Generator) -> tuple[np.ndarray, str]:  # 构建 KL 代理优化种子 / Build KL proxy optimisation seed
    if response_records and index % 5 in {0, 1}:  # 优先使用真实 COMSOL 响应误差 / Prefer real COMSOL response error
        H, name = generate_response_guided_H(response_records, index, levels, default_thickness, max_neighbor_diff, rng)  # 生成真实响应引导种子 / Generate real-response-guided seed
        return H, f"response_{name}"  # 返回响应闭环种子 / Return response-closed-loop seed
    if history and index % 5 == 2:  # 其次复用真实高分历史 / Then reuse real high-scoring history
        item = history[int((index // 4) % min(len(history), 12))]  # 选择历史样本 / Select historical sample
        return item["H"], f"history_{item['candidate_id']}"  # 返回历史种子 / Return history seed
    if parents and index % 5 == 3:  # 再次复用遗传父代 / Then reuse genetic parents
        return parents[int(rng.integers(0, len(parents)))], "parent_seed"  # 返回父代种子 / Return parent seed
    if index % 5 == 4:  # 使用目标感知种子 / Use target-aware seed
        H, name = generate_target_guided_H(target_grid, index + 1000, parents, levels, default_thickness, max_neighbor_diff, rng)  # 生成目标感知种子 / Generate target-aware seed
        return H, f"target_{name}"  # 返回目标种子 / Return target seed
    return generate_random_H(target_grid.shape[0], levels, default_thickness, max_neighbor_diff, rng), "random_seed"  # 返回随机种子 / Return random seed


def generate_kl_proxy_optimised_proposals(config: dict, candidates_dir: Path, target_grid: np.ndarray | None, response_records: list[dict], parents: list[np.ndarray], levels: list[float], default_thickness: float, max_neighbor_diff: float, population: int, rng: np.random.Generator) -> list[tuple[np.ndarray, str]]:  # 生成 KL 直接优化提案 / Generate directly KL-optimised proposals
    if target_grid is None:  # 检查目标网格是否存在 / Check whether target grid exists
        return []  # 无目标则无法直接优化 / Cannot directly optimise without target
    optimisation = config.get("optimisation", {})  # 读取优化配置 / Read optimisation config
    proposal_count = min(population, int(optimisation.get("kl_proxy_optimised_count", max(4, population // 3))))  # 读取 KL 优化候选数量 / Read KL-optimised proposal count
    history = filter_history_by_shape(load_surrogate_history(candidates_dir, config, limit=80), target_grid.shape)  # 读取并过滤历史真实评分样本 / Load and filter historical real-score samples
    reference_designs = [(item["H"], item["candidate_id"]) for item in history[:24]] + [(record["H"], record["candidate_id"]) for record in response_records]  # 汇总历史参考矩阵 / Collect historical reference matrices
    proposals = []  # 创建提案列表 / Create proposal list
    for index in range(max(0, proposal_count)):  # 遍历 KL 优化候选 / Iterate KL-optimised proposals
        seed, seed_name = build_kl_proxy_seed(index, history, response_records, parents, target_grid, levels, default_thickness, max_neighbor_diff, rng)  # 构建优化种子 / Build optimisation seed
        H, score = optimise_kl_proxy_seed(seed, target_grid, levels, default_thickness, max_neighbor_diff, config, rng, history)  # 执行真实校准 KL 局部优化 / Run real-calibrated KL local optimisation
        name = f"kl_proxy_optimised_{seed_name}_score_{score:.3f}"  # 构造来源名称 / Build source name
        if is_diverse_candidate(H, reference_designs, levels, threshold=0.018) and is_diverse_candidate(H, proposals, levels, threshold=0.035):  # 检查历史和本批多样性 / Check historical and batch diversity
            proposals.append((H, name))  # 保存多样提案 / Store diverse proposal
    return proposals[:population]  # 返回数量受限的提案 / Return proposal-limited list


def generate_surrogate_proposals(config: dict, candidates_dir: Path, target_grid: np.ndarray | None, response_records: list[dict], parents: list[np.ndarray], levels: list[float], default_thickness: float, max_neighbor_diff: float, population: int, rng: np.random.Generator) -> list[tuple[np.ndarray, str]]:  # 生成代理优化提案 / Generate surrogate-optimised proposals
    if target_grid is None:  # 检查目标网格是否存在 / Check whether target grid exists
        return []  # 无目标则不使用代理 / Do not use surrogate without target
    optimisation = config.get("optimisation", {})  # 读取优化配置 / Read optimisation config
    history = filter_history_by_shape(load_surrogate_history(candidates_dir, config), target_grid.shape)  # 读取并过滤历史评分样本 / Load and filter historical scored samples
    surrogate = fit_score_surrogate(history, levels, config)  # 拟合代理模型 / Fit surrogate model
    if surrogate is None:  # 检查代理模型是否可用 / Check whether surrogate is available
        return []  # 样本不足则返回空 / Return empty when samples are insufficient
    ensemble = fit_bayesian_surrogate_ensemble(history, levels, int(optimisation.get("bayesian_ensemble_size", 12)), rng, config)  # 拟合贝叶斯式代理集成 / Fit Bayesian-style surrogate ensemble
    if not ensemble:  # 检查集成是否可用 / Check whether ensemble is usable
        return []  # 无集成则返回空 / Return empty without ensemble
    best_score = float(max(item["score"] for item in history))  # 读取历史最佳分 / Read historical best score
    pool = []  # 创建候选池 / Create candidate pool
    configured_pool_size = int(optimisation.get("bayesian_virtual_pool_size", max(72, population * 28)))  # 读取配置候选池大小 / Read configured candidate-pool size
    pool_size = min(configured_pool_size, max(48, population * 10))  # 将交互式候选池限制到实用规模 / Clamp interactive candidate pool to a practical size
    beta = float(optimisation.get("bayesian_ucb_beta", 0.35))  # 读取 UCB 探索强度 / Read UCB exploration strength
    ei_weight = float(optimisation.get("bayesian_expected_improvement_weight", 0.25))  # 读取期望改进权重 / Read expected-improvement weight
    kl_weight = float(optimisation.get("kl_proxy_weight", 0.35))  # 读取 KL 代理权重 / Read KL proxy weight
    kl_cap = float(optimisation.get("kl_proxy_surrogate_cap", 0.20))  # 读取 KL 校准增益上限 / Read KL calibration-gain cap
    kl_pool_stride = max(1, int(optimisation.get("kl_proxy_pool_stride", 4)))  # 读取候选池 KL 精算步长 / Read pool KL exact-scoring stride
    novelty_weight = float(optimisation.get("novelty_weight", 0.18))  # 读取新颖度权重 / Read novelty weight
    mutation_rate = float(optimisation.get("genetic_mutation_rate", 0.12))  # 读取遗传算法变异率 / Read genetic algorithm mutation rate
    for pool_index in range(pool_size):  # 遍历虚拟候选 / Iterate virtual candidates
        H, name = build_surrogate_pool_candidate(pool_index, surrogate, history, response_records, parents, target_grid, levels, default_thickness, max_neighbor_diff, mutation_rate, rng)  # 生成池候选 / Generate pool candidate
        auxiliary_fields = build_auxiliary_design_fields(H, levels, target_grid, config, None, name)  # 构建确定性辅助物理场 / Build deterministic auxiliary physical fields
        predicted, uncertainty = predict_bayesian_surrogate_stats(ensemble, H, levels, auxiliary_fields, config)  # 预测贝叶斯均值和不确定性 / Predict Bayesian mean and uncertainty
        improvement = expected_improvement(predicted, uncertainty, best_score)  # 计算期望改进 / Compute expected improvement
        novelty = surrogate_novelty(surrogate, H, levels, auxiliary_fields, config)  # 计算候选新颖度 / Compute candidate novelty
        alignment = target_alignment_score(H, target_grid, levels)  # 计算弱目标对齐 / Compute weak target alignment
        auxiliary_alignment = auxiliary_alignment_score(auxiliary_fields, target_grid, config)  # 计算辅助变量对齐 / Compute auxiliary-variable alignment
        kl_score = calibrated_kl_proxy_candidate_score(H, target_grid, config, levels, history) if pool_index % kl_pool_stride == 0 else alignment  # 间隔执行昂贵且真实校准的 KL 精算 / Run expensive and real-calibrated KL exact scoring at intervals
        kl_anchor = min(alignment, auxiliary_alignment)  # 使用保守对齐锚点 / Use conservative alignment anchor
        calibrated_kl = min(kl_score, kl_anchor + kl_cap)  # 校准 KL 代理避免压过真实历史 / Calibrate KL proxy so it cannot overpower real history
        acquisition = predicted + beta * uncertainty + ei_weight * improvement + novelty_weight * novelty + 0.04 * alignment + 0.035 * auxiliary_alignment + kl_weight * calibrated_kl  # 合成贝叶斯采集函数 / Combine Bayesian acquisition function
        pool.append((acquisition, predicted, uncertainty, improvement, novelty, kl_score, H, name, alignment, auxiliary_alignment, calibrated_kl))  # 保存池候选 / Store pool candidate
    selected = []  # 创建已选提案列表 / Create selected proposal list
    source_counts = {}  # 创建来源计数字典 / Create source-count dictionary
    source_limit = max(1, population // 2)  # 设置单一来源上限 / Set per-source limit
    for acquisition, predicted, uncertainty, improvement, novelty, kl_score, H, name, alignment, auxiliary_alignment, calibrated_kl in sorted(pool, key=lambda item: item[0], reverse=True):  # 按采集函数排序 / Sort by acquisition value
        source = proposal_source_key(name)  # 提取提案来源 / Extract proposal source
        if source_counts.get(source, 0) >= source_limit:  # 检查来源是否过度集中 / Check whether one source is overused
            continue  # 跳过过度集中的来源 / Skip overused source
        if is_diverse_candidate(H, selected, levels):  # 检查候选多样性 / Check candidate diversity
            selected.append((H, f"{name}_mean_{predicted:.3f}_std_{uncertainty:.3f}_ei_{improvement:.3f}_kl_{kl_score:.3f}_ckl_{calibrated_kl:.3f}_ta_{alignment:.2f}_aux_{auxiliary_alignment:.2f}_novel_{novelty:.2f}"))  # 保存多样候选 / Store diverse candidate
            source_counts[source] = source_counts.get(source, 0) + 1  # 更新来源计数 / Update source count
        if len(selected) >= population:  # 检查是否已满足数量 / Check whether enough proposals are selected
            break  # 停止选择 / Stop selecting
    return selected if len(selected) >= population else [(item[6], f"{item[7]}_ta_{item[8]:.2f}_aux_{item[9]:.2f}_ckl_{item[10]:.3f}_bayesian_fallback") for item in sorted(pool, key=lambda row: row[0], reverse=True)[:population]]  # 返回提案或兜底高分池 / Return proposals or fallback top pool


def interleave_proposal_groups(groups: list[list[tuple[np.ndarray, str]]], population: int) -> list[tuple[np.ndarray, str]]:  # 交错合并候选家族 / Interleave candidate proposal families
    output = []  # 创建输出列表 / Create output list
    max_length = max((len(group) for group in groups), default=0)  # 读取最长家族长度 / Read longest family length
    for index in range(max_length):  # 遍历家族内部序号 / Iterate index within families
        for group in groups:  # 遍历候选家族 / Iterate proposal families
            if index < len(group):  # 检查当前家族是否有该序号 / Check whether family has this index
                output.append(group[index])  # 添加交错候选 / Add interleaved proposal
            if len(output) >= population:  # 检查是否达到人口数量 / Check whether population is reached
                return output  # 提前返回结果 / Return result early
    return output  # 返回交错结果 / Return interleaved result


def save_H_csv(H: np.ndarray, path: str | Path) -> None:  # 保存厚度矩阵 CSV / Save thickness matrix CSV
    output_path = Path(path)  # 转换为路径对象 / Convert to path object
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    np.savetxt(output_path, H, delimiter=",", fmt="%.3f")  # 保存 CSV 文件 / Save CSV file


def scale_field(values: np.ndarray, low: float, high: float) -> np.ndarray:  # 缩放归一化场到物理范围 / Scale normalized field to physical range
    return low + normalise_design_map(values) * (high - low)  # 返回缩放场 / Return scaled field


def stable_auxiliary_rng(H: np.ndarray, variant_name: str) -> np.random.Generator:  # 构建稳定辅助变量随机源 / Build stable auxiliary-variable random generator
    rounded = np.ascontiguousarray(np.round(H.astype(float), 4))  # 压缩厚度矩阵用于哈希 / Compress thickness matrix for hashing
    payload = rounded.tobytes() + variant_name.encode("utf-8", errors="ignore")  # 构造哈希载荷 / Build hash payload
    digest = hashlib.blake2b(payload, digest_size=8).digest()  # 计算稳定摘要 / Compute stable digest
    seed = int.from_bytes(digest, "little", signed=False)  # 转换为随机种子 / Convert digest to random seed
    return np.random.default_rng(seed)  # 返回随机源 / Return random generator


def build_auxiliary_noise(shape: tuple[int, int], rng: np.random.Generator | None) -> np.ndarray:  # 构建辅助变量探索噪声 / Build auxiliary-variable exploration noise
    random_gen = rng or np.random.default_rng(0)  # 读取随机源 / Read random generator
    noise = random_gen.normal(0.0, 1.0, size=shape)  # 生成高斯噪声 / Generate Gaussian noise
    return normalise_design_map(smooth_design_map(noise, 2))  # 平滑并归一化噪声 / Smooth and normalize noise


def build_auxiliary_design_fields(H: np.ndarray, levels: list[float], target_grid: np.ndarray | None, config: dict, rng: np.random.Generator | None = None, variant_name: str = "") -> dict[str, np.ndarray]:  # 构建辅助设计变量场 / Build auxiliary design-variable fields
    settings = config.get("design_variables", {})  # 读取辅助变量配置 / Read auxiliary-variable config
    random_gen = rng or stable_auxiliary_rng(H, variant_name)  # 构建可复现辅助随机源 / Build reproducible auxiliary random generator
    thickness = matrix_to_guidance(H, levels)  # 归一化厚度场 / Normalize thickness field
    target = normalise_design_map(target_grid) if target_grid is not None else thickness  # 读取目标引导图 / Read target guidance map
    edge = target_edge_guidance(target) if target_grid is not None else radial_design_bias(H.shape[0])  # 构造边缘或径向引导 / Build edge or radial guidance
    radial = radial_design_bias(H.shape[0])  # 构造径向惯性引导 / Build radial inertia guidance
    anti_target = 1.0 - target  # 构造目标反相区 / Build target inverse region
    density_noise = build_auxiliary_noise(H.shape, random_gen)  # 构造密度探索噪声 / Build density exploration noise
    loss_noise = build_auxiliary_noise(H.shape, random_gen)  # 构造损耗探索噪声 / Build loss exploration noise
    density_low = float(settings.get("density_scale_min", 0.90))  # 读取密度倍率下限 / Read density-scale lower bound
    density_high = float(settings.get("density_scale_max", 1.15))  # 读取密度倍率上限 / Read density-scale upper bound
    loss_low = float(settings.get("loss_factor_min", 0.00))  # 读取损耗因子下限 / Read loss-factor lower bound
    loss_high = float(settings.get("loss_factor_max", 0.06))  # 读取损耗因子上限 / Read loss-factor upper bound
    density_noise_weight = float(settings.get("density_noise_weight", 0.16))  # 读取密度噪声权重 / Read density-noise weight
    loss_noise_weight = float(settings.get("loss_noise_weight", 0.20))  # 读取损耗噪声权重 / Read loss-noise weight
    response_bias = 0.12 if any(token in variant_name for token in ("extra", "anti_star", "response")) else 0.0  # 根据真实响应变体增强阻尼 / Increase damping for real-response variants
    density_source = 0.36 * (1.0 - thickness) + 0.30 * target + 0.18 * edge + density_noise_weight * density_noise  # 合成单元密度引导 / Combine per-cell density guidance
    loss_source = (0.36 - response_bias) * anti_target + (0.34 + response_bias) * edge + 0.18 * radial + loss_noise_weight * loss_noise  # 合成局部阻尼引导 / Combine local damping guidance
    if "aux_mass_target_heavy" in variant_name:  # 检查目标重质量策略 / Check target-heavy mass strategy
        density_source = 0.18 * density_source + 1.05 * target + 0.25 * edge - 0.20 * anti_target  # 强化目标笔画惯性 / Strengthen inertia on target strokes
        loss_source = 0.30 * loss_source + 0.88 * anti_target + 0.18 * edge  # 抑制目标外响应 / Suppress response outside target
    elif "aux_mass_target_light" in variant_name:  # 检查目标轻质量策略 / Check target-light mass strategy
        density_source = 0.18 * density_source + 0.95 * anti_target + 0.22 * radial - 0.16 * target  # 让目标笔画相对轻 / Make target strokes relatively light
        loss_source = 0.30 * loss_source + 0.78 * edge + 0.24 * anti_target  # 强化边缘阻尼 / Strengthen edge damping
    elif "aux_loss_outer_suppress" in variant_name:  # 检查外区强阻尼策略 / Check outer suppression loss strategy
        density_source = 0.30 * density_source + 0.52 * target + 0.22 * (1.0 - radial)  # 保留目标附近惯性 / Keep inertia near target
        loss_source = 0.18 * loss_source + 1.10 * anti_target + 0.30 * radial  # 强力压制非目标区 / Strongly damp non-target region
    elif "aux_inertia_edge_heavy" in variant_name:  # 检查边缘重惯性策略 / Check edge-heavy inertia strategy
        density_source = 0.22 * density_source + 0.86 * edge + 0.30 * target  # 将惯性放到目标边界 / Place inertia on target edges
        loss_source = 0.22 * loss_source + 0.70 * anti_target + 0.34 * (1.0 - edge)  # 降低边缘以外响应 / Reduce response away from edges
    elif "aux_inertia_ring_break" in variant_name:  # 检查径向破环策略 / Check radial ring-breaking strategy
        density_source = 0.20 * density_source + 0.72 * np.abs(radial - 0.52) + 0.36 * target  # 打破中心环状模态 / Break central ring-like modes
        loss_source = 0.20 * loss_source + 0.66 * radial + 0.32 * anti_target  # 增强外圈损耗 / Increase outer-ring loss
    elif "aux_low_loss_target_channel" in variant_name:  # 检查目标低损耗通道策略 / Check low-loss target-channel strategy
        density_source = 0.24 * density_source + 0.60 * target + 0.26 * edge  # 沿目标保留惯性通道 / Keep inertia channel along target
        loss_source = 0.18 * loss_source + 0.92 * anti_target - 0.34 * target + 0.24 * edge  # 让目标线附近相对低损耗 / Make target-line neighborhood relatively low-loss
    elif "aux_heavy_loss_balanced" in variant_name:  # 检查重质量外区阻尼平衡策略 / Check heavy-mass outer-loss balanced strategy
        density_source = 0.16 * density_source + 0.88 * target + 0.34 * edge + 0.10 * (1.0 - radial)  # 保持目标和边缘较重 / Keep target and edge relatively heavy
        loss_source = 0.16 * loss_source + 0.70 * anti_target + 0.40 * edge - 0.16 * target  # 平衡外区压制和目标通道 / Balance outer suppression and target channel
    elif "aux_target_edge_bridge" in variant_name:  # 检查目标边缘桥接策略 / Check target-edge bridge strategy
        bridge = normalise_design_map(0.56 * target + 0.44 * edge)  # 构造目标边缘桥接场 / Build target-edge bridge field
        density_source = 0.18 * density_source + 0.82 * bridge + 0.18 * (1.0 - radial)  # 沿笔画和边缘加载质量 / Load mass along strokes and edges
        loss_source = 0.18 * loss_source + 0.78 * (1.0 - bridge) + 0.24 * edge  # 对桥接外区域加强损耗 / Increase loss outside bridge field
    elif "aux_recall_outer_trim" in variant_name:  # 检查召回扩展外区裁剪策略 / Check recall-expansion outer-trim strategy
        expanded = normalise_design_map(smooth_design_map(target, 1) + 0.55 * edge)  # 构造稍宽目标通道 / Build slightly expanded target channel
        density_source = 0.18 * density_source + 0.72 * expanded + 0.22 * edge  # 扩大目标附近惯性支撑 / Expand inertia support near target
        loss_source = 0.16 * loss_source + 0.90 * (1.0 - expanded) + 0.16 * radial  # 裁剪非目标外区响应 / Trim non-target outer response
    elif "aux_precision_channel_guard" in variant_name:  # 检查精度通道保护策略 / Check precision channel guard strategy
        guarded = normalise_design_map(target + 0.28 * edge - 0.18 * radial)  # 构造保守目标通道 / Build conservative target channel
        density_source = 0.20 * density_source + 0.72 * guarded + 0.16 * target  # 强化保守通道质量 / Strengthen conservative channel mass
        loss_source = 0.14 * loss_source + 1.02 * (1.0 - guarded) - 0.24 * target + 0.12 * edge  # 强力压制通道外响应 / Strongly suppress response outside channel
    density_scale = scale_field(density_source, density_low, density_high)  # 生成密度倍率场 / Generate density-scale field
    loss_factor = scale_field(loss_source, loss_low, loss_high)  # 生成损耗因子场 / Generate loss-factor field
    return {"density_scale": np.round(density_scale, 4), "loss_factor": np.round(loss_factor, 5)}  # 返回辅助场 / Return auxiliary fields


def latent_physics_basis_maps(H: np.ndarray, target_grid: np.ndarray, levels: list[float]) -> list[np.ndarray]:  # 构建低维潜变量基底图 / Build low-dimensional latent basis maps
    target = normalise_design_map(target_grid)  # 归一化目标图 / Normalize target map
    edge = target_edge_guidance(target)  # 构建目标边缘图 / Build target edge map
    radial = radial_design_bias(H.shape[0])  # 构建径向基底 / Build radial basis
    thickness = matrix_to_guidance(H, levels)  # 构建厚度基底 / Build thickness basis
    axis = np.linspace(-1.0, 1.0, H.shape[0])  # 构建归一化坐标轴 / Build normalized coordinate axis
    yy, xx = np.meshgrid(axis, axis, indexing="ij")  # 构建二维坐标 / Build two-dimensional coordinates
    horizontal = normalise_design_map(np.abs(xx))  # 构建横向基底 / Build horizontal basis
    vertical = normalise_design_map(np.abs(yy))  # 构建纵向基底 / Build vertical basis
    diagonal = normalise_design_map(xx + yy)  # 构建对角基底 / Build diagonal basis
    angular = angular_design_bias(H.shape[0], 0.73)  # 构建角向破缺基底 / Build angular symmetry-breaking basis
    return [target, edge, 1.0 - target, radial, 1.0 - radial, thickness, 1.0 - thickness, horizontal, vertical, diagonal, angular]  # 返回基底列表 / Return basis list


def latent_field_from_coefficients(basis_maps: list[np.ndarray], coefficients: np.ndarray) -> np.ndarray:  # 从潜变量系数合成场 / Compose a field from latent coefficients
    field = np.zeros_like(basis_maps[0], dtype=float)  # 创建累加场 / Create accumulator field
    for index, basis in enumerate(basis_maps):  # 遍历基底图 / Iterate basis maps
        field = field + float(coefficients[index]) * basis  # 累加当前基底 / Add current basis contribution
    return normalise_design_map(field)  # 返回归一化合成场 / Return normalized composed field


def latent_coefficients_fingerprint(coefficients: np.ndarray) -> str:  # 压缩潜变量系数为短指纹 / Compress latent coefficients into a short fingerprint
    rounded = np.ascontiguousarray(np.round(coefficients.astype(float), 3))  # 量化系数 / Quantize coefficients
    return hashlib.blake2b(rounded.tobytes(), digest_size=4).hexdigest()  # 返回短哈希 / Return short hash


def compose_latent_auxiliary_fields(H: np.ndarray, target_grid: np.ndarray, levels: list[float], config: dict, coefficients: np.ndarray, anchor_fields: dict[str, np.ndarray] | None) -> dict[str, np.ndarray]:  # 合成潜变量辅助物理场 / Compose latent auxiliary physics fields
    settings = config.get("design_variables", {})  # 读取设计变量配置 / Read design-variable settings
    basis_maps = latent_physics_basis_maps(H, target_grid, levels)  # 构建潜变量基底 / Build latent basis maps
    basis_count = len(basis_maps)  # 读取基底数量 / Read basis count
    density_source = latent_field_from_coefficients(basis_maps, coefficients[:basis_count])  # 合成密度源场 / Compose density source field
    loss_source = latent_field_from_coefficients(basis_maps, coefficients[basis_count:basis_count * 2])  # 合成损耗源场 / Compose loss source field
    if anchor_fields is not None:  # 检查是否有历史锚点场 / Check whether historical anchor fields exist
        density_source = normalise_design_map(0.46 * normalise_auxiliary_field(anchor_fields["density_scale"], "density_scale", config) + 0.54 * density_source)  # 混合历史密度和潜变量密度 / Blend historical and latent density
        loss_source = normalise_design_map(0.42 * normalise_auxiliary_field(anchor_fields["loss_factor"], "loss_factor", config) + 0.58 * loss_source)  # 混合历史损耗和潜变量损耗 / Blend historical and latent loss
    density_low = float(settings.get("density_scale_min", 0.90))  # 读取密度下限 / Read density lower bound
    density_high = float(settings.get("density_scale_max", 1.15))  # 读取密度上限 / Read density upper bound
    loss_low = float(settings.get("loss_factor_min", 0.00))  # 读取损耗下限 / Read loss lower bound
    loss_high = float(settings.get("loss_factor_max", 0.06))  # 读取损耗上限 / Read loss upper bound
    density_scale = scale_field(density_source, density_low, density_high)  # 缩放密度倍率场 / Scale density field
    loss_factor = scale_field(loss_source, loss_low, loss_high)  # 缩放损耗因子场 / Scale loss field
    return {"density_scale": np.round(density_scale, 4), "loss_factor": np.round(loss_factor, 5)}  # 返回潜变量辅助场 / Return latent auxiliary fields


def auxiliary_field_distance(left: dict[str, np.ndarray], right: dict[str, np.ndarray], config: dict) -> float:  # 计算辅助场距离 / Compute auxiliary-field distance
    density_left = normalise_auxiliary_field(left["density_scale"], "density_scale", config)  # 归一化左密度 / Normalize left density
    density_right = normalise_auxiliary_field(right["density_scale"], "density_scale", config)  # 归一化右密度 / Normalize right density
    loss_left = normalise_auxiliary_field(left["loss_factor"], "loss_factor", config)  # 归一化左损耗 / Normalize left loss
    loss_right = normalise_auxiliary_field(right["loss_factor"], "loss_factor", config)  # 归一化右损耗 / Normalize right loss
    density_distance = float(np.sqrt(np.mean(np.square(density_left - density_right))))  # 计算密度距离 / Compute density distance
    loss_distance = float(np.sqrt(np.mean(np.square(loss_left - loss_right))))  # 计算损耗距离 / Compute loss distance
    return float(0.5 * density_distance + 0.5 * loss_distance)  # 返回联合距离 / Return joint distance


def latent_fields_are_diverse(fields: dict[str, np.ndarray], selected: list[tuple], config: dict, threshold: float = 0.030) -> bool:  # 判断潜变量辅助场是否多样 / Decide whether latent auxiliary fields are diverse
    existing_fields = [proposal_auxiliary_fields(item) for item in selected]  # 提取已选辅助场 / Extract selected auxiliary fields
    distances = [auxiliary_field_distance(fields, item, config) for item in existing_fields if item is not None]  # 计算到已有场的距离 / Compute distances to existing fields
    return True if not distances else min(distances) >= threshold  # 返回多样性判断 / Return diversity decision


def response_record_for_base(base: dict, response_records: list[dict], levels: list[float]) -> dict | None:  # 为潜变量锚点寻找真实响应记录 / Find real-response record for a latent anchor
    if not response_records:  # 检查是否没有响应记录 / Check whether no response records exist
        return None  # 无记录则返回空 / Return none without records
    for record in response_records:  # 优先按候选编号匹配 / Prefer candidate-id matching
        if str(record.get("candidate_id", "")) == str(base.get("candidate_id", "")):  # 检查是否同一候选 / Check whether candidate ids match
            return record  # 返回精确匹配记录 / Return exact record
    anchor = matrix_to_guidance(base["H"], levels).ravel()  # 构建锚点厚度向量 / Build anchor thickness vector
    distances = [(float(np.sqrt(np.mean(np.square(anchor - matrix_to_guidance(record["H"], levels).ravel())))), record) for record in response_records]  # 计算到响应记录距离 / Compute distances to response records
    return min(distances, key=lambda item: item[0])[1]  # 返回最近响应记录 / Return nearest response record


def latent_response_correction_score(fields: dict[str, np.ndarray], response_record: dict | None, target_grid: np.ndarray, config: dict) -> float:  # 计算真实响应误差校正分 / Compute real-response error correction score
    if response_record is None:  # 检查是否没有真实响应记录 / Check whether no real-response record exists
        return auxiliary_alignment_score(fields, target_grid, config)  # 退回辅助变量对齐 / Fall back to auxiliary alignment
    target = normalise_design_map(response_record.get("target", target_grid))  # 读取目标图 / Read target map
    missing = normalise_design_map(smooth_design_map(response_record.get("missing", target), 2))  # 平滑缺失响应图 / Smooth missing-response map
    avoid = normalise_design_map(smooth_design_map(response_record.get("avoid", response_record.get("extra", 1.0 - target)), 2))  # 平滑多余响应规避图 / Smooth extra-response avoidance map
    edge = target_edge_guidance(target)  # 构建目标边缘图 / Build target edge map
    channel = normalise_design_map(0.72 * target + 0.28 * edge)  # 构建目标通道图 / Build target channel map
    density = normalise_auxiliary_field(fields["density_scale"], "density_scale", config)  # 归一化密度倍率场 / Normalize density-scale field
    loss = normalise_auxiliary_field(fields["loss_factor"], "loss_factor", config)  # 归一化损耗因子场 / Normalize loss-factor field
    loss_score = float(np.mean(loss * avoid + (1.0 - loss) * channel))  # 奖励多余区高损耗和目标通道低损耗 / Reward high loss on extra areas and low loss on target channel
    density_positive = float(np.mean(density * missing + (1.0 - density) * avoid))  # 假设缺失区需要更高惯性 / Assume missing areas need higher inertia
    density_negative = float(np.mean((1.0 - density) * missing + density * avoid))  # 假设缺失区需要更低惯性 / Assume missing areas need lower inertia
    missing_channel = float(np.mean((1.0 - loss) * missing + density * channel))  # 奖励缺失目标附近形成低损耗惯性通道 / Reward low-loss inertial channel near missing target strokes
    return float(np.clip(0.46 * loss_score + 0.32 * max(density_positive, density_negative) + 0.22 * missing_channel, 0.0, 1.0))  # 返回校正分 / Return correction score


def latent_physics_acquisition(base: dict, H: np.ndarray, target_grid: np.ndarray, levels: list[float], config: dict, coefficients: np.ndarray, surrogate: dict, ensemble: list[dict], best_score: float, beta: float, response_record: dict | None) -> dict:  # 评估潜变量联合物理采集函数 / Evaluate latent joint-physics acquisition
    fields = compose_latent_auxiliary_fields(H, target_grid, levels, config, coefficients, base.get("auxiliary_fields"))  # 合成显式辅助物理场 / Compose explicit auxiliary physics fields
    predicted, uncertainty = predict_bayesian_surrogate_stats(ensemble, H, levels, fields, config)  # 预测真实评分分布 / Predict real-score distribution
    improvement = expected_improvement(predicted, uncertainty, best_score)  # 计算期望改进 / Compute expected improvement
    novelty = surrogate_novelty(surrogate, H, levels, fields, config)  # 计算联合设计新颖度 / Compute joint-design novelty
    auxiliary_alignment = auxiliary_alignment_score(fields, target_grid, config)  # 计算辅助场目标对齐 / Compute auxiliary-target alignment
    response_correction = latent_response_correction_score(fields, response_record, target_grid, config)  # 计算真实响应误差校正 / Compute real-response error correction
    optimisation = config.get("optimisation", {})  # 读取优化配置 / Read optimisation settings
    optimism_penalty = float(optimisation.get("latent_surrogate_optimism_penalty", 0.45))  # 读取代理乐观惩罚 / Read surrogate optimism penalty
    response_weight = float(optimisation.get("latent_response_correction_weight", 0.075))  # 读取响应校正权重 / Read response-correction weight
    anchor_score = float(base.get("score", best_score))  # 读取锚点真实分数 / Read anchor real score
    optimism = max(0.0, predicted - anchor_score)  # 计算代理超出锚点的乐观差 / Compute optimistic gap beyond anchor
    trusted_prediction = predicted - optimism_penalty * optimism  # 压低过度乐观预测 / Damp over-optimistic prediction
    acquisition = trusted_prediction + beta * uncertainty + 0.44 * improvement + 0.12 * novelty + 0.030 * auxiliary_alignment + response_weight * response_correction  # 合成响应校正采集函数 / Combine response-corrected acquisition
    return {"acquisition": float(acquisition), "fields": fields, "predicted": float(predicted), "trusted_prediction": float(trusted_prediction), "uncertainty": float(uncertainty), "improvement": float(improvement), "novelty": float(novelty), "auxiliary_alignment": float(auxiliary_alignment), "response_correction": float(response_correction), "surrogate_optimism": float(optimism)}  # 返回评估包 / Return evaluation bundle


def latent_proposal_record(H: np.ndarray, base: dict, generation: int, coefficients: np.ndarray, evaluation: dict, optimizer_name: str) -> tuple[float, np.ndarray, str, dict[str, np.ndarray], dict]:  # 构造潜变量提案记录 / Build a latent proposal record
    fingerprint = latent_coefficients_fingerprint(coefficients)  # 生成系数指纹 / Build coefficient fingerprint
    predicted = float(evaluation["predicted"])  # 读取预测均值 / Read predicted mean
    uncertainty = float(evaluation["uncertainty"])  # 读取预测不确定性 / Read predicted uncertainty
    improvement = float(evaluation["improvement"])  # 读取期望改进 / Read expected improvement
    auxiliary_alignment = float(evaluation["auxiliary_alignment"])  # 读取辅助场对齐分 / Read auxiliary alignment
    novelty = float(evaluation["novelty"])  # 读取新颖度 / Read novelty score
    response_correction = float(evaluation.get("response_correction", auxiliary_alignment))  # 读取响应校正分 / Read response-correction score
    name = f"latent_physics_{optimizer_name}_from_{base['candidate_id']}_g{generation:03d}_{fingerprint}_mean_{predicted:.3f}_std_{uncertainty:.3f}_ei_{improvement:.3f}_resp_{response_correction:.2f}_aux_{auxiliary_alignment:.2f}_novel_{novelty:.2f}"  # 构造候选名称 / Build candidate name
    metadata = {"latent_optimizer": optimizer_name, "latent_anchor_candidate": base["candidate_id"], "latent_coefficients": np.round(coefficients.astype(float), 4).tolist(), "latent_predicted_score": predicted, "latent_trusted_prediction": float(evaluation.get("trusted_prediction", predicted)), "latent_uncertainty": uncertainty, "latent_expected_improvement": improvement, "latent_auxiliary_alignment": auxiliary_alignment, "latent_response_correction": response_correction, "latent_surrogate_optimism": float(evaluation.get("surrogate_optimism", 0.0)), "latent_novelty": novelty}  # 构造可追踪元数据 / Build traceable metadata
    return float(evaluation["acquisition"]), H, name, evaluation["fields"], metadata  # 返回提案记录 / Return proposal record


def optimise_latent_coefficients_for_base(base: dict, target_grid: np.ndarray, levels: list[float], default_thickness: float, max_neighbor_diff: float, config: dict, surrogate: dict, ensemble: list[dict], best_score: float, beta: float, basis_count: int, generation: int, rng: np.random.Generator, response_record: dict | None) -> list[tuple[float, np.ndarray, str, dict[str, np.ndarray], dict]]:  # 围绕单个真实锚点优化潜变量系数 / Optimise latent coefficients around one real anchor
    optimisation = config.get("optimisation", {})  # 读取优化配置 / Read optimisation settings
    steps = int(optimisation.get("latent_physics_cma_steps", 5))  # 读取潜变量进化轮数 / Read latent evolutionary step count
    sample_count = int(optimisation.get("latent_physics_cma_population", 22))  # 读取每轮采样数量 / Read samples per step
    elite_fraction = float(optimisation.get("latent_physics_cma_elite_fraction", 0.28))  # 读取精英比例 / Read elite fraction
    elite_count = max(2, min(sample_count, int(round(sample_count * elite_fraction))))  # 计算精英数量 / Compute elite count
    sigma = float(optimisation.get("latent_physics_cma_sigma", 0.82))  # 读取初始探索尺度 / Read initial exploration sigma
    dimension = basis_count * 2  # 读取潜变量维度 / Read latent dimension
    mean = np.zeros(dimension, dtype=float)  # 初始化潜变量均值 / Initialize latent mean
    records = []  # 创建优化记录池 / Create optimisation record pool
    anchor_H = base["H"].copy().astype(float)  # 复制锚点厚度 / Copy anchor thickness
    for step in range(max(1, steps)):  # 遍历进化轮数 / Iterate evolutionary steps
        generation_records = []  # 创建本轮记录 / Create records for this step
        progress = step / max(steps - 1, 1)  # 计算退火进度 / Compute annealing progress
        mutation_rate = 0.006 + 0.014 * (1.0 - progress)  # 计算厚度轻扰率 / Compute light thickness mutation rate
        for sample_index in range(max(2, sample_count)):  # 遍历本轮样本 / Iterate samples in this step
            coefficients = np.clip(mean + rng.normal(0.0, sigma, size=dimension), -2.8, 2.8)  # 采样并裁剪潜变量系数 / Sample and clip latent coefficients
            H = anchor_H if sample_index == 0 and step == 0 else lightly_mutate_physics_base(anchor_H, levels, default_thickness, max_neighbor_diff, rng, rate=mutation_rate)  # 保留锚点或轻扰厚度 / Keep anchor or lightly perturb thickness
            evaluation = latent_physics_acquisition(base, H, target_grid, levels, config, coefficients, surrogate, ensemble, best_score, beta, response_record)  # 评估潜变量采集函数 / Evaluate latent acquisition
            generation_records.append(latent_proposal_record(H, base, generation, coefficients, evaluation, "cma"))  # 保存本轮提案记录 / Store step proposal record
        generation_records = sorted(generation_records, key=lambda item: item[0], reverse=True)  # 按采集函数排序 / Sort by acquisition
        elites = np.asarray([item[4]["latent_coefficients"] for item in generation_records[:elite_count]], dtype=float)  # 提取精英系数 / Extract elite coefficients
        weights = np.linspace(1.0, 0.35, elite_count, dtype=float)  # 构造线性精英权重 / Build linear elite weights
        weights = weights / max(float(weights.sum()), 1.0e-9)  # 归一化权重 / Normalize weights
        mean = np.sum(elites * weights[:, None], axis=0)  # 更新潜变量均值 / Update latent mean
        elite_spread = float(np.sqrt(np.mean(np.square(elites - mean))))  # 估计精英扩散尺度 / Estimate elite spread
        sigma = float(np.clip(0.62 * sigma + 0.38 * elite_spread, 0.16, 1.20))  # 更新探索尺度 / Update exploration scale
        records.extend(generation_records[:max(elite_count, 3)])  # 保存本轮优秀记录 / Store strong records from this step
    return sorted(records, key=lambda item: item[0], reverse=True)  # 返回排序后的优化记录 / Return sorted optimisation records


def generate_latent_physics_proposals(config: dict, candidates_dir: Path, target_grid: np.ndarray | None, response_records: list[dict], levels: list[float], default_thickness: float, max_neighbor_diff: float, population: int, generation: int, rng: np.random.Generator) -> list[tuple[np.ndarray, str, dict[str, np.ndarray], dict]]:  # 生成潜变量联合物理提案 / Generate latent joint-physics proposals
    if target_grid is None or not config.get("design_variables", {}).get("export_auxiliary_fields", True):  # 检查目标和辅助场开关 / Check target and auxiliary-field switch
        return []  # 不满足条件时返回空 / Return empty when unavailable
    optimisation = config.get("optimisation", {})  # 读取优化配置 / Read optimisation settings
    count = min(population, int(optimisation.get("latent_physics_count", max(2, population // 3))))  # 读取潜变量候选数量 / Read latent proposal count
    history = filter_history_by_shape(load_surrogate_history(candidates_dir, config, limit=120), target_grid.shape)  # 读取真实历史样本 / Load real historical samples
    surrogate = fit_score_surrogate(history, levels, config)  # 拟合联合代理模型 / Fit joint surrogate model
    ensemble = fit_bayesian_surrogate_ensemble(history, levels, int(optimisation.get("bayesian_ensemble_size", 12)), rng, config)  # 拟合贝叶斯集成 / Fit Bayesian ensemble
    if surrogate is None or not ensemble:  # 检查代理模型是否可用 / Check whether surrogate models are usable
        return []  # 代理不可用时返回空 / Return empty without surrogate
    bases = history[:max(1, min(len(history), 8))]  # 选择高分历史基底 / Select high-score historical bases
    best_score = float(max(item["score"] for item in history))  # 读取历史最佳分 / Read best historical score
    pool_size = int(optimisation.get("latent_physics_pool_size", max(80, population * 12)))  # 读取潜变量池大小 / Read latent pool size
    beta = float(optimisation.get("bayesian_ucb_beta", 0.35))  # 读取 UCB 探索强度 / Read UCB exploration strength
    pool = []  # 创建潜变量候选池 / Create latent candidate pool
    basis_count = len(latent_physics_basis_maps(bases[0]["H"], target_grid, levels))  # 读取潜变量维度 / Read latent basis dimension
    cma_base_count = min(len(bases), int(optimisation.get("latent_physics_cma_base_count", 6)))  # 读取潜变量优化锚点数量 / Read latent optimisation anchor count
    for base in bases[:cma_base_count]:  # 遍历高分真实锚点 / Iterate high-score real anchors
        response_record = response_record_for_base(base, response_records, levels)  # 查找锚点对应真实响应 / Find real response for anchor
        pool.extend(optimise_latent_coefficients_for_base(base, target_grid, levels, default_thickness, max_neighbor_diff, config, surrogate, ensemble, best_score, beta, basis_count, generation, rng, response_record))  # 加入进化优化记录 / Add evolutionary optimisation records
    for index in range(max(pool_size, count)):  # 遍历虚拟潜变量候选 / Iterate virtual latent candidates
        base = bases[index % len(bases)]  # 选择高分基底 / Select high-score base
        H = base["H"].copy().astype(float) if index < len(bases) * 3 else lightly_mutate_physics_base(base["H"], levels, default_thickness, max_neighbor_diff, rng, rate=0.010 + 0.006 * (index % 4))  # 保留或轻扰厚度基底 / Keep or lightly perturb thickness base
        spread = 0.62 if index < len(bases) * 4 else 0.95  # 设置潜变量探索尺度 / Set latent exploration spread
        coefficients = rng.normal(0.0, spread, size=basis_count * 2)  # 采样潜变量系数 / Sample latent coefficients
        response_record = response_record_for_base(base, response_records, levels)  # 查找随机样本锚点真实响应 / Find real response for random-sample anchor
        evaluation = latent_physics_acquisition(base, H, target_grid, levels, config, coefficients, surrogate, ensemble, best_score, beta, response_record)  # 评估随机潜变量采集函数 / Evaluate random latent acquisition
        pool.append(latent_proposal_record(H, base, generation, coefficients, evaluation, "random"))  # 保存随机潜变量记录 / Store random latent record
    selected = []  # 创建已选潜变量提案 / Create selected latent proposals
    for _score, H, name, fields, metadata in sorted(pool, key=lambda item: item[0], reverse=True):  # 按采集函数排序 / Sort by acquisition value
        if latent_fields_are_diverse(fields, selected, config):  # 检查显式辅助场多样性 / Check explicit auxiliary-field diversity
            selected.append((H, name, fields, metadata))  # 保存显式辅助场提案 / Store explicit auxiliary-field proposal
        if len(selected) >= count:  # 检查是否达到数量 / Check proposal count
            break  # 停止选择 / Stop selection
    return selected  # 返回潜变量提案 / Return latent proposals


def save_auxiliary_fields(candidate_path: Path, fields: dict[str, np.ndarray]) -> None:  # 保存辅助设计变量场 / Save auxiliary design-variable fields
    for name, values in fields.items():  # 遍历辅助变量场 / Iterate auxiliary fields
        fmt = "%.5f" if name == "loss_factor" else "%.4f"  # 选择保存精度 / Choose save precision
        np.savetxt(candidate_path / f"{name}.csv", values, delimiter=",", fmt=fmt)  # 保存辅助变量 CSV / Save auxiliary variable CSV


def save_candidate(candidate_dir: str | Path, H: np.ndarray, metadata: dict, auxiliary_fields: dict[str, np.ndarray] | None = None) -> None:  # 保存候选结构 / Save candidate design
    path = Path(candidate_dir)  # 转换为路径对象 / Convert to path object
    path.mkdir(parents=True, exist_ok=True)  # 创建候选目录 / Create candidate directory
    save_H_csv(H, path / "H.csv")  # 保存厚度矩阵 / Save thickness matrix
    if auxiliary_fields:  # 检查是否存在辅助物理场 / Check whether auxiliary physical fields exist
        save_auxiliary_fields(path, auxiliary_fields)  # 保存辅助物理场 / Save auxiliary physical fields
    with (path / "metadata.json").open("w", encoding="utf-8") as file_obj:  # 打开元数据文件 / Open metadata file
        json.dump(metadata, file_obj, indent=2, ensure_ascii=False)  # 写入元数据 / Write metadata


def generate_candidate_batch(config: dict, generation: int = 0) -> list[str]:  # 生成一批候选 / Generate a batch of candidates
    grid_size = int(config["project"]["grid_size"])  # 读取网格尺寸 / Read grid size
    levels = [float(config["thickness"].get("min_mm", min(config["thickness"]["levels_mm"]))), float(config["thickness"].get("max_mm", max(config["thickness"]["levels_mm"])))]  # 读取连续厚度边界 / Read continuous thickness bounds
    default = float(config["thickness"]["default_mm"])  # 读取默认厚度 / Read default thickness
    max_diff = float(config["thickness"]["max_neighbor_difference_mm"])  # 读取最大相邻差 / Read max neighbour difference
    population = int(config["optimisation"]["population_size"])  # 读取候选数量 / Read population size
    method = str(config.get("optimisation", {}).get("method", "random_search"))  # 读取搜索方法 / Read search method
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选目录 / Read candidate directory
    rng = np.random.default_rng(generation)  # 创建可复现随机源 / Create reproducible random source
    parent_limit = int(config.get("optimisation", {}).get("genetic_parent_count", 8))  # 读取遗传算法父代数量 / Read genetic algorithm parent count
    parents = load_parent_matrices(candidates_dir, parent_limit) if ("evolutionary" in method or "genetic" in method or "ga" in method) and generation > 0 else []  # 读取遗传算法父代 / Load genetic algorithm parents
    parents = [parent for parent in parents if tuple(parent.shape) == (grid_size, grid_size)]  # 过滤旧网格父代 / Filter old-grid parents
    target_grid = load_target_binary_grid(config, grid_size)  # 读取目标感知网格 / Load target-aware grid
    response_records = load_response_guidance_records(config, candidates_dir, target_grid) if target_grid is not None else []  # 读取真实响应闭环记录 / Load real-response closed-loop records
    response_closed_loop_proposals = generate_response_closed_loop_proposals(config, response_records, levels, default, max_diff, population, rng)  # 生成一等真实响应闭环提案 / Generate first-class real-response closed-loop proposals
    latent_physics_proposals = generate_latent_physics_proposals(config, candidates_dir, target_grid, response_records, levels, default, max_diff, population, generation, rng)  # 生成低维潜变量联合物理提案 / Generate low-dimensional latent joint-physics proposals
    auxiliary_physics_proposals = generate_auxiliary_physics_proposals(config, candidates_dir, target_grid, response_records, parents, levels, default, max_diff, population, generation, rng)  # 生成独立质量阻尼提案 / Generate independent mass-damping proposals
    modal_compiler_proposals = generate_modal_compiler_proposals(config, target_grid, parents, levels, default, max_diff, population, rng)  # 生成目标模态编译提案 / Generate target-modal compiler proposals
    kl_proxy_proposals = generate_kl_proxy_optimised_proposals(config, candidates_dir, target_grid, response_records, parents, levels, default, max_diff, population, rng)  # 生成 KL 直接优化提案 / Generate directly KL-optimised proposals
    surrogate_proposals = generate_surrogate_proposals(config, candidates_dir, target_grid, response_records, parents, levels, default, max_diff, population, rng)  # 生成代理模型优化提案 / Generate surrogate-model optimized proposals
    latent_frontload_default = int(config.get("optimisation", {}).get("latent_physics_frontload_count", 0))  # 读取默认潜变量前置数量 / Read default latent front-load count
    auxiliary_frontload_default = int(config.get("optimisation", {}).get("auxiliary_physics_frontload_count", 0))  # 读取默认辅助物理前置数量 / Read default auxiliary front-load count
    latent_frontload_target, auxiliary_frontload_target = adaptive_frontload_counts(config, candidates_dir, latent_frontload_default, auxiliary_frontload_default, population)  # 根据真实表现自适应分配前置名额 / Adapt front-loaded slots from real performance
    latent_frontload_count = min(len(latent_physics_proposals), latent_frontload_target)  # 读取潜变量前置数量 / Read latent front-load count
    frontloaded_latent_proposals = latent_physics_proposals[:latent_frontload_count]  # 提取前置潜变量提案 / Extract front-loaded latent proposals
    remaining_latent_proposals = latent_physics_proposals[latent_frontload_count:]  # 提取剩余潜变量提案 / Extract remaining latent proposals
    auxiliary_frontload_count = min(len(auxiliary_physics_proposals), auxiliary_frontload_target)  # 读取辅助物理前置数量 / Read auxiliary-physics front-load count
    frontloaded_auxiliary_proposals = auxiliary_physics_proposals[:auxiliary_frontload_count]  # 提取前置辅助物理提案 / Extract front-loaded auxiliary proposals
    remaining_auxiliary_proposals = auxiliary_physics_proposals[auxiliary_frontload_count:]  # 提取剩余辅助物理提案 / Extract remaining auxiliary proposals
    remaining_slots = max(0, population - len(frontloaded_latent_proposals) - len(frontloaded_auxiliary_proposals))  # 计算剩余队列名额 / Compute remaining queue slots
    interleaved_proposals = interleave_proposal_groups([remaining_latent_proposals, response_closed_loop_proposals, remaining_auxiliary_proposals, modal_compiler_proposals, surrogate_proposals, kl_proxy_proposals], remaining_slots)  # 交错合并其余候选家族 / Interleave remaining proposal families
    inverse_proposals = (frontloaded_latent_proposals + frontloaded_auxiliary_proposals + interleaved_proposals)[:population]  # 合并前置潜变量、辅助物理与其余逆向提案 / Combine front-loaded latent, auxiliary, and remaining inverse proposals
    response_count = max(min(population, len(response_records) * 2), int(population * 0.75)) if response_records else 0  # 计算闭环响应候选数量 / Compute response-guided candidate count
    target_count = max(response_count, max(min(population, 6), int(population * 0.90 if response_records else population * 0.75))) if target_grid is not None else 0  # 计算目标感知候选数量 / Compute target-aware candidate count
    candidate_ids = []  # 创建候选编号列表 / Create candidate id list
    for index in range(population):  # 遍历候选编号 / Iterate candidate index
        candidate_id = f"candidate_{generation:03d}_{index:04d}"  # 构造候选编号 / Build candidate id
        proposed_auxiliary_fields = None  # 初始化提案自带辅助场 / Initialize proposal-owned auxiliary fields
        proposed_metadata = {}  # 初始化提案自带元数据 / Initialize proposal-owned metadata
        if index < len(inverse_proposals):  # 优先使用逆向优化提案 / Prefer inverse-optimised proposals
            proposal = inverse_proposals[index]  # 读取逆向提案对象 / Read inverse proposal object
            H = proposal_matrix(proposal)  # 读取提案厚度矩阵 / Read proposal thickness matrix
            variant_name = proposal_name(proposal)  # 读取提案名称 / Read proposal name
            proposed_auxiliary_fields = proposal_auxiliary_fields(proposal)  # 读取提案自带辅助场 / Read proposal-owned auxiliary fields
            proposed_metadata = proposal_metadata(proposal)  # 读取提案自带元数据 / Read proposal-owned metadata
            created_by = "latent_physics_inverse_search" if variant_name.startswith("latent_physics") else ("response_guided_inverse_search" if variant_name.startswith("response_closed_loop") else ("auxiliary_physics_inverse_search" if variant_name.startswith("aux_") else ("modal_pde_inverse_compiler" if variant_name.startswith("modal_compiler") else ("kl_proxy_direct_inverse_search" if variant_name.startswith("kl_proxy_optimised") else "surrogate_guided_inverse_search"))))  # 设置生成来源 / Set creation source
        elif response_records and index < response_count:  # 其次生成闭环响应引导候选 / Then generate closed-loop response-guided candidates
            H, variant_name = generate_response_guided_H(response_records, index, levels, default, max_diff, rng)  # 生成闭环响应引导矩阵 / Generate response-guided matrix
            created_by = "response_guided_inverse_search"  # 设置生成来源 / Set creation source
        elif target_grid is not None and index < target_count:  # 其次生成目标感知候选 / Then generate target-aware candidates
            H, variant_name = generate_target_guided_H(target_grid, index, parents, levels, default, max_diff, rng)  # 生成目标感知矩阵 / Generate target-aware matrix
            created_by = "target_guided_evolutionary_search" if parents else "target_guided_initial_search"  # 设置生成来源 / Set creation source
        else:  # 保留一部分探索候选 / Keep some exploration candidates
            mutation_rate = float(config.get("optimisation", {}).get("genetic_mutation_rate", 0.12))  # 读取遗传变异率 / Read genetic mutation rate
            H = generate_evolutionary_H(parents, levels, default, max_diff, rng, mutation_rate) if parents else generate_random_H(grid_size, levels, default, max_diff, rng)  # 生成探索矩阵 / Generate exploration matrix
            variant_name = "genetic_explorer" if parents else "random_explorer"  # 设置探索变体名 / Set explorer variant name
            created_by = "genetic_search" if parents else "random_search"  # 设置生成来源 / Set creation source
        auxiliary_fields = proposed_auxiliary_fields if proposed_auxiliary_fields is not None else (build_auxiliary_design_fields(H, levels, target_grid, config, None, variant_name) if config.get("design_variables", {}).get("export_auxiliary_fields", True) else {})  # 使用显式辅助场或构建默认辅助场 / Use explicit auxiliary fields or build default fields
        metadata = {"candidate_id": candidate_id, "generation": generation, "grid_size": grid_size, "thickness_mode": "continuous", "thickness_bounds_mm": levels, "center_fixed": True, "created_by": created_by, "target_guidance_variant": variant_name, "target_guided": target_grid is not None, "auxiliary_fields": sorted(auxiliary_fields.keys())}  # 记录元数据 / Record metadata
        metadata.update(proposed_metadata)  # 合并提案自带元数据 / Merge proposal-owned metadata
        save_candidate(candidates_dir / candidate_id, H, metadata, auxiliary_fields)  # 保存候选 / Save candidate
        candidate_ids.append(candidate_id)  # 添加候选编号 / Add candidate id
    return candidate_ids  # 返回候选编号 / Return candidate ids
