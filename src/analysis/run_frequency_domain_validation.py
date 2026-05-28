from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析工具 / Import command-line parsing utilities
import csv  # 导入 CSV 写入工具 / Import CSV writing utilities
import os  # 导入环境变量工具 / Import environment-variable utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library
from PIL import Image  # 导入图像保存工具 / Import image saving helper
from PIL import ImageDraw  # 导入绘图工具 / Import drawing helper

os.environ.setdefault("MPLCONFIGDIR", str((Path("reports") / ".matplotlib").resolve()))  # 设置可写 Matplotlib 缓存目录 / Set writable Matplotlib cache directory

from src.frequency_domain.load_frequency_response import load_frequency_response  # 导入频域导出读取器 / Import frequency-domain export loader
from src.scoring.amplitude_valley_score import rank_frequency_responses  # 导入多频率排序 / Import multi-frequency ranking
from src.scoring.amplitude_valley_score import score_amplitude_valley  # 导入振幅谷线评分 / Import amplitude-valley scoring
from src.target.target_bands import build_target_bands  # 导入目标 band 构造 / Import target-band builder
from src.target.target_bands import save_band_overlay  # 导入 band 叠加图输出 / Import band-overlay writer


DEFAULT_TARGETS = (Path("data/processed_targets/target_binary.npy"), Path("data/processed_targets/target_preview.png"), Path("data/target_patterns/ic_target.png"))  # 定义目标自动检测路径 / Define target auto-detection paths


def build_parser() -> argparse.ArgumentParser:  # 构造命令行解析器 / Build command-line parser
    parser = argparse.ArgumentParser(description="Validate COMSOL frequency-domain response with amplitude-valley scoring. / 使用振幅谷线评分验证 COMSOL 频域响应。")  # 创建解析器 / Create parser
    parser.add_argument("--case", default="tags_ic_case_a_target_thick")  # 添加案例名参数 / Add case-name argument
    parser.add_argument("--export-path", default="data/comsol_frequency_exports/tags_ic_case_a_target_thick")  # 添加导出路径参数 / Add export-path argument
    parser.add_argument("--target", default="")  # 添加目标路径参数 / Add target path argument
    parser.add_argument("--output-dir", default="reports/frequency_domain_validation/tags_ic_case_a_target_thick")  # 添加输出目录参数 / Add output-dir argument
    parser.add_argument("--grid-size", type=int, default=256)  # 添加网格尺寸参数 / Add grid-size argument
    parser.add_argument("--target-band-radius-px", type=int, default=2)  # 添加目标带半径参数 / Add target-band radius argument
    parser.add_argument("--side-band-inner-radius-px", type=int, default=4)  # 添加侧带内半径参数 / Add side-band inner radius argument
    parser.add_argument("--side-band-outer-radius-px", type=int, default=10)  # 添加侧带外半径参数 / Add side-band outer radius argument
    parser.add_argument("--center-mask-radius-px", type=int, default=0)  # 添加中心掩膜半径参数 / Add centre-mask radius argument
    parser.add_argument("--epsilon", type=float, default=0.080)  # 添加低振幅阈值参数 / Add low-amplitude threshold argument
    parser.add_argument("--strong-contrast", type=float, default=3.0)  # 添加强可行对比阈值 / Add strong-contrast threshold
    parser.add_argument("--good-contrast", type=float, default=2.0)  # 添加较好对比阈值 / Add good-contrast threshold
    parser.add_argument("--weak-contrast", type=float, default=1.5)  # 添加弱可行对比阈值 / Add weak-contrast threshold
    parser.add_argument("--max-extra-penalty", type=float, default=0.32)  # 添加额外低谷惩罚上限 / Add extra-valley penalty limit
    return parser  # 返回解析器 / Return parser


def resolve_target_path(user_path: str) -> Path:  # 自动解析目标路径 / Resolve target path automatically
    if user_path:  # 检查用户是否传入路径 / Check user-provided path
        requested = Path(user_path)  # 转换用户路径 / Convert requested path
        if requested.exists():  # 检查路径是否存在 / Check path existence
            return requested  # 返回用户路径 / Return requested path
    for candidate in DEFAULT_TARGETS:  # 遍历默认目标路径 / Iterate default target paths
        if candidate.exists():  # 检查默认目标是否存在 / Check default target existence
            return candidate  # 返回默认目标 / Return default target
    raise FileNotFoundError("No target file found. Pass --target data/processed_targets/target_binary.npy or an image path. / 未找到目标文件，请传入 --target data/processed_targets/target_binary.npy 或图片路径。")  # 抛出目标缺失 / Raise missing target error


def csv_safe_row(row: dict[str, object]) -> dict[str, object]:  # 移除不适合 CSV 的数组字段 / Remove array fields unsuitable for CSV
    return {key: value for key, value in row.items() if not isinstance(value, np.ndarray) and key not in {"bands", "hard_valley", "soft_valley"}}  # 返回 CSV 安全字典 / Return CSV-safe dictionary


def write_scores_csv(path: str | Path, rows: list[dict[str, object]]) -> None:  # 写出评分 CSV / Write score CSV
    output = Path(path)  # 转换输出路径 / Convert output path
    output.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    fieldnames = ["frequency_hz", "target_mean_amplitude", "target_median_amplitude", "side_mean_amplitude", "side_median_amplitude", "valley_contrast", "median_valley_contrast", "contrast_margin", "median_contrast_margin", "extra_valley_penalty", "iou", "dice", "layout", "chamfer", "final_amplitude_valley_score"]  # 定义 CSV 列 / Define CSV columns
    with output.open("w", encoding="utf-8", newline="") as file_obj:  # 打开输出文件 / Open output file
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)  # 创建 CSV 写入器 / Create CSV writer
        writer.writeheader()  # 写入表头 / Write header
        for row in rows:  # 遍历评分行 / Iterate score rows
            writer.writerow({key: csv_safe_row(row).get(key, "") for key in fieldnames})  # 写入一行 / Write one row


def amplitude_to_rgb(amplitude: np.ndarray) -> np.ndarray:  # 将振幅图转成 RGB 预览 / Convert amplitude map into RGB preview
    amp = np.asarray(amplitude, dtype=np.float32)  # 转换振幅数组 / Convert amplitude array
    gray = np.uint8(np.clip(1.0 - amp, 0.0, 1.0) * 255.0)  # 低振幅显示更亮 / Show low amplitude brighter
    return np.repeat(gray[:, :, None], 3, axis=2)  # 扩展为 RGB / Expand to RGB


def save_frequency_preview(path: str | Path, amplitude: np.ndarray, target_data: dict[str, np.ndarray], title: str = "") -> None:  # 保存单频响应预览 / Save one frequency-response preview
    panel = amplitude_to_rgb(amplitude)  # 生成振幅面板 / Build amplitude panel
    target_band = target_data["target_band"].astype(bool)  # 读取目标带 / Read target band
    side_band = target_data["side_band"].astype(bool)  # 读取侧带 / Read side band
    panel[side_band] = (0.65 * panel[side_band] + 0.35 * np.asarray([70, 140, 210])).astype(np.uint8)  # 叠加侧带蓝色 / Blend side band blue
    panel[target_band] = (0.50 * panel[target_band] + 0.50 * np.asarray([230, 80, 60])).astype(np.uint8)  # 叠加目标带红色 / Blend target band red
    image = Image.fromarray(panel)  # 转为 PIL 图 / Convert to PIL image
    if title:  # 检查是否有标题 / Check title
        canvas = Image.new("RGB", (image.width, image.height + 24), (248, 248, 246))  # 创建带标题画布 / Create titled canvas
        canvas.paste(image, (0, 24))  # 粘贴图像 / Paste image
        ImageDraw.Draw(canvas).text((6, 5), title, fill=(20, 24, 24))  # 绘制标题 / Draw title
        image = canvas  # 使用带标题图 / Use titled image
    output = Path(path)  # 转换输出路径 / Convert output path
    output.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    image.save(output)  # 保存图像 / Save image


def frequency_token(frequency_hz: float) -> str:  # 将频率转为安全文件名片段 / Convert frequency into safe filename token
    return f"{float(frequency_hz):.3f}".rstrip("0").rstrip(".").replace(".", "p")  # 生成文件名安全字符串 / Build filename-safe string


def mask_panel(mask: np.ndarray, color: tuple[int, int, int], label: str) -> Image.Image:  # 生成单一掩膜面板 / Build a single-mask panel
    mask_bool = np.asarray(mask).astype(bool)  # 转换为布尔掩膜 / Convert to boolean mask
    panel = np.full((mask_bool.shape[0], mask_bool.shape[1], 3), 248, dtype=np.uint8)  # 创建浅色底图 / Create pale background
    panel[mask_bool] = np.asarray(color, dtype=np.uint8)  # 绘制掩膜颜色 / Paint mask color
    image = Image.fromarray(panel).resize((190, 190), Image.Resampling.NEAREST)  # 放大面板并保持块状边界 / Resize panel with nearest sampling
    canvas = Image.new("RGB", (190, 220), (248, 248, 246))  # 创建带标题画布 / Create titled canvas
    canvas.paste(image, (0, 28))  # 粘贴面板 / Paste panel
    ImageDraw.Draw(canvas).text((8, 7), label, fill=(20, 24, 24))  # 绘制标签 / Draw label
    return canvas  # 返回面板 / Return panel


def overlay_panel(target_band: np.ndarray, valley_mask: np.ndarray, label: str) -> Image.Image:  # 生成目标与波谷叠加面板 / Build target-valley overlay panel
    target = np.asarray(target_band).astype(bool)  # 转换目标掩膜 / Convert target mask
    valley = np.asarray(valley_mask).astype(bool)  # 转换波谷掩膜 / Convert valley mask
    overlay = np.full((target.shape[0], target.shape[1], 3), 248, dtype=np.uint8)  # 创建浅色底图 / Create pale background
    overlay[target] = np.asarray([232, 84, 61], dtype=np.uint8)  # 绘制目标红色 / Paint target red
    overlay[valley] = np.asarray([43, 129, 177], dtype=np.uint8)  # 绘制波谷蓝色 / Paint valley blue
    overlay[target & valley] = np.asarray([51, 154, 98], dtype=np.uint8)  # 绘制重合绿色 / Paint overlap green
    image = Image.fromarray(overlay).resize((190, 190), Image.Resampling.NEAREST)  # 放大叠加图 / Resize overlay
    canvas = Image.new("RGB", (190, 220), (248, 248, 246))  # 创建带标题画布 / Create titled canvas
    canvas.paste(image, (0, 28))  # 粘贴叠加图 / Paste overlay
    ImageDraw.Draw(canvas).text((8, 7), label, fill=(20, 24, 24))  # 绘制标签 / Draw label
    return canvas  # 返回叠加面板 / Return overlay panel


def visual_valley_core(amplitude: np.ndarray, target_band: np.ndarray, config: dict[str, float]) -> np.ndarray:  # 提取示意图用低振幅核心区 / Extract low-amplitude core for schematic display
    amp = np.asarray(amplitude, dtype=np.float32)  # 转换振幅图 / Convert amplitude map
    target_fraction = float(np.mean(np.asarray(target_band).astype(bool)))  # 计算目标面积比例 / Compute target area fraction
    multiplier = float(config.get("visual_valley_area_multiplier", 2.2))  # 读取可视化面积倍率 / Read visual area multiplier
    min_quantile = float(config.get("visual_valley_min_quantile", 0.025))  # 读取最小分位数 / Read minimum quantile
    max_quantile = float(config.get("visual_valley_max_quantile", 0.120))  # 读取最大分位数 / Read maximum quantile
    quantile = min(max(target_fraction * multiplier, min_quantile), max_quantile)  # 计算自适应低振幅分位数 / Compute adaptive low-amplitude quantile
    threshold = float(np.quantile(amp, quantile))  # 计算低振幅核心阈值 / Compute low-amplitude core threshold
    return (amp <= threshold).astype(bool)  # 返回低振幅核心掩膜 / Return low-amplitude core mask


def save_valley_schematic(path: str | Path, frequency_hz: float, amplitude: np.ndarray, target_data: dict[str, np.ndarray], config: dict[str, float]) -> dict[str, object]:  # 保存单频波谷三联示意图 / Save one frequency valley triptych
    score = score_amplitude_valley(amplitude, target_data["target_band"], target_data["side_band"], target_data.get("distance_to_target"), config)  # 重新计算含硬波谷的评分 / Recompute score with hard valley mask
    target = target_data["target_band"].astype(bool)  # 读取目标带 / Read target band
    valley = visual_valley_core(amplitude, target, config)  # 提取可读低振幅核心 / Extract readable low-amplitude core
    score["visual_valley"] = valley  # 保存示意图波谷掩膜 / Store schematic valley mask
    target_image = mask_panel(target, (232, 84, 61), "Target / 目标")  # 生成目标面板 / Build target panel
    valley_image = mask_panel(valley, (43, 129, 177), f"Valley core {frequency_hz:.1f} Hz / 波谷核心")  # 生成波谷面板 / Build valley panel
    overlay_image = overlay_panel(target, valley, "Overlay / 重合")  # 生成叠加面板 / Build overlay panel
    legend = Image.new("RGB", (570, 34), (248, 248, 246))  # 创建图例画布 / Create legend canvas
    draw = ImageDraw.Draw(legend)  # 创建绘图对象 / Create drawing object
    draw.rectangle((10, 10, 24, 24), fill=(232, 84, 61))  # 绘制目标图例色块 / Draw target legend swatch
    draw.text((30, 9), "target / 目标", fill=(30, 35, 35))  # 绘制目标图例文字 / Draw target legend text
    draw.rectangle((150, 10, 164, 24), fill=(43, 129, 177))  # 绘制波谷图例色块 / Draw valley legend swatch
    draw.text((170, 9), "low-amplitude valley / 低振幅波谷", fill=(30, 35, 35))  # 绘制波谷图例文字 / Draw valley legend text
    draw.rectangle((390, 10, 404, 24), fill=(51, 154, 98))  # 绘制重合图例色块 / Draw overlap legend swatch
    draw.text((410, 9), "overlap / 重合", fill=(30, 35, 35))  # 绘制重合图例文字 / Draw overlap legend text
    canvas = Image.new("RGB", (570, 254), (248, 248, 246))  # 创建三联总画布 / Create triptych canvas
    canvas.paste(target_image, (0, 0))  # 粘贴目标面板 / Paste target panel
    canvas.paste(valley_image, (190, 0))  # 粘贴波谷面板 / Paste valley panel
    canvas.paste(overlay_image, (380, 0))  # 粘贴叠加面板 / Paste overlay panel
    canvas.paste(legend, (0, 220))  # 粘贴图例 / Paste legend
    output = Path(path)  # 转换输出路径 / Convert output path
    output.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    canvas.save(output)  # 保存三联图 / Save triptych
    return score  # 返回评分数据 / Return score data


def compact_overlay_card(frequency_hz: float, row: dict[str, object], valley_mask: np.ndarray, target_band: np.ndarray) -> Image.Image:  # 生成总览里的紧凑叠加卡片 / Build compact overlay card for montage
    card = overlay_panel(target_band, valley_mask, f"{frequency_hz:.1f} Hz")  # 生成叠加卡片 / Build overlay card
    small = card.resize((150, 174), Image.Resampling.NEAREST)  # 缩小卡片 / Resize card
    draw = ImageDraw.Draw(small)  # 创建绘图对象 / Create draw object
    draw.text((8, 151), f"C {float(row['valley_contrast']):.2f}  S {float(row['final_amplitude_valley_score']):.3f}", fill=(20, 24, 24))  # 绘制指标 / Draw metrics
    return small  # 返回卡片 / Return card


def save_valley_schematic_set(output_dir: Path, ranked_rows: list[dict[str, object]], responses: dict[float, np.ndarray], target_data: dict[str, np.ndarray], config: dict[str, float]) -> None:  # 保存所有频率波谷示意图 / Save valley schematics for all frequencies
    schematic_dir = output_dir / "valley_schematics"  # 定义单频图目录 / Define per-frequency image directory
    per_frequency_scores: dict[float, dict[str, object]] = {}  # 创建单频评分缓存 / Create per-frequency score cache
    for frequency in sorted(responses):  # 按频率遍历响应 / Iterate responses by frequency
        token = frequency_token(float(frequency))  # 生成频率文件名片段 / Build frequency filename token
        score = save_valley_schematic(schematic_dir / f"freq_{token}_valley_schematic.png", float(frequency), responses[frequency], target_data, config)  # 保存单频三联图 / Save one frequency triptych
        per_frequency_scores[float(frequency)] = score  # 缓存评分 / Cache score
    if not per_frequency_scores:  # 检查是否没有频率 / Check empty scores
        return  # 无数据直接返回 / Return when no data
    frequency_rows = sorted(ranked_rows, key=lambda row: float(row["frequency_hz"]))  # 按频率排列行 / Sort rows by frequency
    frequency_cards = []  # 创建按频率卡片列表 / Create frequency-card list
    for row in frequency_rows:  # 遍历按频率排序结果 / Iterate frequency-sorted rows
        frequency = float(row["frequency_hz"])  # 读取频率 / Read frequency
        frequency_cards.append(compact_overlay_card(frequency, row, per_frequency_scores[frequency]["visual_valley"], target_data["target_band"]))  # 添加紧凑卡片 / Add compact card
    save_card_grid(output_dir / "all_frequency_valley_schematics.png", frequency_cards, "Valley schematics by frequency / 按频率排列的波谷示意图")  # 保存全频拼图 / Save all-frequency montage
    top_cards = []  # 创建前五卡片列表 / Create top-card list
    for row in ranked_rows[:5]:  # 遍历前五频率 / Iterate top five rows
        frequency = float(row["frequency_hz"])  # 读取频率 / Read frequency
        top_cards.append(compact_overlay_card(frequency, row, per_frequency_scores[frequency]["visual_valley"], target_data["target_band"]))  # 添加前五卡片 / Add top card
    save_card_grid(output_dir / "top_5_valley_schematics.png", top_cards, "Top valley schematics / 前五波谷示意图", columns=5)  # 保存前五拼图 / Save top-five montage
    if ranked_rows:  # 检查是否有最佳频率 / Check best frequency
        best_frequency = float(ranked_rows[0]["frequency_hz"])  # 读取最佳频率 / Read best frequency
        token = frequency_token(best_frequency)  # 生成最佳频率文件名片段 / Build best frequency token
        save_valley_schematic(output_dir / "best_valley_schematic.png", best_frequency, responses[best_frequency], target_data, config)  # 保存最佳三联图 / Save best triptych
        (output_dir / "best_valley_schematic_source.txt").write_text(f"valley_schematics/freq_{token}_valley_schematic.png\n", encoding="utf-8")  # 写出最佳图来源 / Write best-image source


def save_card_grid(path: str | Path, cards: list[Image.Image], title: str, columns: int = 4) -> None:  # 保存卡片网格拼图 / Save card grid montage
    if not cards:  # 检查是否没有卡片 / Check empty card list
        return  # 无卡片则返回 / Return when no cards
    column_count = max(1, int(columns))  # 规范化列数 / Normalize column count
    card_width, card_height = cards[0].size  # 读取卡片尺寸 / Read card size
    row_count = int(np.ceil(len(cards) / column_count))  # 计算行数 / Compute row count
    title_height = 36  # 设置标题高度 / Set title height
    canvas = Image.new("RGB", (card_width * column_count, title_height + card_height * row_count), (248, 248, 246))  # 创建拼图画布 / Create montage canvas
    ImageDraw.Draw(canvas).text((10, 10), title, fill=(20, 24, 24))  # 绘制标题 / Draw title
    for index, card in enumerate(cards):  # 遍历卡片 / Iterate cards
        x = (index % column_count) * card_width  # 计算 x 坐标 / Compute x coordinate
        y = title_height + (index // column_count) * card_height  # 计算 y 坐标 / Compute y coordinate
        canvas.paste(card, (x, y))  # 粘贴卡片 / Paste card
    output = Path(path)  # 转换输出路径 / Convert output path
    output.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    canvas.save(output)  # 保存拼图 / Save montage


def save_score_vs_frequency(path: str | Path, rows: list[dict[str, object]]) -> None:  # 保存分数随频率图 / Save score-vs-frequency chart
    width, height = 920, 360  # 设置画布尺寸 / Set canvas size
    image = Image.new("RGB", (width, height), (248, 248, 246))  # 创建画布 / Create canvas
    draw = ImageDraw.Draw(image)  # 创建绘图对象 / Create draw object
    draw.text((24, 18), "Amplitude-valley score vs frequency / 振幅谷线分数-频率", fill=(20, 24, 24))  # 绘制标题 / Draw title
    if rows:  # 检查是否有数据 / Check data availability
        ordered = sorted(rows, key=lambda row: float(row["frequency_hz"]))  # 按频率排序 / Sort by frequency
        freqs = [float(row["frequency_hz"]) for row in ordered]  # 读取频率 / Read frequencies
        scores = [float(row["final_amplitude_valley_score"]) for row in ordered]  # 读取分数 / Read scores
        min_f, max_f = min(freqs), max(freqs)  # 读取频率范围 / Read frequency range
        min_s, max_s = min(0.0, min(scores)), max(0.1, max(scores))  # 读取分数范围 / Read score range
        points = []  # 创建折线点列表 / Create line points
        for freq, score in zip(freqs, scores):  # 遍历频率和分数 / Iterate frequencies and scores
            x = 70 + int((freq - min_f) / max(max_f - min_f, 1.0e-12) * 810)  # 映射 x 坐标 / Map x coordinate
            y = 300 - int((score - min_s) / max(max_s - min_s, 1.0e-12) * 230)  # 映射 y 坐标 / Map y coordinate
            points.append((x, y))  # 保存点 / Store point
        draw.line((70, 300, 890, 300), fill=(160, 166, 160), width=1)  # 绘制横轴 / Draw x axis
        draw.line((70, 60, 70, 300), fill=(160, 166, 160), width=1)  # 绘制纵轴 / Draw y axis
        if len(points) >= 2:  # 检查是否可画折线 / Check line availability
            draw.line(points, fill=(38, 126, 177), width=3)  # 绘制分数折线 / Draw score line
        for point in points:  # 遍历点 / Iterate points
            draw.ellipse((point[0] - 3, point[1] - 3, point[0] + 3, point[1] + 3), fill=(214, 88, 70))  # 绘制点 / Draw point
        draw.text((70, 318), f"{min_f:.1f} Hz", fill=(70, 76, 76))  # 绘制最低频率 / Draw minimum frequency
        draw.text((810, 318), f"{max_f:.1f} Hz", fill=(70, 76, 76))  # 绘制最高频率 / Draw maximum frequency
    output = Path(path)  # 转换输出路径 / Convert output path
    output.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    image.save(output)  # 保存图表 / Save chart


def save_top_previews(path: str | Path, ranked_rows: list[dict[str, object]], responses: dict[float, np.ndarray], target_data: dict[str, np.ndarray], count: int = 5) -> None:  # 保存前五频率预览 / Save top frequency previews
    previews: list[Image.Image] = []  # 创建预览图列表 / Create preview list
    for row in ranked_rows[: int(count)]:  # 遍历前若干频率 / Iterate top frequencies
        frequency = float(row["frequency_hz"])  # 读取频率 / Read frequency
        panel = amplitude_to_rgb(responses[frequency])  # 生成振幅面板 / Build amplitude panel
        panel[target_data["target_band"].astype(bool)] = np.asarray([232, 84, 61], dtype=np.uint8)  # 叠加目标带 / Overlay target band
        image = Image.fromarray(panel).resize((180, 180))  # 缩放预览 / Resize preview
        canvas = Image.new("RGB", (180, 220), (248, 248, 246))  # 创建小画布 / Create small canvas
        canvas.paste(image, (0, 28))  # 粘贴预览 / Paste preview
        ImageDraw.Draw(canvas).text((6, 6), f"{frequency:.1f} Hz  score {float(row['final_amplitude_valley_score']):.3f}", fill=(20, 24, 24))  # 绘制标签 / Draw label
        previews.append(canvas)  # 保存小预览 / Store small preview
    if not previews:  # 检查是否没有预览 / Check empty preview list
        return  # 无数据则返回 / Return when no data
    montage = Image.new("RGB", (180 * len(previews), 220), (255, 255, 255))  # 创建拼图 / Create montage
    for index, image in enumerate(previews):  # 遍历小预览 / Iterate previews
        montage.paste(image, (180 * index, 0))  # 粘贴小预览 / Paste preview
    output = Path(path)  # 转换输出路径 / Convert output path
    output.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    montage.save(output)  # 保存拼图 / Save montage


def recommendation_from_best(best: dict[str, object], args: argparse.Namespace) -> tuple[str, bool]:  # 根据最佳频率生成建议 / Build recommendation from best frequency
    contrast = float(best.get("valley_contrast", 0.0))  # 读取对比倍率 / Read contrast ratio
    extra = float(best.get("extra_valley_penalty", 1.0))  # 读取额外低谷惩罚 / Read extra-valley penalty
    target_mean = float(best.get("target_mean_amplitude", 1.0))  # 读取目标均值 / Read target mean
    side_mean = float(best.get("side_mean_amplitude", 0.0))  # 读取侧带均值 / Read side mean
    passes = bool(contrast >= float(args.weak_contrast) and extra <= float(args.max_extra_penalty) and target_mean < side_mean)  # 判断是否通过 / Decide pass state
    if contrast >= float(args.strong_contrast) and passes:  # 检查强通过 / Check strong pass
        return "strong_frequency_domain_candidate", True  # 返回强候选 / Return strong candidate
    if contrast >= float(args.good_contrast) and passes:  # 检查较好通过 / Check good pass
        return "good_frequency_domain_candidate", True  # 返回较好候选 / Return good candidate
    if passes:  # 检查弱通过 / Check weak pass
        return "weak_frequency_domain_candidate", True  # 返回弱候选 / Return weak candidate
    return "not_ready_for_printing_redesign_tags_a_plus", False  # 返回不建议打印 / Return not ready for printing


def write_waiting_report(output_dir: Path, case_name: str, export_path: Path, target_path: Path) -> None:  # 写等待 COMSOL 导出报告 / Write waiting-for-COMSOL-export report
    output_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录 / Create output directory
    lines = ["# Frequency Domain Validation Waiting For COMSOL Export / 频域验证等待 COMSOL 导出", "", f"Case / 案例：`{case_name}`", "", f"Expected export path / 期望导出路径：`{export_path}`", "", f"Target / 目标：`{target_path}`", "", "No frequency-domain CSV was found, so no physical result has been computed. This script did not use eigenmodes or Python free modal combinations as a substitute.", "", "未找到 frequency-domain CSV，因此没有计算任何物理频域结论。本脚本没有用 eigenmode 或 Python 自由模态组合冒充频域结果。", "", "Please export either:", "", "```text", "frequency_response.csv with columns frequency_hz,x,y,abs_uz", "```", "", "or:", "", "```text", "freq_301p1.csv with columns x,y,real_uz,imag_uz", "```"]  # 构造等待报告行 / Build waiting-report lines
    text = "\n".join(lines) + "\n"  # 合成等待报告文本 / Compose waiting-report text
    (output_dir / "frequency_domain_validation_summary.md").write_text(text, encoding="utf-8")  # 写入等待报告 / Write waiting report


def write_summary(path: str | Path, args: argparse.Namespace, target_path: Path, export_path: Path, ranked_rows: list[dict[str, object]], metadata: dict[str, object], recommendation: str, passes: bool) -> None:  # 写频域验证报告 / Write frequency-domain validation report
    best = ranked_rows[0] if ranked_rows else {}  # 读取最佳行 / Read best row
    freqs = [float(row["frequency_hz"]) for row in ranked_rows]  # 读取频率列表 / Read frequencies
    lines: list[str] = []  # 创建报告行 / Create report lines
    lines.append("# Frequency Domain Validation Summary / 频域验证总结")  # 写标题 / Write title
    lines.append("")  # 空行 / Blank line
    lines.append("## Purpose / 研究目的")  # 写小节 / Write section
    lines.append("")  # 空行 / Blank line
    lines.append("验证 A / target thick 是否能在单中心激励 frequency-domain 下形成 IC-like low-amplitude valley。")  # 写目的 / Write purpose
    lines.append("")  # 空行 / Blank line
    lines.append("## Input / 输入信息")  # 写小节 / Write section
    lines.append("")  # 空行 / Blank line
    lines.append(f"- Case: `{args.case}`")  # 写案例名 / Write case name
    lines.append(f"- Target: `{target_path}`")  # 写目标路径 / Write target path
    lines.append(f"- COMSOL export path: `{export_path}`")  # 写导出路径 / Write export path
    lines.append(f"- Frequency samples: `{len(ranked_rows)}`")  # 写频率样本数 / Write frequency sample count
    lines.append(f"- Frequency range: `{min(freqs):.3f}-{max(freqs):.3f} Hz`" if freqs else "- Frequency range: unavailable")  # 写频率范围 / Write frequency range
    lines.append(f"- Detected export format: `{metadata.get('detected_format', '')}`")  # 写格式 / Write detected format
    lines.append("")  # 空行 / Blank line
    lines.append("## Method / 方法")  # 写小节 / Write section
    lines.append("")  # 空行 / Blank line
    lines.append("后处理使用振幅图 `A(x,y)=|u_z(x,y,ω)|`。目标线扩展为 target band，目标两侧构造 side band。评分奖励 target band 上低振幅、side band 上相对高振幅，并惩罚远离目标的大量低振幅谷线。")  # 写方法 / Write method
    lines.append("")  # 空行 / Blank line
    lines.append("这里不用 signed zero crossing 作为主指标，因为 frequency-domain 响应和真实沙粒实验看到的是振动幅值低谷，而不是本征模态符号零线。")  # 写不用零线原因 / Explain no signed zero-crossing
    lines.append("")  # 空行 / Blank line
    lines.append("## Valley Schematics / 波谷示意图")  # 写可视化小节 / Write visualisation section
    lines.append("")  # 空行 / Blank line
    lines.append("- `best_valley_schematic.png`: 最佳频率的 Target / Valley / Overlay 三联图。")  # 写最佳图说明 / Write best-image note
    lines.append("- `all_frequency_valley_schematics.png`: 每个频率对应低振幅波谷的总览图。")  # 写全频图说明 / Write all-frequency note
    lines.append("- `valley_schematics/freq_*_valley_schematic.png`: 每个频率独立的波谷示意图。")  # 写单频图说明 / Write per-frequency note
    lines.append("这些示意图显示的是最低振幅核心区，便于观察每个频率的波谷形状；数值判定仍使用完整 amplitude-valley score。")  # 写可视化解释 / Explain schematic visualisation
    lines.append("")  # 空行 / Blank line
    lines.append("## Top 10 Frequencies / 前 10 个频率")  # 写小节 / Write section
    lines.append("")  # 空行 / Blank line
    lines.append("| Rank | Frequency Hz | Target Mean | Side Mean | Contrast | Extra Penalty | Final Score |")  # 写表头 / Write table header
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")  # 写分隔行 / Write separator
    for index, row in enumerate(ranked_rows[:10], start=1):  # 遍历前十 / Iterate top ten
        lines.append(f"| {index} | {float(row['frequency_hz']):.3f} | {float(row['target_mean_amplitude']):.4f} | {float(row['side_mean_amplitude']):.4f} | {float(row['valley_contrast']):.3f} | {float(row['extra_valley_penalty']):.3f} | {float(row['final_amplitude_valley_score']):.3f} |")  # 写表格行 / Write table row
    lines.append("")  # 空行 / Blank line
    lines.append("## Decision / 判据与结论")  # 写小节 / Write section
    lines.append("")  # 空行 / Blank line
    if best:  # 检查是否有最佳结果 / Check best result
        lines.append(f"- Best frequency: `{float(best['frequency_hz']):.3f} Hz`")  # 写最佳频率 / Write best frequency
        lines.append(f"- Best valley contrast: `{float(best['valley_contrast']):.3f}`")  # 写最佳对比 / Write best contrast
        lines.append(f"- Best final score: `{float(best['final_amplitude_valley_score']):.3f}`")  # 写最佳分数 / Write best score
        lines.append(f"- Target lower than side band: `{float(best['target_mean_amplitude']) < float(best['side_mean_amplitude'])}`")  # 写目标是否低于侧带 / Write target-lower-than-side state
    lines.append(f"- Recommendation state: `{recommendation}`")  # 写推荐状态 / Write recommendation state
    if recommendation.startswith("strong") or recommendation.startswith("good"):  # 检查是否较好或强通过 / Check good or strong pass
        lines.append("结论：建议在最佳频率附近做局部精扫，并准备进入 CAD/打印验证。")  # 写通过结论 / Write pass conclusion
    elif recommendation.startswith("weak"):  # 检查是否弱通过 / Check weak pass
        lines.append("结论：当前只是弱可行。建议围绕最佳频率继续局部精扫并复核波谷示意图，暂不直接进入打印实验。")  # 写弱通过结论 / Write weak-pass conclusion
    else:  # 未通过 / Failed validation
        lines.append("结论：暂不建议进入打印实验。A 的窄频 eigenmode 可行性尚未转化为真实中心激励频响，需要 TAGS-A+ 几何重设计。")  # 写失败结论 / Write fail conclusion
    lines.append("")  # 空行 / Blank line
    lines.append("## TAGS-A+ Next Step / TAGS-A+ 下一步")  # 写小节 / Write section
    lines.append("")  # 空行 / Blank line
    lines.append("如果 A 频域验证不达标，下一步不是回到 B/C，也不是 225-cell 独立优化，而是以 A 为主族做低维目标对齐几何重设计。目标是提高 narrowband score、降低 frequency spread、提高 center-drive reachability，同时仍不添加外部实验设施。")  # 写 A+ 原则 / Write A+ principle
    lines.append("")  # 空行 / Blank line
    lines.append("建议几何族：A1 target thick mild；A2 target thick medium；A3 target thick strong；A4 target thick + side soft mild；A5 target thick + side soft strong；A6 segmented target thick；A7 segmented target thick + side soft；A8 target thick + edge tuning；A9 segmented target thick + edge tuning；A10 segmented target thick + side soft + edge tuning。")  # 写几何族 / Write geometry families
    Path(path).parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")  # 写出报告 / Write report


def run_validation(args: argparse.Namespace) -> int:  # 运行频域验证 / Run frequency-domain validation
    output_dir = Path(args.output_dir)  # 转换输出目录 / Convert output directory
    export_path = Path(args.export_path)  # 转换导出路径 / Convert export path
    target_path = resolve_target_path(args.target)  # 解析目标路径 / Resolve target path
    band_config = {"target_band_radius_px": int(args.target_band_radius_px), "side_band_inner_radius_px": int(args.side_band_inner_radius_px), "side_band_outer_radius_px": int(args.side_band_outer_radius_px), "center_mask_radius_px": int(args.center_mask_radius_px)}  # 构造 band 配置 / Build band config
    target_data = build_target_bands(target_path, int(args.grid_size), band_config)  # 构造目标 band 数据 / Build target band data
    save_band_overlay(output_dir / "target_band_overlay.png", target_data)  # 保存 target/side band 叠加 / Save target/side band overlay
    try:  # 尝试读取 COMSOL 频域导出 / Try loading COMSOL frequency-domain export
        responses, metadata = load_frequency_response(export_path, int(args.grid_size))  # 读取频域响应 / Load frequency responses
    except FileNotFoundError as exc:  # 捕获缺少导出 / Catch missing export
        write_waiting_report(output_dir, str(args.case), export_path, target_path)  # 写等待报告 / Write waiting report
        print(f"{exc} / 已生成 waiting_for_comsol_export 报告。")  # 打印清晰提示 / Print clear hint
        return 2  # 返回等待状态码 / Return waiting status code
    ranked = rank_frequency_responses(responses, target_data, {"epsilon": float(args.epsilon)})  # 对所有频率排序 / Rank all frequencies
    write_scores_csv(output_dir / "frequency_domain_scores.csv", ranked)  # 写评分 CSV / Write score CSV
    best = ranked[0] if ranked else {}  # 读取最佳结果 / Read best result
    if best:  # 检查是否有最佳频率 / Check best frequency availability
        save_frequency_preview(output_dir / "best_frequency_response.png", responses[float(best["frequency_hz"])], target_data, f"Best {float(best['frequency_hz']):.2f} Hz")  # 保存最佳响应图 / Save best response image
    save_score_vs_frequency(output_dir / "score_vs_frequency.png", ranked)  # 保存分数曲线 / Save score chart
    save_top_previews(output_dir / "top_5_frequency_previews.png", ranked, responses, target_data, 5)  # 保存前五预览 / Save top-five previews
    save_valley_schematic_set(output_dir, ranked, responses, target_data, {"epsilon": float(args.epsilon)})  # 保存每个频率的波谷示意图 / Save per-frequency valley schematics
    recommendation, passes = recommendation_from_best(best, args) if best else ("no_frequency_rows", False)  # 生成推荐状态 / Build recommendation state
    write_summary(output_dir / "frequency_domain_validation_summary.md", args, target_path, export_path, ranked, metadata, recommendation, passes)  # 写总结报告 / Write summary report
    print(f"Wrote frequency-domain validation outputs to {output_dir}. / 已写出频域验证输出到 {output_dir}。")  # 打印完成信息 / Print completion message
    return 0 if ranked else 1  # 返回状态码 / Return status code


def main() -> None:  # 主入口 / Main entry point
    args = build_parser().parse_args()  # 解析参数 / Parse arguments
    raise SystemExit(run_validation(args))  # 执行并返回状态码 / Run and return status code


if __name__ == "__main__":  # 检查是否直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
