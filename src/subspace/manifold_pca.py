from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import json  # 导入 JSON 工具 / Import JSON utilities
import math  # 导入数学工具 / Import math helpers
from dataclasses import dataclass  # 导入数据类装饰器 / Import dataclass decorator
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library


@dataclass  # 数据类装饰器 / Dataclass decorator
class DesignManifold:  # 设计变量低维流形 / Design-variable low-dimensional manifold
    mean: np.ndarray  # 训练集均值 (225,) / Training-set mean (225,)
    components: np.ndarray  # 主成分基底 (k, 225) / Principal-component basis (k, 225)
    explained_variance: np.ndarray  # 每主成分方差 (k,) / Variance per component (k,)
    explained_variance_ratio: np.ndarray  # 累计方差比例 (k,) / Cumulative variance ratio (k,)
    grid_size: int  # 原始网格尺寸 / Original grid size
    sample_count: int  # 训练样本数 / Number of training samples
    metadata: dict  # 训练元信息 / Training metadata


def _load_score(score_path: Path) -> float | None:  # 读取候选评分 / Load candidate final score
    if not score_path.exists():  # 文件缺失 / Missing file
        return None  # 返回空 / Return None
    try:  # 尝试解析 JSON / Try parse JSON
        data = json.loads(score_path.read_text(encoding="utf-8"))  # 读取数据 / Read data
    except Exception:  # 处理解析错误 / Handle parse error
        return None  # 返回空 / Return None
    value = data.get("final_score")  # 读取最终分 / Read final score
    if value is None:  # 字段缺失 / Missing field
        return None  # 返回空 / Return None
    try:  # 转浮点 / Convert to float
        return float(value)  # 返回最终分 / Return final score
    except (TypeError, ValueError):  # 处理类型错误 / Handle type error
        return None  # 返回空 / Return None


def collect_design_pool(candidates_dir: Path, grid_size: int = 15, min_final_score: float | None = None, name_prefixes: list[str] | None = None) -> tuple[np.ndarray, list[dict]]:  # 收集设计池 / Collect design pool
    rows: list[np.ndarray] = []  # 创建样本列表 / Create sample list
    records: list[dict] = []  # 创建元信息列表 / Create record list
    for candidate_path in sorted(Path(candidates_dir).glob("*")):  # 遍历候选目录 / Iterate candidate directories
        if not candidate_path.is_dir():  # 跳过非目录 / Skip non-directories
            continue  # 继续 / Continue
        if name_prefixes is not None and not any(candidate_path.name.startswith(pfx) for pfx in name_prefixes):  # 过滤名称前缀 / Filter by prefix
            continue  # 不匹配则跳过 / Skip non-matching
        h_path = candidate_path / "H.csv"  # 候选厚度路径 / Candidate thickness path
        if not h_path.exists():  # 文件缺失 / Missing file
            continue  # 跳过 / Skip
        try:  # 尝试读取 / Try reading
            H = np.loadtxt(h_path, delimiter=",")  # 读取厚度 / Load thickness
        except Exception:  # 处理读取错误 / Handle read error
            continue  # 跳过损坏文件 / Skip broken file
        if H.shape != (grid_size, grid_size):  # 形状不匹配 / Shape mismatch
            continue  # 跳过非匹配 / Skip non-matching
        final_score = _load_score(candidate_path / "score.json")  # 读取评分 / Load score
        if min_final_score is not None and (final_score is None or final_score < float(min_final_score)):  # 评分过滤 / Score filter
            continue  # 跳过低分 / Skip low-score
        rows.append(H.astype(np.float64).reshape(-1))  # 加入样本 / Append sample
        records.append({"candidate_id": candidate_path.name, "final_score": final_score})  # 记录元信息 / Record metadata
    if not rows:  # 池为空 / Empty pool
        raise ValueError(f"No 15x15 H.csv samples matched. / 未找到匹配的 15x15 H.csv 样本。")  # 抛出错误 / Raise error
    return np.stack(rows, axis=0), records  # 返回矩阵和元信息 / Return matrix and records


def fit_pca(X: np.ndarray, variance_target: float = 0.95, max_components: int | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:  # 拟合 PCA / Fit PCA
    if X.ndim != 2:  # 矩阵维度错误 / Wrong matrix dim
        raise ValueError(f"Expected 2-D matrix, got shape {X.shape}. / 预期 2 维矩阵，得到 {X.shape}。")  # 抛出错误 / Raise error
    mean = X.mean(axis=0)  # 计算均值 / Compute mean
    centered = X - mean  # 去中心 / Centre data
    U, S, Vt = np.linalg.svd(centered, full_matrices=False)  # SVD 分解 / SVD decomposition
    n_samples = X.shape[0]  # 样本数 / Sample count
    variances = (S ** 2) / max(n_samples - 1, 1)  # 主成分方差 / Component variances
    total_variance = float(variances.sum())  # 总方差 / Total variance
    ratios = variances / max(total_variance, 1.0e-18)  # 方差比例 / Variance ratios
    cumulative = np.cumsum(ratios)  # 累计比例 / Cumulative ratios
    k_target = int(np.searchsorted(cumulative, float(variance_target)) + 1)  # 命中目标的主成分数 / Components hitting target
    k_target = max(1, min(k_target, Vt.shape[0]))  # 限制范围 / Clip to valid range
    if max_components is not None:  # 用户覆盖上限 / User-specified cap
        k_target = max(1, min(int(max_components), k_target))  # 应用上限 / Apply cap
    components = Vt[:k_target]  # 截取主成分 / Slice components
    return mean, components, variances[:k_target], cumulative[:k_target]  # 返回结果 / Return result


def build_manifold(candidates_dir: Path, variance_target: float = 0.95, grid_size: int = 15, min_final_score: float | None = None, max_components: int | None = None, name_prefixes: list[str] | None = None) -> DesignManifold:  # 构造设计流形 / Build design manifold
    X, records = collect_design_pool(Path(candidates_dir), grid_size=grid_size, min_final_score=min_final_score, name_prefixes=name_prefixes)  # 收集池 / Collect pool
    mean, components, variances, cumulative = fit_pca(X, variance_target=variance_target, max_components=max_components)  # 拟合 PCA / Fit PCA
    metadata = {"variance_target": float(variance_target), "min_final_score": min_final_score, "name_prefixes": name_prefixes, "candidates_used": [r["candidate_id"] for r in records[:50]], "candidates_total": len(records)}  # 元信息 / Metadata
    return DesignManifold(mean=mean.astype(np.float64), components=components.astype(np.float64), explained_variance=variances.astype(np.float64), explained_variance_ratio=cumulative.astype(np.float64), grid_size=int(grid_size), sample_count=int(X.shape[0]), metadata=metadata)  # 返回流形 / Return manifold


def save_manifold(manifold: DesignManifold, output_path: Path) -> Path:  # 保存流形 / Save manifold
    output_path = Path(output_path)  # 转路径 / Convert path
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent dir
    np.savez(output_path, mean=manifold.mean, components=manifold.components, explained_variance=manifold.explained_variance, explained_variance_ratio=manifold.explained_variance_ratio)  # 写 NPZ / Write NPZ
    meta_path = output_path.with_suffix(".json")  # JSON 元数据路径 / JSON metadata path
    meta_payload = {"grid_size": int(manifold.grid_size), "sample_count": int(manifold.sample_count), "num_components": int(manifold.components.shape[0]), "explained_variance_ratio_last": float(manifold.explained_variance_ratio[-1]), "metadata": manifold.metadata, "npz_path": str(output_path.name)}  # 元数据负载 / Metadata payload
    meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 JSON / Write JSON
    return output_path  # 返回路径 / Return path


def load_manifold(path: Path) -> DesignManifold:  # 读取流形 / Load manifold
    path = Path(path)  # 转路径 / Convert path
    npz_path = path if path.suffix == ".npz" else path.with_suffix(".npz")  # 解析 NPZ 路径 / Resolve NPZ path
    payload = np.load(npz_path)  # 读取 NPZ / Load NPZ
    meta_path = npz_path.with_suffix(".json")  # 元数据路径 / Metadata path
    metadata: dict = {}  # 默认元数据 / Default metadata
    grid_size = int(math.isqrt(payload["mean"].shape[0]))  # 推断网格尺寸 / Infer grid size
    sample_count = 0  # 默认样本数 / Default sample count
    if meta_path.exists():  # 元数据存在 / Metadata available
        try:  # 尝试读取 / Try reading
            meta = json.loads(meta_path.read_text(encoding="utf-8"))  # 读取元数据 / Read metadata
            metadata = meta.get("metadata", {}) or {}  # 提取元信息 / Extract metadata
            grid_size = int(meta.get("grid_size", grid_size))  # 读取网格 / Read grid size
            sample_count = int(meta.get("sample_count", 0))  # 读取样本数 / Read sample count
        except Exception:  # 处理坏文件 / Handle broken file
            pass  # 静默跳过 / Silent skip
    return DesignManifold(mean=payload["mean"].astype(np.float64), components=payload["components"].astype(np.float64), explained_variance=payload["explained_variance"].astype(np.float64), explained_variance_ratio=payload["explained_variance_ratio"].astype(np.float64), grid_size=grid_size, sample_count=sample_count, metadata=metadata)  # 返回流形 / Return manifold


def encode(H: np.ndarray, manifold: DesignManifold) -> np.ndarray:  # 编码到 PCA 系数 / Encode into PCA coefficients
    flat = np.asarray(H, dtype=np.float64).reshape(-1) - manifold.mean  # 去均值 / Centre vector
    return manifold.components @ flat  # 投影到主成分 / Project onto components


def decode(c: np.ndarray, manifold: DesignManifold) -> np.ndarray:  # 从 PCA 系数还原 / Decode from PCA coefficients
    flat = manifold.mean + manifold.components.T @ np.asarray(c, dtype=np.float64)  # 还原扁平厚度 / Reconstruct flat thickness
    grid = int(manifold.grid_size)  # 读取网格尺寸 / Read grid size
    return flat.reshape(grid, grid)  # 返回二维厚度 / Return 2-D thickness


def decode_torch(c: "torch.Tensor", manifold_mean_t: "torch.Tensor", manifold_components_t: "torch.Tensor", grid_size: int) -> "torch.Tensor":  # 在 torch 中可微还原 / Differentiable decode in torch
    import torch  # 延迟导入 / Lazy import
    flat = manifold_mean_t + manifold_components_t.T @ c  # 矩阵还原 / Matrix decode
    return flat.reshape(int(grid_size), int(grid_size))  # 返回二维张量 / Return 2-D tensor


def reconstruction_error(X: np.ndarray, manifold: DesignManifold) -> dict[str, float]:  # 评估重建误差 / Evaluate reconstruction error
    centered = X - manifold.mean  # 去均值 / Centre data
    coeffs = centered @ manifold.components.T  # 投影 / Project
    reconstructed = manifold.mean + coeffs @ manifold.components  # 还原 / Reconstruct
    abs_err = np.abs(X - reconstructed)  # 绝对误差 / Absolute error
    return {"mean_abs_error_mm": float(abs_err.mean()), "max_abs_error_mm": float(abs_err.max()), "mean_rel_error": float((abs_err / np.maximum(np.abs(X), 1.0e-6)).mean())}  # 返回三种误差 / Return three error metrics
