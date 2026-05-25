from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

try:  # 优先使用 SciPy 子空间特征求解 / Prefer SciPy subset eigen solve
    from scipy.linalg import eigh as scipy_eigh  # 导入 SciPy 对称特征求解器 / Import SciPy symmetric eigensolver
except Exception:  # 兼容无 SciPy 环境 / Support environments without SciPy
    scipy_eigh = None  # 标记不可用并回退 NumPy / Mark unavailable and fall back to NumPy

try:  # 优先使用 SciPy 稀疏矩阵求解高分辨率代理 / Prefer SciPy sparse matrices for high-resolution proxy solving
    from scipy.sparse import coo_matrix as sparse_coo_matrix  # 导入稀疏 COO 矩阵 / Import sparse COO matrix
    from scipy.sparse import diags as sparse_diags  # 导入稀疏对角矩阵 / Import sparse diagonal matrix
    from scipy.sparse.linalg import eigsh as sparse_eigsh  # 导入稀疏特征求解器 / Import sparse eigensolver
except Exception:  # 兼容无 SciPy 稀疏模块环境 / Support environments without SciPy sparse modules
    sparse_coo_matrix = None  # 标记 COO 不可用 / Mark COO unavailable
    sparse_diags = None  # 标记对角矩阵不可用 / Mark diagonal matrix unavailable
    sparse_eigsh = None  # 标记稀疏特征求解不可用 / Mark sparse eigensolver unavailable

from src.candidate.constraints import center_cells_for_grid  # 导入中心单元工具 / Import centre-cell helper
from src.scoring.metrics import area_similarity  # 导入面积相似度 / Import area similarity
from src.scoring.metrics import chamfer_distance  # 导入倒角距离场 / Import chamfer distance field
from src.scoring.metrics import chamfer_similarity  # 导入倒角距离相似度 / Import chamfer-distance similarity
from src.scoring.metrics import component_similarity  # 导入连通拓扑相似度 / Import connected-topology similarity
from src.scoring.metrics import complexity_similarity  # 导入复杂度相似度 / Import complexity similarity
from src.scoring.metrics import coverage_f_score  # 导入覆盖 F 分数 / Import coverage F-score
from src.scoring.metrics import compute_dice  # 导入 Dice 指标 / Import Dice metric
from src.scoring.metrics import compute_iou  # 导入 IoU 指标 / Import IoU metric
from src.scoring.metrics import compute_overlap_balance  # 导入覆盖平衡分 / Import overlap balance score
from src.scoring.metrics import compute_precision_recall  # 导入精度召回 / Import precision-recall metrics
from src.scoring.metrics import extent_similarity  # 导入包围盒尺度相似度 / Import extent similarity
from src.scoring.metrics import foreground_extent  # 导入前景包围盒特征 / Import foreground extent features
from src.scoring.metrics import layout_similarity  # 导入布局相似度 / Import layout similarity
from src.scoring.metrics import overcoverage_penalty  # 导入过覆盖惩罚 / Import overcoverage penalty
from src.scoring.metrics import pattern_similarity  # 导入统一图案相似度 / Import unified pattern similarity
from src.scoring.metrics import projection_similarity  # 导入投影相似度 / Import projection similarity


def bending_stiffness_pa_m3(H_mm: np.ndarray, youngs_modulus_pa: float, poisson_ratio: float) -> np.ndarray:  # 计算 Kirchhoff-Love 弯曲刚度 / Compute Kirchhoff-Love bending stiffness
    h_m = np.maximum(H_mm.astype(float) * 1.0e-3, 1.0e-6)  # 转换厚度到米并限下界 / Convert thickness to metres and clamp lower bound
    denominator = 12.0 * max(1.0 - poisson_ratio * poisson_ratio, 1.0e-6)  # 计算弯曲刚度分母 / Compute bending-stiffness denominator
    return youngs_modulus_pa * h_m**3 / denominator  # 返回 D=Eh^3/[12(1-nu^2)] / Return D=Eh^3/[12(1-nu^2)]


def mass_per_area_kg_m2(H_mm: np.ndarray, density_kg_m3: float) -> np.ndarray:  # 计算面密度 / Compute mass per area
    return density_kg_m3 * np.maximum(H_mm.astype(float) * 1.0e-3, 1.0e-6)  # 返回 rho*h / Return rho*h


def flat_index(row: int, col: int, cols: int) -> int:  # 计算扁平索引 / Compute flat index
    return row * cols + col  # 返回扁平索引 / Return flat index


def build_laplacian_matrix(rows: int, cols: int, dx_m: float, dy_m: float) -> np.ndarray:  # 构建五点拉普拉斯矩阵 / Build five-point Laplacian matrix
    count = rows * cols  # 计算自由度总数 / Compute total degrees of freedom
    L = np.zeros((count, count), dtype=float)  # 创建矩阵 / Create matrix
    for row in range(rows):  # 遍历行 / Iterate rows
        for col in range(cols):  # 遍历列 / Iterate columns
            index = flat_index(row, col, cols)  # 计算当前索引 / Compute current index
            L[index, index] = -2.0 / (dx_m * dx_m) - 2.0 / (dy_m * dy_m)  # 设置中心系数 / Set centre coefficient
            if row > 0:  # 检查上邻居 / Check upper neighbour
                L[index, flat_index(row - 1, col, cols)] = 1.0 / (dy_m * dy_m)  # 设置上邻居系数 / Set upper-neighbour coefficient
            if row + 1 < rows:  # 检查下邻居 / Check lower neighbour
                L[index, flat_index(row + 1, col, cols)] = 1.0 / (dy_m * dy_m)  # 设置下邻居系数 / Set lower-neighbour coefficient
            if col > 0:  # 检查左邻居 / Check left neighbour
                L[index, flat_index(row, col - 1, cols)] = 1.0 / (dx_m * dx_m)  # 设置左邻居系数 / Set left-neighbour coefficient
            if col + 1 < cols:  # 检查右邻居 / Check right neighbour
                L[index, flat_index(row, col + 1, cols)] = 1.0 / (dx_m * dx_m)  # 设置右邻居系数 / Set right-neighbour coefficient
    return L  # 返回拉普拉斯矩阵 / Return Laplacian matrix


def build_sparse_laplacian_matrix(rows: int, cols: int, dx_m: float, dy_m: float):  # 构建稀疏五点拉普拉斯矩阵 / Build sparse five-point Laplacian matrix
    row_indices = []  # 创建稀疏矩阵行索引 / Create sparse row indices
    col_indices = []  # 创建稀疏矩阵列索引 / Create sparse column indices
    values = []  # 创建稀疏矩阵数值 / Create sparse matrix values
    for row in range(rows):  # 遍历网格行 / Iterate grid rows
        for col in range(cols):  # 遍历网格列 / Iterate grid columns
            index = flat_index(row, col, cols)  # 计算当前自由度索引 / Compute current degree-of-freedom index
            entries = [(index, -2.0 / (dx_m * dx_m) - 2.0 / (dy_m * dy_m))]  # 创建本行中心项 / Create centre entry for this row
            if row > 0:  # 检查上邻居 / Check upper neighbour
                entries.append((flat_index(row - 1, col, cols), 1.0 / (dy_m * dy_m)))  # 添加上邻居项 / Add upper-neighbour entry
            if row + 1 < rows:  # 检查下邻居 / Check lower neighbour
                entries.append((flat_index(row + 1, col, cols), 1.0 / (dy_m * dy_m)))  # 添加下邻居项 / Add lower-neighbour entry
            if col > 0:  # 检查左邻居 / Check left neighbour
                entries.append((flat_index(row, col - 1, cols), 1.0 / (dx_m * dx_m)))  # 添加左邻居项 / Add left-neighbour entry
            if col + 1 < cols:  # 检查右邻居 / Check right neighbour
                entries.append((flat_index(row, col + 1, cols), 1.0 / (dx_m * dx_m)))  # 添加右邻居项 / Add right-neighbour entry
            for col_index, value in entries:  # 遍历当前行非零项 / Iterate nonzero entries for this row
                row_indices.append(index)  # 保存行索引 / Store row index
                col_indices.append(col_index)  # 保存列索引 / Store column index
                values.append(value)  # 保存矩阵数值 / Store matrix value
    count = rows * cols  # 计算自由度数量 / Compute degree-of-freedom count
    return sparse_coo_matrix((values, (row_indices, col_indices)), shape=(count, count)).tocsr()  # 返回 CSR 稀疏矩阵 / Return CSR sparse matrix


def free_dof_indices(rows: int, cols: int) -> np.ndarray:  # 生成去除中心夹持后的自由度索引 / Build free DOF indices after centre clamp removal
    fixed = set(center_cells_for_grid(rows))  # 读取中心固定单元 / Read centre fixed cells
    indices = [flat_index(row, col, cols) for row in range(rows) for col in range(cols) if (row, col) not in fixed]  # 构建自由索引 / Build free indices
    return np.asarray(indices, dtype=int)  # 返回索引数组 / Return index array


def upsample_thickness_nearest(H_mm: np.ndarray, proxy_grid_size: int) -> np.ndarray:  # 将设计厚度上采样到代理网格 / Upsample design thickness to proxy grid
    rows, cols = H_mm.shape  # 读取设计网格尺寸 / Read design-grid shape
    if proxy_grid_size <= max(rows, cols):  # 检查是否不需要上采样 / Check whether upsampling is unnecessary
        return H_mm.astype(float)  # 返回原厚度场 / Return original thickness field
    row_index = np.minimum((np.arange(proxy_grid_size) * rows / proxy_grid_size).astype(int), rows - 1)  # 计算最近邻行索引 / Compute nearest-neighbour row indices
    col_index = np.minimum((np.arange(proxy_grid_size) * cols / proxy_grid_size).astype(int), cols - 1)  # 计算最近邻列索引 / Compute nearest-neighbour column indices
    return H_mm.astype(float)[np.ix_(row_index, col_index)]  # 返回上采样厚度场 / Return upsampled thickness field


def solve_kl_modes_sparse(H_mm: np.ndarray, plate_length_mm: float, plate_width_mm: float, material: dict, num_modes: int = 8) -> list[np.ndarray]:  # 求解稀疏高分辨率 KL 模态 / Solve sparse high-resolution KL modes
    rows, cols = H_mm.shape  # 读取厚度网格尺寸 / Read thickness-grid shape
    dx_m = (plate_length_mm * 1.0e-3) / max(cols, 1)  # 计算 x 单元尺寸 / Compute x cell size
    dy_m = (plate_width_mm * 1.0e-3) / max(rows, 1)  # 计算 y 单元尺寸 / Compute y cell size
    youngs = float(material.get("youngs_modulus_pa", 2.0e9))  # 读取杨氏模量 / Read Young's modulus
    poisson = float(material.get("poisson_ratio", 0.35))  # 读取泊松比 / Read Poisson ratio
    density = float(material.get("density_kg_m3", 1200.0))  # 读取密度 / Read density
    D = bending_stiffness_pa_m3(H_mm, youngs, poisson).ravel()  # 计算扁平弯曲刚度 / Compute flattened bending stiffness
    M = mass_per_area_kg_m2(H_mm, density).ravel()  # 计算扁平质量 / Compute flattened mass
    L = build_sparse_laplacian_matrix(rows, cols, dx_m, dy_m)  # 构建稀疏拉普拉斯矩阵 / Build sparse Laplacian matrix
    K = L.T @ sparse_diags(D) @ L  # 构建稀疏 KL 刚度矩阵 / Build sparse KL stiffness matrix
    free = free_dof_indices(rows, cols)  # 获取自由自由度索引 / Get free degree-of-freedom indices
    Kf = K[free, :][:, free]  # 截取自由刚度矩阵 / Slice free stiffness matrix
    Mf = np.maximum(M[free], 1.0e-9)  # 截取自由质量并限下界 / Slice free mass and clamp lower bound
    mode_count = min(max(1, int(num_modes)), max(1, Kf.shape[0] - 2))  # 限制求解模态数量 / Clamp requested mode count
    try:  # 捕获稀疏求解失败 / Catch sparse solve failures
        values, vectors = sparse_eigsh(Kf, k=mode_count, M=sparse_diags(Mf), which="SM", tol=1.0e-5, maxiter=max(1000, 30 * Kf.shape[0]))  # 求解最低阶广义特征模态 / Solve lowest generalized eigenmodes
    except Exception:  # 稀疏小特征值求解失败时使用移位反演 / Use shift-invert if small-eigen solve fails
        values, vectors = sparse_eigsh(Kf, k=mode_count, M=sparse_diags(Mf), sigma=1.0e-9, which="LM", tol=1.0e-5, maxiter=max(1000, 30 * Kf.shape[0]))  # 用移位反演求低阶模态 / Solve low modes with shift-invert
    order = np.argsort(values)  # 按特征值排序 / Sort by eigenvalue
    modes = []  # 创建模态列表 / Create mode list
    for item in order:  # 遍历排序后的模态 / Iterate sorted modes
        full = np.zeros(rows * cols, dtype=float)  # 创建全自由度向量 / Create full degree-of-freedom vector
        full[free] = vectors[:, int(item)]  # 写入自由自由度模态 / Store free degree-of-freedom mode
        modes.append(full.reshape(rows, cols))  # 保存二维模态 / Store two-dimensional mode
    return modes  # 返回模态列表 / Return mode list


def solve_kl_modes(H_mm: np.ndarray, plate_length_mm: float, plate_width_mm: float, material: dict, num_modes: int = 8) -> list[np.ndarray]:  # 求解简化 KL 离散特征模态 / Solve simplified KL discrete eigenmodes
    if H_mm.size > 400 and sparse_eigsh is not None and sparse_diags is not None and sparse_coo_matrix is not None:  # 高分辨率时使用稀疏求解 / Use sparse solve at high resolution
        return solve_kl_modes_sparse(H_mm, plate_length_mm, plate_width_mm, material, num_modes)  # 返回稀疏求解结果 / Return sparse solve result
    rows, cols = H_mm.shape  # 读取厚度网格尺寸 / Read thickness-grid shape
    dx_m = (plate_length_mm * 1.0e-3) / max(cols, 1)  # 计算 x 单元尺寸 / Compute x cell size
    dy_m = (plate_width_mm * 1.0e-3) / max(rows, 1)  # 计算 y 单元尺寸 / Compute y cell size
    youngs = float(material.get("youngs_modulus_pa", 2.0e9))  # 读取杨氏模量 / Read Young's modulus
    poisson = float(material.get("poisson_ratio", 0.35))  # 读取泊松比 / Read Poisson ratio
    density = float(material.get("density_kg_m3", 1200.0))  # 读取密度 / Read density
    D = bending_stiffness_pa_m3(H_mm, youngs, poisson).ravel()  # 计算扁平弯曲刚度 / Compute flattened bending stiffness
    M = mass_per_area_kg_m2(H_mm, density).ravel()  # 计算扁平面密度 / Compute flattened mass per area
    L = build_laplacian_matrix(rows, cols, dx_m, dy_m)  # 构建离散拉普拉斯 / Build discrete Laplacian
    K = L.T @ (D[:, None] * L)  # 构建 KL 代理刚度 K=L^T D L / Build KL proxy stiffness K=L^T D L
    free = free_dof_indices(rows, cols)  # 获取自由度索引 / Get free DOF indices
    Kf = K[np.ix_(free, free)]  # 截取自由刚度矩阵 / Slice free stiffness matrix
    Mf = np.maximum(M[free], 1.0e-9)  # 截取自由质量并限下界 / Slice free mass and clamp lower bound
    scaled = Kf / np.sqrt(np.outer(Mf, Mf))  # 转换广义特征问题为标准特征问题 / Convert generalized eigenproblem to standard eigenproblem
    scaled = 0.5 * (scaled + scaled.T)  # 强制数值对称 / Enforce numerical symmetry
    if scipy_eigh is not None:  # 检查是否可用 SciPy 快路径 / Check whether SciPy fast path is available
        values, vectors = scipy_eigh(scaled, subset_by_index=[0, min(max(num_modes - 1, 0), scaled.shape[0] - 1)])  # 只求最低阶模态 / Solve only the lowest modes
        order = np.arange(len(values))  # SciPy 已按特征值排序 / SciPy already sorts eigenvalues
    else:  # 回退完整 NumPy 求解 / Fall back to full NumPy solve
        values, vectors = np.linalg.eigh(scaled)  # 求解特征值问题 / Solve eigenvalue problem
        order = np.argsort(values)[:num_modes]  # 选取最低若干阶 / Select lowest modes
    modes = []  # 创建模态列表 / Create mode list
    for item in order:  # 遍历选中模态 / Iterate selected modes
        full = np.zeros(rows * cols, dtype=float)  # 创建全自由度向量 / Create full DOF vector
        full[free] = vectors[:, int(item)] / np.sqrt(Mf)  # 还原广义模态 / Recover generalized mode
        modes.append(full.reshape(rows, cols))  # 保存二维模态 / Store two-dimensional mode
    return modes  # 返回模态列表 / Return mode list


def nodal_map_from_mode(mode: np.ndarray, epsilon_ratio: float = 0.12) -> np.ndarray:  # 从代理模态提取节点线 / Extract nodal map from proxy mode
    values = mode.astype(float)  # 转换模态为浮点矩阵 / Convert mode to float matrix
    amplitude = np.abs(values)  # 计算振幅绝对值 / Compute absolute amplitude
    threshold = float(epsilon_ratio) * max(float(amplitude.max()), 1.0e-9)  # 计算节点阈值 / Compute nodal threshold
    nodal = amplitude <= threshold  # 提取近零位移区域 / Extract near-zero displacement area
    vertical_change = values[:-1, :] * values[1:, :] <= 0.0  # 检测纵向符号翻转 / Detect vertical sign changes
    horizontal_change = values[:, :-1] * values[:, 1:] <= 0.0  # 检测横向符号翻转 / Detect horizontal sign changes
    nodal[:-1, :] |= vertical_change  # 标记纵向翻转上侧 / Mark upper side of vertical changes
    nodal[1:, :] |= vertical_change  # 标记纵向翻转下侧 / Mark lower side of vertical changes
    nodal[:, :-1] |= horizontal_change  # 标记横向翻转左侧 / Mark left side of horizontal changes
    nodal[:, 1:] |= horizontal_change  # 标记横向翻转右侧 / Mark right side of horizontal changes
    padded = np.pad(nodal, 1, mode="constant", constant_values=False)  # 填充节点图用于加粗 / Pad nodal map for line thickening
    nodal = padded[1:-1, 1:-1] | padded[:-2, 1:-1] | padded[2:, 1:-1] | padded[1:-1, :-2] | padded[1:-1, 2:]  # 加粗一格代理节点线 / Thicken proxy nodal lines by one cell
    for row, col in center_cells_for_grid(mode.shape[0]):  # 遍历中心固定单元 / Iterate centre fixed cells
        nodal[row, col] = False  # 移除中心夹持点 / Remove centre clamp point
    return nodal.astype(bool)  # 返回布尔节点图 / Return boolean nodal map


def score_kl_mode(nodal: np.ndarray, target_grid: np.ndarray) -> float:  # 评分单个 KL 代理模态 / Score one KL proxy mode
    target = target_grid > 0.15  # 二值化目标网格 / Binarize target grid
    iou = compute_iou(nodal, target)  # 计算 IoU / Compute IoU
    dice = compute_dice(nodal, target)  # 计算 Dice / Compute Dice
    area = area_similarity(nodal, target)  # 计算面积相似度 / Compute area similarity
    overlap = compute_overlap_balance(nodal, target)  # 计算覆盖平衡 / Compute overlap balance
    precision, recall = compute_precision_recall(nodal, target)  # 计算精度和召回 / Compute precision and recall
    layout = layout_similarity(nodal, target, cells=min(8, nodal.shape[0]))  # 计算粗布局相似度 / Compute coarse layout similarity
    projection = projection_similarity(nodal, target)  # 计算投影相似度 / Compute projection similarity
    extent = extent_similarity(nodal, target)  # 计算尺度相似度 / Compute extent similarity
    complexity = complexity_similarity(nodal, target)  # 计算复杂度相似度 / Compute complexity similarity
    topology = component_similarity(nodal, target)  # 计算连通拓扑相似度 / Compute connected-topology similarity
    return pattern_similarity(iou, dice, 0.0, overlap, layout, area, precision, recall, projection, extent, complexity, topology)  # 返回统一口径的代理合成分 / Return unified proxy combined score


def compact_center_trap_penalty(nodal: np.ndarray, target_grid: np.ndarray) -> float:  # 惩罚中心小团陷阱 / Penalize compact-centre traps
    mode = nodal.astype(bool)  # 转换代理模态节点图 / Convert proxy nodal map
    target = target_grid > 0.15  # 二值化目标图案 / Binarize target pattern
    if not mode.any() or not target.any():  # 检查空图案 / Check empty maps
        return 1.0  # 空响应视为严重陷阱 / Treat empty response as severe trap
    mode_width, mode_height, mode_x, mode_y, _ = foreground_extent(mode)  # 读取模态包围盒 / Read mode bounding box
    target_width, target_height, _, _, _ = foreground_extent(target)  # 读取目标包围盒 / Read target bounding box
    mode_extent = 0.5 * (mode_width + mode_height)  # 计算模态平均尺度 / Compute average mode extent
    target_extent = max(0.5 * (target_width + target_height), 1.0e-9)  # 计算目标平均尺度 / Compute average target extent
    missing_extent = max(0.0, target_extent - mode_extent) / target_extent  # 计算模态尺度不足 / Compute missing extent
    mode_area = float(mode.mean())  # 计算模态面积比例 / Compute mode area ratio
    target_area = max(float(target.mean()), 1.0e-9)  # 计算目标面积比例 / Compute target area ratio
    undersize = max(0.0, target_area - mode_area) / target_area  # 计算面积不足 / Compute area undersize
    center_distance = float(np.hypot(mode_x - 0.5, mode_y - 0.5))  # 计算模态中心偏移 / Compute mode centre offset
    centered = float(np.clip(1.0 - center_distance / 0.42, 0.0, 1.0))  # 计算中心陷阱权重 / Compute centre-trap weight
    return float(np.clip(centered * (0.65 * missing_extent + 0.35 * undersize), 0.0, 1.0))  # 返回陷阱惩罚 / Return trap penalty


def radial_spoke_trap_penalty(nodal: np.ndarray, target_grid: np.ndarray) -> float:  # 惩罚中心辐射骨架陷阱 / Penalize centre-radiating spoke traps
    mode = nodal.astype(bool)  # 转换代理模态节点图 / Convert proxy nodal map
    target = target_grid > 0.15  # 二值化目标图案 / Binarize target pattern
    rows, cols = mode.shape  # 读取图像尺寸 / Read map shape
    yy, xx = np.meshgrid(np.linspace(-1.0, 1.0, rows), np.linspace(-1.0, 1.0, cols), indexing="ij")  # 构建归一化坐标 / Build normalized coordinates
    radius = np.sqrt(xx * xx + yy * yy)  # 计算归一化半径 / Compute normalized radius
    central = radius < 0.30  # 定义中心影响区域 / Define centre-influence zone
    edge_band = (np.abs(xx) > 0.78) | (np.abs(yy) > 0.78)  # 定义边缘触达区域 / Define edge-touch zone
    mode_central = float(mode[central].mean()) if central.any() else 0.0  # 计算模态中心占用 / Compute mode centre occupancy
    target_central = float(target[central].mean()) if central.any() else 0.0  # 计算目标中心占用 / Compute target centre occupancy
    mode_edge = float(mode[edge_band].mean()) if edge_band.any() else 0.0  # 计算模态边缘占用 / Compute mode edge occupancy
    target_edge = float(target[edge_band].mean()) if edge_band.any() else 0.0  # 计算目标边缘占用 / Compute target edge occupancy
    center_excess = float(np.clip((mode_central - target_central - 0.04) / 0.28, 0.0, 1.0))  # 计算中心过量占用 / Compute excessive centre occupancy
    edge_excess = float(np.clip((mode_edge - target_edge - 0.03) / 0.24, 0.0, 1.0))  # 计算边缘过量触达 / Compute excessive edge touch
    return float(np.clip(0.60 * center_excess + 0.40 * center_excess * edge_excess, 0.0, 1.0))  # 返回辐射骨架惩罚 / Return spoke-trap penalty


def target_crossing_sign_field(target_grid: np.ndarray, axis: int) -> np.ndarray:  # 根据目标笔画构造穿越符号场 / Build crossing sign field from target strokes
    stroke = target_grid > 0.15  # 二值化目标笔画 / Binarize target strokes
    transitions = np.cumsum(stroke.astype(int), axis=axis) % 2  # 统计沿轴穿越目标的奇偶性 / Count crossing parity along axis
    return np.where(transitions == 0, 1.0, -1.0)  # 返回正负符号图 / Return signed field


def target_modal_field_variants(target_grid: np.ndarray) -> list[np.ndarray]:  # 构造期望模态符号场变体 / Build desired modal sign-field variants
    stroke = target_grid > 0.15  # 二值化目标笔画 / Binarize target strokes
    distance = chamfer_distance(stroke)  # 计算到目标笔画的距离 / Compute distance to target strokes
    envelope = np.tanh(distance / 1.8)  # 构造离开零线后的幅值包络 / Build amplitude envelope away from zero line
    x_sign = target_crossing_sign_field(target_grid, axis=1)  # 构造横向穿越符号 / Build horizontal crossing sign
    y_sign = target_crossing_sign_field(target_grid, axis=0)  # 构造纵向穿越符号 / Build vertical crossing sign
    variants = [x_sign, y_sign, x_sign * y_sign, np.sign(0.70 * x_sign + 0.30 * y_sign), np.sign(0.35 * x_sign + 0.65 * y_sign)]  # 组合多种符号假设 / Combine multiple sign hypotheses
    fields = []  # 创建期望场列表 / Create desired-field list
    for sign in variants:  # 遍历符号假设 / Iterate sign hypotheses
        field = sign.astype(float) * envelope  # 生成目标零线模态场 / Build target-zero modal field
        field[stroke] = 0.0  # 强制目标线为零位移 / Force target strokes to zero displacement
        field = field - float(field.mean())  # 去除常量偏置 / Remove constant bias
        fields.append(field)  # 保存期望场 / Store desired field
    return fields  # 返回期望场变体 / Return desired field variants


def normalised_field_correlation(left: np.ndarray, right: np.ndarray) -> float:  # 计算两个场的归一化相关 / Compute normalized field correlation
    left_vec = (left.astype(float) - float(left.mean())).ravel()  # 展平并去均值左场 / Flatten and center left field
    right_vec = (right.astype(float) - float(right.mean())).ravel()  # 展平并去均值右场 / Flatten and center right field
    denominator = max(float(np.linalg.norm(left_vec) * np.linalg.norm(right_vec)), 1.0e-9)  # 计算稳定分母 / Compute stable denominator
    return float(abs(np.dot(left_vec, right_vec)) / denominator)  # 返回翻转不变相关 / Return sign-flip-invariant correlation


def modal_field_alignment(mode: np.ndarray, target_grid: np.ndarray) -> float:  # 计算模态场与目标符号场的一致性 / Compute alignment between mode field and target sign fields
    variants = target_modal_field_variants(target_grid)  # 构造目标模态场变体 / Build target modal-field variants
    return max(normalised_field_correlation(mode, variant) for variant in variants) if variants else 0.0  # 返回最佳符号场相关 / Return best sign-field correlation


def score_kl_mode_search(mode: np.ndarray, nodal: np.ndarray, target_grid: np.ndarray) -> float:  # 给搜索用的连续软评分 / Score one KL mode with a continuous search objective
    target = target_grid > 0.15  # 二值化目标网格 / Binarize target grid
    iou = compute_iou(nodal, target)  # 计算 IoU / Compute IoU
    dice = compute_dice(nodal, target)  # 计算 Dice / Compute Dice
    area = area_similarity(nodal, target)  # 计算面积相似度 / Compute area similarity
    overlap = compute_overlap_balance(nodal, target)  # 计算覆盖平衡 / Compute overlap balance
    precision, recall = compute_precision_recall(nodal, target)  # 计算精度召回 / Compute precision and recall
    layout = layout_similarity(nodal, target, cells=min(8, nodal.shape[0]))  # 计算粗布局相似度 / Compute coarse layout similarity
    projection = projection_similarity(nodal, target)  # 计算投影相似度 / Compute projection similarity
    extent = extent_similarity(nodal, target)  # 计算包围盒尺度相似度 / Compute extent similarity
    complexity = complexity_similarity(nodal, target)  # 计算复杂度相似度 / Compute complexity similarity
    topology = component_similarity(nodal, target)  # 计算连通拓扑相似度 / Compute connected topology similarity
    chamfer = chamfer_similarity(nodal, target)  # 计算距离场软相似度 / Compute distance-field soft similarity
    balance = coverage_f_score(precision, recall)  # 计算精度召回 F 分数 / Compute precision-recall F-score
    signed = modal_field_alignment(mode, target_grid)  # 计算符号场相关分 / Compute signed-field alignment score
    soft = 0.05 * iou + 0.06 * dice + 0.14 * chamfer + 0.08 * overlap + 0.10 * layout + 0.10 * projection + 0.10 * extent + 0.05 * area + 0.03 * complexity + 0.03 * topology + 0.03 * balance + 0.23 * signed  # 合成搜索软分 / Combine search soft score
    penalty = overcoverage_penalty(precision, recall, area)  # 计算过覆盖惩罚 / Compute overcoverage penalty
    trap = compact_center_trap_penalty(nodal, target)  # 计算中心小团陷阱惩罚 / Compute compact-centre trap penalty
    spoke = radial_spoke_trap_penalty(nodal, target)  # 计算中心辐射骨架惩罚 / Compute centre-spoke trap penalty
    precision_shortfall = float(np.clip((0.22 - precision) / 0.22, 0.0, 1.0))  # 计算精度不足惩罚 / Compute precision-shortfall penalty
    return float(max(0.0, soft - 0.16 * penalty - 0.22 * trap - 0.18 * spoke - 0.12 * precision_shortfall))  # 返回连续搜索评分 / Return continuous search score


def resize_target_to_grid(target_grid: np.ndarray, grid_size: int) -> np.ndarray:  # 将目标图压缩到代理网格 / Compress target map to proxy grid
    if target_grid.shape == (grid_size, grid_size):  # 检查尺寸是否已匹配 / Check whether shape already matches
        return target_grid.astype(float)  # 返回浮点目标 / Return float target
    rows, cols = target_grid.shape  # 读取目标尺寸 / Read target shape
    row_edges = np.linspace(0, rows, grid_size + 1).astype(int)  # 构造行边界 / Build row edges
    col_edges = np.linspace(0, cols, grid_size + 1).astype(int)  # 构造列边界 / Build column edges
    resized = np.zeros((grid_size, grid_size), dtype=float)  # 创建压缩目标 / Create compressed target
    for row in range(grid_size):  # 遍历代理网格行 / Iterate proxy-grid rows
        for col in range(grid_size):  # 遍历代理网格列 / Iterate proxy-grid columns
            block = target_grid[row_edges[row]:row_edges[row + 1], col_edges[col]:col_edges[col + 1]]  # 读取目标块 / Read target block
            resized[row, col] = float(block.mean()) if block.size else 0.0  # 保存平均占用 / Store average occupancy
    return resized  # 返回压缩目标 / Return compressed target


def load_full_resolution_target(config: dict) -> np.ndarray | None:  # 读取完整分辨率目标图 / Load full-resolution target map
    target_path = Path(config.get("paths", {}).get("processed_targets_dir", "")) / "target_binary.npy"  # 构造目标数组路径 / Build target array path
    if not target_path.exists():  # 检查目标数组是否存在 / Check whether target array exists
        return None  # 缺失时返回空 / Return none when missing
    return np.load(target_path).astype(float)  # 返回目标数组 / Return target array


def proxy_target_for_grid(target_grid: np.ndarray, config: dict, grid_size: int) -> np.ndarray:  # 为代理网格准备目标图 / Prepare target map for proxy grid
    full_target = load_full_resolution_target(config)  # 尝试读取完整目标图 / Try loading full target map
    source = full_target if full_target is not None else target_grid  # 优先使用完整目标 / Prefer full target
    return resize_target_to_grid(source, grid_size)  # 缩放到代理网格 / Resize to proxy grid


def score_thickness_with_kl_proxy(H_mm: np.ndarray, target_grid: np.ndarray, config: dict, num_modes: int = 8) -> dict:  # 使用 KL 离散特征方程评分厚度场 / Score thickness field with KL discrete eigen equation
    proxy_grid_size = int(config.get("optimisation", {}).get("kl_proxy_grid_size", H_mm.shape[0]))  # 读取 KL 代理网格尺寸 / Read KL proxy grid size
    proxy_grid_size = max(int(H_mm.shape[0]), proxy_grid_size + (1 if proxy_grid_size % 2 == 0 else 0))  # 保持代理网格为不小于设计网格的奇数 / Keep proxy grid odd and no smaller than design grid
    proxy_H = upsample_thickness_nearest(H_mm, proxy_grid_size)  # 上采样厚度到代理网格 / Upsample thickness to proxy grid
    modes = solve_kl_modes(proxy_H, float(config["project"]["plate_length_mm"]), float(config["project"]["plate_width_mm"]), config.get("material", {}), num_modes=num_modes)  # 求解代理模态 / Solve proxy modes
    target = proxy_target_for_grid(target_grid, config, proxy_H.shape[0])  # 对齐完整目标到代理网格 / Align full target to proxy grid
    min_mode = int(config.get("optimisation", {}).get("kl_proxy_min_mode", config.get("optimisation", {}).get("target_min_mode", 1)))  # 读取代理最低匹配模态 / Read minimum proxy matching mode
    objective = str(config.get("optimisation", {}).get("kl_proxy_objective", "search_soft"))  # 读取代理优化目标 / Read proxy optimisation objective
    scoring_fn = score_kl_mode_search if objective == "search_soft" else score_kl_mode  # 选择搜索软分或严格分 / Choose search-soft or strict score
    indexed_scores = [(index + 1, scoring_fn(mode, nodal_map_from_mode(mode), target) if objective == "search_soft" else scoring_fn(nodal_map_from_mode(mode), target)) for index, mode in enumerate(modes) if index + 1 >= min_mode]  # 计算过滤后的代理评分 / Compute filtered proxy scores
    if not indexed_scores:  # 检查是否没有高阶代理模态 / Check whether no high-order proxy mode exists
        indexed_scores = [(index + 1, scoring_fn(mode, nodal_map_from_mode(mode), target) if objective == "search_soft" else scoring_fn(nodal_map_from_mode(mode), target)) for index, mode in enumerate(modes)]  # 回退全部模态评分 / Fall back to all mode scores
    best_mode, best_score = max(indexed_scores, key=lambda item: item[1]) if indexed_scores else (1, 0.0)  # 选择最佳代理模态 / Select best proxy mode
    best_nodal = nodal_map_from_mode(modes[max(0, min(len(modes) - 1, best_mode - 1))]) if modes else np.zeros_like(target, dtype=bool)  # 读取最佳模态节点图 / Read best-mode nodal map
    strict_score = score_kl_mode(best_nodal, target) if modes else 0.0  # 计算严格参考分 / Compute strict reference score
    return {"kl_proxy_score": float(best_score), "kl_proxy_strict_score": float(strict_score), "kl_proxy_mode": int(best_mode), "kl_proxy_grid_size": int(proxy_H.shape[0]), "kl_proxy_objective": objective}  # 返回代理评分结果 / Return proxy score result
