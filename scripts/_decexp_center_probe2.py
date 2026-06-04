"""Probe2: confirm whether CURRENT-pipeline COMSOL fields clamp the center.
只读 / read-only. 直接打印中心原始数值，判定 COMSOL 是否也有"中心夹持成0"。"""
from __future__ import annotations
from pathlib import Path
import numpy as np
from src.scoring.amplitude_valley_score import normalise_amplitude_grid, soft_valley_map

ROOT = Path(__file__).resolve().parents[1]
CLAMP_MM, PLATE_MM, EPS = 8.0, 150.0, 0.080


def disk(n, r):
    yy, xx = np.ogrid[:n, :n]; c = (n - 1) / 2.0
    return (yy - c) ** 2 + (xx - c) ** 2 <= r ** 2


CASES = [
    ("W10c_ic_tier1_sr3 (COMSOL)", "reports/w10_comsol_validation/w10_ic_tier1_sr3/composite_amplitude.npy"),
    ("W10c_ic_tier2_sweep (COMSOL)", "reports/w10_comsol_validation/orthotropic_sweep/w10_ic_tier2_sr12/composite_amplitude.npy"),
    ("W9_ic_iter0_f225 (COMSOL)", "reports/mosaic_z/comsol_closed_loop/w9_ic_v1_iter0_comsol/w9_ic_v1_iter0_sweep_f225p5/eps_0p05/comsol_forced_amplitude.npy"),
    ("SURR_prod_p2 (surrogate)", "reports/production_pla/production_design/phase2_best_composite_amp.npy"),
    ("SURR_cfpetg_ic_p2 (surrogate)", "reports/_battery/cfpetg/ic/bat_cfpetg_ic/phase2_best_composite_amp.npy"),
]

print(f"{'case':<32}{'N':>5}{'ctrRawMin':>11}{'ctrMean':>9}{'globMean':>9}{'quiet_x':>9}{'phantom%':>10}{'peak@ctr':>10}")
for label, rel in CASES:
    p = ROOT / rel
    if not p.exists():
        print(f"{label:<32} MISSING {rel}"); continue
    raw = np.load(p)
    amp = normalise_amplitude_grid(raw)
    n = amp.shape[0]
    r = CLAMP_MM / PLATE_MM * n
    m = disk(n, r)
    powder = soft_valley_map(amp, EPS)
    ctr_raw_min = float(np.abs(raw)[m].min())          # 中心原始最小幅值(看是否=0被夹持)
    ctr_mean = float(amp[m].mean())
    glob = float(amp.mean())
    quiet = glob / max(ctr_mean, 1e-6)
    phantom = 100 * float(powder[m].sum()) / max(float(powder.sum()), 1e-12)
    peak = bool(m[np.unravel_index(int(np.argmax(powder)), powder.shape)])
    print(f"{label:<32}{n:>5}{ctr_raw_min:>11.3g}{ctr_mean:>9.4f}{glob:>9.4f}{quiet:>9.2f}{phantom:>10.2f}{str(peak):>10}")
