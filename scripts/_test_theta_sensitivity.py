"""Crucial sanity check: does the W10 surrogate actually USE θ?

We take a converged CF-PETG run (diagonal target), keep its H + ω + weights,
and recompute the surrogate enrichment with θ replaced by:
    1. The original drifted θ (std=51.6°)
    2. Uniform θ = 0
    3. Uniform θ = π/4

If the surrogate enrichment is the same across all three, then the surrogate's
"signal through θ" is essentially zero — explains why W10 doesn't drive θ to
uniform: it doesn't drive it anywhere coherent because the gradient is ~0. /
检验 surrogate 对 θ 的实际敏感性
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

os.environ.setdefault("MPLCONFIGDIR", str(PROJECT / "data" / ".matplotlib_cache"))
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

import json
import numpy as np
import torch
import yaml

from src.physics.orthotropic_plate import OrthotropicPlate
from src.physics.recognisability_loss import (
    combined_recognisability_loss,
    RecognisabilityLossWeights as LossWeights,
    compose_multifreq_amplitude_with_weights,
)


def load_target(path: Path) -> np.ndarray:
    return np.load(path).astype(np.float64)


def evaluate_surrogate(H_mm, theta_deg, freqs_hz, weights, target_npy_path,
                        stiffness_ratio, shear_ratio, plate_cfg, verbose=False) -> dict:
    """Recompute surrogate enrichment for given (H, θ, ω, w).
    Returns dict of (enrichment, recall, contrast)."""
    cfg = plate_cfg
    plate = OrthotropicPlate(
        cfg, proxy_grid_size=25, base_accel=1.0, default_damping=0.02,
        reference_frequency_hz=600.0,
        stiffness_ratio=stiffness_ratio, shear_ratio=shear_ratio,
        dtype=torch.float64, device="cpu",
    )
    if verbose:
        print(f"  plate: sr={plate.stiffness_ratio:.2f}  E∥={plate.E_parallel_pa:.3e}  E⊥={plate.E_perp_pa:.3e}  ρ={plate.rho_kg_m3:.0f}")
    H_m = torch.tensor(H_mm * 1e-3, dtype=torch.float64)
    theta_rad = torch.tensor(np.deg2rad(theta_deg), dtype=torch.float64)
    f_t = torch.tensor(np.asarray(freqs_hz), dtype=torch.float64)
    w_t = torch.tensor(np.asarray(weights), dtype=torch.float64)
    target = load_target(target_npy_path)
    # Downsample target to proxy_grid_size = 25
    proxy = 25
    bins = np.linspace(0, target.shape[0], proxy + 1).astype(int)
    tgt_proxy = np.zeros((proxy, proxy), dtype=np.float64)
    for i in range(proxy):
        for j in range(proxy):
            block = target[bins[i]:bins[i+1], bins[j]:bins[j+1]]
            tgt_proxy[i, j] = block.mean() > 0.3
    tgt_proxy_t = torch.tensor(tgt_proxy, dtype=torch.float64)

    per_freq_responses = []
    with torch.no_grad():
        for freq in f_t:
            amp = plate.amplitude_at_frequency(H_m, theta_rad, freq, damping_ratio=0.02)
            per_freq_responses.append(amp)
    composite_amp = compose_multifreq_amplitude_with_weights(per_freq_responses, w_t)
    if verbose:
        print(f"  composite_amp stats: mean={composite_amp.abs().mean():.3e}  max={composite_amp.abs().max():.3e}  θ range=[{theta_rad.min().item()*180/3.14159:.1f}°, {theta_rad.max().item()*180/3.14159:.1f}°]")
    composite_complex = composite_amp.to(torch.complex128) + 0.0j
    lw = LossWeights()
    lw.sigma_rel = 0.025
    _, parts = combined_recognisability_loss(composite_complex, tgt_proxy_t, weights=lw)
    return {
        "enrichment": float(parts["enrichment"].item()),
        "recall": float(parts["recall"].item()),
        "contrast": float(parts["contrast"].item()),
    }


def main() -> int:
    cfg_path = PROJECT / "config.yaml"
    plate_cfg = yaml.safe_load(cfg_path.read_text())

    target_path = PROJECT / "data" / "processed_targets" / "target_diagonal.npy"

    runs = [
        ("CF-PETG diagonal  (θ drift)", "candidates/bat_cfpetg_diagonal", 3.0, 1.0),
        ("PLA diagonal      (θ frozen by sr=1)", "candidates/bat_pla_diagonal", 1.0, 1.0),
    ]

    print(f"{'run':<42} {'θ pattern':<22} {'surr enr':<10} {'surr rec':<10}")
    print('-' * 90)
    for label, cand_dir, sr, gr in runs:
        cand = PROJECT / cand_dir
        H = np.loadtxt(cand / "H.csv", delimiter=",")
        theta_orig = np.loadtxt(cand / "theta_continuous_deg.csv", delimiter=",")
        w10_sum = json.loads((cand / "w10_optimization_summary.json").read_text())
        freqs = w10_sum["frequencies_hz"]
        weights = w10_sum["weights"]

        # Original
        r_orig = evaluate_surrogate(H, theta_orig, freqs, weights, target_path, sr, gr, plate_cfg, verbose=True)
        # θ = 0 uniform
        r_zero = evaluate_surrogate(H, np.zeros_like(theta_orig), freqs, weights, target_path, sr, gr, plate_cfg, verbose=True)
        # θ = 45° uniform
        r_45 = evaluate_surrogate(H, np.full_like(theta_orig, 45.0), freqs, weights, target_path, sr, gr, plate_cfg, verbose=True)

        print(f"{label:<42} {'original (drift)':<22} {r_orig['enrichment']:<10.4f} {r_orig['recall']:<10.4f}")
        print(f"{label:<42} {'uniform θ=0':<22} {r_zero['enrichment']:<10.4f} {r_zero['recall']:<10.4f}")
        print(f"{label:<42} {'uniform θ=45°':<22} {r_45['enrichment']:<10.4f} {r_45['recall']:<10.4f}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
