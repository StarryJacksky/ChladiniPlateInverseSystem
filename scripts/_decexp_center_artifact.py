"""Decision experiment: quantify the center-excitation phantom-sand artifact.

只读决策实验 / Read-only decision experiment.
针对《改进方向五》：仿真在板中心堆"幻影沙"，而现实中心几乎不积沙。
本脚本用管线真实的撒粉模型(soft_valley_map)与评分函数(score_amplitude_valley_grid)，
在现成的真实 COMSOL 场 + surrogate 场上量化伪影强度，并比较"挖掉中心圆盘"前后的头部指标变化。
不重跑 COMSOL、不改任何跟踪文件。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from src.scoring.amplitude_valley_score import (
    normalise_amplitude_grid,
    soft_valley_map,
    score_amplitude_valley_grid,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "_decision_experiments" / "center_artifact"
OUT.mkdir(parents=True, exist_ok=True)

CLAMP_MM = 8.0      # config 默认中心夹持半径 / default center clamp radius
PLATE_MM = 150.0
DRIVE_MM = 12.0     # 略大的"驱动影响区"做敏感度对照 / slightly larger drive zone for sensitivity
EPS = 0.080         # 撒粉模型阈值 / powder model epsilon (pipeline default)


def disk_mask(n: int, radius_px: float) -> np.ndarray:
    yy, xx = np.ogrid[:n, :n]
    cy = cx = (n - 1) / 2.0
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= radius_px ** 2


def analyse_field(label: str, amp_path: Path, target_path: Path | None) -> dict:
    amp_raw = np.load(amp_path)
    amp = normalise_amplitude_grid(amp_raw)          # 与管线一致: abs/max -> [0,1]
    n = amp.shape[0]
    r_clamp = CLAMP_MM / PLATE_MM * n
    r_drive = DRIVE_MM / PLATE_MM * n
    clamp = disk_mask(n, r_clamp)
    drive = disk_mask(n, r_drive)

    powder = soft_valley_map(amp, EPS)               # p(x)=exp(-(amp/eps)^2)  真实撒粉模型
    hard = (amp <= EPS)                              # 硬谷线(沙会留下的安静区)

    # 中心是不是被误判成"最安静"？ / Is the center wrongly the quietest spot?
    amp_center = float(amp[clamp].mean())
    amp_global = float(amp.mean())
    # 幻影沙占比 / phantom-sand fraction (soft powder weight in center disk)
    soft_total = float(powder.sum())
    soft_in_clamp = float(powder[clamp].sum()) / max(soft_total, 1e-12)
    soft_in_drive = float(powder[drive].sum()) / max(soft_total, 1e-12)
    # 硬谷线像素占比 / hard-valley pixel fraction in center disk
    hard_total = int(hard.sum())
    hard_in_clamp = (int(hard[clamp].sum()) / hard_total) if hard_total else 0.0
    # 撒粉峰值是否落在中心圆盘内（"中心堆一坨"的直接证据）
    peak_idx = np.unravel_index(int(np.argmax(powder)), powder.shape)
    peak_in_clamp = bool(clamp[peak_idx])
    # 占面积比作参照：中心圆盘只占全板这么点面积 / area share of the clamp disk
    area_share = float(clamp.mean())

    row = {
        "label": label,
        "grid_N": n,
        "clamp_radius_px": round(r_clamp, 2),
        "clamp_area_share_%": round(100 * area_share, 2),
        "amp_center_mean": round(amp_center, 4),
        "amp_global_mean": round(amp_global, 4),
        "center_quietness_ratio": round(amp_global / max(amp_center, 1e-6), 2),  # >1 => 中心比全板更"安静"
        "phantom_soft_frac_clamp_%": round(100 * soft_in_clamp, 2),
        "phantom_soft_frac_drive_%": round(100 * soft_in_drive, 2),
        "hard_valley_frac_clamp_%": round(100 * hard_in_clamp, 2),
        "powder_peak_in_center": peak_in_clamp,
    }

    # 有目标图时，比较"挖中心前/后"的头部指标 / metric shift when masking center
    if target_path is not None and target_path.exists():
        tgt = np.load(target_path)
        r_px = int(round(r_clamp))
        s0 = score_amplitude_valley_grid(amp_raw, tgt, EPS, center_radius_px=0)
        s1 = score_amplitude_valley_grid(amp_raw, tgt, EPS, center_radius_px=r_px)
        row["contrast_no_mask"] = round(float(s0["valley_contrast"]), 3)
        row["contrast_center_masked"] = round(float(s1["valley_contrast"]), 3)
        row["contrast_shift_%"] = round(100 * (float(s1["valley_contrast"]) - float(s0["valley_contrast"])) / max(float(s0["valley_contrast"]), 1e-9), 1)
        row["iou_no_mask"] = round(float(s0["iou"]), 3)
        row["iou_center_masked"] = round(float(s1["iou"]), 3)
        row["target_mean_amp_no_mask"] = round(float(s0["target_mean_amplitude"]), 4)
        row["target_mean_amp_masked"] = round(float(s1["target_mean_amplitude"]), 4)

    # 存一张预览图（振幅 / 撒粉 / 撒粉挖中心）/ save a 3-panel preview
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        masked = powder.copy()
        masked[clamp] = 0.0
        fig, ax = plt.subplots(1, 3, figsize=(11, 3.6))
        ax[0].imshow(amp, cmap="viridis"); ax[0].set_title(f"{label}\nnorm amplitude")
        ax[1].imshow(powder, cmap="magma"); ax[1].set_title("powder p=exp(-(amp/eps)^2)\n(center blob = phantom sand)")
        ax[2].imshow(masked, cmap="magma"); ax[2].set_title("powder, center disk masked")
        for a in ax:
            t = plt.Circle(((n-1)/2.0, (n-1)/2.0), r_clamp, color="cyan", fill=False, lw=1.2)
            a.add_patch(t); a.axis("off")
        fig.tight_layout()
        fig.savefig(OUT / f"preview_{label}.png", dpi=110)
        plt.close(fig)
    except Exception as e:  # matplotlib 可选 / optional
        row["_preview_error"] = str(e)
    return row


CASES = [
    # (label, amplitude_npy, target_npy or None)
    ("COMSOL_IC_f220", "reports/mosaic_z/comsol_closed_loop/sprint1_baseline_ic_comsol/sprint1_baseline_ic_sweep_f220p2/eps_0p05/comsol_forced_amplitude.npy", None),
    ("COMSOL_IC_f481", "reports/mosaic_z/comsol_closed_loop/sprint1_baseline_ic_comsol/sprint1_baseline_ic_sweep_f481p6/eps_0p05/comsol_forced_amplitude.npy", None),
    ("COMSOL_IC_f882", "reports/mosaic_z/comsol_closed_loop/sprint1_baseline_ic_comsol/sprint1_baseline_ic_sweep_f882p6/eps_0p05/comsol_forced_amplitude.npy", None),
    ("SURR_prod_p2", "reports/production_pla/production_design/phase2_best_composite_amp.npy", "reports/production_pla/production_design/target_resized.npy"),
    ("SURR_prod_p1", "reports/production_pla/production_design/phase1_best_composite_amp.npy", "reports/production_pla/production_design/target_resized.npy"),
    ("SURR_cfpetg_ic_p2", "reports/_battery/cfpetg/ic/bat_cfpetg_ic/phase2_best_composite_amp.npy", "reports/_battery/cfpetg/ic/bat_cfpetg_ic/target_resized.npy"),
]

rows = []
for label, ap, tp in CASES:
    apath = ROOT / ap
    if not apath.exists():
        print(f"SKIP {label}: missing {ap}")
        continue
    rows.append(analyse_field(label, apath, (ROOT / tp) if tp else None))

(OUT / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

# 打印紧凑表 / compact table
keys_core = ["label", "grid_N", "clamp_area_share_%", "center_quietness_ratio",
             "phantom_soft_frac_clamp_%", "hard_valley_frac_clamp_%", "powder_peak_in_center"]
print("\n=== CENTER ARTIFACT — core metrics ===")
print("(clamp_area_share = 中心圆盘理论面积占比; phantom_soft_frac = 落在中心的撒粉权重占比)")
hdr = ["label", "N", "area%", "quiet_x", "phantom%", "hardval%", "peak@ctr"]
print("{:<20}{:>5}{:>8}{:>9}{:>10}{:>10}{:>10}".format(*hdr))
for r in rows:
    print("{:<20}{:>5}{:>8}{:>9}{:>10}{:>10}{:>10}".format(
        r["label"], r["grid_N"], r["clamp_area_share_%"], r["center_quietness_ratio"],
        r["phantom_soft_frac_clamp_%"], r["hard_valley_frac_clamp_%"], str(r["powder_peak_in_center"])))

print("\n=== METRIC SHIFT when masking center (cases with target) ===")
for r in rows:
    if "contrast_no_mask" in r:
        print(f"{r['label']:<20} contrast {r['contrast_no_mask']:>7} -> {r['contrast_center_masked']:>7}  ({r['contrast_shift_%']:+.1f}%)   "
              f"iou {r['iou_no_mask']:>6} -> {r['iou_center_masked']:>6}   "
              f"target_meanAmp {r['target_mean_amp_no_mask']:>7} -> {r['target_mean_amp_masked']:>7}")

print(f"\nsaved -> {OUT}")
