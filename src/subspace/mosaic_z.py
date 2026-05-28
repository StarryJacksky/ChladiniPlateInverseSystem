from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 写入工具 / Import CSV writing utilities
import json  # 导入 JSON 写入工具 / Import JSON writing utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
import torch  # 导入张量优化库 / Import tensor optimisation library
from PIL import Image  # 导入图像输出库 / Import image output library
from scipy.ndimage import distance_transform_edt  # 导入欧氏距离变换 / Import Euclidean distance transform

from src.comsol.import_results import interpolate_to_grid  # 导入 COMSOL 插值函数 / Import COMSOL interpolation helper
from src.comsol.import_results import load_mode_csv  # 导入 COMSOL 模态读取函数 / Import COMSOL mode loader
from src.nodal.extract_nodal import extract_nodal_region  # 导入零线提取函数 / Import zero-line extractor
from src.nodal.extract_nodal import postprocess_nodal_region  # 导入零线后处理函数 / Import zero-line postprocessor
from src.nodal.extract_nodal import remove_center_region  # 导入中心区移除函数 / Import centre-region remover
from src.scoring.metrics import chamfer_similarity  # 导入距离相似度 / Import distance similarity
from src.scoring.metrics import compute_dice  # 导入 Dice 指标 / Import Dice metric
from src.scoring.metrics import compute_iou  # 导入 IoU 指标 / Import IoU metric
from src.scoring.metrics import layout_similarity  # 导入布局相似度 / Import layout similarity
from src.scoring.signed_distance_loss import zero_contour_loss  # 导入 MOSAIC-Z 零线损失 / Import MOSAIC-Z zero-contour loss
from src.target.preprocess_target import skeletonize_binary  # 导入目标骨架化函数 / Import target skeletonisation helper

try:  # 优先使用 scikit-image 的成熟骨架化实现 / Prefer mature scikit-image skeletonisation
    from skimage.morphology import skeletonize as skimage_skeletonize  # 导入 skimage 骨架化函数 / Import skimage skeletonisation helper
except Exception:  # 兼容未安装 scikit-image 的部署环境 / Support deployments without scikit-image
    skimage_skeletonize = None  # 标记 skimage 骨架化不可用 / Mark skimage skeletonisation unavailable


def parse_mode_span(text: str) -> list[int]:  # 解析模态范围文本 / Parse mode-range text
    if ":" in text:  # 检查是否是闭区间写法 / Check for closed-range syntax
        start_text, stop_text = text.split(":", 1)  # 拆分起止文本 / Split start and stop text
        return list(range(int(start_text), int(stop_text) + 1))  # 返回闭区间模态列表 / Return inclusive mode list
    return [int(part.strip()) for part in text.split(",") if part.strip()]  # 解析逗号分隔模态 / Parse comma-separated modes


def mode_number_from_path(path: Path) -> int:  # 从文件名读取模态编号 / Read mode number from filename
    return int(path.stem.split("_")[-1])  # 提取末尾编号 / Extract trailing number


def resize_binary_nearest(binary: np.ndarray, image_size: int) -> np.ndarray:  # 最近邻缩放二值目标 / Resize binary target with nearest neighbour
    data = binary.astype(bool)  # 转成布尔图 / Convert to boolean map
    if data.shape == (image_size, image_size):  # 检查尺寸是否已经匹配 / Check whether shape already matches
        return data  # 直接返回原图 / Return original map
    row_index = np.rint(np.linspace(0, data.shape[0] - 1, image_size)).astype(int)  # 构造行采样索引 / Build row sampling indices
    col_index = np.rint(np.linspace(0, data.shape[1] - 1, image_size)).astype(int)  # 构造列采样索引 / Build column sampling indices
    return data[np.ix_(row_index, col_index)].astype(bool)  # 返回重采样布尔图 / Return resampled boolean map


def build_center_valid_mask(shape: tuple[int, int], center_radius_px: int) -> np.ndarray:  # 构造有效评分掩膜 / Build valid scoring mask
    mask = np.ones(shape, dtype=bool)  # 默认全区域有效 / Mark full region valid by default
    if center_radius_px <= 0:  # 检查是否无需移除中心 / Check whether centre removal is disabled
        return mask  # 返回全区域掩膜 / Return full-region mask
    rows, cols = shape  # 读取图像尺寸 / Read image shape
    yy, xx = np.ogrid[:rows, :cols]  # 构造坐标网格 / Build coordinate grid
    center_y = (rows - 1) / 2.0  # 计算中心 y 坐标 / Compute centre y coordinate
    center_x = (cols - 1) / 2.0  # 计算中心 x 坐标 / Compute centre x coordinate
    mask[(yy - center_y) ** 2 + (xx - center_x) ** 2 <= center_radius_px**2] = False  # 移除中心夹持区 / Remove centre clamp region
    return mask  # 返回有效掩膜 / Return valid mask


def build_target_skeleton(target_binary: np.ndarray) -> np.ndarray:  # 构造目标中心线 / Build target centreline
    skeleton = skimage_skeletonize(target_binary.astype(bool)) if skimage_skeletonize is not None else skeletonize_binary(target_binary.astype(bool))  # 优先使用 skimage 骨架化 / Prefer skimage skeletonisation
    if skeleton.any():  # 检查骨架是否有效 / Check whether skeleton is valid
        return skeleton.astype(bool)  # 返回骨架 / Return skeleton
    return target_binary.astype(bool)  # 骨架失败时回退原目标 / Fall back to original target


def estimate_normal_sample_points(skeleton: np.ndarray, delta_px: int = 3, window_px: int = 4) -> tuple[np.ndarray, np.ndarray]:  # 估计目标线两侧采样点 / Estimate target-side sample points
    coords = np.argwhere(skeleton.astype(bool))  # 读取骨架坐标 / Read skeleton coordinates
    plus_points = []  # 创建正法向采样列表 / Create positive-normal sample list
    minus_points = []  # 创建负法向采样列表 / Create negative-normal sample list
    rows, cols = skeleton.shape  # 读取图像尺寸 / Read image shape
    for row, col in coords:  # 遍历骨架点 / Iterate skeleton points
        near_mask = (np.abs(coords[:, 0] - row) <= window_px) & (np.abs(coords[:, 1] - col) <= window_px)  # 找到局部邻域骨架点 / Find local skeleton neighbours
        local = coords[near_mask].astype(float)  # 取出局部坐标 / Select local coordinates
        if len(local) < 2:  # 检查局部点是否太少 / Check whether too few local points exist
            normal = np.asarray([1.0, 0.0])  # 使用默认法向 / Use default normal
        else:  # 处理可估计切向的情况 / Handle estimable tangent case
            centred = local - local.mean(axis=0, keepdims=True)  # 局部坐标去中心 / Centre local coordinates
            covariance = centred.T @ centred  # 计算局部协方差 / Compute local covariance
            eigen_values, eigen_vectors = np.linalg.eigh(covariance)  # 求主方向 / Solve principal direction
            tangent = eigen_vectors[:, int(np.argmax(eigen_values))]  # 读取切向向量 / Read tangent vector
            normal = np.asarray([-tangent[1], tangent[0]])  # 切向旋转得到法向 / Rotate tangent into normal
        plus = np.rint(np.asarray([row, col], dtype=float) + float(delta_px) * normal).astype(int)  # 计算正侧采样点 / Compute positive-side sample
        minus = np.rint(np.asarray([row, col], dtype=float) - float(delta_px) * normal).astype(int)  # 计算负侧采样点 / Compute negative-side sample
        if 0 <= plus[0] < rows and 0 <= plus[1] < cols and 0 <= minus[0] < rows and 0 <= minus[1] < cols:  # 检查采样点是否在图内 / Check whether samples are inside image
            plus_points.append((int(plus[0]), int(plus[1])))  # 保存正侧点 / Store positive-side point
            minus_points.append((int(minus[0]), int(minus[1])))  # 保存负侧点 / Store negative-side point
    return np.asarray(plus_points, dtype=np.int64), np.asarray(minus_points, dtype=np.int64)  # 返回两侧采样数组 / Return side-sample arrays


def build_target_data(target_binary: np.ndarray, image_size: int, center_radius_px: int, device: torch.device) -> dict[str, object]:  # 构造优化目标数据 / Build optimisation target data
    target = resize_binary_nearest(target_binary, image_size)  # 对齐目标尺寸 / Align target size
    valid = build_center_valid_mask(target.shape, center_radius_px)  # 构造有效区域 / Build valid region
    target = target & valid  # 移除中心目标点 / Remove centre target points
    skeleton = build_target_skeleton(target) & valid  # 构造有效骨架 / Build valid skeleton
    distance = distance_transform_edt(~skeleton).astype(np.float32) / max(float(np.hypot(*skeleton.shape)), 1.0)  # 计算归一化目标距离场 / Compute normalised target distance field
    target_points = np.argwhere(skeleton)  # 读取目标骨架点 / Read target skeleton points
    if target_points.size == 0:  # 检查目标是否为空 / Check whether target is empty
        raise ValueError("Target skeleton is empty. / 目标骨架为空。")  # 抛出目标错误 / Raise target error
    plus_points, minus_points = estimate_normal_sample_points(skeleton)  # 估计法向两侧采样 / Estimate normal-side samples
    return {"target": target, "skeleton": skeleton, "distance": distance, "valid": valid, "target_points": torch.as_tensor(target_points, dtype=torch.long, device=device), "distance_to_target": torch.as_tensor(distance, dtype=torch.float32, device=device), "valid_mask": torch.as_tensor(valid.astype(np.float32), dtype=torch.float32, device=device), "plus_points": torch.as_tensor(plus_points, dtype=torch.long, device=device), "minus_points": torch.as_tensor(minus_points, dtype=torch.long, device=device)}  # 返回 NumPy 和 Torch 目标数据 / Return NumPy and Torch target data


def available_mode_files(candidate_dir: Path, modes: list[int]) -> list[Path]:  # 查找可用模态文件 / Find available mode files
    wanted = set(int(mode) for mode in modes)  # 构造目标模态集合 / Build wanted mode set
    files = sorted(path for path in candidate_dir.glob("mode_*.csv") if mode_number_from_path(path) in wanted)  # 查找匹配 CSV 文件 / Find matching CSV files
    if not files:  # 检查是否没有模态文件 / Check whether no mode files exist
        raise FileNotFoundError(f"No requested mode CSV files found in {candidate_dir}. / 在 {candidate_dir} 中没有找到请求的模态 CSV。")  # 抛出缺失错误 / Raise missing-file error
    return files  # 返回可用模态文件 / Return available mode files


def basis_cache_paths(candidate_dir: Path, mode_numbers: list[int], image_size: int) -> tuple[Path, Path]:  # 构造基底缓存路径 / Build basis cache paths
    mode_key = f"m{min(mode_numbers):02d}_{max(mode_numbers):02d}_n{len(mode_numbers):02d}_{image_size}"  # 构造缓存键 / Build cache key
    return candidate_dir / f"mosaic_basis_{mode_key}.npy", candidate_dir / f"mosaic_basis_{mode_key}.json"  # 返回数组和元数据路径 / Return array and metadata paths


def load_modal_basis(candidate_dir: str | Path, modes: list[int], image_size: int = 128, use_cache: bool = True) -> tuple[np.ndarray, list[int]]:  # 读取并插值模态基底 / Load and interpolate modal basis
    candidate_path = Path(candidate_dir)  # 转换候选目录 / Convert candidate directory
    files = available_mode_files(candidate_path, modes)  # 查找可用模态 CSV / Find available mode CSV files
    mode_numbers = [mode_number_from_path(path) for path in files]  # 读取实际模态编号 / Read actual mode numbers
    cache_array, cache_meta = basis_cache_paths(candidate_path, mode_numbers, image_size)  # 构造缓存路径 / Build cache paths
    if use_cache and cache_array.exists() and cache_meta.exists():  # 检查缓存是否存在 / Check whether cache exists
        return np.load(cache_array), json.loads(cache_meta.read_text(encoding="utf-8"))["modes"]  # 读取缓存基底和模态 / Load cached basis and modes
    fields = []  # 创建模态场列表 / Create modal-field list
    for mode_file in files:  # 遍历模态文件 / Iterate mode files
        x, y, w = load_mode_csv(mode_file)  # 读取散点模态 / Load scattered mode samples
        field = interpolate_to_grid(x, y, w, image_size)  # 插值到规则网格 / Interpolate to regular grid
        max_abs = float(np.max(np.abs(field)))  # 计算最大绝对位移 / Compute maximum absolute displacement
        fields.append((field / max(max_abs, 1.0e-12)).astype(np.float32))  # 保存归一化模态 / Store normalised mode
    basis = np.stack([field.reshape(-1) for field in fields], axis=1).astype(np.float32)  # 组装像素乘模态矩阵 / Assemble pixel-by-mode matrix
    if use_cache:  # 检查是否写入缓存 / Check whether cache should be written
        np.save(cache_array, basis)  # 保存基底缓存 / Save basis cache
        cache_meta.write_text(json.dumps({"modes": mode_numbers, "image_size": image_size}, indent=2), encoding="utf-8")  # 保存缓存元数据 / Save cache metadata
    return basis, mode_numbers  # 返回基底和模态编号 / Return basis and mode numbers


def extract_response_nodal(response: np.ndarray, epsilon_ratio: float, center_radius_px: int) -> np.ndarray:  # 从组合响应提取零线图 / Extract zero-line map from combined response
    nodal = extract_nodal_region(response, epsilon_ratio)  # 提取近零区域和符号翻转 / Extract near-zero and sign-crossing region
    nodal = postprocess_nodal_region(nodal)  # 后处理零线 / Postprocess zero line
    return remove_center_region(nodal, center_radius_px) if center_radius_px > 0 else nodal  # 可选移除中心区 / Optionally remove centre region


def response_metrics(response: np.ndarray, target: np.ndarray, epsilon_ratio: float, center_radius_px: int) -> dict[str, float]:  # 计算组合响应指标 / Compute combined-response metrics
    nodal = extract_response_nodal(response, epsilon_ratio, center_radius_px)  # 提取响应零线 / Extract response zero line
    aligned_target = resize_binary_nearest(target, response.shape[0])  # 对齐目标尺寸 / Align target size
    return {"iou": compute_iou(nodal, aligned_target), "dice": compute_dice(nodal, aligned_target), "chamfer": chamfer_similarity(nodal, aligned_target), "layout": layout_similarity(nodal, aligned_target)}  # 返回关键指标 / Return key metrics


def write_alpha_csv(path: Path, mode_numbers: list[int], alpha: np.ndarray) -> None:  # 写入模态系数 CSV / Write modal coefficient CSV
    with path.open("w", encoding="utf-8", newline="") as file_obj:  # 打开输出文件 / Open output file
        writer = csv.writer(file_obj)  # 创建 CSV 写入器 / Create CSV writer
        writer.writerow(["mode", "alpha"])  # 写入表头 / Write header
        for mode, value in zip(mode_numbers, alpha):  # 遍历模态系数 / Iterate modal coefficients
            writer.writerow([int(mode), float(value)])  # 写入一行系数 / Write one coefficient row


def panel_from_mask(mask: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:  # 从掩膜生成彩色面板 / Build coloured panel from mask
    panel = np.full((*mask.shape, 3), 245, dtype=np.uint8)  # 创建浅色背景 / Create light background
    panel[mask.astype(bool)] = np.asarray(color, dtype=np.uint8)  # 写入前景颜色 / Paint foreground colour
    return panel  # 返回面板 / Return panel


def panel_from_response(response: np.ndarray, nodal: np.ndarray) -> np.ndarray:  # 从响应场生成面板 / Build response panel
    scaled = response / max(float(np.max(np.abs(response))), 1.0e-12)  # 归一化响应 / Normalise response
    gray = np.uint8(np.clip((scaled + 1.0) * 0.5, 0.0, 1.0) * 255.0)  # 转成灰度图 / Convert to grayscale
    panel = np.repeat(gray[:, :, None], 3, axis=2)  # 扩展成 RGB / Expand to RGB
    panel[nodal.astype(bool)] = np.asarray([37, 131, 180], dtype=np.uint8)  # 用蓝色标出零线 / Mark zero line in blue
    return panel  # 返回响应面板 / Return response panel


def write_preview(path: Path, target: np.ndarray, response: np.ndarray, nodal: np.ndarray) -> None:  # 写入 MOSAIC-Z 预览图 / Write MOSAIC-Z preview image
    target_panel = panel_from_mask(target, (232, 84, 61))  # 生成目标面板 / Build target panel
    response_panel = panel_from_response(response, nodal)  # 生成响应面板 / Build response panel
    overlay = np.full((*target.shape, 3), 245, dtype=np.uint8)  # 创建叠加面板 / Create overlay panel
    overlay[target.astype(bool)] = np.asarray([232, 84, 61], dtype=np.uint8)  # 绘制目标红色 / Draw target red
    overlay[nodal.astype(bool)] = np.asarray([37, 131, 180], dtype=np.uint8)  # 绘制响应蓝色 / Draw response blue
    overlay[target.astype(bool) & nodal.astype(bool)] = np.asarray([50, 160, 90], dtype=np.uint8)  # 绘制重叠绿色 / Draw overlap green
    spacer = np.full((target.shape[0], 8, 3), 255, dtype=np.uint8)  # 创建面板间隔 / Create panel spacer
    canvas = np.concatenate([target_panel, spacer, response_panel, spacer, overlay], axis=1)  # 拼接三联图 / Concatenate triptych
    Image.fromarray(canvas).save(path)  # 保存预览图 / Save preview image


def optimise_modal_subspace(candidate_dir: str | Path, target_binary: np.ndarray, modes: list[int], output_dir: str | Path, image_size: int = 128, steps: int = 600, restarts: int = 4, learning_rate: float = 0.035, center_radius_px: int = 0, epsilon: float = 0.045, seed: int = 17, loss_weights: dict[str, float] | None = None) -> dict[str, object]:  # 优化模态子空间组合 / Optimise modal subspace combination
    torch.manual_seed(int(seed))  # 固定 Torch 随机种子 / Fix Torch random seed
    np.random.seed(int(seed))  # 固定 NumPy 随机种子 / Fix NumPy random seed
    device = torch.device("cpu")  # 当前使用 CPU 以便部署稳定 / Use CPU for deployment stability
    basis_np, mode_numbers = load_modal_basis(candidate_dir, modes, image_size)  # 读取模态基底 / Load modal basis
    basis = torch.as_tensor(basis_np, dtype=torch.float32, device=device)  # 转成 Torch 张量 / Convert basis to Torch tensor
    target_data = build_target_data(target_binary, image_size, center_radius_px, device)  # 构造目标数据 / Build target data
    best: dict[str, object] | None = None  # 初始化最佳记录 / Initialise best record
    for restart in range(max(1, int(restarts))):  # 多起点优化 / Run multi-start optimisation
        alpha = torch.randn(len(mode_numbers), dtype=torch.float32, device=device, requires_grad=True)  # 初始化组合系数 / Initialise combination coefficients
        optimiser = torch.optim.Adam([alpha], lr=float(learning_rate))  # 创建 Adam 优化器 / Create Adam optimiser
        for _ in range(max(1, int(steps))):  # 迭代优化步骤 / Iterate optimisation steps
            coeff = alpha / (torch.linalg.norm(alpha) + 1.0e-8)  # 归一化组合系数 / Normalise combination coefficients
            response = torch.matmul(basis, coeff).reshape(image_size, image_size)  # 合成模态响应 / Compose modal response
            loss, parts = zero_contour_loss(response, target_data["target_points"], target_data["distance_to_target"], target_data["valid_mask"], target_data["plus_points"], target_data["minus_points"], epsilon=float(epsilon), weights=loss_weights)  # 计算 MOSAIC-Z 损失 / Compute MOSAIC-Z loss
            optimiser.zero_grad()  # 清空梯度 / Clear gradients
            loss.backward()  # 反向传播 / Backpropagate
            optimiser.step()  # 更新系数 / Update coefficients
        coeff = alpha / (torch.linalg.norm(alpha) + 1.0e-8)  # 读取最终归一化系数 / Read final normalised coefficients
        response = torch.matmul(basis, coeff).reshape(image_size, image_size)  # 生成最终响应 / Build final response
        loss, parts = zero_contour_loss(response, target_data["target_points"], target_data["distance_to_target"], target_data["valid_mask"], target_data["plus_points"], target_data["minus_points"], epsilon=float(epsilon), weights=loss_weights)  # 重新计算损失 / Recompute loss
        if best is None or float(loss.detach().cpu()) < float(best["loss"]):  # 检查是否刷新最佳 / Check whether best improved
            best = {"loss": float(loss.detach().cpu()), "parts": {key: float(value.detach().cpu()) for key, value in parts.items()}, "alpha": coeff.detach().cpu().numpy(), "response": response.detach().cpu().numpy(), "restart": restart}  # 保存最佳结果 / Store best result
    assert best is not None  # 帮助类型检查确认最佳存在 / Help type checker know best exists
    response_np = np.asarray(best["response"], dtype=np.float32)  # 读取最佳响应数组 / Read best response array
    nodal = extract_response_nodal(response_np, float(epsilon), center_radius_px)  # 提取最佳响应零线 / Extract best response zero line
    metrics = response_metrics(response_np, np.asarray(target_data["target"], dtype=bool), float(epsilon), center_radius_px)  # 计算最佳指标 / Compute best metrics
    out_dir = Path(output_dir)  # 转换输出目录 / Convert output directory
    out_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    np.save(out_dir / "best_subspace_response.npy", response_np)  # 保存响应场 / Save response field
    np.save(out_dir / "best_subspace_nodal.npy", nodal.astype(np.uint8))  # 保存零线图 / Save zero-line map
    write_alpha_csv(out_dir / "best_alpha.csv", mode_numbers, np.asarray(best["alpha"], dtype=float))  # 保存模态组合系数 / Save modal coefficients
    write_preview(out_dir / "best_subspace_response.png", np.asarray(target_data["target"], dtype=bool), response_np, nodal)  # 保存三联预览图 / Save triptych preview
    summary = {"candidate": Path(candidate_dir).name, "modes": mode_numbers, "image_size": image_size, "steps": int(steps), "restarts": int(restarts), "epsilon": float(epsilon), "loss_weights": loss_weights or {}, "loss": best["loss"], "loss_parts": best["parts"], "metrics": metrics, "best_restart": best["restart"]}  # 构造摘要 / Build summary
    (out_dir / "subspace_loss.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")  # 写入摘要 JSON / Write summary JSON
    return summary  # 返回摘要 / Return summary
