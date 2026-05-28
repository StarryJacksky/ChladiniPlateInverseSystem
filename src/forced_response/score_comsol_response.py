from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
import json  # 导入 JSON 工具 / Import JSON utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.comsol.import_results import interpolate_to_grid  # 导入散点插值函数 / Import scattered interpolation helper
from src.forced_response.predict_response import response_preview  # 导入强迫响应预览函数 / Import forced-response preview helper
from src.forced_response.predict_response import score_amplitude_valley  # 导入振幅谷线评分函数 / Import amplitude-valley scoring helper


def load_forced_response_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:  # 读取 COMSOL 强迫响应 CSV / Load COMSOL forced-response CSV
    xs = []  # 创建 x 坐标列表 / Create x-coordinate list
    ys = []  # 创建 y 坐标列表 / Create y-coordinate list
    real_values = []  # 创建实部列表 / Create real-value list
    imag_values = []  # 创建虚部列表 / Create imaginary-value list
    abs_values = []  # 创建振幅列表 / Create amplitude list
    with Path(path).open("r", encoding="utf-8") as file_obj:  # 打开响应 CSV / Open response CSV
        reader = csv.DictReader(file_obj)  # 创建字典读取器 / Create dictionary reader
        for row in reader:  # 遍历响应行 / Iterate response rows
            xs.append(float(row["x"]))  # 读取 x 坐标 / Read x coordinate
            ys.append(float(row["y"]))  # 读取 y 坐标 / Read y coordinate
            real_values.append(float(row["w_real"]))  # 读取实部 / Read real component
            imag_values.append(float(row["w_imag"]))  # 读取虚部 / Read imaginary component
            abs_values.append(float(row["w_abs"]))  # 读取振幅 / Read amplitude
    return np.asarray(xs), np.asarray(ys), np.asarray(real_values), np.asarray(imag_values), np.asarray(abs_values)  # 返回全部列 / Return all columns


def normalise_amplitude(amplitude: np.ndarray) -> np.ndarray:  # 归一化振幅场 / Normalise amplitude field
    max_value = float(np.nanmax(np.abs(amplitude))) if amplitude.size else 0.0  # 计算最大振幅 / Compute maximum amplitude
    if max_value <= 0.0:  # 检查是否全零 / Check whether all values are zero
        return np.zeros_like(amplitude, dtype=np.float32)  # 返回零振幅场 / Return zero amplitude field
    return (amplitude.astype(np.float32) / max_value).astype(np.float32)  # 返回归一化振幅 / Return normalised amplitude


def score_comsol_forced_response(response_csv: str | Path, target_binary: np.ndarray, output_dir: str | Path, image_size: int = 160, epsilon: float = 0.080, center_radius_px: int = 0) -> dict[str, object]:  # 评分真实 COMSOL 强迫响应 / Score real COMSOL forced response
    x, y, w_real, w_imag, w_abs = load_forced_response_csv(response_csv)  # 读取响应散点 / Load response samples
    real_grid = interpolate_to_grid(x, y, w_real, image_size)  # 插值实部到规则网格 / Interpolate real component to grid
    imag_grid = interpolate_to_grid(x, y, w_imag, image_size)  # 插值虚部到规则网格 / Interpolate imaginary component to grid
    abs_grid = interpolate_to_grid(x, y, w_abs, image_size)  # 插值振幅到规则网格 / Interpolate amplitude to grid
    amplitude = normalise_amplitude(abs_grid)  # 归一化振幅场 / Normalise amplitude field
    valley, metrics = score_amplitude_valley(amplitude, target_binary, epsilon, center_radius_px)  # 评分低振幅谷线 / Score low-amplitude valley
    out_dir = Path(output_dir)  # 转换输出目录 / Convert output directory
    out_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    np.save(out_dir / "comsol_forced_real_grid.npy", real_grid.astype(np.float32))  # 保存实部网格 / Save real grid
    np.save(out_dir / "comsol_forced_imag_grid.npy", imag_grid.astype(np.float32))  # 保存虚部网格 / Save imaginary grid
    np.save(out_dir / "comsol_forced_amplitude.npy", amplitude.astype(np.float32))  # 保存振幅网格 / Save amplitude grid
    np.save(out_dir / "comsol_forced_valley.npy", valley.astype(np.uint8))  # 保存谷线二值图 / Save valley binary map
    response_preview(out_dir / "comsol_forced_response_preview.png", target_binary, amplitude, valley)  # 保存预览图 / Save preview image
    stats = {"sample_count": int(len(w_abs)), "max_abs": float(np.nanmax(w_abs)) if len(w_abs) else 0.0, "mean_abs": float(np.nanmean(w_abs)) if len(w_abs) else 0.0, "nonzero_count": int(np.count_nonzero(np.abs(w_abs) > 1.0e-18))}  # 统计响应幅值 / Summarise response amplitude
    summary = {"response_csv": str(response_csv), "image_size": int(image_size), "epsilon": float(epsilon), "center_radius_px": int(center_radius_px), "stats": stats, "metrics": metrics}  # 构造摘要 / Build summary
    (out_dir / "comsol_forced_response_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")  # 写入摘要 JSON / Write summary JSON
    return summary  # 返回摘要 / Return summary
