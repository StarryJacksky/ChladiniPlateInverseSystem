from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析工具 / Import command-line parsing tools
import json  # 导入 JSON 工具 / Import JSON utilities
import shutil  # 导入目录清理工具 / Import directory cleanup helper
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.comsol.export_parameters import export_candidate_for_comsol  # 导入 COMSOL 参数导出 / Import COMSOL parameter export
from src.config import load_config  # 导入配置读取 / Import config loader
from src.tags.target_aligned_geometry import build_default_tags_cases  # 导入默认 TAGS 案例 / Import default TAGS cases
from src.tags.target_aligned_geometry import build_tags_bands  # 导入目标带构造 / Import TAGS band builder
from src.tags.target_aligned_geometry import generate_tags_thickness_matrix  # 导入厚度矩阵生成 / Import thickness-matrix generator
from src.target.preprocess_target import preprocess_target  # 导入目标预处理 / Import target preprocessing
from src.visualisation.plot_thickness import render_candidate_preview  # 导入厚度预览渲染 / Import thickness preview renderer


def build_parser() -> argparse.ArgumentParser:  # 构建命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Generate TAGS target-aligned passive thickness candidates. / 生成 TAGS 目标对齐被动厚度候选。")  # 初始化解析器 / Initialise parser
    parser.add_argument("--config", default="config.yaml", help="Project config path. / 项目配置路径。")  # 添加配置参数 / Add config argument
    parser.add_argument("--target-npy", default="", help="Processed target_binary.npy path. / 已处理目标 npy 路径。")  # 添加目标数组参数 / Add target array argument
    parser.add_argument("--output-root", default="", help="Candidate output root. / 候选输出根目录。")  # 添加输出根目录 / Add output root
    parser.add_argument("--prefix", default="tags_passive", help="Candidate name prefix. / 候选名称前缀。")  # 添加名称前缀 / Add name prefix
    parser.add_argument("--target-radius-px", type=float, default=0.0, help="Target skeleton band radius in pixels. / 目标骨架带像素半径。")  # 添加目标半径 / Add target radius
    parser.add_argument("--side-radius-px", type=float, default=0.0, help="Side guard band radius in pixels. / 侧向保护带像素半径。")  # 添加侧带半径 / Add side radius
    parser.add_argument("--background-mm", type=float, default=0.0, help="Background underside thickness in mm. / 背景下表面厚度 mm。")  # 添加背景厚度 / Add background thickness
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing TAGS candidate directories. / 覆盖已有 TAGS 候选目录。")  # 添加覆盖开关 / Add overwrite flag
    return parser  # 返回解析器 / Return parser


def processed_target_path(config: dict, override: str) -> Path:  # 解析目标数组路径 / Resolve target array path
    if override:  # 检查是否给了覆盖路径 / Check override path
        return Path(override)  # 返回覆盖路径 / Return override path
    return Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 返回默认处理目标 / Return default processed target


def ensure_processed_target(config: dict, target_path: Path) -> np.ndarray:  # 确保目标数组存在 / Ensure target array exists
    if target_path.exists():  # 检查目标数组是否已存在 / Check whether target array exists
        return np.load(target_path).astype(bool)  # 读取目标数组 / Load target array
    image_size = int(config["nodal_extraction"]["image_size"])  # 读取图像尺寸 / Read image size
    line_width = int(config["nodal_extraction"]["target_line_width_px"])  # 读取目标线宽 / Read target line width
    center_radius_px = int(image_size * float(config["project"]["center_clamp_radius_mm"]) / float(config["project"]["plate_length_mm"])) if config["nodal_extraction"].get("remove_center_region", True) else None  # 计算中心移除半径 / Compute centre-removal radius
    return preprocess_target(config["paths"]["target_pattern"], output_size=image_size, line_width_px=line_width, center_radius_px=center_radius_px, output_dir=target_path.parent, target_mode=str(config["nodal_extraction"].get("target_mode", "chladni")))  # 预处理并返回目标 / Preprocess and return target


def default_band_radii(config: dict, target_radius_px: float, side_radius_px: float) -> tuple[float, float]:  # 解析默认带宽 / Resolve default band radii
    line_width = float(config["nodal_extraction"].get("target_line_width_px", 8))  # 读取目标线宽 / Read target line width
    target_radius = float(target_radius_px) if target_radius_px > 0.0 else max(4.0, 0.75 * line_width)  # 设置目标半径 / Set target radius
    side_radius = float(side_radius_px) if side_radius_px > 0.0 else max(target_radius + 4.0, 2.6 * line_width)  # 设置侧带半径 / Set side radius
    return target_radius, side_radius  # 返回半径 / Return radii


def default_background_thickness(config: dict, override: float) -> float:  # 解析背景厚度 / Resolve background thickness
    if override > 0.0:  # 检查是否指定背景厚度 / Check explicit background thickness
        return float(override)  # 返回指定值 / Return explicit value
    low = float(config["thickness"].get("min_mm", min(config["thickness"]["levels_mm"])))  # 读取最小厚度 / Read minimum thickness
    high = float(config["thickness"].get("max_mm", max(config["thickness"]["levels_mm"])))  # 读取最大厚度 / Read maximum thickness
    return round(0.5 * (low + high), 3)  # 返回中间背景厚度 / Return middle background thickness


def reset_output_dir(path: Path, overwrite: bool) -> None:  # 准备输出目录 / Prepare output directory
    if path.exists() and not overwrite:  # 检查已存在且不覆盖 / Check existing path without overwrite
        raise FileExistsError(f"Candidate already exists: {path}")  # 抛出保护错误 / Raise protective error
    if path.exists():  # 检查是否需要删除旧目录 / Check whether old directory should be removed
        shutil.rmtree(path)  # 删除旧目录 / Remove old directory
    path.mkdir(parents=True, exist_ok=True)  # 创建新目录 / Create new directory


def save_matrix_csv(path: Path, matrix: np.ndarray, fmt: str) -> None:  # 保存矩阵 CSV / Save matrix CSV
    np.savetxt(path, matrix, delimiter=",", fmt=fmt)  # 写入 CSV / Write CSV


def save_tags_candidate(candidate_dir: Path, H: np.ndarray, bands: dict[str, np.ndarray], metadata: dict, config: dict, overwrite: bool) -> dict:  # 保存一个 TAGS 候选 / Save one TAGS candidate
    reset_output_dir(candidate_dir, overwrite)  # 准备候选目录 / Prepare candidate directory
    save_matrix_csv(candidate_dir / "H.csv", H, "%.3f")  # 保存厚度矩阵 / Save thickness matrix
    save_matrix_csv(candidate_dir / "density_scale.csv", np.ones_like(H), "%.4f")  # 保存单位密度倍率 / Save neutral density scale
    save_matrix_csv(candidate_dir / "loss_factor.csv", np.zeros_like(H), "%.5f")  # 保存零损耗场 / Save neutral loss field
    save_matrix_csv(candidate_dir / "tags_target_band.csv", bands["target"], "%.6f")  # 保存目标带诊断图 / Save target-band diagnostic map
    save_matrix_csv(candidate_dir / "tags_side_band.csv", bands["side"], "%.6f")  # 保存侧带诊断图 / Save side-band diagnostic map
    with (candidate_dir / "metadata.json").open("w", encoding="utf-8") as file_obj:  # 打开元数据文件 / Open metadata file
        json.dump(metadata, file_obj, indent=2, ensure_ascii=False)  # 写入元数据 / Write metadata
    export_candidate_for_comsol(candidate_dir, config.get("material"), config)  # 导出 COMSOL 参数合同 / Export COMSOL parameter contract
    preview_path = render_candidate_preview(candidate_dir)  # 生成厚度预览 / Render thickness preview
    return {"candidate_id": candidate_dir.name, "path": str(candidate_dir), "preview": str(preview_path), "min_thickness_mm": float(np.min(H)), "max_thickness_mm": float(np.max(H)), "mean_thickness_mm": float(np.mean(H))}  # 返回摘要 / Return summary


def main() -> None:  # 脚本入口 / Script entry point
    args = build_parser().parse_args()  # 解析命令行参数 / Parse command-line arguments
    config = load_config(args.config)  # 读取项目配置 / Load project config
    grid_size = int(config["project"]["grid_size"])  # 读取厚度网格尺寸 / Read thickness grid size
    low_mm = float(config["thickness"].get("min_mm", min(config["thickness"]["levels_mm"])))  # 读取最小厚度 / Read minimum thickness
    high_mm = float(config["thickness"].get("max_mm", max(config["thickness"]["levels_mm"])))  # 读取最大厚度 / Read maximum thickness
    center_mm = float(config["thickness"]["default_mm"])  # 读取中心固定厚度 / Read centre fixed thickness
    max_diff_mm = float(config["thickness"]["max_neighbor_difference_mm"])  # 读取相邻厚度差约束 / Read neighbour thickness-difference constraint
    target = ensure_processed_target(config, processed_target_path(config, args.target_npy))  # 读取或生成目标数组 / Load or create target array
    target_radius, side_radius = default_band_radii(config, args.target_radius_px, args.side_radius_px)  # 解析 TAGS 带宽 / Resolve TAGS band radii
    background_mm = default_background_thickness(config, args.background_mm)  # 解析背景厚度 / Resolve background thickness
    bands = build_tags_bands(target, grid_size, target_radius, side_radius)  # 构建目标带和侧带 / Build target and side bands
    cases = build_default_tags_cases(low_mm, high_mm, background_mm)  # 构建默认 A/B/C 案例 / Build default A/B/C cases
    output_root = Path(args.output_root) if args.output_root else Path(config["paths"]["candidates_dir"])  # 解析输出根目录 / Resolve output root
    summaries = []  # 创建摘要列表 / Create summary list
    for case in cases:  # 遍历 TAGS 案例 / Iterate TAGS cases
        H = generate_tags_thickness_matrix(bands, case, background_mm, low_mm, high_mm, center_mm, max_diff_mm)  # 生成厚度矩阵 / Generate thickness matrix
        candidate_dir = output_root / f"{args.prefix}_{case.name}"  # 构造候选目录 / Build candidate directory
        metadata = {"candidate_id": candidate_dir.name, "created_by": "target_aligned_passive_geometry", "tags_case": case.name, "tags_description": case.description, "tags_target_radius_px": target_radius, "tags_side_radius_px": side_radius, "tags_background_mm": background_mm, "thickness_mode": "continuous", "grid_size": grid_size, "center_fixed": True, "python_role": "geometry_generation_only_comsol_is_physics_feedback", "auxiliary_fields": ["density_scale", "loss_factor"]}  # 构造元数据 / Build metadata
        summaries.append(save_tags_candidate(candidate_dir, H, bands, metadata, config, bool(args.overwrite)))  # 保存候选并记录摘要 / Save candidate and record summary
    print(json.dumps({"generated": summaries, "target_radius_px": target_radius, "side_radius_px": side_radius, "background_mm": background_mm}, indent=2, ensure_ascii=False))  # 打印生成摘要 / Print generation summary


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行入口 / Run entry point
