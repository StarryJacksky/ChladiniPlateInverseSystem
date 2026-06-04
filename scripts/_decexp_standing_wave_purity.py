"""Decision experiment 2: are COMSOL-predicted patterns physically realizable standing waves?
只读 / read-only.

物理判据 / Physics:
谐波强迫响应是复数场 u(x) = R(x) + i I(x)。真实 Chladni 图案要求"驻波"：
板存在永不动的节线 <=> R(x) 与 I(x) 空间成比例(同一模态形状)。
purity = s1^2/(s1^2+s2^2)，对 M=[vec(R), vec(I)] (N x 2) 做 SVD。
purity≈1 -> 单一驻波(有干净节线, 现实可复现)；
purity->0.5 -> R 与 I 方向错开(多模态/行波, |u| 只在孤立点为零, 无节线, 现实震不出图)。
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def purity_and_depth(real_path: Path, imag_path: Path) -> dict:
    R = np.nan_to_num(np.load(real_path).astype(np.float64).ravel())
    I = np.nan_to_num(np.load(imag_path).astype(np.float64).ravel())
    M = np.stack([R, I], axis=1)                       # N x 2
    # 去掉全板均值不影响节线判定；这里直接对位移场做 SVD
    s = np.linalg.svd(M, compute_uv=False)
    purity = float(s[0] ** 2 / (s[0] ** 2 + s[1] ** 2 + 1e-30))
    A = np.sqrt(R ** 2 + I ** 2)
    amean = float(A.mean()) or 1e-30
    valley_floor = float(np.percentile(A, 1)) / amean   # 最深谷相对均值(越接近0越像真节线)
    frac_below_5pct = float((A < 0.05 * A.max()).mean())  # 低于峰值5%的面积占比
    # 相位集中度: 每像素相位 atan2(I,R), 用 A 加权的圆方差 (低=相位一致=驻波)
    ang = np.arctan2(I, R)
    w = A / A.sum()
    Cbar = np.sqrt((w * np.cos(2 * ang)).sum() ** 2 + (w * np.sin(2 * ang)).sum() ** 2)  # 轴向(mod pi)
    phase_concentration = float(Cbar)                   # ->1 相位一致(驻波), ->0 相位发散
    return {"purity": purity, "valley_floor_rel": valley_floor,
            "area_below_5pct_%": 100 * frac_below_5pct, "phase_concentration": phase_concentration}


def run(label: str, comsol_dir: Path, freqs: list[str], eps: str, best_id: str | None):
    print(f"\n=== {label} ===   (chosen by pipeline: {best_id})")
    print(f"{'freq_Hz':>10}{'purity':>9}{'phase_conc':>12}{'valley_floor':>14}{'area<5%':>10}   verdict")
    rows = []
    for f in freqs:
        base = comsol_dir / f"{comsol_dir.name.replace('_comsol','')}_sweep_{f}" / eps
        rp = base / "comsol_forced_real_grid.npy"
        ip = base / "comsol_forced_imag_grid.npy"
        if not (rp.exists() and ip.exists()):
            print(f"{f:>10}   MISSING real/imag at {base}")
            continue
        m = purity_and_depth(rp, ip)
        fhz = f.replace("sweep_f", "").replace("f", "").replace("p", ".")
        chosen = "  <== CHOSEN" if (best_id and f in best_id) else ""
        verdict = "standing-wave" if m["purity"] > 0.9 else ("mixed" if m["purity"] > 0.7 else "TRAVELING/mixed")
        print(f"{fhz:>10}{m['purity']:>9.3f}{m['phase_concentration']:>12.3f}{m['valley_floor_rel']:>14.4f}{m['area_below_5pct_%']:>9.1f}   {verdict}{chosen}")
        rows.append({"freq": fhz, **m})
    return rows


# W9 IC iter0 (closed-loop COMSOL)
w9 = ROOT / "reports/mosaic_z/comsol_closed_loop/w9_ic_v1_iter0_comsol"
w9_freqs = ["f225p5", "f381p8", "f594p5", "f706p8", "f775p8", "f938p7"]
run("W9 IC iter0 (real COMSOL forced response)", w9, w9_freqs, "eps_0p05", "f381p8")

# sprint1 baseline IC (older closed-loop COMSOL)
sp = ROOT / "reports/mosaic_z/comsol_closed_loop/sprint1_baseline_ic_comsol"
sp_freqs = ["f220p2", "f318p5", "f481p6", "f714p5", "f837p7", "f882p6"]
run("sprint1 baseline IC (real COMSOL forced response)", sp, sp_freqs, "eps_0p05", None)

print("\n[reference] purity=1.0 => perfect single standing wave (clean nodal lines, reality reproduces).")
print("            purity~0.5 => R perp I (no nodal lines; |u| valleys are NOT physical nodes).")
