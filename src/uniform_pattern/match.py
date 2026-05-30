from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 路径工具 / Path utilities

import numpy as np  # 数值库 / Numerical library

from src.uniform_pattern.perturb import PerturbationParams  # 微扰参数数据类 / Perturbation params dataclass
from src.uniform_pattern.perturb import apply_perturbation  # 应用微扰 / Apply perturbation
from src.uniform_pattern.perturb import normalise_params  # 参数规范化 / Param normaliser
from src.uniform_pattern.render import render_pattern_mask  # 渲染节点线掩膜 / Render nodal mask

try:  # 优先 SciPy 的精确欧氏距离变换 / Prefer SciPy's exact EDT
    from scipy.ndimage import distance_transform_edt as _scipy_edt  # noqa: F401
except Exception:  # 兜底 / Fallback
    _scipy_edt = None  # 标记不可用 / Mark unavailable


def _distance_transform(binary: np.ndarray) -> np.ndarray:  # 距离变换：到最近 True 像素的欧氏距离 / EDT: distance to nearest True pixel
    if _scipy_edt is not None:  # 走 SciPy / Use SciPy
        return _scipy_edt(~binary.astype(bool))  # 注意：EDT 计算到 False 区域的距离 / EDT measures distance through False to nearest True
    # 简易回退：曼哈顿距离扫描（足够当作粗排） / Simple Manhattan fallback (rough)
    h, w = binary.shape  # 形状 / Shape
    INF = h + w + 1  # 大数 / Large value
    dist = np.where(binary, 0, INF).astype(np.int32)  # 初始化 / Init
    for i in range(1, h):  # 前向扫描 / Forward sweep
        dist[i, :] = np.minimum(dist[i, :], dist[i - 1, :] + 1)  # 上邻 / Top neighbour
    for j in range(1, w):  # 前向列 / Forward col
        dist[:, j] = np.minimum(dist[:, j], dist[:, j - 1] + 1)  # 左邻 / Left neighbour
    for i in range(h - 2, -1, -1):  # 后向行 / Backward row
        dist[i, :] = np.minimum(dist[i, :], dist[i + 1, :] + 1)  # 下邻 / Bottom neighbour
    for j in range(w - 2, -1, -1):  # 后向列 / Backward col
        dist[:, j] = np.minimum(dist[:, j], dist[:, j + 1] + 1)  # 右邻 / Right neighbour
    return dist.astype(np.float32)  # 返回浮点距离 / Return float distance


def _resize_binary(binary: np.ndarray, output_size: int) -> np.ndarray:  # 二值掩膜最近邻缩放 / Nearest-neighbour resize for binary masks
    h, w = binary.shape  # 输入形状 / Input shape
    if h == output_size and w == output_size:  # 已是目标尺寸 / Already correct size
        return binary.astype(bool)  # 直接返回 / Return as-is
    rows = (np.linspace(0, h - 1, int(output_size))).round().astype(int)  # 行索引 / Row indices
    cols = (np.linspace(0, w - 1, int(output_size))).round().astype(int)  # 列索引 / Column indices
    return binary[np.ix_(rows, cols)].astype(bool)  # 取样 / Sample


def symmetric_chamfer(mask_a: np.ndarray, mask_b: np.ndarray, dt_a: np.ndarray | None = None) -> float:  # 对称 Chamfer 距离 / Symmetric Chamfer distance
    if not mask_a.any() or not mask_b.any():  # 空图样不可比 / Empty masks not comparable
        return float("inf")  # 返回无穷 / Return infinity
    if dt_a is None:  # 按需算 A 的距离变换 / Compute A's distance transform on demand
        dt_a = _distance_transform(mask_a)  # / Compute EDT of A
    dt_b = _distance_transform(mask_b)  # B 的距离变换 / B's distance transform
    d_ba = float(dt_a[mask_b].mean())  # B 上每个像素到 A 的平均距离 / Mean distance from B-pixels to A
    d_ab = float(dt_b[mask_a].mean())  # A 上每个像素到 B 的平均距离 / Mean distance from A-pixels to B
    return 0.5 * (d_ba + d_ab)  # 对称平均 / Symmetric average


_SEARCH_ROTATIONS_DEG = (-90.0, -45.0, 0.0, 45.0, 90.0, 180.0)  # 离散旋转候选 / Discrete rotation candidates
_SEARCH_STRETCHES = ((1.0, 1.0), (1.30, 1.0 / 1.30), (1.0 / 1.30, 1.30), (1.50, 1.0 / 1.50), (1.0 / 1.50, 1.50))  # 体积近似守恒的 X/Y 拉伸 / Volume-preserving X/Y stretches

EXCITABILITY_HARD_FLOOR = 0.10  # 中心驱动参与度硬过滤阈值（低于此模态在中心激励下基本激不出来） / Hard filter for centre-drive participation
EXCITABILITY_SOFT_TARGET = 0.30  # 中心驱动参与度软目标（低于此值在 score 上加惩罚） / Soft target above which no penalty
EXCITABILITY_SOFT_WEIGHT = 4.0  # 软惩罚权重（按 (target - p) 线性加到 Chamfer 分数上） / Soft-penalty weight added to Chamfer score


def _params_dict(rotate_deg: float = 0.0, stretch_x: float = 1.0, stretch_y: float = 1.0) -> dict:  # 构造微扰参数字典 / Build perturbation params dict
    return {"stretch_x": float(stretch_x), "stretch_y": float(stretch_y), "rotate_deg": float(rotate_deg), "scale": 1.0, "shear": 0.0, "translate_x": 0.0, "translate_y": 0.0, "bump_amplitude": 0.0, "bump_x": 0.0, "bump_y": 0.0, "bump_sigma": 0.20}  # / Default dict


def find_closest_matches(target_mask_full: np.ndarray, entries: list[dict], cache_dir: Path, *, line_width_px: int, plate_length_mm: float, centre_clamp_radius_mm: float, top_k: int = 5, refine_top: int = 8, search_size: int = 192, excitability_floor: float = EXCITABILITY_HARD_FLOOR, excitability_target: float = EXCITABILITY_SOFT_TARGET, excitability_weight: float = EXCITABILITY_SOFT_WEIGHT) -> list[dict]:  # 主匹配入口 / Main matching entry point
    target = _resize_binary(target_mask_full, search_size).astype(bool)  # 把目标降采样到搜索分辨率 / Downscale target to search resolution
    target_dt = _distance_transform(target)  # 预计算目标距离变换 / Precompute target distance transform
    if not target.any():  # 空目标 / Empty target
        return []  # 返回空 / Return empty
    line_width_search = max(2, int(line_width_px) * search_size // max(256, search_size))  # 与目标线宽匹配 / Match target line width
    coarse: list[tuple[int, float, float, float]] = []  # 粗排：(index, score_with_penalty, raw_score, participation) / Coarse list
    fields_cache: dict[int, np.ndarray] = {}  # 模态场缓存（避免重复读盘） / Mode-field cache
    participation_cache: dict[int, float] = {}  # 参与度缓存 / Participation cache
    for record in entries:  # 遍历条目 / Iterate entries
        idx = int(record.get("index", 0))  # 模态编号 / Mode index
        if idx <= 0:  # 跳过非法 / Skip invalid
            continue  # / Skip
        participation = float(record.get("centre_participation", 1.0))  # 中心驱动参与度（缺失则视为 1，向后兼容） / Centre participation (default 1 for legacy)
        if participation < float(excitability_floor):  # 硬过滤：物理上激不出来 / Hard filter: physically unreachable
            continue  # / Skip
        field_path = Path(cache_dir) / f"mode_{idx:03d}_field.npy"  # 模态文件 / Mode field file
        if not field_path.exists():  # 文件缺失 / Missing file
            continue  # / Skip
        field = np.load(field_path).astype(np.float32)  # 加载模态 / Load mode
        fields_cache[idx] = field  # 入缓存 / Cache
        participation_cache[idx] = participation  # 缓存参与度 / Cache participation
        mask = render_pattern_mask(field, output_size=search_size, line_width_px=line_width_search, plate_length_mm=plate_length_mm, centre_clamp_radius_mm=centre_clamp_radius_mm)  # 渲染原始模态 / Render baseline mask
        raw_score = symmetric_chamfer(target, mask, dt_a=target_dt)  # 粗 Chamfer 分数 / Coarse Chamfer score
        penalty = float(excitability_weight) * max(0.0, float(excitability_target) - participation)  # 软惩罚 / Soft penalty
        coarse.append((idx, raw_score + penalty, raw_score, participation))  # 记录（带惩罚分） / Record with penalty
    coarse.sort(key=lambda x: x[1])  # 升序 / Ascend
    refine_candidates = [item[0] for item in coarse[: max(int(refine_top), int(top_k))]]  # 取前 N 精搜 / Top-N for refinement
    refined: list[dict] = []  # 精搜结果 / Refinement results
    for idx in refine_candidates:  # 遍历候选 / Iterate candidates
        field = fields_cache[idx]  # 复用缓存 / Reuse cache
        participation = participation_cache.get(idx, 1.0)  # 取参与度 / Get participation
        penalty = float(excitability_weight) * max(0.0, float(excitability_target) - participation)  # 计算软惩罚 / Compute soft penalty
        best_raw = float("inf")  # 初始原始分 / Initial raw score
        best_params: dict = _params_dict()  # 初始参数 / Initial params
        for rot in _SEARCH_ROTATIONS_DEG:  # 遍历旋转 / Iterate rotations
            for sx, sy in _SEARCH_STRETCHES:  # 遍历拉伸 / Iterate stretches
                params_dict = _params_dict(rotate_deg=rot, stretch_x=sx, stretch_y=sy)  # 构参 / Build params
                params = normalise_params(params_dict)  # 规范化 / Normalise
                perturbed = apply_perturbation(field, params)  # 应用 / Apply
                mask = render_pattern_mask(perturbed, output_size=search_size, line_width_px=line_width_search, plate_length_mm=plate_length_mm, centre_clamp_radius_mm=centre_clamp_radius_mm)  # 渲染 / Render
                raw = symmetric_chamfer(target, mask, dt_a=target_dt)  # Chamfer / Chamfer
                if raw < best_raw:  # 更新最佳 / Update best
                    best_raw = raw  # / Update raw
                    best_params = params_dict  # / Update params
        record = next((e for e in entries if int(e.get("index", -1)) == idx), {})  # 取元信息 / Get metadata
        refined.append({  # 加入结果 / Append result
            "mode_index": idx,  # 模态编号 / Mode index
            "score": float(best_raw + penalty),  # 含惩罚的最终排序分 / Final score with penalty
            "raw_score": float(best_raw),  # 纯几何 Chamfer / Pure geometric Chamfer
            "centre_participation": float(participation),  # 物理可达性 / Physical reachability
            "params": best_params,  # 推荐微扰参数 / Recommended perturbation
            "frequency_hz": float(record.get("frequency_hz", 0.0)),  # 频率 / Frequency
            "family": record.get("family", "unknown"),  # 族 / Family
        })
    refined.sort(key=lambda x: x["score"])  # 按总分排序 / Sort by total score
    return refined[: max(1, int(top_k))]  # 返回前 K / Return top-K
