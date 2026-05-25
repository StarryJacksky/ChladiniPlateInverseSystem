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
from src.scoring.metrics import complexity_similarity  # 导入复杂度相似度 / Import complexity similarity
from src.scoring.metrics import compute_dice  # 导入 Dice 指标 / Import Dice metric
from src.scoring.metrics import compute_iou  # 导入 IoU 指标 / Import IoU metric
from src.scoring.metrics import compute_precision_recall  # 导入精度召回 / Import precision-recall metrics
from src.scoring.metrics import extent_similarity  # 导入包围盒尺度相似度 / Import extent similarity
from src.scoring.metrics import layout_similarity  # 导入布局相似度 / Import layout similarity
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
    amplitude = np.abs(mode)  # 计算振幅绝对值 / Compute absolute amplitude
    threshold = float(epsilon_ratio) * max(float(amplitude.max()), 1.0e-9)  # 计算节点阈值 / Compute nodal threshold
    nodal = amplitude <= threshold  # 提取近零位移区域 / Extract near-zero displacement area
    for row, col in center_cells_for_grid(mode.shape[0]):  # 遍历中心固定单元 / Iterate centre fixed cells
        nodal[row, col] = False  # 移除中心夹持点 / Remove centre clamp point
    return nodal.astype(bool)  # 返回布尔节点图 / Return boolean nodal map


def score_kl_mode(nodal: np.ndarray, target_grid: np.ndarray) -> float:  # 评分单个 KL 代理模态 / Score one KL proxy mode
    target = target_grid > 0.15  # 二值化目标网格 / Binarize target grid
    iou = compute_iou(nodal, target)  # 计算 IoU / Compute IoU
    dice = compute_dice(nodal, target)  # 计算 Dice / Compute Dice
    area = area_similarity(nodal, target)  # 计算面积相似度 / Compute area similarity
    precision, recall = compute_precision_recall(nodal, target)  # 计算精度和召回 / Compute precision and recall
    layout = layout_similarity(nodal, target, cells=min(8, nodal.shape[0]))  # 计算粗布局相似度 / Compute coarse layout similarity
    projection = projection_similarity(nodal, target)  # 计算投影相似度 / Compute projection similarity
    extent = extent_similarity(nodal, target)  # 计算尺度相似度 / Compute extent similarity
    complexity = complexity_similarity(nodal, target)  # 计算复杂度相似度 / Compute complexity similarity
    return float(0.08 * iou + 0.12 * dice + 0.08 * layout + 0.05 * area + 0.05 * precision + 0.22 * recall + 0.20 * projection + 0.14 * extent + 0.06 * complexity)  # 返回覆盖优先的代理合成分 / Return coverage-first proxy combined score


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
    scores = [score_kl_mode(nodal_map_from_mode(mode), target) for mode in modes]  # 计算各阶代理评分 / Compute per-mode proxy scores
    best_index = int(np.argmax(scores)) if scores else 0  # 找最佳模态索引 / Find best mode index
    return {"kl_proxy_score": float(scores[best_index] if scores else 0.0), "kl_proxy_mode": best_index + 1, "kl_proxy_grid_size": int(proxy_H.shape[0])}  # 返回代理评分结果 / Return proxy score result
