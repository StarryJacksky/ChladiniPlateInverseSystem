from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 命令行 / Argparse
import json  # JSON / JSON
import sys  # 系统 / System
from pathlib import Path  # 路径 / Paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 项目根 / Project root
if str(PROJECT_ROOT) not in sys.path:  # 检查 / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加 / Add

import numpy as np  # NumPy / NumPy

from src.symmetry.d4_decomposition import D4_CHARACTERS  # 特标 / Characters
from src.symmetry.d4_decomposition import coupling_accessibility  # 可达性 / Accessibility
from src.symmetry.d4_decomposition import decompose  # 分解 / Decompose
from src.symmetry.d4_decomposition import irrep_energy_ratios  # 占比 / Ratios


TARGETS: list[tuple[str, str]] = [
    ("IC letters", "data/processed_targets/target_binary.npy"),
    ("Diagonal (top-left to bottom-right)", "data/processed_targets/target_diagonal.npy"),
    ("X-form (both diagonals)", "data/processed_targets/target_xform.npy"),
    ("+ Cross (horizontal + vertical)", "data/processed_targets/target_cross.npy"),
]  # 目标列表 / Targets


def make_pattern_label(ratios: dict[str, float]) -> str:  # 给出可读对称类型描述 / Human-readable symmetry label
    sorted_irreps = sorted(ratios.items(), key=lambda kv: -kv[1])  # 排序 / Sort
    parts = [f"{k}={v*100:.1f}%" for k, v in sorted_irreps if v > 0.01]  # 大于 1% 才显示 / Filter
    dominant = sorted_irreps[0][0]  # 主导 / Dominant
    return f"dominant={dominant}, " + " | ".join(parts)  # 拼接 / Join


def render_irrep_decomposition(target: np.ndarray, name: str, output_dir: Path) -> None:  # 渲染 5 个 irrep 投影到 PNG / Render 5 irrep projections to PNG
    import matplotlib  # matplotlib / matplotlib
    matplotlib.use("Agg")  # Agg / Agg
    import matplotlib.pyplot as plt  # pyplot / pyplot
    parts = decompose(target.astype(np.float64))  # 分解 / Decompose
    ratios = irrep_energy_ratios(target.astype(np.float64))  # 占比 / Ratios
    fig, axes = plt.subplots(1, 6, figsize=(20, 4))  # 1×6 / 1x6
    axes[0].imshow(target, cmap="gray_r")  # 原图 / Original
    axes[0].set_title(f"target: {name}", fontsize=11)  # 标题 / Title
    axes[0].axis("off")  # 关轴 / No axis
    irreps_order = ["A1", "A2", "B1", "B2", "E"]  # 顺序 / Order
    for col, irrep in enumerate(irreps_order):  # 遍历 / Iterate
        ax = axes[col + 1]  # 子图 / Subplot
        p = parts[irrep]  # 分量 / Part
        ax.imshow(p, cmap="seismic", vmin=-float(np.abs(p).max() + 1e-9), vmax=float(np.abs(p).max() + 1e-9))  # 双色图 / Diverging
        ax.set_title(f"{irrep}  {ratios[irrep]*100:.1f}%", fontsize=11)  # 标题 / Title
        ax.axis("off")  # 关轴 / No axis
    plt.suptitle(f"D4 irrep decomposition: {name}", fontsize=13)  # 总标 / Suptitle
    plt.tight_layout()  # 紧凑 / Tight
    out = output_dir / f"irrep_{name.split()[0].lower().replace(',','').replace('+','plus')}.png"  # 输出 / Output
    plt.savefig(out, dpi=110, bbox_inches="tight")  # 保存 / Save
    plt.close(fig)  # 关闭 / Close
    print(f"  Saved figure: {out}")  # 提示 / Print


def main(argv: list[str] | None = None) -> int:  # 主 / Main
    parser = argparse.ArgumentParser(description="Decompose all targets into D4 irreps; report accessibility under center excitation. / 把所有目标分解到 D4 irrep，给出中心激振下的可达性。")  # 解析器 / Parser
    parser.add_argument("--accessible-irreps", type=str, default="A1", help="Comma-separated accessible irreps (center excitation → A1). / 可达 irrep（中心激振 → A1）。")  # 可达 / Accessible
    parser.add_argument("--render", action="store_true", default=True, help="Also render irrep projection PNGs. / 渲染 PNG。")  # 渲染 / Render
    parser.add_argument("--output-json", type=str, default="reports/target_irrep_analysis.json", help="Output JSON. / 输出 JSON。")  # JSON / JSON
    parser.add_argument("--output-dir", type=str, default="reports/irrep_decompositions", help="Output PNG dir. / 输出 PNG 目录。")  # 目录 / Dir
    args = parser.parse_args(argv)  # 解析 / Parse
    accessible = tuple(s.strip() for s in args.accessible_irreps.split(",") if s.strip())  # 元组 / Tuple
    out_dir = Path(args.output_dir)  # 目录 / Dir
    out_dir.mkdir(parents=True, exist_ok=True)  # 建目录 / Mkdir
    results: list[dict[str, object]] = []  # 结果 / Results
    print(f"=== D4 irrep decomposition analysis (accessible: {accessible}) / D4 irrep 分解分析 ===\n")  # 标题 / Header
    for name, target_path in TARGETS:  # 遍历 / Iterate
        path = Path(target_path)  # 路径 / Path
        if not path.exists():  # 跳过 / Skip
            print(f"[skip] {name}: missing {path}")  # 提示 / Hint
            continue  # 跳过 / Skip
        target = np.load(path)  # 加载 / Load
        if target.ndim != 2:  # 检查 / Check
            print(f"[skip] {name}: wrong ndim={target.ndim}")  # 跳过 / Skip
            continue  # 跳过 / Skip
        target = target.astype(np.float64)  # 浮点 / Float
        if target.shape[0] != target.shape[1]:  # 必须方阵 / Must square
            print(f"[skip] {name}: non-square {target.shape}")  # 跳过 / Skip
            continue  # 跳过 / Skip
        ratios = irrep_energy_ratios(target)  # 占比 / Ratios
        accessibility = coupling_accessibility(target, accessible)  # 可达 / Accessibility
        label = make_pattern_label(ratios)  # 标签 / Label
        symmetry_type = "D4-friendly" if accessibility > 0.95 else "partly D4" if accessibility > 0.70 else "D4-incompatible"  # 类型 / Type
        achievable_upper_bound = float(accessibility)  # 上界 / Upper bound
        print(f"--- {name} ---")  # 标题 / Header
        print(f"  shape: {target.shape}, foreground: {int(target.sum())}/{target.size} ({float(target.sum())/target.size*100:.2f}%)")  # 基本 / Basic
        print(f"  irrep ratios: {label}")  # 占比 / Ratios
        print(f"  accessible-irrep energy fraction = {accessibility*100:.2f}%  ({symmetry_type})")  # 可达 / Accessibility
        print(f"  → physical upper bound for 'how recognizable under center excitation': ~{achievable_upper_bound*100:.1f}% of target energy reachable\n")  # 上界 / Upper bound
        if args.render:  # 渲染 / Render
            render_irrep_decomposition(target, name, out_dir)  # 渲染 / Render
        results.append({"name": name, "target_path": str(path), "shape": list(target.shape), "foreground_pixels": int(target.sum()), "irrep_ratios": ratios, "accessible_irreps": list(accessible), "accessible_energy_fraction": float(accessibility), "achievable_upper_bound_fraction": float(achievable_upper_bound), "symmetry_type": symmetry_type})  # 收集 / Collect
    out_path = Path(args.output_json)  # 输出 / Output
    out_path.parent.mkdir(parents=True, exist_ok=True)  # 建目录 / Mkdir
    out_path.write_text(json.dumps({"d4_character_table": D4_CHARACTERS, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 / Write
    print(f"\nReport: {out_path}")  # 路径 / Path
    print(f"PNG dir: {out_dir}")  # 路径 / Path
    return 0  # 返回 / Return


if __name__ == "__main__":  # 直接 / Direct
    raise SystemExit(main())  # 退出 / Exit
