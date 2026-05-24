from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
from PIL import Image  # 导入图像工具 / Import image utilities
from PIL import ImageDraw  # 导入绘图工具 / Import drawing utilities

from src.comsol.import_results import interpolate_to_grid  # 导入插值函数 / Import interpolation helper
from src.comsol.import_results import load_mode_csv  # 导入模态读取函数 / Import mode CSV loader
from src.nodal.extract_nodal import extract_nodal_region  # 导入节点线提取函数 / Import nodal extraction helper
from src.nodal.extract_nodal import postprocess_nodal_region  # 导入节点线后处理函数 / Import nodal postprocessing helper
from src.nodal.extract_nodal import remove_center_region  # 导入中心区域移除函数 / Import centre-region removal helper


def resize_binary_to_shape(binary: np.ndarray, shape: tuple[int, int]) -> np.ndarray:  # 缩放二值图到指定尺寸 / Resize binary map to target shape
    if binary.shape == shape:  # 检查尺寸是否已匹配 / Check whether shape already matches
        return binary.astype(bool)  # 返回布尔图 / Return boolean map
    y_index = np.rint(np.linspace(0, binary.shape[0] - 1, shape[0])).astype(int)  # 生成 y 采样索引 / Build y sampling indices
    x_index = np.rint(np.linspace(0, binary.shape[1] - 1, shape[1])).astype(int)  # 生成 x 采样索引 / Build x sampling indices
    resized = binary[np.ix_(y_index, x_index)]  # 最近邻重采样 / Nearest-neighbour resampling
    return resized.astype(bool)  # 返回布尔结果 / Return boolean result


def save_binary_preview(binary: np.ndarray, output_path: str | Path, foreground: tuple[int, int, int]) -> Path:  # 保存二值预览图 / Save binary preview image
    output = Path(output_path)  # 转换输出路径 / Convert output path
    output.parent.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    rgb = np.full((*binary.shape, 3), 255, dtype=np.uint8)  # 创建白色背景 / Create white background
    rgb[binary.astype(bool)] = np.array(foreground, dtype=np.uint8)  # 写入前景颜色 / Apply foreground colour
    Image.fromarray(rgb, mode="RGB").save(output)  # 保存预览图 / Save preview image
    return output  # 返回输出路径 / Return output path


def render_target_simulation_overlay(target_binary: np.ndarray, simulated_binary: np.ndarray, output_path: str | Path) -> Path:  # 渲染目标与仿真叠图 / Render target-simulation overlay
    output = Path(output_path)  # 转换输出路径 / Convert output path
    output.parent.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    target = resize_binary_to_shape(target_binary, simulated_binary.shape)  # 对齐目标尺寸 / Align target size
    simulated = simulated_binary.astype(bool)  # 转为布尔仿真图 / Convert simulated map to boolean
    rgb = np.full((*simulated.shape, 3), 255, dtype=np.uint8)  # 创建白色背景 / Create white background
    rgb[target] = np.array([227, 92, 63], dtype=np.uint8)  # 目标区域标为红色 / Mark target in red
    rgb[simulated] = np.array([36, 125, 174], dtype=np.uint8)  # 仿真区域标为蓝色 / Mark simulation in blue
    rgb[target & simulated] = np.array([50, 150, 86], dtype=np.uint8)  # 重叠区域标为绿色 / Mark overlap in green
    Image.fromarray(rgb, mode="RGB").save(output)  # 保存叠图 / Save overlay image
    return output  # 返回输出路径 / Return output path


def nodal_map_from_mode(mode_csv: str | Path, image_size: int, epsilon_ratio: float, center_radius_px: int = 0) -> np.ndarray:  # 从模态 CSV 提取节点线 / Extract nodal map from mode CSV
    x, y, w = load_mode_csv(mode_csv)  # 读取模态 CSV / Load mode CSV
    W = interpolate_to_grid(x, y, w, image_size)  # 插值到图像网格 / Interpolate to image grid
    nodal = postprocess_nodal_region(extract_nodal_region(W, epsilon_ratio))  # 提取并后处理节点线 / Extract and postprocess nodal lines
    return remove_center_region(nodal, center_radius_px) if center_radius_px > 0 else nodal  # 可选移除中心区 / Optionally remove centre region


def render_candidate_comparison(export_dir: str | Path, target_binary: np.ndarray, best_mode: int, image_size: int, epsilon_ratio: float, center_radius_px: int = 0) -> dict[str, Path]:  # 渲染候选对比资产 / Render candidate comparison assets
    export_path = Path(export_dir)  # 转换导出目录 / Convert export directory
    mode_path = export_path / f"mode_{best_mode:02d}.csv"  # 构造最佳模态路径 / Build best-mode path
    if not mode_path.exists():  # 检查模态文件是否存在 / Check mode file existence
        return {}  # 返回空资产 / Return empty assets
    comparison_dir = export_path / "comparison"  # 构造对比图目录 / Build comparison directory
    simulated = nodal_map_from_mode(mode_path, image_size, epsilon_ratio, center_radius_px)  # 提取仿真节点线 / Extract simulated nodal map
    target = resize_binary_to_shape(target_binary, simulated.shape)  # 对齐目标图 / Align target map
    target_path = save_binary_preview(target, comparison_dir / "target_binary.png", (227, 92, 63))  # 保存目标预览 / Save target preview
    simulated_path = save_binary_preview(simulated, comparison_dir / "simulated_nodal.png", (36, 125, 174))  # 保存仿真预览 / Save simulation preview
    overlay_path = render_target_simulation_overlay(target, simulated, comparison_dir / "target_sim_overlay.png")  # 保存叠图 / Save overlay
    return {"target": target_path, "simulated": simulated_path, "overlay": overlay_path}  # 返回资产路径 / Return asset paths


def normalise_to_uint8(W: np.ndarray) -> np.ndarray:  # 归一化到 8 位灰度 / Normalise to 8-bit grayscale
    max_abs = float(np.max(np.abs(W)))  # 计算最大绝对值 / Compute maximum absolute value
    if max_abs == 0.0:  # 检查零场 / Check zero field
        return np.zeros_like(W, dtype=np.uint8)  # 返回黑图 / Return black image
    scaled = (W / max_abs * 0.5 + 0.5) * 255.0  # 映射到灰度范围 / Map to grayscale range
    return np.clip(scaled, 0, 255).astype(np.uint8)  # 裁剪并转为 8 位 / Clip and convert to 8-bit


def render_mode_preview(mode_csv: str | Path, output_path: str | Path, image_size: int, epsilon_ratio: float, center_radius_px: int = 0) -> Path:  # 渲染单个模态预览 / Render one mode preview
    mode_path = Path(mode_csv)  # 转换模态路径 / Convert mode path
    output = Path(output_path)  # 转换输出路径 / Convert output path
    output.parent.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    x, y, w = load_mode_csv(mode_path)  # 读取模态 CSV / Load mode CSV
    W = interpolate_to_grid(x, y, w, image_size)  # 插值到图像网格 / Interpolate to image grid
    nodal = postprocess_nodal_region(extract_nodal_region(W, epsilon_ratio))  # 提取节点线 / Extract nodal lines
    nodal = remove_center_region(nodal, center_radius_px) if center_radius_px > 0 else nodal  # 移除中心夹持区 / Remove centre clamp region
    grey = normalise_to_uint8(W)  # 生成位移灰度图 / Build displacement grayscale image
    rgb = np.stack([grey, grey, grey], axis=2)  # 转成 RGB 图 / Convert to RGB image
    rgb[nodal] = np.array([230, 30, 40], dtype=np.uint8)  # 用红色标记节点线 / Mark nodal lines in red
    image = Image.fromarray(rgb, mode="RGB")  # 创建 PIL 图像 / Create PIL image
    draw = ImageDraw.Draw(image)  # 创建绘图对象 / Create drawing object
    draw.text((8, 8), mode_path.stem, fill=(255, 255, 255))  # 绘制模态名称 / Draw mode name
    image.save(output)  # 保存预览图 / Save preview image
    return output  # 返回输出路径 / Return output path


def render_export_previews(export_dir: str | Path, image_size: int, epsilon_ratio: float, limit: int | None = None, center_radius_px: int = 0) -> list[Path]:  # 渲染导出目录预览 / Render export previews
    export_path = Path(export_dir)  # 转换导出目录 / Convert export directory
    mode_files = sorted(export_path.glob("mode_*.csv"))  # 查找模态文件 / Find mode files
    selected_files = mode_files[:limit] if limit else mode_files  # 选择要渲染的文件 / Select files to render
    preview_dir = export_path / "previews"  # 构造预览目录 / Build preview directory
    return [render_mode_preview(mode_file, preview_dir / f"{mode_file.stem}.png", image_size, epsilon_ratio, center_radius_px) for mode_file in selected_files]  # 渲染并返回路径 / Render and return paths
