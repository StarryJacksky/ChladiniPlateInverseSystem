from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from io import BytesIO  # 导入字节流 / Import byte stream
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
from PIL import Image  # 导入图像库 / Import image library


def _bilinear_upsample(field: np.ndarray, output_size: int) -> np.ndarray:  # 双线性升采样 / Bilinear upsample
    rows, cols = field.shape  # 输入尺寸 / Input shape
    if rows <= 1 or cols <= 1:  # 防退化 / Guard degenerate input
        return np.zeros((int(output_size), int(output_size)), dtype=float)  # 返回零场 / Return zero field
    src_y = np.linspace(0.0, rows - 1.0, int(output_size))  # 输出行的源行坐标 / Output rows' source-row coords
    src_x = np.linspace(0.0, cols - 1.0, int(output_size))  # 输出列的源列坐标 / Output cols' source-col coords
    y_floor = np.floor(src_y).astype(int)  # 行下整 / Row floor
    x_floor = np.floor(src_x).astype(int)  # 列下整 / Column floor
    y_ceil = np.clip(y_floor + 1, 0, rows - 1)  # 行上整 / Row ceil
    x_ceil = np.clip(x_floor + 1, 0, cols - 1)  # 列上整 / Column ceil
    wy = (src_y - y_floor).reshape(-1, 1)  # 行权重 / Row weight
    wx = (src_x - x_floor).reshape(1, -1)  # 列权重 / Column weight
    f_yy_xx = field[np.ix_(y_floor, x_floor)]  # 左上 / Top-left
    f_yy_xc = field[np.ix_(y_floor, x_ceil)]  # 右上 / Top-right
    f_yc_xx = field[np.ix_(y_ceil, x_floor)]  # 左下 / Bottom-left
    f_yc_xc = field[np.ix_(y_ceil, x_ceil)]  # 右下 / Bottom-right
    upper = f_yy_xx * (1.0 - wx) + f_yy_xc * wx  # 上行插值 / Top-row interpolation
    lower = f_yc_xx * (1.0 - wx) + f_yc_xc * wx  # 下行插值 / Bottom-row interpolation
    return upper * (1.0 - wy) + lower * wy  # 返回插值结果 / Return interpolated field


def _hi_res_nodal_mask(mode_field: np.ndarray, output_size: int) -> np.ndarray:  # 高分辨率节点线 / Hi-res nodal mask
    upsampled = _bilinear_upsample(mode_field, int(output_size))  # 升采样位移场 / Upsample displacement field
    amplitude = np.abs(upsampled)  # 振幅 / Amplitude
    threshold = max(float(amplitude.max()), 1.0e-9) * 0.020  # 近零阈值 / Near-zero threshold
    nodal = amplitude <= threshold  # 近零像素 / Near-zero pixels
    vertical = upsampled[:-1, :] * upsampled[1:, :] <= 0.0  # 纵向翻转 / Vertical sign change
    horizontal = upsampled[:, :-1] * upsampled[:, 1:] <= 0.0  # 横向翻转 / Horizontal sign change
    nodal[:-1, :] |= vertical  # 标记上侧 / Mark upper side
    nodal[1:, :] |= vertical  # 标记下侧 / Mark lower side
    nodal[:, :-1] |= horizontal  # 标记左侧 / Mark left side
    nodal[:, 1:] |= horizontal  # 标记右侧 / Mark right side
    return nodal.astype(bool)  # 返回布尔图 / Return boolean map


def _binary_dilate(mask: np.ndarray, iterations: int) -> np.ndarray:  # 简单膨胀 / Simple dilation
    result = mask.astype(bool)  # 转布尔 / To bool
    for _ in range(int(iterations)):  # 遍历次数 / Iterate
        padded = np.pad(result, 1, mode="constant", constant_values=False)  # 填充边框 / Pad border
        result = padded[1:-1, 1:-1] | padded[:-2, 1:-1] | padded[2:, 1:-1] | padded[1:-1, :-2] | padded[1:-1, 2:]  # 十字膨胀 / Cross dilation
    return result  # 返回膨胀结果 / Return dilation result


def _mask_centre_clamp(mask: np.ndarray, centre_clamp_radius_mm: float, plate_length_mm: float) -> np.ndarray:  # 清除中心夹持区 / Clear centre clamp region
    if centre_clamp_radius_mm <= 0.0:  # 无夹持 / No clamp
        return mask  # 直接返回 / Return as-is
    height, width = mask.shape  # 读取尺寸 / Read shape
    yy, xx = np.ogrid[:height, :width]  # 坐标网格 / Coordinate grid
    cy = (height - 1) / 2.0  # y 中心 / y centre
    cx = (width - 1) / 2.0  # x 中心 / x centre
    radius_px = (centre_clamp_radius_mm / max(plate_length_mm, 1.0e-9)) * float(min(height, width))  # 夹持半径像素 / Clamp radius pixels
    centre = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius_px ** 2  # 中心圆 / Centre circle
    cleared = mask.copy()  # 复制 / Copy
    cleared[centre] = False  # 清零 / Clear
    return cleared  # 返回清理结果 / Return cleared mask


def render_pattern_mask(mode_field: np.ndarray, output_size: int = 512, line_width_px: int = 4, plate_length_mm: float = 150.0, centre_clamp_radius_mm: float = 8.0) -> np.ndarray:  # 渲染为二值节点线掩膜 / Render to boolean nodal-line mask
    mask = _hi_res_nodal_mask(mode_field, int(output_size))  # 高分辨率节点线 / Hi-res nodal mask
    iterations = max(0, int(line_width_px) // 2)  # 膨胀次数 / Dilation iterations
    if iterations > 0:  # 是否膨胀 / Apply dilation?
        mask = _binary_dilate(mask, iterations)  # 加粗 / Thicken
    return _mask_centre_clamp(mask, float(centre_clamp_radius_mm), float(plate_length_mm))  # 清中心 / Clear centre


def render_pattern_png(mode_field: np.ndarray, output_size: int = 512, line_width_px: int = 4, plate_length_mm: float = 150.0, centre_clamp_radius_mm: float = 8.0) -> Image.Image:  # 渲染节点线 PNG / Render nodal-line PNG
    mask = render_pattern_mask(mode_field, int(output_size), int(line_width_px), float(plate_length_mm), float(centre_clamp_radius_mm))  # 复用掩膜渲染 / Reuse mask renderer
    image = Image.new("L", (int(output_size), int(output_size)), color=255)  # 创建白底灰度图 / Create white grayscale image
    array = np.asarray(image).copy()  # 拷为可写数组 / Copy as writable array
    array[mask] = 0  # 节点线设为黑 / Set nodal lines to black
    return Image.fromarray(array, mode="L").convert("RGB")  # 返回 RGB 图 / Return RGB image


def render_pattern_bytes(mode_field: np.ndarray, output_size: int = 512, line_width_px: int = 4, plate_length_mm: float = 150.0, centre_clamp_radius_mm: float = 8.0, fmt: str = "PNG") -> bytes:  # 渲染并返回字节 / Render and return bytes
    image = render_pattern_png(mode_field, int(output_size), int(line_width_px), float(plate_length_mm), float(centre_clamp_radius_mm))  # 渲染图像 / Render image
    buffer = BytesIO()  # 内存缓冲 / Memory buffer
    image.save(buffer, format=str(fmt))  # 保存到缓冲 / Save to buffer
    return buffer.getvalue()  # 返回字节 / Return bytes


def render_thumbnail_bytes(mode_field: np.ndarray, output_size: int = 160, line_width_px: int = 2, plate_length_mm: float = 150.0, centre_clamp_radius_mm: float = 8.0) -> bytes:  # 渲染缩略图 / Render thumbnail
    return render_pattern_bytes(mode_field, int(output_size), int(line_width_px), float(plate_length_mm), float(centre_clamp_radius_mm), fmt="PNG")  # 返回 PNG 字节 / Return PNG bytes


def save_pattern_png(mode_field: np.ndarray, output_path: Path | str, output_size: int = 512, line_width_px: int = 4, plate_length_mm: float = 150.0, centre_clamp_radius_mm: float = 8.0) -> Path:  # 保存到文件 / Save to file
    image = render_pattern_png(mode_field, int(output_size), int(line_width_px), float(plate_length_mm), float(centre_clamp_radius_mm))  # 渲染 / Render
    path = Path(output_path)  # 转路径 / Convert to path
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent
    image.save(path, format="PNG")  # 写 PNG / Write PNG
    return path  # 返回路径 / Return path
