from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
from dataclasses import dataclass  # 导入数据类装饰器 / Import dataclass decorator
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.physics.kirchhoff_love import bending_stiffness_pa_m3  # 复用主项目的弯曲刚度 / Reuse main project's bending stiffness
from src.physics.kirchhoff_love import build_laplacian_matrix  # 复用主项目的稠密拉普拉斯 / Reuse main project's dense Laplacian
from src.physics.kirchhoff_love import build_sparse_laplacian_matrix  # 复用主项目的稀疏拉普拉斯 / Reuse main project's sparse Laplacian
from src.physics.kirchhoff_love import free_dof_indices  # 复用主项目的自由度索引 / Reuse main project's free DOF indices
from src.physics.kirchhoff_love import mass_per_area_kg_m2  # 复用主项目的面密度 / Reuse main project's mass per area

try:  # 优先稀疏求解 / Prefer sparse solver
    from scipy.sparse import diags as sparse_diags  # 导入稀疏对角矩阵 / Import sparse diagonal matrix
    from scipy.sparse.linalg import eigsh as sparse_eigsh  # 导入稀疏特征求解器 / Import sparse eigensolver
except Exception:  # 兼容环境 / Compatibility
    sparse_diags = None  # 标记不可用 / Mark unavailable
    sparse_eigsh = None  # 标记不可用 / Mark unavailable

try:  # 优先 SciPy 子集 eigh / Prefer SciPy subset eigh
    from scipy.linalg import eigh as scipy_eigh  # 导入 SciPy 对称特征求解器 / Import SciPy symmetric eigensolver
except Exception:  # 兼容环境 / Compatibility
    scipy_eigh = None  # 标记不可用 / Mark unavailable


@dataclass  # 数据类装饰器 / Dataclass decorator
class UniformMode:  # 单个均匀板模态 / One uniform-plate mode
    index: int  # 模态编号（从 1 起） / 1-indexed mode number
    frequency_hz: float  # 本征频率 Hz / Eigenfrequency in Hz
    omega_squared: float  # 角频率平方 ω² / Angular frequency squared
    mode_field: np.ndarray  # 代理网格上的模态位移场 / Mode displacement field on proxy grid
    nodal_mask: np.ndarray  # 代理网格上的节点线布尔图 / Boolean nodal-line mask on proxy grid


def _solve_eigenpairs(H_mm: np.ndarray, plate_length_mm: float, plate_width_mm: float, material: dict, num_modes: int) -> tuple[np.ndarray, np.ndarray]:  # 求解前 N 阶本征对 / Solve first N eigenpairs
    rows, cols = H_mm.shape  # 读取代理网格尺寸 / Read proxy-grid shape
    dx_m = (plate_length_mm * 1.0e-3) / max(cols, 1)  # x 单元尺寸 / Cell size in x
    dy_m = (plate_width_mm * 1.0e-3) / max(rows, 1)  # y 单元尺寸 / Cell size in y
    youngs = float(material.get("youngs_modulus_pa", 2.0e9))  # 杨氏模量 / Young's modulus
    poisson = float(material.get("poisson_ratio", 0.35))  # 泊松比 / Poisson ratio
    density = float(material.get("density_kg_m3", 1200.0))  # 密度 / Density
    D = bending_stiffness_pa_m3(H_mm, youngs, poisson).ravel()  # 扁平弯曲刚度 / Flat bending stiffness
    M = mass_per_area_kg_m2(H_mm, density).ravel()  # 扁平面密度 / Flat mass per area
    free = free_dof_indices(rows, cols)  # 自由度索引（去掉中心夹持） / Free DOF indices (centre clamp removed)
    Mf = np.maximum(M[free], 1.0e-9)  # 自由质量 / Free mass
    if H_mm.size > 400 and sparse_eigsh is not None and sparse_diags is not None:  # 用稀疏求解 / Use sparse solver
        L = build_sparse_laplacian_matrix(rows, cols, dx_m, dy_m)  # 稀疏拉普拉斯 / Sparse Laplacian
        K = L.T @ sparse_diags(D) @ L  # 稀疏双调和刚度 / Sparse biharmonic stiffness
        Kf = K[free, :][:, free]  # 截取自由子矩阵 / Slice free submatrix
        mode_count = min(max(1, int(num_modes)), max(1, Kf.shape[0] - 2))  # 限制模态数 / Clamp mode count
        try:  # 优先小特征值直求 / Prefer direct smallest-eigvals
            values, vectors = sparse_eigsh(Kf, k=mode_count, M=sparse_diags(Mf), which="SM", tol=1.0e-5, maxiter=max(1000, 30 * Kf.shape[0]))  # 求最小特征对 / Smallest eigenpairs
        except Exception:  # 失败时移位反演 / Shift-invert fallback
            values, vectors = sparse_eigsh(Kf, k=mode_count, M=sparse_diags(Mf), sigma=1.0e-9, which="LM", tol=1.0e-5, maxiter=max(1000, 30 * Kf.shape[0]))  # 移位反演 / Shift-invert
        order = np.argsort(values)  # 排序 / Sort
        eigvals_free = values[order]  # 排序后特征值 / Sorted eigenvalues
        eigvecs_free = vectors[:, order]  # 排序后特征向量 / Sorted eigenvectors
    else:  # 稠密回退 / Dense fallback
        L = build_laplacian_matrix(rows, cols, dx_m, dy_m)  # 稠密拉普拉斯 / Dense Laplacian
        K = L.T @ (D[:, None] * L)  # 稠密双调和刚度 / Dense biharmonic stiffness
        Kf = K[np.ix_(free, free)]  # 自由子矩阵 / Free submatrix
        scaled = Kf / np.sqrt(np.outer(Mf, Mf))  # 标准化特征问题 / Standardise eigenproblem
        scaled = 0.5 * (scaled + scaled.T)  # 强制对称 / Force symmetry
        if scipy_eigh is not None:  # 用 SciPy 子集 / Use SciPy subset
            top = min(int(num_modes) - 1, scaled.shape[0] - 1)  # 上界索引 / Upper bound index
            eigvals_free, vectors = scipy_eigh(scaled, subset_by_index=[0, max(0, top)])  # 子集特征对 / Subset eigenpairs
        else:  # 全特征解 / Full eigensolve
            eigvals_full, vectors_full = np.linalg.eigh(scaled)  # 完整求解 / Full solve
            order = np.argsort(eigvals_full)[: int(num_modes)]  # 选最低 / Keep lowest
            eigvals_free = eigvals_full[order]  # 选中的特征值 / Selected eigenvalues
            vectors = vectors_full[:, order]  # 选中的特征向量 / Selected eigenvectors
        eigvecs_free = vectors / np.sqrt(Mf)[:, None]  # 还原广义特征向量 / Recover generalised eigenvectors
    full_modes = np.zeros((eigvecs_free.shape[1], rows * cols), dtype=float)  # 全自由度模态矩阵 / Full-DOF mode matrix
    full_modes[:, free] = eigvecs_free.T  # 写入自由位移 / Write free displacements
    return np.asarray(eigvals_free, dtype=float), full_modes.reshape(-1, rows, cols)  # 返回 (本征值, 模态阵列) / Return (eigvals, mode stack)


def _nodal_mask_from_field(field: np.ndarray, epsilon_ratio: float = 0.060) -> np.ndarray:  # 从位移场提取节点线 / Extract nodal lines from displacement field
    values = field.astype(float)  # 转浮点 / Float copy
    amplitude = np.abs(values)  # 振幅 / Amplitude
    threshold = float(epsilon_ratio) * max(float(amplitude.max()), 1.0e-9)  # 阈值 / Threshold
    nodal = amplitude <= threshold  # 近零位移 / Near-zero displacement
    vertical_change = values[:-1, :] * values[1:, :] <= 0.0  # 纵向符号翻转 / Vertical sign change
    horizontal_change = values[:, :-1] * values[:, 1:] <= 0.0  # 横向符号翻转 / Horizontal sign change
    nodal[:-1, :] |= vertical_change  # 标记上侧 / Mark upper side
    nodal[1:, :] |= vertical_change  # 标记下侧 / Mark lower side
    nodal[:, :-1] |= horizontal_change  # 标记左侧 / Mark left side
    nodal[:, 1:] |= horizontal_change  # 标记右侧 / Mark right side
    return nodal.astype(bool)  # 返回布尔节点图 / Return boolean nodal map


def _classify_pattern(mode_field: np.ndarray, nodal_mask: np.ndarray) -> dict:  # 粗略分类节点线形状 / Roughly classify nodal-line shape
    rows, cols = mode_field.shape  # 读取尺寸 / Read shape
    yy, xx = np.mgrid[0:rows, 0:cols].astype(float)  # 坐标网格 / Coordinate grid
    cy = (rows - 1) / 2.0  # y 中心 / y centre
    cx = (cols - 1) / 2.0  # x 中心 / x centre
    radius = np.sqrt(((yy - cy) / cy) ** 2 + ((xx - cx) / cx) ** 2)  # 归一化半径 / Normalised radius
    nodal_pixels = nodal_mask.sum()  # 节点像素数 / Nodal pixel count
    if nodal_pixels == 0:  # 防零 / Avoid zero
        return {"family": "empty", "ring_score": 0.0, "cross_score": 0.0, "horizontal_score": 0.0, "vertical_score": 0.0, "diagonal_score": 0.0}  # 空族 / Empty family
    r_values = radius[nodal_mask]  # 节点像素半径 / Radii of nodal pixels
    ring_score = float(1.0 - np.std(r_values) / (np.mean(r_values) + 1.0e-6))  # 环形度（半径方差越小越像环） / Ring-likeness (smaller radial spread = more ring-like)
    horizontal_score = float(nodal_mask[max(0, int(cy) - 1):int(cy) + 2, :].sum()) / float(nodal_pixels)  # 横线占比 / Horizontal-line fraction
    vertical_score = float(nodal_mask[:, max(0, int(cx) - 1):int(cx) + 2].sum()) / float(nodal_pixels)  # 竖线占比 / Vertical-line fraction
    diagonal = np.abs(yy - cy - (xx - cx)) <= 1.0  # 主对角带 / Main-diagonal band
    anti_diagonal = np.abs(yy - cy + (xx - cx)) <= 1.0  # 副对角带 / Anti-diagonal band
    diagonal_score = float(nodal_mask[diagonal | anti_diagonal].sum()) / float(nodal_pixels)  # 对角线占比 / Diagonal fraction
    cross_score = horizontal_score + vertical_score  # 十字度 / Cross-likeness
    scores = {"ring": ring_score, "cross": cross_score, "diagonal": diagonal_score}  # 候选家族 / Family candidates
    family = max(scores, key=scores.get)  # 取最高 / Highest score wins
    return {"family": family, "ring_score": float(ring_score), "cross_score": float(cross_score), "horizontal_score": float(horizontal_score), "vertical_score": float(vertical_score), "diagonal_score": float(diagonal_score)}  # 返回分类信息 / Return classification


def build_uniform_catalogue(config: dict, num_modes: int = 30, proxy_grid_size: int = 51, output_dir: Path | str | None = None) -> dict:  # 构建均匀板模态目录 / Build uniform-plate mode catalogue
    plate_length_mm = float(config["project"]["plate_length_mm"])  # 板长度 / Plate length
    plate_width_mm = float(config["project"]["plate_width_mm"])  # 板宽度 / Plate width
    thickness_mm = float(config.get("thickness", {}).get("default_mm", 2.0))  # 默认均匀厚度 / Default uniform thickness
    material = dict(config.get("material", {}))  # 材料字典 / Material dict
    grid = int(proxy_grid_size)  # 代理网格 / Proxy grid
    if grid % 2 == 0:  # 奇数对齐中心 / Force odd to align centre
        grid += 1  # 增一 / Plus one
    H_mm = np.full((grid, grid), thickness_mm, dtype=float)  # 均匀厚度场 / Uniform thickness field
    eigvals, modes = _solve_eigenpairs(H_mm, plate_length_mm, plate_width_mm, material, int(num_modes))  # 求解本征对 / Solve eigenpairs
    safe_eigvals = np.clip(eigvals, a_min=0.0, a_max=None)  # 防数值负值 / Clip numerical negatives
    omega = np.sqrt(safe_eigvals)  # 角频率 / Angular frequency
    freqs_hz = omega / (2.0 * np.pi)  # 频率 Hz / Frequency in Hz
    entries: list[UniformMode] = []  # 模态条目列表 / Mode entry list
    for index in range(modes.shape[0]):  # 遍历模态 / Iterate modes
        mode_field = modes[index]  # 单个模态场 / Single mode field
        mode_field = mode_field / max(float(np.max(np.abs(mode_field))), 1.0e-12)  # 归一到 [-1, 1] / Normalise to [-1, 1]
        nodal = _nodal_mask_from_field(mode_field)  # 节点线掩膜 / Nodal mask
        entries.append(UniformMode(index=index + 1, frequency_hz=float(freqs_hz[index]), omega_squared=float(safe_eigvals[index]), mode_field=mode_field, nodal_mask=nodal))  # 追加条目 / Append entry
    metadata = {"plate_length_mm": plate_length_mm, "plate_width_mm": plate_width_mm, "thickness_mm": thickness_mm, "material": material, "proxy_grid_size": grid, "num_modes": int(modes.shape[0])}  # 元信息 / Metadata
    if output_dir is not None:  # 检查是否保存 / Check whether to save
        _persist_catalogue(entries, metadata, Path(output_dir))  # 持久化目录 / Persist catalogue
    return {"metadata": metadata, "entries": entries}  # 返回结果 / Return result


def _persist_catalogue(entries: list[UniformMode], metadata: dict, output_dir: Path) -> None:  # 把目录写到磁盘 / Persist catalogue to disk
    output_dir.mkdir(parents=True, exist_ok=True)  # 确保目录存在 / Ensure directory exists
    catalogue_records: list[dict] = []  # 记录列表 / Record list
    for entry in entries:  # 遍历条目 / Iterate entries
        np.save(output_dir / f"mode_{entry.index:03d}_field.npy", entry.mode_field.astype(np.float32))  # 保存位移场 / Save displacement field
        np.save(output_dir / f"mode_{entry.index:03d}_nodal.npy", entry.nodal_mask.astype(np.uint8))  # 保存节点掩膜 / Save nodal mask
        family_info = _classify_pattern(entry.mode_field, entry.nodal_mask)  # 分类 / Classify
        record = {"index": entry.index, "frequency_hz": float(entry.frequency_hz), "omega_squared": float(entry.omega_squared), "nodal_field_path": f"mode_{entry.index:03d}_field.npy", "nodal_mask_path": f"mode_{entry.index:03d}_nodal.npy", **family_info}  # 单条记录 / Single record
        catalogue_records.append(record)  # 加入记录 / Append record
    summary = {"metadata": metadata, "entries": catalogue_records}  # 摘要 / Summary
    (output_dir / "catalogue.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 JSON / Write JSON


def load_catalogue(output_dir: Path | str) -> dict | None:  # 读取已缓存目录 / Read cached catalogue
    path = Path(output_dir) / "catalogue.json"  # 元信息路径 / Metadata path
    if not path.exists():  # 文件不存在 / Missing file
        return None  # 返回空 / Return None
    return json.loads(path.read_text(encoding="utf-8"))  # 返回结构 / Return structure


def load_catalogue_entry(output_dir: Path | str, index: int) -> tuple[np.ndarray, np.ndarray] | None:  # 加载单个条目 / Load one entry
    base = Path(output_dir)  # 基目录 / Base directory
    field_path = base / f"mode_{int(index):03d}_field.npy"  # 位移场路径 / Field path
    nodal_path = base / f"mode_{int(index):03d}_nodal.npy"  # 节点路径 / Nodal path
    if not field_path.exists() or not nodal_path.exists():  # 检查缺失 / Check missing
        return None  # 缺失返回空 / Return None when missing
    return np.load(field_path).astype(float), np.load(nodal_path).astype(bool)  # 返回 (位移场, 节点掩膜) / Return (field, nodal mask)


def catalogue_default_dir(config: dict) -> Path:  # 计算缓存目录 / Compute cache directory
    base = Path(config.get("paths", {}).get("processed_targets_dir", "data/processed_targets")).parent  # 取 data/ 父目录 / Take data/ parent
    return base / "uniform_catalogue"  # 返回缓存目录 / Return cache directory
