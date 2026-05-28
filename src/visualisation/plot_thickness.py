from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
from PIL import Image  # 导入图像工具 / Import image utilities
from PIL import ImageDraw  # 导入绘图工具 / Import drawing utilities
from PIL import ImageFont  # 导入字体工具 / Import font utilities

from src.candidate.constraints import center_cells_for_grid  # 导入中心单元函数 / Import centre-cell helper


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:  # 加载字体 / Load font
    font_path = Path("C:/Windows/Fonts/msyh.ttc")  # 设置微软雅黑字体路径 / Set Microsoft YaHei font path
    if font_path.exists():  # 检查字体是否存在 / Check whether font exists
        return ImageFont.truetype(str(font_path), size)  # 返回 TrueType 字体 / Return TrueType font
    return ImageFont.load_default()  # 返回默认字体 / Return default font


def thickness_colour(value: float, min_value: float, max_value: float) -> tuple[int, int, int]:  # 计算厚度颜色 / Compute thickness colour
    ratio = (value - min_value) / max(max_value - min_value, 1e-12)  # 计算归一化比例 / Compute normalised ratio
    red = int(36 + 184 * ratio)  # 计算红色通道 / Compute red channel
    green = int(84 + 88 * (1.0 - abs(ratio - 0.5) * 2.0))  # 计算绿色通道 / Compute green channel
    blue = int(120 + 92 * (1.0 - ratio))  # 计算蓝色通道 / Compute blue channel
    return red, green, blue  # 返回 RGB 颜色 / Return RGB colour


def draw_center_marker(draw: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int) -> None:  # 绘制中心约束标记 / Draw center-constraint marker
    draw.line((x0 + 8, y0 + 8, x1 - 8, y1 - 8), fill=(255, 255, 255), width=3)  # 绘制白色斜线 / Draw white diagonal line
    draw.line((x0 + 8, y1 - 8, x1 - 8, y0 + 8), fill=(255, 255, 255), width=3)  # 绘制白色反斜线 / Draw white anti-diagonal line


def legend_values_for_thickness(H: np.ndarray) -> list[float]:  # 选择连续厚度图例值 / Choose legend values for continuous thickness
    unique = sorted(set(float(v) for v in H.ravel()))  # 读取唯一厚度值 / Read unique thickness values
    if len(unique) <= 8:  # 检查是否为少量离散值 / Check whether values are few and discrete
        return unique  # 返回所有离散值 / Return all discrete values
    minimum = float(np.min(H))  # 读取最小值 / Read minimum value
    maximum = float(np.max(H))  # 读取最大值 / Read maximum value
    return [minimum, (minimum + maximum) / 2.0, maximum]  # 返回连续图例三点 / Return three continuous legend points


def adaptive_precision(H: np.ndarray) -> int:  # 根据动态范围选数字精度 / Pick label precision based on dynamic range
    """Return the number of decimal places that lets the highest-value cell
    visually differ from the lowest-value cell. 2dp is enough when H spans
    say 0.6-2.0 mm, but when W10 converges near h_max (e.g. 1.99-2.00 mm)
    everything rounds to '2.00' and the grid looks uniform even though the
    colours differ — this helper bumps to 3dp / 4dp so the user can read
    the actual gradient."""
    finite = H[np.isfinite(H)]
    if finite.size == 0:
        return 2
    span = float(np.max(finite) - np.min(finite))
    if span <= 0.0:  # 全相等，无信息可读 → 2 位足够 / Exactly uniform field → 2 dp is fine
        return 2
    if span >= 0.05:  # 范围 >= 0.05 mm，2 位足够 / 2 dp is enough when range >= 0.05 mm
        return 2
    if span >= 0.005:  # 1.99 ~ 2.00 这类，需要 3 位 / Need 3 dp for tight clusters
        return 3
    return 4  # 极端紧密，给 4 位 / Very tight cluster, fall back to 4 dp


def render_thickness_matrix(H: np.ndarray, output_path: str | Path, title: str = "Thickness matrix") -> Path:  # 渲染厚度矩阵 / Render thickness matrix
    path = Path(output_path)  # 转换为路径对象 / Convert to path object
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    rows, cols = H.shape  # 获取矩阵尺寸 / Get matrix size
    cell = 80  # 设置单元格像素尺寸 / Set cell pixel size
    margin = 36  # 设置边距 / Set margin
    title_height = 56  # 设置标题高度 / Set title height
    legend_height = 56  # 设置图例高度 / Set legend height
    width = cols * cell + margin * 2  # 计算画布宽度 / Compute canvas width
    height = rows * cell + margin * 2 + title_height + legend_height  # 计算画布高度 / Compute canvas height
    image = Image.new("RGB", (width, height), (248, 249, 250))  # 创建浅色背景 / Create light background
    draw = ImageDraw.Draw(image)  # 创建绘图对象 / Create drawing object
    title_font = load_font(24)  # 加载标题字体 / Load title font
    label_font = load_font(18)  # 加载标签字体 / Load label font
    small_font = load_font(14)  # 加载小字体 / Load small font
    draw.text((margin, 18), title, fill=(24, 32, 40), font=title_font)  # 绘制标题 / Draw title
    min_value = float(np.min(H))  # 获取最小厚度 / Get minimum thickness
    max_value = float(np.max(H))  # 获取最大厚度 / Get maximum thickness
    precision = adaptive_precision(H)  # 自适应小数位 / Adaptive decimal precision
    fmt = f".{precision}f"  # 数字格式化模板 / Number format template
    # 小字体保险：高精度（4 位）的标签可能挤不下 80px 格子，降一档字号 /
    # Smaller font for high-precision labels so 4-digit numbers still fit
    if precision >= 4:
        label_font = load_font(13)
    elif precision == 3:
        label_font = load_font(15)
    grid_top = title_height + margin  # 计算网格顶部位置 / Compute grid top position
    center_cells = set(center_cells_for_grid(rows)) if rows == cols else set()  # 计算中心单元集合 / Compute centre-cell set
    for row in range(rows):  # 遍历矩阵行 / Iterate matrix rows
        for col in range(cols):  # 遍历矩阵列 / Iterate matrix columns
            x0 = margin + col * cell  # 计算单元左边界 / Compute cell left edge
            y0 = grid_top + row * cell  # 计算单元上边界 / Compute cell top edge
            x1 = x0 + cell  # 计算单元右边界 / Compute cell right edge
            y1 = y0 + cell  # 计算单元下边界 / Compute cell bottom edge
            colour = thickness_colour(float(H[row, col]), min_value, max_value)  # 计算单元颜色 / Compute cell colour
            draw.rectangle((x0, y0, x1, y1), fill=colour, outline=(255, 255, 255), width=3)  # 绘制单元格 / Draw cell
            label = format(float(H[row, col]), fmt)  # 自适应精度厚度标签 / Adaptive-precision thickness label
            box = draw.textbbox((0, 0), label, font=label_font)  # 计算文字边界 / Compute text bounding box
            tx = x0 + (cell - (box[2] - box[0])) / 2  # 计算文字 x 坐标 / Compute text x coordinate
            ty = y0 + (cell - (box[3] - box[1])) / 2  # 计算文字 y 坐标 / Compute text y coordinate
            draw.text((tx, ty), label, fill=(255, 255, 255), font=label_font)  # 绘制厚度数值 / Draw thickness value
            if (row, col) in center_cells:  # 判断是否为中心固定单元 / Check whether this is center fixed cell
                draw_center_marker(draw, x0, y0, x1, y1)  # 绘制中心标记 / Draw center marker
    legend_y = grid_top + rows * cell + 22  # 计算图例 y 坐标 / Compute legend y coordinate
    span_text = f"  ·  range {max_value - min_value:{fmt}} mm" if max_value > min_value else ""  # 范围提示 / Show dynamic range hint
    draw.text((margin, legend_y), f"Thickness / 厚度 (mm){span_text}", fill=(24, 32, 40), font=small_font)  # 绘制图例标题 / Draw legend title
    for index, value in enumerate(legend_values_for_thickness(H)):  # 遍历厚度图例值 / Iterate thickness legend values
        swatch_x = margin + 220 + index * 86  # 计算色块 x 坐标（让位给 range 提示）/ Compute swatch x (leave room for range hint)
        colour = thickness_colour(value, min_value, max_value)  # 计算色块颜色 / Compute swatch colour
        draw.rectangle((swatch_x, legend_y - 2, swatch_x + 24, legend_y + 22), fill=colour)  # 绘制色块 / Draw swatch
        draw.text((swatch_x + 30, legend_y), format(value, fmt), fill=(24, 32, 40), font=small_font)  # 绘制自适应精度厚度标签 / Adaptive-precision legend label
    image.save(path)  # 保存预览图 / Save preview image
    return path  # 返回输出路径 / Return output path


def render_candidate_preview(candidate_dir: str | Path) -> Path:  # 渲染候选预览 / Render candidate preview
    path = Path(candidate_dir)  # 转换为路径对象 / Convert to path object
    H = np.loadtxt(path / "H.csv", delimiter=",")  # 读取厚度矩阵 / Load thickness matrix
    return render_thickness_matrix(H, path / "preview_thickness.png", path.name)  # 渲染并返回预览 / Render and return preview
