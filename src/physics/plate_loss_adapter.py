from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from dataclasses import dataclass  # 导入数据类装饰器 / Import dataclass decorator
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
import torch  # 导入张量计算库 / Import tensor computation library
from scipy.ndimage import distance_transform_edt  # 导入距离变换 / Import distance transform

from src.scoring.amplitude_valley_loss import amplitude_valley_loss  # 复用 W2 振幅谷线损失 / Reuse W2 amplitude-valley loss
from src.scoring.geometry_helpers import build_center_valid_mask  # 复用有效掩膜 / Reuse valid mask helper
from src.scoring.geometry_helpers import build_target_skeleton  # 复用目标骨架 / Reuse target skeleton helper
from src.scoring.geometry_helpers import resize_binary_nearest  # 复用最近邻缩放 / Reuse nearest resize


@dataclass  # 数据类装饰器 / Dataclass decorator
class TargetBundle:  # 目标数据集 / Target data bundle
    proxy_grid_size: int  # 代理网格尺寸 / Proxy grid size
    target_grid: np.ndarray  # 目标二值图 (N, N) / Target binary map (N, N)
    skeleton: np.ndarray  # 目标骨架 (N, N) / Target skeleton (N, N)
    distance_to_target: np.ndarray  # 归一化距离场 (N, N) / Normalised distance field (N, N)
    valid_mask: np.ndarray  # 有效掩膜 (N, N) / Valid-region mask (N, N)
    target_points: np.ndarray  # 目标点 (P, 2) / Target points (P, 2)
    plus_points: np.ndarray  # 正侧采样 / Positive-side samples
    minus_points: np.ndarray  # 负侧采样 / Negative-side samples
    verdict: dict | None  # W1 可达性判定 / W1 realizability verdict


def estimate_normal_sample_points(skeleton: np.ndarray, delta_px: int = 2, window_px: int = 3) -> tuple[np.ndarray, np.ndarray]:  # 估计骨架两侧采样点 / Estimate skeleton-side sample points
    coords = np.argwhere(skeleton.astype(bool))  # 读取骨架坐标 / Read skeleton coordinates
    plus_points: list[tuple[int, int]] = []  # 正侧点列表 / Positive-side list
    minus_points: list[tuple[int, int]] = []  # 负侧点列表 / Negative-side list
    rows, cols = skeleton.shape  # 读取图像尺寸 / Read shape
    for row, col in coords:  # 遍历骨架点 / Iterate skeleton points
        near_mask = (np.abs(coords[:, 0] - row) <= window_px) & (np.abs(coords[:, 1] - col) <= window_px)  # 局部邻域 / Local neighbourhood
        local = coords[near_mask].astype(float)  # 局部坐标 / Local coordinates
        if len(local) < 2:  # 局部点过少 / Too few local points
            normal = np.asarray([1.0, 0.0])  # 默认法向 / Default normal
        else:  # 估计切向 / Estimate tangent
            centred = local - local.mean(axis=0, keepdims=True)  # 去中心 / Centre coordinates
            covariance = centred.T @ centred  # 协方差矩阵 / Covariance matrix
            eigen_values, eigen_vectors = np.linalg.eigh(covariance)  # 求主方向 / Solve principal direction
            tangent = eigen_vectors[:, int(np.argmax(eigen_values))]  # 主切向 / Tangent direction
            normal = np.asarray([-tangent[1], tangent[0]])  # 切向旋转为法向 / Rotate tangent to normal
        plus = np.rint(np.asarray([row, col], dtype=float) + float(delta_px) * normal).astype(int)  # 正侧点 / Positive-side point
        minus = np.rint(np.asarray([row, col], dtype=float) - float(delta_px) * normal).astype(int)  # 负侧点 / Negative-side point
        if 0 <= plus[0] < rows and 0 <= plus[1] < cols and 0 <= minus[0] < rows and 0 <= minus[1] < cols:  # 检查在图内 / Inside image
            plus_points.append((int(plus[0]), int(plus[1])))  # 保存正侧 / Store positive side
            minus_points.append((int(minus[0]), int(minus[1])))  # 保存负侧 / Store negative side
    if not plus_points:  # 无可用采样时回退骨架本身 / Fallback to skeleton itself when empty
        plus_points = [(int(r), int(c)) for r, c in coords]  # 复制骨架坐标到正侧 / Copy skeleton coords to plus side
        minus_points = list(plus_points)  # 同步到负侧 / Mirror to minus side
    return np.asarray(plus_points, dtype=np.int64), np.asarray(minus_points, dtype=np.int64)  # 返回两侧点 / Return side samples


def build_target_bundle(target_binary_full: np.ndarray, proxy_grid_size: int, center_clamp_radius_mm: float, plate_length_mm: float, verdict: dict | None = None) -> TargetBundle:  # 构造代理网格目标包 / Build proxy-grid target bundle
    target = resize_binary_nearest(target_binary_full.astype(bool), int(proxy_grid_size))  # 缩放目标 / Resize target
    clamp_radius_px = int(round((float(center_clamp_radius_mm) / float(plate_length_mm)) * float(proxy_grid_size)))  # 夹持半径换算 / Clamp radius in cells
    valid = build_center_valid_mask(target.shape, clamp_radius_px)  # 有效区域 / Valid region
    target = target & valid  # 移除中心目标 / Remove centre target
    skeleton = build_target_skeleton(target) & valid  # 构造有效骨架 / Build valid skeleton
    if not skeleton.any():  # 骨架全空时回退原目标 / Fall back when skeleton is empty
        skeleton = target.copy()  # 复制目标 / Copy target
    distance = distance_transform_edt(~skeleton).astype(np.float32)  # 计算到骨架距离 / Distance to skeleton
    distance /= max(float(np.hypot(*skeleton.shape)), 1.0)  # 归一化距离 / Normalise distance
    target_points = np.argwhere(skeleton)  # 收集骨架点 / Collect skeleton points
    plus_points, minus_points = estimate_normal_sample_points(skeleton)  # 估计两侧采样 / Estimate side samples
    return TargetBundle(proxy_grid_size=int(proxy_grid_size), target_grid=target.astype(bool), skeleton=skeleton.astype(bool), distance_to_target=distance, valid_mask=valid.astype(np.float32), target_points=target_points.astype(np.int64), plus_points=plus_points, minus_points=minus_points, verdict=verdict)  # 返回目标包 / Return target bundle


def bundle_to_torch(bundle: TargetBundle, device: torch.device, dtype: torch.dtype = torch.float64) -> dict[str, torch.Tensor]:  # 把目标包转为张量字典 / Convert target bundle to tensor dict
    return {"target_points": torch.as_tensor(bundle.target_points, dtype=torch.long, device=device), "distance_to_target": torch.as_tensor(bundle.distance_to_target, dtype=dtype, device=device), "valid_mask": torch.as_tensor(bundle.valid_mask, dtype=dtype, device=device), "plus_points": torch.as_tensor(bundle.plus_points, dtype=torch.long, device=device), "minus_points": torch.as_tensor(bundle.minus_points, dtype=torch.long, device=device)}  # 返回张量字典 / Return tensor dict


def amplitude_valley_loss_on_response(response_complex: torch.Tensor, bundle_tensors: dict[str, torch.Tensor], epsilon: float = 0.060, weights: dict[str, float] | None = None) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:  # 在复数响应上跑振幅谷线损失 / Run amplitude-valley loss on complex response
    return amplitude_valley_loss(response_complex, bundle_tensors["target_points"], bundle_tensors["distance_to_target"], bundle_tensors["valid_mask"], bundle_tensors["plus_points"], bundle_tensors["minus_points"], epsilon=float(epsilon), weights=weights)  # 调用 W2 损失 / Call W2 loss


def load_target_binary(config: dict, override_path: str | Path | None = None) -> np.ndarray:  # 读取目标二值图 / Load target binary map
    if override_path is not None:  # 提供覆盖路径 / Override provided
        return np.load(override_path).astype(bool)  # 读取覆盖目标 / Load override target
    target_path = Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 默认目标路径 / Default target path
    if not target_path.exists():  # 缺失目标 / Missing target
        raise FileNotFoundError(f"Target binary not found: {target_path}. / 未找到目标二值图：{target_path}。")  # 抛出文件错误 / Raise missing-file error
    return np.load(target_path).astype(bool)  # 返回目标二值图 / Return target binary map
