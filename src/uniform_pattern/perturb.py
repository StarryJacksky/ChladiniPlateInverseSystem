from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from dataclasses import dataclass  # 导入数据类 / Import dataclass

import numpy as np  # 导入数值库 / Import numerical library


@dataclass  # 数据类装饰器 / Dataclass decorator
class PerturbationParams:  # 微扰参数 / Perturbation parameters
    stretch_x: float = 1.0  # X 方向拉伸（>1 拉宽，<1 压缩） / X stretch (>1 wider, <1 narrower)
    stretch_y: float = 1.0  # Y 方向拉伸 / Y stretch
    rotate_deg: float = 0.0  # 平面旋转角度 / In-plane rotation in degrees
    scale: float = 1.0  # 整体缩放 / Uniform scale
    shear: float = 0.0  # 切变（横向相对竖向的偏移因子） / Shear factor
    translate_x: float = 0.0  # 水平平移（归一化板长 [-1, 1]） / Horizontal shift in normalised plate length [-1, 1]
    translate_y: float = 0.0  # 垂直平移（归一化板长 [-1, 1]） / Vertical shift in normalised plate length [-1, 1]
    bump_amplitude: float = 0.0  # 高斯隆起幅度（相对单位场） / Gaussian bump amplitude (relative to unit field)
    bump_x: float = 0.0  # 隆起中心 x（归一化 [-1, 1]） / Bump centre x (normalised [-1, 1])
    bump_y: float = 0.0  # 隆起中心 y / Bump centre y
    bump_sigma: float = 0.20  # 隆起标准差 / Bump standard deviation


def _bilinear_sample(field: np.ndarray, sample_y: np.ndarray, sample_x: np.ndarray) -> np.ndarray:  # 反向双线性采样 / Inverse bilinear sampling
    rows, cols = field.shape  # 输入尺寸 / Input shape
    y_clip = np.clip(sample_y, 0.0, rows - 1.0)  # 限制行坐标 / Clamp row coordinates
    x_clip = np.clip(sample_x, 0.0, cols - 1.0)  # 限制列坐标 / Clamp column coordinates
    y0 = np.floor(y_clip).astype(int)  # 行下整 / Row floor
    x0 = np.floor(x_clip).astype(int)  # 列下整 / Column floor
    y1 = np.clip(y0 + 1, 0, rows - 1)  # 行上整 / Row ceil
    x1 = np.clip(x0 + 1, 0, cols - 1)  # 列上整 / Column ceil
    wy = (y_clip - y0)  # 行权重 / Row weight
    wx = (x_clip - x0)  # 列权重 / Column weight
    a = field[y0, x0]  # 左上 / Top-left
    b = field[y0, x1]  # 右上 / Top-right
    c = field[y1, x0]  # 左下 / Bottom-left
    d = field[y1, x1]  # 右下 / Bottom-right
    upper = a * (1.0 - wx) + b * wx  # 上行 / Top row
    lower = c * (1.0 - wx) + d * wx  # 下行 / Bottom row
    return upper * (1.0 - wy) + lower * wy  # 双线性插值 / Bilinear interpolation


def apply_perturbation(mode_field: np.ndarray, params: PerturbationParams) -> np.ndarray:  # 把微扰应用到位移场 / Apply perturbation to displacement field
    rows, cols = mode_field.shape  # 网格尺寸 / Grid shape
    yy, xx = np.mgrid[0:rows, 0:cols].astype(float)  # 像素网格 / Pixel grid
    cy = (rows - 1) / 2.0  # 行中心 / Row centre
    cx = (cols - 1) / 2.0  # 列中心 / Column centre
    nx = (xx - cx) / max(cx, 1.0e-9)  # 归一化 x （-1 ~ 1） / Normalised x
    ny = (yy - cy) / max(cy, 1.0e-9)  # 归一化 y / Normalised y
    sx = float(params.stretch_x) if params.stretch_x != 0.0 else 1.0  # 防零 X 拉伸 / Guard zero X stretch
    sy = float(params.stretch_y) if params.stretch_y != 0.0 else 1.0  # 防零 Y 拉伸 / Guard zero Y stretch
    s = float(params.scale) if params.scale != 0.0 else 1.0  # 防零整体缩放 / Guard zero scale
    nx_shift = nx - float(params.translate_x)  # 平移 X / Translate X
    ny_shift = ny - float(params.translate_y)  # 平移 Y / Translate Y
    sh = float(params.shear)  # 切变 / Shear
    nx_shear = nx_shift - sh * ny_shift  # 切变后的 X / Sheared X
    ny_shear = ny_shift  # 切变保留 Y / Keep Y under shear
    theta = float(params.rotate_deg) * np.pi / 180.0  # 弧度 / Radians
    cos_t = np.cos(theta)  # 余弦 / Cosine
    sin_t = np.sin(theta)  # 正弦 / Sine
    nx_rot = cos_t * nx_shear + sin_t * ny_shear  # 旋转后的 X / Rotated X
    ny_rot = -sin_t * nx_shear + cos_t * ny_shear  # 旋转后的 Y / Rotated Y
    nx_pre = nx_rot / sx / s  # 反向 X 缩放 / Inverse X scale
    ny_pre = ny_rot / sy / s  # 反向 Y 缩放 / Inverse Y scale
    sample_x = nx_pre * cx + cx  # 像素 X 坐标 / Pixel X coordinate
    sample_y = ny_pre * cy + cy  # 像素 Y 坐标 / Pixel Y coordinate
    warped = _bilinear_sample(mode_field, sample_y, sample_x)  # 反向采样 / Inverse sample
    radius_sq = (nx - float(params.bump_x)) ** 2 + (ny - float(params.bump_y)) ** 2  # 隆起半径平方（归一化坐标） / Bump squared radius (normalised coords)
    bump_sigma = max(float(params.bump_sigma), 1.0e-3)  # 防零 sigma / Guard zero sigma
    bump = float(params.bump_amplitude) * np.exp(-0.5 * radius_sq / (bump_sigma * bump_sigma))  # 高斯隆起 / Gaussian bump
    perturbed = warped + bump  # 合成位移场 / Composed displacement field
    return perturbed.astype(float)  # 返回结果 / Return result


def normalise_params(payload: dict) -> PerturbationParams:  # 校验并规范化前端载荷 / Validate and normalise frontend payload
    def safe_float(key: str, default: float, lo: float, hi: float) -> float:  # 取浮点并裁剪 / Read float and clip
        try:  # 防转换失败 / Guard conversion failure
            return float(np.clip(float(payload.get(key, default)), lo, hi))  # 返回裁剪后值 / Return clipped value
        except (TypeError, ValueError):  # 处理无效输入 / Handle invalid input
            return float(default)  # 回退默认值 / Fall back to default
    return PerturbationParams(  # 构造参数 / Build params
        stretch_x=safe_float("stretch_x", 1.0, 0.30, 3.0),  # X 拉伸限幅 / X stretch limits
        stretch_y=safe_float("stretch_y", 1.0, 0.30, 3.0),  # Y 拉伸限幅 / Y stretch limits
        rotate_deg=safe_float("rotate_deg", 0.0, -180.0, 180.0),  # 旋转限幅 / Rotation limits
        scale=safe_float("scale", 1.0, 0.50, 2.0),  # 缩放限幅 / Scale limits
        shear=safe_float("shear", 0.0, -0.50, 0.50),  # 切变限幅 / Shear limits
        translate_x=safe_float("translate_x", 0.0, -0.40, 0.40),  # 平移限幅 / Translate limits
        translate_y=safe_float("translate_y", 0.0, -0.40, 0.40),  # 平移限幅 / Translate limits
        bump_amplitude=safe_float("bump_amplitude", 0.0, -1.0, 1.0),  # 隆起幅度限幅 / Bump amplitude limits
        bump_x=safe_float("bump_x", 0.0, -1.0, 1.0),  # 隆起 x 限幅 / Bump x limits
        bump_y=safe_float("bump_y", 0.0, -1.0, 1.0),  # 隆起 y 限幅 / Bump y limits
        bump_sigma=safe_float("bump_sigma", 0.20, 0.05, 0.80),  # 隆起 sigma 限幅 / Bump sigma limits
    )  # 结束构造 / End build


def params_summary(params: PerturbationParams) -> dict:  # 输出可序列化摘要 / Output serialisable summary
    return {  # 返回字典 / Return dict
        "stretch_x": float(params.stretch_x),  # X 拉伸 / X stretch
        "stretch_y": float(params.stretch_y),  # Y 拉伸 / Y stretch
        "rotate_deg": float(params.rotate_deg),  # 旋转角度 / Rotation degrees
        "scale": float(params.scale),  # 缩放 / Scale
        "shear": float(params.shear),  # 切变 / Shear
        "translate_x": float(params.translate_x),  # X 平移 / X translate
        "translate_y": float(params.translate_y),  # Y 平移 / Y translate
        "bump_amplitude": float(params.bump_amplitude),  # 隆起幅度 / Bump amplitude
        "bump_x": float(params.bump_x),  # 隆起 X / Bump X
        "bump_y": float(params.bump_y),  # 隆起 Y / Bump Y
        "bump_sigma": float(params.bump_sigma),  # 隆起 sigma / Bump sigma
    }  # 结束字典 / End dict
