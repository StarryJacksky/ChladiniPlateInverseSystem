from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from dataclasses import dataclass  # 导入数据类工具 / Import dataclass helper

import numpy as np  # 导入数值计算库 / Import numerical library
from scipy.ndimage import distance_transform_edt  # 导入欧氏距离变换 / Import Euclidean distance transform

from src.candidate.constraints import center_cells_for_grid  # 导入中心单元工具 / Import centre-cell helper
from src.candidate.constraints import enforce_center_constraint  # 导入中心约束工具 / Import centre-constraint helper
from src.candidate.constraints import repair_continuous_neighbor_constraint  # 导入连续厚度修复 / Import continuous-thickness repair
from src.target.preprocess_target import skeletonize_binary  # 导入目标骨架化工具 / Import target skeletonizer


@dataclass(frozen=True)  # 使用不可变数据类描述单个 TAGS 案例 / Use immutable dataclass for one TAGS case
class TagsCase:  # 定义 TAGS 案例 / Define TAGS case
    name: str  # 案例名称 / Case name
    target_delta_mm: float  # 目标骨架带厚度变化 / Thickness change on target band
    side_delta_mm: float  # 目标侧带厚度变化 / Thickness change on side band
    description: str  # 人类可读描述 / Human-readable description


def normalise_field(values: np.ndarray) -> np.ndarray:  # 归一化场 / Normalize a field
    low = float(np.min(values))  # 读取最小值 / Read minimum value
    high = float(np.max(values))  # 读取最大值 / Read maximum value
    if high - low < 1.0e-9:  # 检查是否近似常量 / Check whether nearly constant
        return np.zeros_like(values, dtype=float)  # 常量场返回零 / Return zero field for constant input
    return (values.astype(float) - low) / (high - low)  # 返回 0-1 场 / Return 0-1 field


def smooth_field(values: np.ndarray, passes: int = 1) -> np.ndarray:  # 平滑二维场 / Smooth a two-dimensional field
    smoothed = values.astype(float)  # 转为浮点数 / Convert to float
    for _ in range(max(0, int(passes))):  # 遍历平滑次数 / Iterate smoothing passes
        padded = np.pad(smoothed, 1, mode="edge")  # 边缘复制填充 / Pad with edge values
        smoothed = 0.40 * padded[1:-1, 1:-1] + 0.15 * padded[:-2, 1:-1] + 0.15 * padded[2:, 1:-1] + 0.15 * padded[1:-1, :-2] + 0.15 * padded[1:-1, 2:]  # 五点模板平滑 / Smooth with a five-point stencil
    return smoothed  # 返回平滑场 / Return smoothed field


def downsample_float_to_grid(values: np.ndarray, grid_size: int, reducer: str = "mean") -> np.ndarray:  # 降采样高分辨率场 / Downsample high-resolution field
    rows, cols = values.shape  # 读取输入尺寸 / Read input size
    row_edges = np.linspace(0, rows, grid_size + 1).astype(int)  # 生成行边界 / Build row edges
    col_edges = np.linspace(0, cols, grid_size + 1).astype(int)  # 生成列边界 / Build column edges
    output = np.zeros((grid_size, grid_size), dtype=float)  # 创建输出矩阵 / Create output matrix
    for row in range(grid_size):  # 遍历输出行 / Iterate output rows
        for col in range(grid_size):  # 遍历输出列 / Iterate output columns
            block = values[row_edges[row]:row_edges[row + 1], col_edges[col]:col_edges[col + 1]]  # 读取对应图像块 / Read source image block
            if block.size == 0:  # 防御空块 / Guard empty block
                output[row, col] = 0.0  # 空块写零 / Store zero for empty block
            elif reducer == "max":  # 检查是否使用最大池化 / Check max-pooling mode
                output[row, col] = float(np.max(block))  # 保存最大值 / Store maximum value
            else:  # 默认使用均值 / Use mean by default
                output[row, col] = float(np.mean(block))  # 保存均值 / Store mean value
    return output  # 返回降采样矩阵 / Return downsampled matrix


def robust_target_skeleton(target_binary: np.ndarray) -> np.ndarray:  # 构建稳健目标骨架 / Build robust target skeleton
    binary = target_binary.astype(bool)  # 转为布尔目标 / Convert target to boolean
    skeleton = skeletonize_binary(binary)  # 执行骨架化 / Run skeletonisation
    if int(np.count_nonzero(skeleton)) == 0:  # 检查骨架是否为空 / Check whether skeleton is empty
        return binary  # 回退到原目标 / Fall back to original target
    return skeleton.astype(bool)  # 返回骨架 / Return skeleton


def build_tags_bands(target_binary: np.ndarray, grid_size: int, target_radius_px: float, side_radius_px: float) -> dict[str, np.ndarray]:  # 构造 TAGS 目标带和侧带 / Build TAGS target and side bands
    skeleton = robust_target_skeleton(target_binary)  # 获取目标骨架 / Get target skeleton
    distance = distance_transform_edt(~skeleton)  # 计算到骨架的距离 / Compute distance to skeleton
    target_radius = max(float(target_radius_px), 1.0)  # 限制目标带半径 / Clamp target-band radius
    side_radius = max(float(side_radius_px), target_radius + 1.0)  # 限制侧带半径 / Clamp side-band radius
    target_weight = np.exp(-0.5 * np.square(distance / target_radius))  # 生成目标带软权重 / Build soft target-band weight
    side_center = 0.5 * (target_radius + side_radius)  # 计算侧带中心半径 / Compute side-band centre radius
    side_sigma = max(0.5 * (side_radius - target_radius), 1.0)  # 计算侧带宽度 / Compute side-band width
    side_weight = np.exp(-0.5 * np.square((distance - side_center) / side_sigma))  # 生成侧带软权重 / Build soft side-band weight
    side_weight = side_weight * (1.0 - np.clip(target_weight, 0.0, 1.0))  # 从侧带中扣除目标带 / Remove target band from side band
    target_grid = normalise_field(downsample_float_to_grid(target_weight, grid_size, "max"))  # 目标带降采样 / Downsample target band
    side_grid = normalise_field(downsample_float_to_grid(side_weight, grid_size, "max"))  # 侧带降采样 / Downsample side band
    side_grid = normalise_field(smooth_field(side_grid, 1))  # 平滑侧带 / Smooth side band
    target_grid = normalise_field(np.maximum(target_grid, downsample_float_to_grid(skeleton.astype(float), grid_size, "max")))  # 保留细骨架穿格信息 / Preserve thin-skeleton cells
    background_grid = normalise_field(1.0 - np.clip(0.82 * target_grid + 0.55 * side_grid, 0.0, 1.0))  # 构造背景参考场 / Build background reference field
    return {"target": target_grid, "side": side_grid, "background": background_grid, "skeleton": skeleton.astype(float)}  # 返回带集合 / Return band set


def build_default_tags_cases(low_mm: float, high_mm: float, background_mm: float) -> list[TagsCase]:  # 构建默认 A/B/C 案例 / Build default A/B/C cases
    target_thin_delta = float(low_mm) - float(background_mm)  # 计算目标变薄幅度 / Compute target-thinning delta
    target_thick_delta = float(high_mm) - float(background_mm)  # 计算目标加厚幅度 / Compute target-thickening delta
    side_thick_delta = float(high_mm) - float(background_mm)  # 计算侧带加厚幅度 / Compute side-thickening delta
    return [  # 返回默认案例列表 / Return default case list
        TagsCase("case_a_target_thick", target_thick_delta, 0.0, "目标骨架带加厚 / Thicken the target skeleton band"),  # A 案例 / Case A
        TagsCase("case_b_target_thin", target_thin_delta, 0.0, "目标骨架带变薄 / Thin the target skeleton band"),  # B 案例 / Case B
        TagsCase("case_c_target_thin_side_thick", target_thin_delta, side_thick_delta, "目标骨架带变薄，两侧保护带加厚 / Thin target band and thicken side guard band"),  # C 案例 / Case C
    ]  # 结束默认案例 / End default cases


def generate_tags_thickness_matrix(bands: dict[str, np.ndarray], case: TagsCase, background_mm: float, low_mm: float, high_mm: float, default_center_mm: float, max_neighbor_diff_mm: float) -> np.ndarray:  # 生成 TAGS 厚度矩阵 / Generate TAGS thickness matrix
    target_band = np.clip(bands["target"].astype(float), 0.0, 1.0)  # 读取目标带 / Read target band
    side_band = np.clip(bands["side"].astype(float), 0.0, 1.0) * (1.0 - target_band)  # 读取并扣除目标重叠的侧带 / Read side band and remove target overlap
    raw = np.full(target_band.shape, float(background_mm), dtype=float)  # 创建背景厚度 / Create background thickness
    raw = raw + float(case.side_delta_mm) * side_band  # 应用侧带变化 / Apply side-band change
    raw = raw + float(case.target_delta_mm) * target_band  # 应用目标带变化 / Apply target-band change
    clipped = np.clip(raw, float(low_mm), float(high_mm))  # 裁剪厚度范围 / Clip thickness range
    center_cells = center_cells_for_grid(clipped.shape[0])  # 获取中心固定单元 / Get centre fixed cells
    centered = enforce_center_constraint(clipped, center_cells, float(default_center_mm))  # 固定中心厚度 / Fix centre thickness
    repaired = repair_continuous_neighbor_constraint(centered, float(low_mm), float(high_mm), float(max_neighbor_diff_mm), passes=36, fixed_cells=center_cells)  # 修复制造相邻约束 / Repair manufacturing neighbour constraint
    return enforce_center_constraint(repaired, center_cells, float(default_center_mm))  # 再次固定中心并返回 / Fix centre again and return
