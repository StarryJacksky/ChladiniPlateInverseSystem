"""Compare COMSOL eigenmodes with surrogate (OrthotropicPlate) eigenmodes for the same nominal plate.

For a nominal plate (H=2mm uniform, θ=0 everywhere, ortho E1/E2=12, G/G_iso=1.5):
- Load COMSOL eigfreqs + mode shapes from data/comsol_exports/.../eigenfrequency/
- Compute surrogate K, M via OrthotropicPlate; solve generalized eigenvalue problem
- Match modes 1-by-1 using Modal Assurance Criterion (MAC)
- Output:
  - Frequency mapping plot: f_comsol vs f_surrogate
  - Linear fit f_comsol = α * f_surrogate^β
  - Mode-shape MAC matrix
  - JSON decision_summary.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import torch
import matplotlib.pyplot as plt
from scipy.linalg import eigh

from src.config import load_config
from src.physics.orthotropic_plate import OrthotropicPlate


def load_comsol_modes(eig_dir: Path, n_modes: int) -> tuple[np.ndarray, list[np.ndarray], np.ndarray, np.ndarray]:
    """Returns: (freqs[n], modes_list[n] each (n_pts,), x[n_pts], y[n_pts])"""
    eig_csv = eig_dir / "eigenfrequencies.csv"
    arr = np.loadtxt(eig_csv, delimiter=",", skiprows=1)
    if arr.ndim == 1: arr = arr.reshape(-1, 2)
    freqs = arr[:n_modes, 1].astype(float)
    xy = np.loadtxt(eig_dir / "mode_xy.csv", delimiter=",", skiprows=1)
    x, y = xy[:, 0], xy[:, 1]
    modes = []
    for k in range(1, n_modes + 1):
        m = np.loadtxt(eig_dir / f"mode_{k:03d}.csv", delimiter=",", skiprows=1)
        if m.ndim == 1: m = m.reshape(-1, 2)
        # Use real part (eigenmodes for undamped problem should be real up to phase)
        mode = m[:, 0]  # real
        modes.append(mode)
    return freqs, modes, x, y


def downsample_comsol_to_proxy(x_m: np.ndarray, y_m: np.ndarray, mode: np.ndarray, proxy_n: int, plate_length_mm: float) -> np.ndarray:
    """Bin (irregular x,y,mode) onto proxy_n × proxy_n grid by averaging."""
    half_m = plate_length_mm / 2000.0
    edges = np.linspace(-half_m, half_m, proxy_n + 1)
    col = np.clip(np.searchsorted(edges, x_m, side="right") - 1, 0, proxy_n - 1)
    row_from_bottom = np.clip(np.searchsorted(edges, y_m, side="right") - 1, 0, proxy_n - 1)
    row = proxy_n - 1 - row_from_bottom
    accum = np.zeros((proxy_n, proxy_n), dtype=float)
    counts = np.zeros((proxy_n, proxy_n), dtype=int)
    np.add.at(accum, (row, col), mode)
    np.add.at(counts, (row, col), 1)
    grid = np.where(counts > 0, accum / np.where(counts > 0, counts, 1), 0.0)
    # Dilate to fill holes
    from scipy.ndimage import binary_dilation, grey_dilation
    mask = counts > 0
    for _ in range(6):
        if mask.all(): break
        expanded = binary_dilation(mask)
        new = expanded & ~mask
        if not new.any(): break
        gd = grey_dilation(grid, size=3)
        grid = np.where(new, gd, grid)
        mask = mask | new
    return grid


def compute_surrogate_eigenmodes(plate: OrthotropicPlate, H_proxy_mm: torch.Tensor, theta_proxy_rad: torch.Tensor, n_modes: int) -> tuple[np.ndarray, list[np.ndarray]]:
    """Solve generalised eigenvalue problem K φ = ω² M φ on free DOFs."""
    K, M_diag = plate.assemble_K_M(H_proxy_mm, theta_proxy_rad)
    free = plate.free_indices
    K_free = K.index_select(0, free).index_select(1, free).cpu().numpy()
    M_free = M_diag.index_select(0, free).cpu().numpy()
    # Symmetrise
    K_free = 0.5 * (K_free + K_free.T)
    M_mat = np.diag(M_free)
    # eigh: returns ascending eigenvalues
    eigvals, eigvecs = eigh(K_free, M_mat)
    eigvals = np.maximum(eigvals, 0.0)
    omega = np.sqrt(eigvals)
    freqs = omega / (2.0 * np.pi)
    # Build full-grid modes
    modes = []
    free_idx = free.cpu().numpy()
    for k in range(min(n_modes, eigvecs.shape[1])):
        full = np.zeros(plate.N * plate.N, dtype=float)
        full[free_idx] = eigvecs[:, k]
        modes.append(full.reshape(plate.N, plate.N))
    return freqs[:n_modes], modes


def mac_matrix(comsol_grid_modes: list[np.ndarray], surrogate_modes: list[np.ndarray]) -> np.ndarray:
    """Modal Assurance Criterion: MAC_ij = (φ_i · ψ_j)² / (||φ_i||² ||ψ_j||²)"""
    n_c = len(comsol_grid_modes)
    n_s = len(surrogate_modes)
    M = np.zeros((n_c, n_s), dtype=float)
    for i, ci in enumerate(comsol_grid_modes):
        for j, sj in enumerate(surrogate_modes):
            ci_flat = ci.flatten()
            sj_flat = sj.flatten()
            num = float(np.abs(np.dot(ci_flat, sj_flat))) ** 2
            den = float(np.dot(ci_flat, ci_flat)) * float(np.dot(sj_flat, sj_flat))
            M[i, j] = num / (den + 1e-30)
    return M


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--n-modes", type=int, default=30)
    p.add_argument("--proxy-n", type=int, default=25, help="Surrogate proxy grid (must match orthotropic_plate default).")
    p.add_argument("--H-mm", type=float, default=2.0)
    p.add_argument("--theta-rad", type=float, default=0.0)
    p.add_argument("--H-csv", default="", help="Optional path to non-uniform H.csv (overrides --H-mm).")
    p.add_argument("--theta-csv", default="", help="Optional path to theta_continuous_rad.csv (overrides --theta-rad).")
    p.add_argument("--stiffness-ratio", type=float, default=12.0)
    p.add_argument("--shear-ratio", type=float, default=1.5)
    p.add_argument("--candidate-name", default="modal_calibration_nominal_orthotropic")
    p.add_argument("--output-dir", default="reports/modal_calibration")
    p.add_argument("--output-tag", default="", help="Tag appended to output filenames to distinguish runs.")
    args = p.parse_args()

    config = load_config(args.config)
    plate_length_mm = float(config["project"]["plate_length_mm"])
    design_grid = int(config["project"]["grid_size"])

    # === Surrogate eigenmodes ===
    plate = OrthotropicPlate(
        config=config,
        proxy_grid_size=args.proxy_n,
        stiffness_ratio=args.stiffness_ratio,
        shear_ratio=args.shear_ratio,
        dtype=torch.float64,
    )
    if args.H_csv:
        H_arr = np.loadtxt(args.H_csv, delimiter=",")
        H_design = torch.tensor(H_arr, dtype=torch.float64)
    else:
        H_design = torch.full((design_grid, design_grid), float(args.H_mm), dtype=torch.float64)
    if args.theta_csv:
        theta_arr = np.loadtxt(args.theta_csv, delimiter=",")
        theta_design = torch.tensor(theta_arr, dtype=torch.float64)
    else:
        theta_design = torch.full((design_grid, design_grid), float(args.theta_rad), dtype=torch.float64)
    H_proxy = plate.upsample(H_design)
    theta_proxy = plate.upsample(theta_design)
    surrogate_freqs, surrogate_modes = compute_surrogate_eigenmodes(plate, H_proxy, theta_proxy, args.n_modes)
    print(f"Surrogate eigenfrequencies (first 10):")
    for k in range(min(10, len(surrogate_freqs))):
        print(f"  mode {k+1:3d}: {surrogate_freqs[k]:.3f} Hz")
    print(f"  ... {len(surrogate_freqs)} total")

    # === COMSOL eigenmodes ===
    eig_dir = Path("data/comsol_exports") / args.candidate_name / "eigenfrequency"
    comsol_freqs, comsol_modes_raw, x_m, y_m = load_comsol_modes(eig_dir, args.n_modes)
    # Downsample each COMSOL mode to surrogate proxy grid
    comsol_modes_proxy = [downsample_comsol_to_proxy(x_m, y_m, m, plate.N, plate_length_mm) for m in comsol_modes_raw]

    # === MAC matrix ===
    mac = mac_matrix(comsol_modes_proxy, surrogate_modes)
    # Best-match (greedy on COMSOL side)
    best_surrogate_for_comsol = np.argmax(mac, axis=1)
    best_mac_value = mac[np.arange(len(comsol_freqs)), best_surrogate_for_comsol]

    # === Frequency mapping ===
    matched_pairs = []
    for ci in range(len(comsol_freqs)):
        sj = int(best_surrogate_for_comsol[ci])
        matched_pairs.append({
            "comsol_mode": ci + 1,
            "comsol_freq_hz": float(comsol_freqs[ci]),
            "surrogate_mode": sj + 1,
            "surrogate_freq_hz": float(surrogate_freqs[sj]),
            "mac": float(mac[ci, sj]),
            "freq_ratio_comsol_over_surrogate": float(comsol_freqs[ci] / surrogate_freqs[sj]) if surrogate_freqs[sj] > 1e-6 else float("nan"),
        })

    # Linear fit on log-freq for modes with MAC > 0.3
    well_matched = [p for p in matched_pairs if p["mac"] > 0.3 and p["surrogate_freq_hz"] > 1.0]
    if len(well_matched) >= 3:
        log_s = np.log(np.array([p["surrogate_freq_hz"] for p in well_matched]))
        log_c = np.log(np.array([p["comsol_freq_hz"] for p in well_matched]))
        # log f_c = beta * log f_s + log alpha
        coef = np.polyfit(log_s, log_c, 1)
        beta_fit = float(coef[0])
        alpha_fit = float(np.exp(coef[1]))
    else:
        beta_fit, alpha_fit = float("nan"), float("nan")

    print(f"\n=== Modal matching summary ===")
    print(f"{'COMSOL #':>10} {'f_comsol':>10} {'surr #':>8} {'f_surr':>10} {'MAC':>8} {'ratio':>8}")
    for pr in matched_pairs[:20]:
        print(f"{pr['comsol_mode']:>10d} {pr['comsol_freq_hz']:>10.2f} {pr['surrogate_mode']:>8d} {pr['surrogate_freq_hz']:>10.2f} {pr['mac']:>8.3f} {pr['freq_ratio_comsol_over_surrogate']:>8.3f}")

    print(f"\nFrequency fit (MAC>0.3, n={len(well_matched)}): f_c = {alpha_fit:.3f} * f_s^{beta_fit:.3f}")
    well_macs = [p["mac"] for p in matched_pairs[:20]]
    mean_mac = float(np.mean(well_macs))
    n_good = int(sum(1 for m in well_macs if m > 0.5))
    print(f"First-20 modes: mean MAC={mean_mac:.3f}, modes with MAC>0.5: {n_good}/20")

    # === Visualisation ===
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(1, 2, figsize=(14, 5))
    # Freq mapping
    s_freqs_all = np.array([p["surrogate_freq_hz"] for p in matched_pairs])
    c_freqs_all = np.array([p["comsol_freq_hz"] for p in matched_pairs])
    macs_all = np.array([p["mac"] for p in matched_pairs])
    sc = ax[0].scatter(s_freqs_all, c_freqs_all, c=macs_all, s=60, cmap="viridis", vmin=0, vmax=1, edgecolors="black", linewidths=0.5)
    fmin = min(s_freqs_all.min(), c_freqs_all.min())
    fmax = max(s_freqs_all.max(), c_freqs_all.max())
    ax[0].plot([fmin, fmax], [fmin, fmax], "k--", alpha=0.5, label="f_c = f_s (no shift)")
    if np.isfinite(alpha_fit):
        fs_grid = np.linspace(fmin, fmax, 50)
        fc_grid = alpha_fit * fs_grid ** beta_fit
        ax[0].plot(fs_grid, fc_grid, "r-", alpha=0.8, label=f"fit: {alpha_fit:.3f}·f_s^{beta_fit:.3f}")
    ax[0].set_xlabel("Surrogate eigenfrequency (Hz)")
    ax[0].set_ylabel("COMSOL eigenfrequency (Hz)")
    ax[0].set_title("Modal frequency mapping (color = MAC)")
    ax[0].legend()
    ax[0].grid(alpha=0.3)
    plt.colorbar(sc, ax=ax[0], label="MAC")

    # MAC matrix
    im = ax[1].imshow(mac, cmap="hot", origin="upper", vmin=0, vmax=1, aspect="auto")
    ax[1].set_xlabel("Surrogate mode index")
    ax[1].set_ylabel("COMSOL mode index")
    ax[1].set_title("MAC matrix (Modal Assurance Criterion)")
    plt.colorbar(im, ax=ax[1])
    plt.tight_layout()
    fig.suptitle(f"Modal calibration probe: nominal plate (H={args.H_mm}mm, θ=0, sr={args.stiffness_ratio})", fontsize=11, y=1.02)
    tag = f"_{args.output_tag}" if args.output_tag else ""
    fig.savefig(output_dir / f"modal_calibration{tag}.png", dpi=120, bbox_inches="tight")
    plt.close(fig)

    # Visualise 6 best-matched mode pairs side-by-side
    top_pairs = sorted([p for p in matched_pairs if p["mac"] > 0.3], key=lambda x: -x["mac"])[:6]
    if top_pairs:
        fig, axes = plt.subplots(len(top_pairs), 2, figsize=(8, 3 * len(top_pairs)))
        if len(top_pairs) == 1: axes = axes.reshape(1, 2)
        for ri, pr in enumerate(top_pairs):
            ci = pr["comsol_mode"] - 1
            sj = pr["surrogate_mode"] - 1
            axes[ri, 0].imshow(comsol_modes_proxy[ci], cmap="RdBu_r", origin="upper")
            axes[ri, 0].set_title(f"COMSOL #{pr['comsol_mode']} @ {pr['comsol_freq_hz']:.1f}Hz", fontsize=9)
            axes[ri, 0].axis("off")
            axes[ri, 1].imshow(surrogate_modes[sj], cmap="RdBu_r", origin="upper")
            axes[ri, 1].set_title(f"Surrogate #{pr['surrogate_mode']} @ {pr['surrogate_freq_hz']:.1f}Hz (MAC={pr['mac']:.2f})", fontsize=9)
            axes[ri, 1].axis("off")
        plt.tight_layout()
        fig.savefig(output_dir / f"modal_calibration_mode_pairs{tag}.png", dpi=120, bbox_inches="tight")
        plt.close(fig)

    # === Decision summary ===
    summary = {
        "setup": {
            "H_mm": float(args.H_mm),
            "theta_rad": float(args.theta_rad),
            "stiffness_ratio": float(args.stiffness_ratio),
            "shear_ratio": float(args.shear_ratio),
            "n_modes": int(args.n_modes),
            "proxy_n": int(plate.N),
        },
        "comsol_freqs_hz": comsol_freqs.tolist(),
        "surrogate_freqs_hz": surrogate_freqs.tolist(),
        "matched_pairs": matched_pairs,
        "frequency_fit": {
            "alpha": alpha_fit,
            "beta": beta_fit,
            "n_pairs_used": len(well_matched),
            "interpretation": "f_comsol = alpha * f_surrogate ^ beta (over MAC>0.3 matched pairs)",
        },
        "modal_quality": {
            "mean_mac_first20": mean_mac,
            "n_modes_with_mac_above_0.5_first20": n_good,
        },
    }

    # Decision logic
    if mean_mac > 0.6 and n_good >= 12 and abs(beta_fit - 1.0) < 0.15 and 0.4 < alpha_fit < 1.5:
        decision = "GREEN: modes align well, single-scalar α calibration likely sufficient. Sprint 2 §4 (modal-calibrated W9) is feasible."
    elif mean_mac > 0.35 and n_good >= 6:
        decision = "YELLOW: modes partially align. Calibration possible but needs per-mode mapping (not single scalar). Sprint 2 §4 needs richer calibration table; risk medium."
    else:
        decision = "RED: surrogate modes don't match COMSOL modes. Calibration won't fix it — must switch to direct COMSOL eigenmode optimisation (slow but correct)."
    summary["decision"] = decision
    print(f"\n=== DECISION ===\n{decision}")

    (output_dir / f"modal_calibration_summary{tag}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFigures:\n  {output_dir/('modal_calibration'+tag+'.png')}\n  {output_dir/('modal_calibration_mode_pairs'+tag+'.png')}")
    print(f"Summary: {output_dir/('modal_calibration_summary'+tag+'.json')}")


if __name__ == "__main__":
    main()
