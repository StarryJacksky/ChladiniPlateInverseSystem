from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
from PIL import Image  # 导入图像读取库 / Import image library


def load_target_image(path: str | Path) -> np.ndarray:  # 读取目标图像 / Load target image
    image = Image.open(path).convert("L")  # 读取并转为灰度图 / Open and convert to grayscale
    return np.asarray(image, dtype=np.float32) / 255.0  # 转为 0-1 数组 / Convert to 0-1 array


def resize_image(image: np.ndarray, output_size: int) -> np.ndarray:  # 缩放图像 / Resize image
    pil_image = Image.fromarray(np.uint8(np.clip(image, 0.0, 1.0) * 255.0))  # 转为 PIL 图像 / Convert to PIL image
    resized = pil_image.resize((output_size, output_size), Image.Resampling.BILINEAR)  # 双线性缩放 / Bilinear resize
    return np.asarray(resized, dtype=np.float32) / 255.0  # 返回 0-1 数组 / Return 0-1 array


def binarize_target(image: np.ndarray, threshold: float = 0.5) -> np.ndarray:  # 二值化目标图 / Binarise target image
    dark_line = image < threshold  # 默认深色线条为目标 / Treat dark strokes as target
    light_line = image > threshold  # 支持白色线条输入 / Support light strokes as input
    choose_dark = dark_line.mean() < light_line.mean()  # 选择面积较小的一侧作为线条 / Choose smaller side as strokes
    binary = dark_line if choose_dark else light_line  # 得到目标线条区域 / Get target stroke region
    return binary.astype(bool)  # 返回布尔数组 / Return boolean array


def remove_center_region(binary: np.ndarray, radius_px: int) -> np.ndarray:  # 移除中心夹持区 / Remove center clamp region
    height, width = binary.shape  # 获取图像尺寸 / Get image size
    yy, xx = np.ogrid[:height, :width]  # 创建坐标网格 / Create coordinate grid
    center_y = (height - 1) / 2.0  # 计算中心 y 坐标 / Compute center y coordinate
    center_x = (width - 1) / 2.0  # 计算中心 x 坐标 / Compute center x coordinate
    mask = (yy - center_y) ** 2 + (xx - center_x) ** 2 <= radius_px**2  # 生成圆形掩膜 / Create circular mask
    cleaned = binary.copy()  # 复制二值图 / Copy binary image
    cleaned[mask] = False  # 清除中心区域 / Clear center region
    return cleaned  # 返回处理结果 / Return processed result


def binary_dilation(binary: np.ndarray, iterations: int) -> np.ndarray:  # 执行简单二值膨胀 / Run simple binary dilation
    result = binary.astype(bool)  # 转为布尔数组 / Convert to boolean array
    for _ in range(iterations):  # 遍历膨胀次数 / Iterate dilation passes
        padded = np.pad(result, 1, mode="constant", constant_values=False)  # 给图像加边框 / Pad image border
        result = padded[1:-1, 1:-1] | padded[:-2, 1:-1] | padded[2:, 1:-1] | padded[1:-1, :-2] | padded[1:-1, 2:]  # 十字邻域膨胀 / Cross-neighbour dilation
    return result  # 返回膨胀结果 / Return dilated result


def binary_erosion(binary: np.ndarray, iterations: int) -> np.ndarray:  # 执行简单二值腐蚀 / Run simple binary erosion
    result = binary.astype(bool)  # 转为布尔数组 / Convert to boolean array
    for _ in range(iterations):  # 遍历腐蚀次数 / Iterate erosion passes
        padded = np.pad(result, 1, mode="constant", constant_values=False)  # 给图像加边框 / Pad image border
        result = padded[1:-1, 1:-1] & padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]  # 十字邻域腐蚀 / Cross-neighbour erosion
    return result  # 返回腐蚀结果 / Return eroded result


def extract_target_edges(binary: np.ndarray) -> np.ndarray:  # 提取填充图案边界 / Extract filled-pattern edges
    eroded = binary_erosion(binary, 1)  # 腐蚀前景区域 / Erode foreground region
    edges = binary & ~eroded  # 用原图减去腐蚀图得到边界 / Subtract eroded map from original to get edges
    return edges.astype(bool)  # 返回边界图 / Return edge map


def apply_target_mode(binary: np.ndarray, mode: str) -> np.ndarray:  # 应用目标提取模式 / Apply target extraction mode
    if mode == "edge":  # 判断是否提取边界 / Check edge mode
        return extract_target_edges(binary)  # 返回边界目标 / Return edge target
    if mode == "filled":  # 判断是否保留填充区域 / Check filled mode
        return binary.astype(bool)  # 返回填充目标 / Return filled target
    return binary.astype(bool)  # 默认按线条处理 / Default to stroke target


def thicken_target_line(binary: np.ndarray, target_width_px: int) -> np.ndarray:  # 加粗目标线 / Thicken target line
    iterations = max(0, int(target_width_px // 2))  # 计算膨胀次数 / Compute dilation iterations
    if iterations == 0:  # 判断是否需要膨胀 / Check whether dilation is needed
        return binary  # 直接返回原图 / Return original image
    thickened = binary_dilation(binary, iterations)  # 执行二值膨胀 / Run binary dilation
    return thickened.astype(bool)  # 返回布尔结果 / Return boolean result


def save_target_outputs(binary: np.ndarray, output_dir: str | Path) -> None:  # 保存目标输出 / Save target outputs
    out_dir = Path(output_dir)  # 转换为路径对象 / Convert to path object
    out_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    np.save(out_dir / "target_binary.npy", binary.astype(np.uint8))  # 保存 NumPy 数组 / Save NumPy array
    preview = Image.fromarray(np.uint8(binary) * 255)  # 生成预览图 / Create preview image
    preview.save(out_dir / "target_preview.png")  # 保存预览图 / Save preview image


def preprocess_target(path: str | Path, output_size: int = 256, line_width_px: int = 12, center_radius_px: int | None = None, output_dir: str | Path | None = None, target_mode: str = "stroke") -> np.ndarray:  # 预处理目标图 / Preprocess target image
    image = load_target_image(path)  # 读取目标图 / Load target image
    resized = resize_image(image, output_size)  # 缩放到统一尺寸 / Resize to unified size
    binary = binarize_target(resized)  # 二值化图像 / Binarise image
    shaped = apply_target_mode(binary, target_mode)  # 应用目标提取模式 / Apply target extraction mode
    thickened = thicken_target_line(shaped, line_width_px)  # 加粗目标线 / Thicken target line
    processed = remove_center_region(thickened, center_radius_px) if center_radius_px else thickened  # 可选移除中心区 / Optionally remove center region
    if output_dir is not None:  # 判断是否保存输出 / Check whether to save outputs
        save_target_outputs(processed, output_dir)  # 保存结果文件 / Save result files
    return processed  # 返回预处理目标图 / Return preprocessed target
