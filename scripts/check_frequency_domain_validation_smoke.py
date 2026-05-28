from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 写入工具 / Import CSV writing utilities
import os  # 导入环境变量工具 / Import environment-variable utilities
import tempfile  # 导入临时目录工具 / Import temporary-directory helper
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

os.environ.setdefault("MPLCONFIGDIR", str((Path("reports") / ".matplotlib").resolve()))  # 设置可写 Matplotlib 缓存目录 / Set writable Matplotlib cache directory

from src.frequency_domain.load_frequency_response import load_frequency_response  # 导入频域响应读取器 / Import frequency-response loader
from src.scoring.amplitude_valley_score import rank_frequency_responses  # 导入多频率排序 / Import multi-frequency ranking
from src.scoring.amplitude_valley_score import score_amplitude_valley  # 导入振幅谷线评分 / Import amplitude-valley scoring
from src.target.target_bands import build_target_bands_from_binary  # 导入目标 band 构造 / Import target-band builder


def make_target(size: int = 48) -> dict[str, np.ndarray]:  # 构造合成目标数据 / Build synthetic target data
    target = np.zeros((size, size), dtype=bool)  # 创建空目标图 / Create empty target map
    target[8:-8, size // 2] = True  # 绘制竖线目标 / Draw vertical target line
    return build_target_bands_from_binary(target, size, {"target_band_radius_px": 2, "side_band_inner_radius_px": 4, "side_band_outer_radius_px": 8})  # 返回目标 band 数据 / Return target band data


def amplitude_with_target_valley(target_data: dict[str, np.ndarray], off_target: bool = False) -> np.ndarray:  # 构造目标低谷振幅图 / Build amplitude map with target valley
    amp = np.ones(target_data["target_band"].shape, dtype=np.float32)  # 创建高振幅背景 / Create high-amplitude background
    amp[target_data["target_band"].astype(bool)] = 0.02  # 目标带设低振幅 / Set target band low
    if off_target:  # 检查是否添加错误低谷 / Check whether to add false valley
        amp[2:12, 2:12] = 0.02  # 添加远离目标的低振幅块 / Add off-target low-amplitude block
    return amp  # 返回振幅图 / Return amplitude map


def test_scoring_contrast() -> None:  # 测试目标低、侧带高时分数更高 / Test high score when target low and side high
    target_data = make_target()  # 构造目标数据 / Build target data
    good = score_amplitude_valley(amplitude_with_target_valley(target_data), target_data["target_band"], target_data["side_band"], target_data["distance_to_target"])  # 评分好响应 / Score good response
    flat = score_amplitude_valley(np.ones_like(target_data["distance_to_target"], dtype=np.float32), target_data["target_band"], target_data["side_band"], target_data["distance_to_target"])  # 评分全图均匀响应 / Score uniform response
    assert float(good["valley_contrast"]) > 3.0  # 确认谷线对比强 / Ensure strong valley contrast
    assert float(good["final_amplitude_valley_score"]) > float(flat["final_amplitude_valley_score"])  # 确认好响应分数更高 / Ensure good response scores higher


def test_extra_valley_penalty() -> None:  # 测试目标外低谷惩罚升高 / Test off-target valley penalty increases
    target_data = make_target()  # 构造目标数据 / Build target data
    clean = score_amplitude_valley(amplitude_with_target_valley(target_data), target_data["target_band"], target_data["side_band"], target_data["distance_to_target"])  # 评分干净低谷 / Score clean valley
    noisy = score_amplitude_valley(amplitude_with_target_valley(target_data, True), target_data["target_band"], target_data["side_band"], target_data["distance_to_target"])  # 评分错误低谷 / Score off-target valley
    assert float(noisy["extra_valley_penalty"]) > float(clean["extra_valley_penalty"])  # 确认额外低谷惩罚变大 / Ensure extra penalty increases


def write_combined_csv(path: Path, target_data: dict[str, np.ndarray]) -> None:  # 写合成统一 CSV / Write synthetic combined CSV
    yy, xx = np.indices(target_data["target_band"].shape)  # 创建像素坐标 / Build pixel coordinates
    responses = {100.0: np.ones(target_data["target_band"].shape, dtype=np.float32), 120.0: amplitude_with_target_valley(target_data)}  # 创建两频率响应 / Create two-frequency responses
    with path.open("w", encoding="utf-8", newline="") as file_obj:  # 打开 CSV / Open CSV
        writer = csv.writer(file_obj)  # 创建写入器 / Create writer
        writer.writerow(["frequency_hz", "x", "y", "real_uz", "imag_uz"])  # 写入表头 / Write header
        for frequency, amp in responses.items():  # 遍历频率响应 / Iterate frequency responses
            for row, col in zip(yy.ravel(), xx.ravel()):  # 遍历网格点 / Iterate grid points
                value = float(amp[int(row), int(col)])  # 读取振幅值 / Read amplitude value
                writer.writerow([frequency, float(col), float(row), value, 0.0])  # 写入实虚部 / Write real and imaginary values


def write_per_frequency_csv(path: Path, target_data: dict[str, np.ndarray]) -> None:  # 写合成单频 CSV / Write synthetic per-frequency CSV
    yy, xx = np.indices(target_data["target_band"].shape)  # 创建像素坐标 / Build pixel coordinates
    amp = amplitude_with_target_valley(target_data)  # 构造目标低谷响应 / Build target-valley response
    with path.open("w", encoding="utf-8", newline="") as file_obj:  # 打开 CSV / Open CSV
        writer = csv.writer(file_obj)  # 创建写入器 / Create writer
        writer.writerow(["x", "y", "abs_uz"])  # 写入表头 / Write header
        for row, col in zip(yy.ravel(), xx.ravel()):  # 遍历网格点 / Iterate grid points
            writer.writerow([float(col), float(row), float(amp[int(row), int(col)])])  # 写入振幅 / Write amplitude


def test_loader_and_ranking() -> None:  # 测试读取器和排序 / Test loader and ranking
    target_data = make_target()  # 构造目标数据 / Build target data
    with tempfile.TemporaryDirectory() as tmp:  # 创建临时目录 / Create temporary directory
        root = Path(tmp)  # 转换临时路径 / Convert temporary path
        combined = root / "frequency_response.csv"  # 构造统一文件路径 / Build combined-file path
        write_combined_csv(combined, target_data)  # 写统一 CSV / Write combined CSV
        responses, metadata = load_frequency_response(combined, 48)  # 读取统一文件 / Load combined file
        ranked = rank_frequency_responses(responses, target_data)  # 频率排序 / Rank frequencies
        assert metadata["detected_format"] == "combined_csv"  # 确认格式识别 / Ensure format detection
        assert float(ranked[0]["frequency_hz"]) == 120.0  # 确认选中目标低谷频率 / Ensure best target-valley frequency wins
        per_dir = root / "per_frequency"  # 构造单频目录 / Build per-frequency directory
        per_dir.mkdir()  # 创建单频目录 / Create per-frequency directory
        write_per_frequency_csv(per_dir / "freq_301p1.csv", target_data)  # 写单频文件 / Write per-frequency file
        per_responses, per_metadata = load_frequency_response(per_dir, 48)  # 读取单频目录 / Load per-frequency directory
        assert 301.1 in per_responses  # 确认文件名频率解析 / Ensure filename frequency parsing
        assert per_metadata["detected_format"] == "per_frequency_csv"  # 确认单频格式识别 / Ensure per-frequency format detection


def main() -> None:  # 主入口 / Main entry point
    test_scoring_contrast()  # 运行对比评分测试 / Run contrast scoring test
    test_extra_valley_penalty()  # 运行额外低谷测试 / Run extra-valley test
    test_loader_and_ranking()  # 运行读取与排序测试 / Run loading and ranking test
    print("Frequency-domain validation smoke tests passed. / 频域验证烟测通过。")  # 打印通过信息 / Print success message


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
