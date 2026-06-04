"""Decision experiment 3: DOES improvement Direction 5 actually work?
只读 / read-only (writes only PNG/JSON into reports/_decision_experiments/).

在真实 production_design 前向解上对比:
  current : 相对位移撒粉模型 p = exp(-(|u_rel|/eps)^2)   <- 中心夹持=0 -> 木星
  FIX-A   : 快修, 直接挖掉中心圆盘
  FIX-B   : 正修, 绝对位移 u_abs = u_rel + a_base/omega^2 (报告方向五公式)
  FIX-C   : 撒粉物理升级, 绝对加速度阈值  sand <=> omega^2|u_abs| < a_crit
判据: 木星是否消失? 外围图案是否保住(相关性)? 富集/覆盖怎么变?
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
EPS = 0.080
BASE_ACCEL = 1.0  # config / OrthotropicPlate default (m/s^2)


def load_grid_csv(p: Path) -> np.ndarray:
    rows = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = [x for x in line.replace(",", " ").split() if x]
            try:
                rows.append([float(x) for x in parts])
            except ValueError:
                continue  # skip header
    return np.array(rows, dtype=float)


def load_col(p: Path) -> list[float]:
    out = []
    with p.open() as f:
        r = csv.reader(f)
        for row in r:
            if not row:
                continue
            try:
                out.append(float(row[0]))
            except ValueError:
                continue
    return out


# --- load config (yaml if available, else minimal dict) ---
try:
    import yaml
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
except Exception:
    config = {"project": {"plate_length_mm": 150.0, "plate_width_mm": 150.0, "center_clamp_radius_mm": 8.0},
              "material": {"youngs_modulus_pa": 1.55e9, "poisson_ratio": 0.4, "density_kg_m3": 1270.0}}

H = load_grid_csv(DES / "H.csv")
theta = load_grid_csv(DES / "theta_continuous_rad.csv")
freqs = load_col(DES / "frequencies_hz.csv")
weights = load_col(DES / "weights.csv")
summ = json.loads((DES / "w10_optimization_summary.json").read_text(encoding="utf-8"))
sr = float(summ.get("stiffness_ratio_used", 3.0))
shear = float(summ.get("shear_ratio_used", 1.0))
damping = float(summ.get("damping_ratio", 0.02))
print(f"design: H{H.shape} theta{theta.shape}  sr={sr} shear={shear} damp={damping}")
print(f"freqs={[round(f,1) for f in freqs]}  weights={[round(w,3) for w in weights]}")

plate = OrthotropicPlate(config, base_accel=BASE_ACCEL, default_damping=damping,
                         stiffness_ratio=sr, shear_ratio=shear,
                         dtype=torch.float64, device="cpu")
N = plate.N
Hh = torch.tensor(H, dtype=torch.float64)
Th = torch.tensor(theta, dtype=torch.float64)


def complex_u_grid(freq_hz: float) -> np.ndarray:
    """复现 amplitude_at_frequency 但保留复数 u_grid (中心夹持=0)."""
    H_proxy = plate.upsample(Hh)
    theta_proxy = plate.upsample(Th)
    K, M = plate.assemble_K_M(H_proxy, theta_proxy)
    free = plate.free_indices
    K_free = K.index_select(0, free).index_select(1, free)
    M_free = M.index_select(0, free)
    omega = torch.tensor(2.0 * np.pi * freq_hz, dtype=torch.float64)
    u_free = plate.direct_forced_response(K_free, M_free, omega, damping)  # complex
    u_grid = plate.expand_to_grid(u_free)  # complex N x N, center clamped = 0
    return u_grid.detach().cpu().numpy()


def disk(n, r):
    yy, xx = np.ogrid[:n, :n]; c = (n - 1) / 2.0
    return (yy - c) ** 2 + (xx - c) ** 2 <= r ** 2


def norm01(a):
    a = np.abs(a); m = a.max()
    return a / m if m > 0 else a


r_clamp = config["project"]["center_clamp_radius_mm"] / config["project"]["plate_length_mm"] * N
clamp = disk(N, r_clamp)

# per-frequency complex relative field; composite by weights
W = np.array(weights[:len(freqs)], dtype=float); W = W / W.sum()
comp_rel = np.zeros((N, N)); comp_abs = np.zeros((N, N)); comp_acc_stay = np.zeros((N, N))
ubase_list = []
for f, w in zip(freqs, W):
    u = complex_u_grid(f)
    omega = 2.0 * np.pi * f
    u_base = BASE_ACCEL / (omega ** 2)         # 绝对位移基底项 (实, 均匀)
    ubase_list.append(u_base)
    u_abs = u + u_base                         # FIX-B: 绝对位移
    comp_rel += w * norm01(u)                  # current: |u_rel|
    comp_abs += w * norm01(u_abs)              # FIX-B
    # FIX-C: 绝对加速度  a = omega^2 |u_abs|; "留沙"权重 = 低加速度
    a = (omega ** 2) * np.abs(u_abs)
    comp_acc_stay += w * (a / a.max())

comp_rel = comp_rel / comp_rel.max()
comp_abs = comp_abs / comp_abs.max()
comp_acc = comp_acc_stay / comp_acc_stay.max()

# 撒粉图 / powder maps
p_current = np.exp(-(comp_rel / EPS) ** 2)            # current (Jupiter expected)
p_fixA = p_current.copy(); p_fixA[clamp] = 0.0        # FIX-A quick mask
p_fixB = np.exp(-(comp_abs / EPS) ** 2)               # FIX-B absolute displacement
p_fixC = np.exp(-(comp_acc / EPS) ** 2)               # FIX-C absolute acceleration


def center_frac(p):
    return 100 * float(p[clamp].sum()) / max(float(p.sum()), 1e-12)


def outer_corr(p_new, p_old):
    m = ~clamp
    a, b = p_new[m].ravel(), p_old[m].ravel()
    if a.std() < 1e-9 or b.std() < 1e-9:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


print(f"\nu_base (abs displacement offset) per freq, m: {[f'{u:.2e}' for u in ubase_list]}")
print(f"|u_rel| typical scale (max of comp before norm handled per-freq) -- see ratio below")
# 关键比值: 共振相对响应 vs 基底位移
peak_rel_each = []
for f in freqs:
    u = complex_u_grid(f); peak_rel_each.append(float(np.abs(u).max()))
for f, pr, ub in zip(freqs, peak_rel_each, ubase_list):
    print(f"  f={f:7.1f}Hz  max|u_rel|={pr:.3e} m   u_base={ub:.3e} m   ratio rel/base={pr/ub:8.2f}")

print("\n=== Direction 5 effectiveness ===")
print(f"{'model':<28}{'center_powder%':>16}{'peak@center':>13}{'outer_corr_vs_current':>24}")
for name, p in [("current (relative)", p_current), ("FIX-A center-mask", p_fixA),
                ("FIX-B abs-displacement", p_fixB), ("FIX-C abs-acceleration", p_fixC)]:
    peak = bool(clamp[np.unravel_index(int(np.argmax(p)), p.shape)])
    print(f"{name:<28}{center_frac(p):>15.2f}%{str(peak):>13}{outer_corr(p, p_current):>24.3f}")

# 预览图 / preview
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 4, figsize=(15, 3.8))
    for a, (name, p) in zip(ax, [("current (relative)\nJUPITER", p_current), ("FIX-A mask", p_fixA),
                                  ("FIX-B abs-displacement", p_fixB), ("FIX-C abs-acceleration", p_fixC)]):
        a.imshow(p, cmap="magma"); a.set_title(name); a.axis("off")
        a.add_patch(plt.Circle(((N-1)/2, (N-1)/2), r_clamp, color="cyan", fill=False, lw=1.2))
    fig.tight_layout(); fig.savefig(OUT / "dir5_fix_comparison.png", dpi=120); plt.close(fig)
    print(f"\nsaved preview -> {OUT/'dir5_fix_comparison.png'}")
except Exception as e:
    print("preview skipped:", e)
