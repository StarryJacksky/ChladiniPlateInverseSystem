"""Decision experiment 4: dynamic amplification vs frequency for the production design.
只读 / read-only.

放大倍率 A(f) = max|u_rel| / u_base,  u_base = base_accel/omega^2.
A >> 1  : 尖锐共振 -> 相对响应主导, 绝对场有深节线 -> 现实可复现图案.
A ~ 1   : 离共振 -> 均匀基底激励主导, 绝对场近乎平 -> 沙堆不出图(现实事与愿违).
对比设计实际用的 6 个频率落在哪里.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
import numpy as np
import torch
from src.physics.orthotropic_plate import OrthotropicPlate

ROOT = Path(__file__).resolve().parents[1]
DES = ROOT / "reports/production_pla/production_design"
OUT = ROOT / "reports/_decision_experiments/dir5_effectiveness"
OUT.mkdir(parents=True, exist_ok=True)
BASE_ACCEL = 1.0


def load_grid_csv(p):
    rows = []
    for line in p.read_text().splitlines():
        parts = [x for x in line.replace(",", " ").split() if x]
        try:
            rows.append([float(x) for x in parts])
        except ValueError:
            pass
    return np.array(rows)


def load_col(p):
    out = []
    for row in csv.reader(p.open()):
        try:
            out.append(float(row[0]))
        except (ValueError, IndexError):
            pass
    return out


try:
    import yaml
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
except Exception:
    config = {"project": {"plate_length_mm": 150.0, "plate_width_mm": 150.0, "center_clamp_radius_mm": 8.0},
              "material": {"youngs_modulus_pa": 1.55e9, "poisson_ratio": 0.4, "density_kg_m3": 1270.0}}

H = load_grid_csv(DES / "H.csv")
theta = load_grid_csv(DES / "theta_continuous_rad.csv")
design_freqs = load_col(DES / "frequencies_hz.csv")
weights = load_col(DES / "weights.csv")
summ = json.loads((DES / "w10_optimization_summary.json").read_text(encoding="utf-8"))
sr = float(summ.get("stiffness_ratio_used", 3.0)); shear = float(summ.get("shear_ratio_used", 1.0))
damp = float(summ.get("damping_ratio", 0.02))

plate = OrthotropicPlate(config, base_accel=BASE_ACCEL, default_damping=damp,
                         stiffness_ratio=sr, shear_ratio=shear, dtype=torch.float64)
# K, M 不随频率变化, 预装配一次 / assemble once (freq-independent)
H_proxy = plate.upsample(torch.tensor(H)); theta_proxy = plate.upsample(torch.tensor(theta))
K, M = plate.assemble_K_M(H_proxy, theta_proxy)
free = plate.free_indices
K_free = K.index_select(0, free).index_select(1, free)
M_free = M.index_select(0, free)
omega_ref = 2.0 * np.pi * plate.reference_frequency_hz
alpha = damp * omega_ref; beta = damp / omega_ref
Kc = K_free.to(plate.cdtype); Mc = M_free.to(plate.cdtype)
Mdiag = torch.diag(Mc)
force = (-M_free * BASE_ACCEL).to(plate.cdtype)


def amplification(freq_hz: float) -> float:
    omega = 2.0 * np.pi * freq_hz
    A = Kc + 1j * omega * (alpha * Mdiag + beta * Kc) - (omega ** 2) * Mdiag
    u = torch.linalg.solve(A, force)
    u_base = BASE_ACCEL / (omega ** 2)
    return float(torch.abs(u).max().item()) / u_base


fs = np.linspace(40.0, 1200.0, 360)
amps = np.array([amplification(f) for f in fs])

# 找尖锐共振峰 / find sharp resonance peaks
peaks = [(fs[i], amps[i]) for i in range(1, len(fs) - 1) if amps[i] > amps[i-1] and amps[i] > amps[i+1] and amps[i] > 8.0]
peaks.sort(key=lambda t: -t[1])

print(f"design freqs (Hz) and their amplification A=max|u_rel|/u_base:")
for f, w in zip(design_freqs, weights):
    a = amplification(f)
    tag = "  <-- weak/off-resonance" if a < 8 else "  (resonant)"
    print(f"  f={f:8.1f}Hz  weight={w:5.3f}  A={a:7.2f}{tag}")

print(f"\nsweep A(f) summary: min={amps.min():.2f}  median={np.median(amps):.2f}  max={amps.max():.2f}")
print(f"top sharp resonances (A>8) the design did NOT prioritise:")
for f, a in peaks[:10]:
    print(f"  f={f:8.1f}Hz   A={a:7.2f}")

try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    plt.figure(figsize=(11, 4))
    plt.semilogy(fs, amps, lw=1.3, label="amplification A(f)=max|u_rel|/u_base")
    plt.axhline(8, color="gray", ls=":", lw=1, label="A=8 (weak/strong cutoff)")
    for f, w in zip(design_freqs, weights):
        a = amplification(f)
        plt.scatter([f], [a], s=40 + 300 * w, color="red", zorder=5)
        plt.annotate(f"{f:.0f}\nw={w:.2f}", (f, a), fontsize=7, ha="center", va="bottom")
    plt.xlabel("drive frequency (Hz)"); plt.ylabel("dynamic amplification (log)")
    plt.title("Design leans on LOW-amplification (off-resonance) freqs (red);\nsharp resonances (tall peaks) give realizable patterns")
    plt.legend(fontsize=8); plt.tight_layout()
    plt.savefig(OUT / "amplification_sweep.png", dpi=120); plt.close()
    print(f"\nsaved -> {OUT/'amplification_sweep.png'}")
except Exception as e:
    print("plot skipped:", e)
