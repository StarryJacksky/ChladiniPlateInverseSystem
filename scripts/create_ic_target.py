from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import sys  # 导入系统工具 / Import system utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

from PIL import Image  # 导入图像工具 / Import image utilities
from PIL import ImageDraw  # 导入绘图工具 / Import drawing utilities
from PIL import ImageFont  # 导入字体工具 / Import font utilities


def create_ic_target(output_path: str | Path = "data/target_patterns/target.png") -> Path:  # 创建 IC 目标图 / Create IC target image
    path = Path(output_path)  # 转换为路径对象 / Convert to path object
    path.parent.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    canvas_size = 1024  # 设置画布尺寸 / Set canvas size
    image = Image.new("RGB", (canvas_size, canvas_size), "white")  # 创建白色背景图 / Create white-background image
    draw = ImageDraw.Draw(image)  # 创建绘图对象 / Create drawing object
    font_path = Path("C:/Windows/Fonts/timesbd.ttf")  # 设置 Times New Roman 粗体路径 / Set Times New Roman bold path
    font = ImageFont.truetype(str(font_path), 520)  # 加载字体 / Load font
    text = "IC"  # 设置目标文字 / Set target text
    box = draw.textbbox((0, 0), text, font=font)  # 获取文字边界 / Get text bounding box
    text_width = box[2] - box[0]  # 计算文字宽度 / Compute text width
    text_height = box[3] - box[1]  # 计算文字高度 / Compute text height
    x = (canvas_size - text_width) // 2 - box[0]  # 计算居中 x 坐标 / Compute centered x coordinate
    y = (canvas_size - text_height) // 2 - box[1]  # 计算居中 y 坐标 / Compute centered y coordinate
    color = (0, 37, 93)  # 设置深蓝颜色 / Set dark blue colour
    draw.text((x, y), text, font=font, fill=color)  # 绘制 IC 文字 / Draw IC text
    image.save(path)  # 保存目标图 / Save target image
    return path  # 返回输出路径 / Return output path


if __name__ == "__main__":  # 判断是否直接运行 / Check direct execution
    sys.stdout.reconfigure(encoding="utf-8")  # 设置 UTF-8 输出 / Set UTF-8 output
    created = create_ic_target()  # 创建目标图 / Create target image
    print(f"Created {created}. / 已创建 {created}。")  # 打印输出路径 / Print output path
