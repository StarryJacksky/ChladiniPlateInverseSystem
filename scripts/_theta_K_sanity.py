"""Quick θ sanity check: does the plate's K matrix actually depend on θ?"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch
import yaml
from src.physics.orthotropic_plate import OrthotropicPlate

cfg = yaml.safe_load(Path("config.yaml").read_text())
plate = OrthotropicPlate(cfg, proxy_grid_size=25, stiffness_ratio=3.0, shear_ratio=1.0, dtype=torch.float64)

# uniform H
H = torch.full((25, 25), 1.3e-3, dtype=torch.float64)
# Two different θ patterns
theta_a = torch.zeros((25, 25), dtype=torch.float64)
theta_b = torch.full((25, 25), torch.pi / 4, dtype=torch.float64)
theta_c = torch.full((25, 25), torch.pi / 2, dtype=torch.float64)

# Check per-cell stiffness for one cell
D_a = plate.compute_per_cell_stiffness(H, theta_a)
D_b = plate.compute_per_cell_stiffness(H, theta_b)
D_c = plate.compute_per_cell_stiffness(H, theta_c)
print("per-cell stiffness (cell 0,0):")
print(f"  θ=0°  : D11={D_a[0][0,0]:.4e}  D22={D_a[1][0,0]:.4e}  D12={D_a[2][0,0]:.4e}  D66={D_a[3][0,0]:.4e}  D16={D_a[4][0,0]:.4e}")
print(f"  θ=45° : D11={D_b[0][0,0]:.4e}  D22={D_b[1][0,0]:.4e}  D12={D_b[2][0,0]:.4e}  D66={D_b[3][0,0]:.4e}  D16={D_b[4][0,0]:.4e}")
print(f"  θ=90° : D11={D_c[0][0,0]:.4e}  D22={D_c[1][0,0]:.4e}  D12={D_c[2][0,0]:.4e}  D66={D_c[3][0,0]:.4e}  D16={D_c[4][0,0]:.4e}")

print("\nAssembled K matrix Frobenius norm:")
Ka, _ = plate.assemble_K_M(H, theta_a)
Kb, _ = plate.assemble_K_M(H, theta_b)
Kc, _ = plate.assemble_K_M(H, theta_c)
print(f"  θ=0°  : ||K||_F = {Ka.norm():.6e}")
print(f"  θ=45° : ||K||_F = {Kb.norm():.6e}")
print(f"  θ=90° : ||K||_F = {Kc.norm():.6e}")
print(f"  ||Kb - Ka||_F = {(Kb-Ka).norm():.6e}")
print(f"  ||Kc - Ka||_F = {(Kc-Ka).norm():.6e}")

print("\nForced response — sweeping freqs to find where θ matters:")
print(f"{'freq (Hz)':<10} {'|amp| at θ=0':<18} {'|amp| at θ=45':<18} {'rel diff':<10}")
for freq_hz in [50, 100, 200, 300, 400, 500, 700, 1000, 1500, 2000]:
    freq = torch.tensor(float(freq_hz), dtype=torch.float64)
    amp_a = plate.amplitude_at_frequency(H, theta_a, freq, damping_ratio=0.02)
    amp_b = plate.amplitude_at_frequency(H, theta_b, freq, damping_ratio=0.02)
    rel = (amp_b - amp_a).norm() / amp_a.norm()
    print(f"{freq_hz:<10} {amp_a.abs().max().item():<18.4e} {amp_b.abs().max().item():<18.4e} {rel.item():<10.2e}")

# Also load the actual W10 H for diagonal and try its freqs
print("\nReal H from CF-PETG diagonal run, at W10-picked freqs:")
import numpy as np
H_real = np.loadtxt('candidates/bat_cfpetg_diagonal/H.csv', delimiter=',')
H_real_t = torch.tensor(H_real * 1e-3, dtype=torch.float64)
H_real_up = plate.upsample(H_real_t)
import json
freqs = json.load(open('candidates/bat_cfpetg_diagonal/w10_optimization_summary.json'))['frequencies_hz']
for f in freqs[:6]:
    freq = torch.tensor(float(f), dtype=torch.float64)
    amp_a = plate.amplitude_at_frequency(H_real_t, theta_a, freq, damping_ratio=0.02)
    amp_b = plate.amplitude_at_frequency(H_real_t, theta_b, freq, damping_ratio=0.02)
    rel = (amp_b - amp_a).norm() / amp_a.norm()
    print(f"  freq={f:.1f} Hz  |amp|_max(θ=0)={amp_a.abs().max():.3e}  |amp|_max(θ=45°)={amp_b.abs().max():.3e}  rel_diff={rel:.3e}")
