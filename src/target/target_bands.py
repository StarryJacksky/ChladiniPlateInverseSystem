from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
from PIL import Image  # 导入图像读取工具 / Import image loading helper
from scipy.ndimage import distance_transform_edt  # 导入距离变换 / Import distance transform

from src.subspace.mosaic_z import build_center_valid_mask  # 复用中心有效掩膜 / Reuse centre-valid mask helper
from src.subspace.mosaic_z import build_target_skeleton  # 复用骨架提取 / Reuse target skeleton builder
from src.subspace.mosaic_z import resize_binary_nearest  # 复用二值缩放 / Reuse binary resize helper
from src.target.preprocess_target import binarize_target  # 复用目标二值化 / Reuse target binarisation
from src.target.preprocess_target import load_target_image  # 复用目标图读取 / Reuse target image loader
from src.target.preprocess_target import resize_image  # 复用目标图缩放 / Reuse target image resizing


DEFAULT_BAND_CONFIG = {"target_band_radius_px": 2, "side_band_inner_radius_px": 4, "side_band_outer_radius_px": 10, "center_mask_radius_px": 0}  # 定义默认 band 参数 / Define default band parameters


def load_target_binary(path: str | Path, image_size: int) -> np.ndarray:  # 从 NPY 或图片读取目标二值图 / Load target binary map from NPY or image
    target_path = Path(path)  # 转换目标路径 / Convert target path
    if not target_path.exists():  # 检查目标文件是否存在 / Check target-file existence
        raise FileNotFoundError(f"Target file not found: {target_path}. / 未找到目标文件：{target_path}。")  # 抛出缺失错误 / Raise missing-file error
    if target_path.suffix.lower() == ".npy":  # 检查是否为 NPY / Check NPY input
        data = np.load(target_path).astype(bool)  # 读取 NPY 目标 / Load NPY target
        return resize_binary_nearest(data, int(image_size)).astype(bool)  # 缩放到目标尺寸 / Resize to target size
    image = load_target_image(target_path)  # 读取图片目标 / Load image target
    resized = resize_image(image, int(image_size))  # 缩放灰度图 / Resize grayscale image
    return binarize_target(resized).astype(bool)  # 二值化并返回 / Binarise and return


def save_band_overlay(path: str | Path, target_data: dict[str, np.ndarray]) -> None:  # 保存目标带/侧带叠加图 / Save target-band and side-band overlay
    target = target_data["target_binary"].astype(bool)  # 读取目标二值图 / Read target binary map
    target_band = target_data["target_band"].astype(bool)  # 读取目标带 / Read target band
    side_band = target_data["side_band"].astype(bool)  # 读取侧带 / Read side band
    overlay = np.full((*target.shape, 3), 247, dtype=np.uint8)  # 创建浅色背景 / Create light background
    overlay[side_band] = np.asarray([198, 219, 239], dtype=np.uint8)  # 绘制侧带浅蓝 / Paint side band light blue
    overlay[target_band] = np.asarray([65, 145, 117], dtype=np.uint8)  # 绘制目标带绿色 / Paint target band green
    overlay[target] = np.asarray([232, 84, 61], dtype=np.uint8)  # 绘制原目标红色 / Paint original target red
    output = Path(path)  # 转换输出路径 / Convert output path
    output.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    Image.fromarray(overlay).save(output)  # 保存叠加图 / Save overlay image


def build_target_bands_from_binary(target_binary: np.ndarray, image_size: int, config: dict | None = None) -> dict[str, np.ndarray]:  # 从二值目标构造 band 数据 / Build band data from binary target
    selected = {**DEFAULT_BAND_CONFIG, **(config or {})}  # 合并默认配置 / Merge default config
    target = resize_binary_nearest(target_binary.astype(bool), int(image_size)).astype(bool)  # 缩放目标 / Resize target
    skeleton = build_target_skeleton(target).astype(bool)  # 构造目标骨架 / Build target skeleton
    distance = distance_transform_edt(~skeleton).astype(np.float32)  # 计算到目标骨架距离 / Compute distance to target skeleton
    target_band = distance <= float(selected["target_band_radius_px"])  # 构造目标带 / Build target band
    side_band = (distance >= float(selected["side_band_inner_radius_px"])) & (distance <= float(selected["side_band_outer_radius_px"]))  # 构造侧带 / Build side band
    center_radius = int(selected.get("center_mask_radius_px", 0))  # 读取中心掩膜半径 / Read centre-mask radius
    if center_radius > 0:  # 检查是否需要移除中心 / Check centre-mask need
        valid = build_center_valid_mask(target.shape, center_radius)  # 构造中心有效掩膜 / Build centre-valid mask
        target = target & valid  # 从目标移除中心区 / Remove centre from target
        skeleton = skeleton & valid  # 从骨架移除中心区 / Remove centre from skeleton
        target_band = target_band & valid  # 从目标带移除中心区 / Remove centre from target band
        side_band = side_band & valid  # 从侧带移除中心区 / Remove centre from side band
    return {"target_binary": target, "target_skeleton": skeleton, "target_band": target_band.astype(bool), "side_band": side_band.astype(bool), "distance_to_target": distance, "config": selected}  # 返回目标 band 数据 / Return target band data


def build_target_bands(target_path: str | Path, image_size: int, config: dict | None = None) -> dict[str, np.ndarray]:  # 从目标文件构造 band 数据 / Build band data from target file
    binary = load_target_binary(target_path, int(image_size))  # 读取目标二值图 / Load target binary map
    data = build_target_bands_from_binary(binary, int(image_size), config)  # 构造 band 数据 / Build band data
    data["target_path"] = str(target_path)  # 记录目标路径 / Record target path
    return data  # 返回 band 数据 / Return band data
