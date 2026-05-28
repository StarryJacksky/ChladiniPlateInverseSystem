from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
from PIL import Image  # 导入图像工具 / Import image helper
from PIL import ImageDraw  # 导入绘图工具 / Import drawing helper

from src.subspace.free_subspace_feasibility import SubspaceResult  # 导入子空间结果结构 / Import subspace result structure
from src.subspace.mosaic_z import resize_binary_nearest  # 复用目标缩放工具 / Reuse target resizing helper


def _save_rgb(path: str | Path, array: np.ndarray) -> None:  # 保存 RGB 图像 / Save RGB image
    target = Path(path)  # 转换路径 / Convert path
    target.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    Image.fromarray(array.astype(np.uint8)).save(target)  # 保存图像 / Save image


def _mask_panel(mask: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:  # 从掩膜生成彩色面板 / Build colored panel from mask
    panel = np.full((*mask.shape, 3), 247, dtype=np.uint8)  # 创建浅色背景 / Create light background
    panel[mask.astype(bool)] = np.asarray(color, dtype=np.uint8)  # 绘制前景 / Paint foreground
    return panel  # 返回面板 / Return panel


def _response_panel(response: np.ndarray, nodal: np.ndarray) -> np.ndarray:  # 从响应场生成面板 / Build panel from response field
    scaled = response / max(float(np.max(np.abs(response))), 1.0e-12)  # 归一化响应 / Normalize response
    gray = np.uint8(np.clip((scaled + 1.0) * 0.5, 0.0, 1.0) * 255.0)  # 转成灰度 / Convert to grayscale
    panel = np.repeat(gray[:, :, None], 3, axis=2)  # 扩展成 RGB / Expand to RGB
    panel[nodal.astype(bool)] = np.asarray([38, 126, 177], dtype=np.uint8)  # 标出零线 / Mark zero contour
    return panel  # 返回面板 / Return panel


def save_response_triptych(path: str | Path, target_binary: np.ndarray, result: SubspaceResult) -> None:  # 保存目标/响应/叠加三联图 / Save target-response-overlay triptych
    target = resize_binary_nearest(target_binary, result.response.shape[0]).astype(bool)  # 对齐目标尺寸 / Align target size
    target_panel = _mask_panel(target, (232, 84, 61))  # 生成目标面板 / Build target panel
    response_panel = _response_panel(result.response, result.nodal)  # 生成响应面板 / Build response panel
    overlay = np.full((*target.shape, 3), 247, dtype=np.uint8)  # 创建叠加背景 / Create overlay background
    overlay[target] = np.asarray([232, 84, 61], dtype=np.uint8)  # 绘制目标 / Draw target
    overlay[result.nodal.astype(bool)] = np.asarray([38, 126, 177], dtype=np.uint8)  # 绘制模拟零线 / Draw simulated zero contour
    overlay[target & result.nodal.astype(bool)] = np.asarray([44, 153, 93], dtype=np.uint8)  # 绘制重叠 / Draw overlap
    spacer = np.full((target.shape[0], 10, 3), 255, dtype=np.uint8)  # 创建间隔 / Create spacer
    _save_rgb(path, np.concatenate([target_panel, spacer, response_panel, spacer, overlay], axis=1))  # 拼接并保存 / Concatenate and save


def _bar_canvas(title: str, width: int = 920, height: int = 360) -> tuple[Image.Image, ImageDraw.ImageDraw]:  # 创建条形图画布 / Create bar-chart canvas
    image = Image.new("RGB", (int(width), int(height)), (248, 248, 246))  # 创建浅色画布 / Create light canvas
    draw = ImageDraw.Draw(image)  # 创建绘图对象 / Create drawing object
    draw.text((24, 18), title, fill=(20, 24, 24))  # 绘制标题 / Draw title
    draw.line((70, height - 54, width - 24, height - 54), fill=(160, 166, 160), width=1)  # 绘制横轴 / Draw x axis
    draw.line((70, 58, 70, height - 54), fill=(160, 166, 160), width=1)  # 绘制纵轴 / Draw y axis
    return image, draw  # 返回画布和绘图对象 / Return canvas and draw object


def save_alpha_frequency_barplot(path: str | Path, result: SubspaceResult) -> None:  # 保存 alpha-频率条形图 / Save alpha-frequency bar chart
    image, draw = _bar_canvas("Modal coefficient energy by frequency / 模态系数能量-频率")  # 创建画布 / Create canvas
    freqs = np.asarray(result.freqs, dtype=float)  # 读取频率 / Read frequencies
    weights = np.square(np.asarray(result.alpha, dtype=float))  # 计算权重 / Compute weights
    weights = weights / max(float(weights.max()), 1.0e-12)  # 归一化条高 / Normalize bar heights
    f_min, f_max = float(freqs.min()), float(freqs.max())  # 读取频率范围 / Read frequency range
    for index, (freq, weight, alpha) in enumerate(zip(freqs, weights, result.alpha)):  # 遍历模态权重 / Iterate modal weights
        x = 80 + int((float(freq) - f_min) / max(f_max - f_min, 1.0e-12) * 780)  # 映射频率到横坐标 / Map frequency to x coordinate
        height = int(float(weight) * 230)  # 计算条形高度 / Compute bar height
        color = (38, 126, 177) if float(alpha) >= 0.0 else (214, 88, 70)  # 按符号选择颜色 / Select color by sign
        draw.rectangle((x - 5, 306 - height, x + 5, 306), fill=color)  # 绘制条形 / Draw bar
        if index % 4 == 0:  # 控制标签密度 / Control label density
            draw.text((x - 14, 312), str(int(result.mode_ids[index])), fill=(70, 76, 76))  # 绘制模态编号 / Draw mode id
    draw.text((80, 332), f"{f_min:.0f} Hz", fill=(70, 76, 76))  # 绘制最低频率 / Draw minimum frequency
    draw.text((820, 332), f"{f_max:.0f} Hz", fill=(70, 76, 76))  # 绘制最高频率 / Draw maximum frequency
    Path(path).parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    image.save(path)  # 保存图像 / Save image


def save_drive_participation_barplot(path: str | Path, mode_ids: list[int], freqs: np.ndarray, participation: np.ndarray) -> None:  # 保存中心参与度条形图 / Save centre-participation bar chart
    image, draw = _bar_canvas("Center-drive participation by mode / 中心激励参与度")  # 创建画布 / Create canvas
    values = np.asarray(participation, dtype=float)  # 读取参与度 / Read participation values
    if values.size == 0:  # 检查空数据 / Check empty data
        Path(path).parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
        image.save(path)  # 保存空图 / Save empty chart
        return  # 结束函数 / End function
    freqs_np = np.asarray(freqs, dtype=float)  # 读取频率数组 / Read frequency array
    f_min, f_max = float(freqs_np.min()), float(freqs_np.max())  # 读取频率范围 / Read frequency range
    for index, value in enumerate(values):  # 遍历参与度 / Iterate participation values
        x = 80 + int((float(freqs_np[index]) - f_min) / max(f_max - f_min, 1.0e-12) * 780)  # 映射频率到横坐标 / Map frequency to x coordinate
        height = int(float(value) * 230)  # 计算条形高度 / Compute bar height
        draw.rectangle((x - 5, 306 - height, x + 5, 306), fill=(65, 145, 117))  # 绘制条形 / Draw bar
        if index % 4 == 0:  # 控制标签密度 / Control label density
            draw.text((x - 14, 312), str(int(mode_ids[index])), fill=(70, 76, 76))  # 绘制模态编号 / Draw mode id
    draw.text((80, 332), f"{f_min:.0f} Hz", fill=(70, 76, 76))  # 绘制最低频率 / Draw minimum frequency
    draw.text((820, 332), f"{f_max:.0f} Hz", fill=(70, 76, 76))  # 绘制最高频率 / Draw maximum frequency
    Path(path).parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    image.save(path)  # 保存图像 / Save image


def save_summary_score_barplot(path: str | Path, rows: list[dict[str, object]]) -> None:  # 保存物理分数总览图 / Save physical-score summary chart
    image = Image.new("RGB", (920, 360), (248, 248, 246))  # 创建画布 / Create canvas
    draw = ImageDraw.Draw(image)  # 创建绘图对象 / Create drawing object
    draw.text((24, 18), "Physical feasibility score / 物理可达性分数", fill=(20, 24, 24))  # 绘制标题 / Draw title
    if not rows:  # 检查空记录 / Check empty rows
        Path(path).parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
        image.save(path)  # 保存空图 / Save empty chart
        return  # 结束函数 / End function
    scores = [float(row.get("physical_score", 0.0)) for row in rows]  # 读取分数 / Read scores
    min_score = min(0.0, min(scores))  # 读取最小分 / Read minimum score
    max_score = max(0.1, max(scores))  # 读取最大分 / Read maximum score
    bar_width = max(18, int(760 / max(len(rows), 1)))  # 计算条宽 / Compute bar width
    zero_y = 300 - int((0.0 - min_score) / max(max_score - min_score, 1.0e-12) * 230)  # 计算零轴位置 / Compute zero-axis position
    draw.line((70, zero_y, 890, zero_y), fill=(160, 166, 160), width=1)  # 绘制零轴 / Draw zero axis
    for index, row in enumerate(rows):  # 遍历记录 / Iterate rows
        score = float(row.get("physical_score", 0.0))  # 读取分数 / Read score
        x0 = 80 + index * bar_width  # 计算条形左侧 / Compute bar left
        y = 300 - int((score - min_score) / max(max_score - min_score, 1.0e-12) * 230)  # 计算条形高度坐标 / Compute bar y coordinate
        color = (65, 145, 117) if score >= 0.0 else (214, 88, 70)  # 按正负选择颜色 / Select color by sign
        draw.rectangle((x0, min(y, zero_y), x0 + max(8, bar_width - 6), max(y, zero_y)), fill=color)  # 绘制条形 / Draw bar
        label = str(row.get("case_label", row.get("case_name", "")))[:10]  # 构造标签 / Build label
        draw.text((x0, 310), label, fill=(70, 76, 76))  # 绘制标签 / Draw label
    Path(path).parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    image.save(path)  # 保存图像 / Save image
