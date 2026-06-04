"""Decision experiment 5: are the design's drive frequencies ON COMSOL resonances?
只读 / read-only. 纯 COMSOL 真值, 不用 surrogate.

判据: 每个驱动频率到最近 COMSOL 本征频率的间距, 以半功率带宽 (zeta*f) 为尺.
 gap < 1 bandwidth  -> on-resonance (现实/COMSOL 会出清晰图)
 gap > ~2 bandwidth -> off-resonance (响应弱且多模混叠 -> 现实难复现)
同时核对: 优化器假设的材料(sr/shear) 是否与 COMSOL 本征频率所用材料一致.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DES = ROOT / "reports/production_pla/production_design"
EIG = ROOT / "reports/modal_calibration/prod_eig_production_design_comsol_eigfreqs.json"


def load_col(p):
    out = []
    for row in csv.reader(p.open(encoding="utf-8")):
        try:
            out.append(float(row[0]))
        except (ValueError, IndexError):
            pass
    return out


drive = load_col(DES / "frequencies_hz.csv")
weights = load_col(DES / "weights.csv")
wsum = json.loads((DES / "w10_optimization_summary.json").read_text(encoding="utf-8"))
eig = json.loads(EIG.read_text(encoding="utf-8"))
eigfreqs = np.array(eig["comsol_eigfreqs_hz"], dtype=float)
zeta = float(wsum.get("damping_ratio", 0.02))

opt_sr = wsum.get("stiffness_ratio_used", "?")
opt_shear = wsum.get("shear_ratio_used", "?")
eig_sr = eig.get("material_summary", {}).get("stiffness_ratio", "?")
eig_shear = eig.get("material_summary", {}).get("shear_ratio", "?")

print("=== MATERIAL CONSISTENCY (optimizer vs COMSOL eigen-model) ===")
print(f"  optimizer used : stiffness_ratio={opt_sr}  shear_ratio={opt_shear}")
print(f"  COMSOL eig used: stiffness_ratio={eig_sr}  shear_ratio={eig_shear}")
print(f"  -> {'MISMATCH (drive freqs tuned to a DIFFERENT plate than COMSOL solves!)' if str(opt_sr)!=str(eig_sr) else 'consistent'}")
print(f"  damping zeta={zeta}  (half-power bandwidth ~ zeta*f)")

print(f"\nCOMSOL eigenfreqs (Hz): {[round(float(x),1) for x in eigfreqs[:30]]}")

print(f"\n=== drive freq vs nearest COMSOL eigenfreq ===")
print(f"{'drive_Hz':>10}{'weight':>8}{'nearest_eig':>13}{'gap_Hz':>9}{'gap/bw':>9}   verdict")
onres_w = 0.0
for f, w in zip(drive, weights):
    i = int(np.argmin(np.abs(eigfreqs - f)))
    nearest = float(eigfreqs[i]); gap = f - nearest
    bw = zeta * nearest                       # half-power bandwidth
    gbw = abs(gap) / bw
    v = "ON-resonance" if gbw <= 1.0 else ("near" if gbw <= 2.0 else "OFF-RESONANCE")
    if gbw <= 1.0:
        onres_w += w
    print(f"{f:>10.1f}{w:>8.3f}{nearest:>13.1f}{gap:>+9.1f}{gbw:>9.2f}   {v}")

print(f"\nweight-fraction of drive energy that is ON-resonance (gap<=1 bandwidth): {onres_w:.1%}")
print("(low fraction => the design mostly drives between/off COMSOL modes => weak, non-reproducible response)")
