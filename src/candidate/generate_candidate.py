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


def quantise_guidance_to_levels(guidance: np.ndarray, levels: list[float]) -> np.ndarray:  # 将引导图量化为厚度等级 / Quantize guidance map to thickness levels
    level_array = np.asarray(levels, dtype=float)  # 转为厚度等级数组 / Convert levels to array
    scaled = normalise_design_map(guidance) * (len(level_array) - 1)  # 缩放到等级索引范围 / Scale to level-index range
    indices = np.clip(np.rint(scaled).astype(int), 0, len(level_array) - 1)  # 四舍五入并限制索引 / Round and clamp indices
    return level_array[indices]  # 返回厚度矩阵 / Return thickness matrix


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
    level_array = np.asarray(levels, dtype=float)  # 转为厚度等级数组 / Convert levels to array
    guided = quantise_guidance_to_levels(guidance, levels)  # 量化目标引导图 / Quantize target guidance
    blend = float(rng.uniform(0.35, 0.70))  # 随机选择引导强度 / Randomly choose guidance strength
    mixed = (1.0 - blend) * parent + blend * guided  # 混合父代和引导图 / Mix parent and guidance map
    indices = np.argmin(np.abs(mixed[..., None] - level_array), axis=2)  # 找最近厚度等级 / Find nearest thickness levels
    return level_array[indices]  # 返回量化混合矩阵 / Return quantized mixed matrix


def matrix_to_guidance(H: np.ndarray, levels: list[float]) -> np.ndarray:  # 将厚度矩阵转为 0-1 引导图 / Convert thickness matrix to 0-1 guidance map
    low = float(min(levels))  # 读取最小厚度 / Read minimum thickness
    high = float(max(levels))  # 读取最大厚度 / Read maximum thickness
    return np.clip((H.astype(float) - low) / max(high - low, 1.0e-9), 0.0, 1.0)  # 返回归一化厚度 / Return normalized thickness


def load_response_guidance_records(config: dict, candidates_dir: Path, target_grid: np.ndarray, limit: int = 4) -> list[dict]:  # 读取上一轮真实响应作为闭环引导 / Load previous real responses as closed-loop guidance
    ranking_path = candidates_dir / "ranked_candidates.csv"  # 构造排行文件路径 / Build ranking file path
    if not ranking_path.exists():  # 检查排行文件是否存在 / Check whether ranking exists
        return []  # 没有排行则无响应引导 / Return no response guidance without ranking
    import csv  # 局部导入 CSV 工具 / Locally import CSV utilities
    records = []  # 创建响应记录列表 / Create response record list
    with ranking_path.open("r", encoding="utf-8", newline="") as file_obj:  # 打开排行文件 / Open ranking file
        for row in csv.DictReader(file_obj):  # 遍历排行行 / Iterate ranking rows
            record = build_response_guidance_record(config, candidates_dir, row, target_grid)  # 构建单个响应记录 / Build one response record
            if record is not None:  # 检查记录是否可用 / Check whether record is usable
                records.append(record)  # 保存响应记录 / Store response record
            if len(records) >= limit:  # 检查记录上限 / Check record limit
                break  # 停止读取 / Stop reading
    return records  # 返回响应记录 / Return response records


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
    simulated_grid = downsample_binary_to_grid(nodal, target_grid.shape[0])  # 将仿真节点线压到厚度网格 / Compress simulated nodal lines to thickness grid
    missing = np.clip(target_grid - simulated_grid, 0.0, 1.0)  # 计算目标有而仿真缺失区域 / Compute target-present simulation-missing area
    extra = np.clip(simulated_grid - target_grid, 0.0, 1.0)  # 计算仿真多余区域 / Compute simulation-extra area
    score = float(ranking_row.get("final_score", 0.0) or 0.0)  # 读取最终分数 / Read final score
    return {"candidate_id": candidate_id, "H": np.loadtxt(matrix_path, delimiter=","), "target": target_grid, "simulated": simulated_grid, "missing": missing, "extra": extra, "score": score, "mode": best_mode}  # 返回闭环记录 / Return closed-loop record


def response_error_guidance(record: dict, variant_index: int, levels: list[float], rng: np.random.Generator) -> tuple[np.ndarray, str]:  # 根据真实响应误差生成引导图 / Build guidance from real response error
    parent = matrix_to_guidance(record["H"], levels)  # 读取父代归一化厚度 / Read normalized parent thickness
    target = normalise_design_map(record["target"])  # 读取目标占用图 / Read target occupancy map
    simulated = normalise_design_map(record["simulated"])  # 读取仿真占用图 / Read simulated occupancy map
    missing = smooth_design_map(record["missing"], 2)  # 平滑缺失区域 / Smooth missing area
    extra = smooth_design_map(record["extra"], 2)  # 平滑多余区域 / Smooth extra area
    edge = target_edge_guidance(target)  # 构建目标边缘图 / Build target edge map
    radial = radial_design_bias(parent.shape[0])  # 构建径向破缺图 / Build radial breaking map
    angular = angular_design_bias(parent.shape[0], float(rng.uniform(0.0, 2.0 * np.pi)))  # 构建角向破缺图 / Build angular breaking map
    kind = variant_index % 8  # 选择闭环变体类型 / Select closed-loop variant type
    if kind == 0:  # 第一类：缺失区增厚、多余区减薄 / Type one: thicken missing and thin extra
        return normalise_design_map(0.45 * parent + 0.55 * target + 0.55 * missing - 0.40 * extra), "error_push_positive"  # 返回正向误差推动 / Return positive error push
    if kind == 1:  # 第二类：反向符号探索 / Type two: opposite-sign exploration
        return normalise_design_map(0.45 * parent + 0.50 * target - 0.45 * missing + 0.45 * extra), "error_push_negative"  # 返回反向误差推动 / Return negative error push
    if kind == 2:  # 第三类：目标边缘和缺失区优先 / Type three: target edge and missing area first
        return normalise_design_map(0.35 * parent + 0.35 * edge + 0.55 * missing - 0.25 * simulated), "missing_edge_focus"  # 返回缺失边缘聚焦 / Return missing-edge focus
    if kind == 3:  # 第四类：强力压制多余星形臂 / Type four: strongly suppress extra star arms
        return normalise_design_map(0.55 * parent + 0.45 * target - 0.70 * extra + 0.20 * angular), "extra_suppression"  # 返回多余响应压制 / Return extra-response suppression
    if kind == 4:  # 第五类：反相目标和径向破缺 / Type five: inverse target and radial breaking
        return normalise_design_map(0.35 * parent + 0.45 * (1.0 - target) + 0.25 * radial - 0.35 * extra), "inverse_breaking"  # 返回反相破缺 / Return inverse breaking
    if kind == 5:  # 第六类：父代保持加非对称扰动 / Type six: parent keeping with asymmetric perturbation
        return normalise_design_map(0.65 * parent + 0.25 * target + 0.35 * angular - 0.25 * simulated), "asymmetric_parent"  # 返回非对称父代引导 / Return asymmetric parent guidance
    if kind == 6:  # 第七类：缺失区和反星形共同驱动 / Type seven: missing area and anti-star jointly drive
        return normalise_design_map(0.40 * parent + 0.45 * missing + 0.35 * (1.0 - simulated) + 0.20 * edge), "anti_star_missing"  # 返回反星形缺失引导 / Return anti-star missing guidance
    return normalise_design_map(0.30 * parent + 0.40 * target + 0.20 * radial + 0.20 * angular + rng.normal(0.0, 0.10, size=parent.shape)), "noisy_surrogate"  # 返回噪声代理探索 / Return noisy surrogate exploration


def generate_response_guided_H(records: list[dict], index: int, levels: list[float], default_thickness: float, max_neighbor_diff: float, rng: np.random.Generator) -> tuple[np.ndarray, str]:  # 生成闭环响应引导厚度矩阵 / Generate closed-loop response-guided thickness matrix
    record = records[index % len(records)]  # 选择响应记录 / Select response record
    guidance, variant = response_error_guidance(record, index, levels, rng)  # 生成误差引导图 / Build error guidance map
    H = quantise_guidance_to_levels(guidance, levels)  # 量化为厚度等级 / Quantize to thickness levels
    center_cells = center_cells_for_grid(H.shape[0])  # 获取中心单元 / Get center cells
    fixed_cells = set(center_cells)  # 创建固定中心集合 / Create fixed center set
    mutation_mask = rng.random(H.shape) < 0.08  # 创建闭环探索变异掩膜 / Build closed-loop exploration mutation mask
    for row, col in np.argwhere(mutation_mask):  # 遍历变异单元 / Iterate mutated cells
        if (int(row), int(col)) not in fixed_cells:  # 跳过固定中心单元 / Skip fixed centre cells
            H[row, col] = random_level_near(float(H[row, col]), levels, rng)  # 执行邻近变异 / Apply nearby mutation
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 固定中心厚度 / Fix centre thickness
    H = repair_neighbor_constraint(H, levels, max_neighbor_diff, passes=32, fixed_cells=center_cells)  # 强化修复相邻约束 / Strongly repair neighbour constraints
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 再次固定中心 / Fix centre again
    return H, f"{variant}_from_{record['candidate_id']}"  # 返回矩阵和来源 / Return matrix and source


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
        H = quantise_guidance_to_levels(guided, levels)  # 直接量化引导图 / Directly quantize guidance map
    center_cells = center_cells_for_grid(H.shape[0])  # 获取中心单元 / Get center cells
    mutation_rate = 0.06 if parents else 0.10  # 设置变异率 / Set mutation rate
    mutation_mask = rng.random(H.shape) < mutation_rate  # 创建变异掩膜 / Build mutation mask
    fixed_cells = set(center_cells)  # 创建中心固定集合 / Create fixed center-cell set
    for row, col in np.argwhere(mutation_mask):  # 遍历变异单元 / Iterate mutated cells
        if (int(row), int(col)) not in fixed_cells:  # 跳过中心固定单元 / Skip fixed center cells
            H[row, col] = random_level_near(float(H[row, col]), levels, rng)  # 执行邻近厚度变异 / Apply nearby thickness mutation
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 固定中心厚度 / Fix center thickness
    H = repair_neighbor_constraint(H, levels, max_neighbor_diff, passes=24, fixed_cells=center_cells)  # 修复相邻厚度约束 / Repair neighbour thickness constraint
    H = enforce_center_constraint(H, center_cells, default_thickness)  # 再次固定中心 / Fix centre again
    return H, variant_name  # 返回矩阵和变体名 / Return matrix and variant name


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
    target_grid = load_target_binary_grid(config, grid_size)  # 读取目标感知网格 / Load target-aware grid
    response_records = load_response_guidance_records(config, candidates_dir, target_grid) if target_grid is not None else []  # 读取真实响应闭环记录 / Load real-response closed-loop records
    response_count = max(min(population, len(response_records) * 2), int(population * 0.75)) if response_records else 0  # 计算闭环响应候选数量 / Compute response-guided candidate count
    target_count = max(response_count, max(min(population, 6), int(population * 0.90 if response_records else population * 0.75))) if target_grid is not None else 0  # 计算目标感知候选数量 / Compute target-aware candidate count
    candidate_ids = []  # 创建候选编号列表 / Create candidate id list
    for index in range(population):  # 遍历候选编号 / Iterate candidate index
        candidate_id = f"candidate_{generation:03d}_{index:04d}"  # 构造候选编号 / Build candidate id
        if response_records and index < response_count:  # 优先生成闭环响应引导候选 / Prefer closed-loop response-guided candidates
            H, variant_name = generate_response_guided_H(response_records, index, levels, default, max_diff, rng)  # 生成闭环响应引导矩阵 / Generate response-guided matrix
            created_by = "response_guided_inverse_search"  # 设置生成来源 / Set creation source
        elif target_grid is not None and index < target_count:  # 其次生成目标感知候选 / Then generate target-aware candidates
            H, variant_name = generate_target_guided_H(target_grid, index, parents, levels, default, max_diff, rng)  # 生成目标感知矩阵 / Generate target-aware matrix
            created_by = "target_guided_evolutionary_search" if parents else "target_guided_initial_search"  # 设置生成来源 / Set creation source
        else:  # 保留一部分探索候选 / Keep some exploration candidates
            H = generate_evolutionary_H(parents, levels, default, max_diff, rng) if parents else generate_random_H(grid_size, levels, default, max_diff, rng)  # 生成探索矩阵 / Generate exploration matrix
            variant_name = "evolutionary_explorer" if parents else "random_explorer"  # 设置探索变体名 / Set explorer variant name
            created_by = "evolutionary_search" if parents else "random_search"  # 设置生成来源 / Set creation source
        metadata = {"candidate_id": candidate_id, "generation": generation, "grid_size": grid_size, "thickness_levels_mm": levels, "center_fixed": True, "created_by": created_by, "target_guidance_variant": variant_name, "target_guided": target_grid is not None}  # 记录元数据 / Record metadata
        save_candidate(candidates_dir / candidate_id, H, metadata)  # 保存候选 / Save candidate
        candidate_ids.append(candidate_id)  # 添加候选编号 / Add candidate id
    return candidate_ids  # 返回候选编号 / Return candidate ids
