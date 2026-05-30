from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import hashlib  # 导入哈希工具用于档位 ID / Hash utilities for tier IDs
import json  # 导入 JSON 工具 / Import JSON utilities
import time  # 时间戳 / Timestamps
from dataclasses import dataclass  # 导入数据类装饰器 / Import dataclass decorator
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.physics.drive_reachability import center_participation as _center_participation_fn  # 中心驱动参与度（主项目共享） / Centre-drive participation (shared with main project)
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
    if entries:  # 一次性算完所有模态的中心参与度 / Compute centre participation for all modes at once
        stacked = np.stack([entry.mode_field for entry in entries], axis=0)  # 堆叠模态场 / Stack mode fields
        raw_part, norm_part = _center_participation_fn(stacked, radius_fraction=0.07)  # 沿用主项目默认半径 / Same default radius as main project
    else:  # 空目录兜底 / Empty fallback
        raw_part = np.zeros(0, dtype=np.float32)  # 空原始 / Empty raw
        norm_part = np.zeros(0, dtype=np.float32)  # 空归一 / Empty normalised
    for i, entry in enumerate(entries):  # 遍历条目 / Iterate entries
        np.save(output_dir / f"mode_{entry.index:03d}_field.npy", entry.mode_field.astype(np.float32))  # 保存位移场 / Save displacement field
        np.save(output_dir / f"mode_{entry.index:03d}_nodal.npy", entry.nodal_mask.astype(np.uint8))  # 保存节点掩膜 / Save nodal mask
        family_info = _classify_pattern(entry.mode_field, entry.nodal_mask)  # 分类 / Classify
        record = {  # 单条记录 / Single record
            "index": entry.index,  # 模态编号 / Mode index
            "frequency_hz": float(entry.frequency_hz),  # 频率 / Frequency
            "omega_squared": float(entry.omega_squared),  # 角频率平方 / Omega squared
            "nodal_field_path": f"mode_{entry.index:03d}_field.npy",  # 位移场文件 / Field file
            "nodal_mask_path": f"mode_{entry.index:03d}_nodal.npy",  # 节点掩膜文件 / Nodal-mask file
            "centre_participation": float(norm_part[i]) if i < len(norm_part) else 0.0,  # 0-1 归一化中心驱动可达性 / Normalised 0-1 centre-drive reachability
            "centre_participation_raw": float(raw_part[i]) if i < len(raw_part) else 0.0,  # 未归一化的原始幅值 / Raw unnormalised amplitude
            **family_info,  # 形状家族 / Shape family
        }
        catalogue_records.append(record)  # 加入记录 / Append record
    summary = {"metadata": metadata, "entries": catalogue_records}  # 摘要 / Summary
    (output_dir / "catalogue.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 JSON / Write JSON


def load_catalogue(output_dir: Path | str) -> dict | None:  # 读取已缓存目录 / Read cached catalogue
    path = Path(output_dir) / "catalogue.json"  # 元信息路径 / Metadata path
    if not path.exists():  # 文件不存在 / Missing file
        return None  # 返回空 / Return None
    return json.loads(path.read_text(encoding="utf-8"))  # 返回结构 / Return structure


def backfill_centre_participation(cache_dir: Path | str) -> bool:  # 给老档位补齐中心参与度字段 / Back-fill centre_participation on legacy tiers
    cache_dir = Path(cache_dir)  # 路径 / Path
    summary = load_catalogue(cache_dir)  # 读取 / Load
    if summary is None:  # 无 / Missing
        return False  # / Skip
    entries = summary.get("entries", []) or []  # 条目 / Entries
    if not entries:  # 空 / Empty
        return False  # / Skip
    if all("centre_participation" in entry for entry in entries):  # 已有字段 / Already populated
        return False  # / Skip
    fields: list[np.ndarray] = []  # 模态场列表 / Mode-field list
    valid_indices: list[int] = []  # 有效条目下标 / Valid entry indices
    for i, entry in enumerate(entries):  # 遍历 / Iterate
        rel = entry.get("nodal_field_path") or f"mode_{int(entry.get('index', 0)):03d}_field.npy"  # 文件名 / File name
        path = cache_dir / rel  # 完整路径 / Full path
        if not path.exists():  # 缺失文件 / Missing file
            continue  # / Skip
        fields.append(np.load(path).astype(np.float32))  # 加载 / Load
        valid_indices.append(i)  # 记录 / Record
    if not fields:  # 全缺 / All missing
        return False  # / Skip
    stacked = np.stack(fields, axis=0)  # 堆叠 / Stack
    raw_part, norm_part = _center_participation_fn(stacked, radius_fraction=0.07)  # 计算参与度 / Compute participation
    for k, i in enumerate(valid_indices):  # 写回字段 / Write fields back
        entries[i]["centre_participation"] = float(norm_part[k])  # 归一化值 / Normalised value
        entries[i]["centre_participation_raw"] = float(raw_part[k])  # 原始值 / Raw value
    summary["entries"] = entries  # 更新 / Update
    (cache_dir / "catalogue.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")  # 落盘 / Persist
    return True  # 完成 / Done


def load_catalogue_entry(output_dir: Path | str, index: int) -> tuple[np.ndarray, np.ndarray] | None:  # 加载单个条目 / Load one entry
    base = Path(output_dir)  # 基目录 / Base directory
    field_path = base / f"mode_{int(index):03d}_field.npy"  # 位移场路径 / Field path
    nodal_path = base / f"mode_{int(index):03d}_nodal.npy"  # 节点路径 / Nodal path
    if not field_path.exists() or not nodal_path.exists():  # 检查缺失 / Check missing
        return None  # 缺失返回空 / Return None when missing
    return np.load(field_path).astype(float), np.load(nodal_path).astype(bool)  # 返回 (位移场, 节点掩膜) / Return (field, nodal mask)


def catalogue_default_dir(config: dict) -> Path:  # 计算基础缓存目录 / Compute base cache directory
    base = Path(config.get("paths", {}).get("processed_targets_dir", "data/processed_targets")).parent  # 取 data/ 父目录 / Take data/ parent
    return base / "uniform_catalogue"  # 返回基础目录 / Return base directory


def _material_fingerprint(material: dict) -> dict:  # 提取参与求解的材料字段 / Extract solver-relevant material fields
    keys = ("youngs_modulus_pa", "poisson_ratio", "density_kg_m3", "stiffness_ratio", "shear_ratio")  # 影响 surrogate / Solver-relevant subset
    return {k: float(material.get(k)) for k in keys if material.get(k) is not None}  # 仅保留存在的字段 / Keep only present fields


def compute_tier_signature(config: dict, num_modes: int | None = None) -> dict:  # 计算唯一签名 / Compute unique tier signature
    return {  # 返回签名字典 / Return signature dict
        "plate_length_mm": float(config["project"]["plate_length_mm"]),  # 板长 / Plate length
        "plate_width_mm": float(config["project"]["plate_width_mm"]),  # 板宽 / Plate width
        "thickness_mm": float(config.get("thickness", {}).get("default_mm", 2.0)),  # 默认厚度 / Default thickness
        "material": _material_fingerprint(config.get("material", {})),  # 材料指纹 / Material fingerprint
        "num_modes": int(num_modes) if num_modes is not None else None,  # 模态数（参与签名） / Mode count (part of signature)
    }


def compute_tier_id(config: dict, num_modes: int | None = None) -> str:  # 计算档位短 ID / Compute short tier ID
    signature = compute_tier_signature(config, num_modes)  # 取签名 / Get signature
    raw = json.dumps(signature, sort_keys=True, separators=(",", ":")).encode("utf-8")  # 规范化 JSON / Canonical JSON
    return hashlib.sha1(raw).hexdigest()[:10]  # 前 10 位即可 / 10-hex prefix is enough


def compute_tier_label(config: dict, num_modes: int | None = None) -> str:  # 计算可读标签 / Human-readable label
    material = config.get("material", {})  # 材料字典 / Material dict
    e_mpa = float(material.get("youngs_modulus_pa", 0.0)) / 1.0e9  # GPa / GPa
    sr = float(material.get("stiffness_ratio", 1.0))  # 各向异性比 / Anisotropy ratio
    density = float(material.get("density_kg_m3", 0.0))  # 密度 / Density
    thickness = float(config.get("thickness", {}).get("default_mm", 2.0))  # 厚度 / Thickness
    if sr <= 1.10:  # 接近各向同性 / Near isotropic
        nickname = "isotropic"  # / Isotropic
    elif sr <= 1.6:  # PLA / PLA
        nickname = "PLA-like"  # / PLA-like
    elif sr <= 3.5:  # CF-PETG / CF-PETG
        nickname = "CF-PETG-like"  # / CF-PETG-like
    else:  # 连续碳纤 / Continuous CF
        nickname = "continuous-CF"  # / Continuous CF
    mode_suffix = f" · {int(num_modes)} modes" if num_modes is not None else ""  # 模态数后缀 / Mode-count suffix
    return f"{nickname} · E={e_mpa:.1f} GPa · sr={sr:.2f} · ρ={density:.0f} kg/m³ · t={thickness:.2f} mm{mode_suffix}"  # 组合标签 / Compose label


def catalogue_tier_dir(config: dict, tier_id: str | None = None, num_modes: int | None = None) -> Path:  # 计算档位缓存目录 / Compute tier cache directory
    base = catalogue_default_dir(config)  # 基础目录 / Base directory
    effective_id = tier_id or compute_tier_id(config, num_modes)  # 使用给定或当前 ID / Use provided or current ID
    return base / effective_id  # 返回档位目录 / Return tier directory


def _tiers_index_path(base_dir: Path) -> Path:  # 档位索引路径 / Tiers-index file path
    return base_dir / "index.json"  # 索引固定名 / Fixed filename


def load_tiers_index(base_dir: Path | str) -> dict:  # 读取档位索引 / Load tiers index
    path = _tiers_index_path(Path(base_dir))  # 索引路径 / Index path
    if not path.exists():  # 索引不存在 / Missing index
        return {"tiers": {}}  # 返回空索引 / Return empty index
    try:  # 防解析失败 / Guard parse failure
        data = json.loads(path.read_text(encoding="utf-8"))  # 读取并解析 / Read & parse
        if isinstance(data, dict) and "tiers" in data:  # 校验结构 / Validate structure
            return data  # 返回索引 / Return index
    except Exception:  # 解析失败兜底 / Parse failure fallback
        pass  # 走默认 / Fall through
    return {"tiers": {}}  # 兜底返回 / Default fallback


def register_tier(base_dir: Path | str, tier_id: str, label: str, signature: dict, num_modes: int) -> dict:  # 注册一个档位 / Register a tier
    base = Path(base_dir)  # 基础目录 / Base directory
    base.mkdir(parents=True, exist_ok=True)  # 确保存在 / Ensure exists
    index = load_tiers_index(base)  # 读取索引 / Load index
    index.setdefault("tiers", {})[tier_id] = {  # 更新条目 / Update entry
        "tier_id": tier_id,  # 档位 ID / Tier ID
        "label": label,  # 可读标签 / Friendly label
        "signature": signature,  # 配置签名 / Config signature
        "num_modes": int(num_modes),  # 模态数 / Mode count
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),  # 更新时间 / Timestamp
    }
    _tiers_index_path(base).write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")  # 落盘 / Persist
    return index["tiers"][tier_id]  # 返回最新条目 / Return latest entry


def list_known_tiers(base_dir: Path | str) -> list[dict]:  # 列出所有已生成档位 / List all known tiers
    base = Path(base_dir)  # 基础目录 / Base directory
    index = load_tiers_index(base)  # 读取索引 / Load index
    items: list[dict] = []  # 结果列表 / Result list
    for tier_id, entry in (index.get("tiers", {}) or {}).items():  # 遍历记录 / Iterate records
        catalogue_path = base / tier_id / "catalogue.json"  # 元信息路径 / Metadata path
        if catalogue_path.exists():  # 仍可用才纳入 / Include only if still on disk
            items.append({**entry, "tier_id": tier_id, "available": True})  # 标记可用 / Mark available
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)  # 最新优先 / Newest first
    return items  # 返回列表 / Return list
