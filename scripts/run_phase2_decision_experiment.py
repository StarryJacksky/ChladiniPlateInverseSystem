"""Phase 2 决策实验：测试 H+θ 扰动对 COMSOL eigenmode 形状/IC-likeness 的影响。

核心问题：trust-region 真的能用 H+θ 调控 reshape COMSOL eigenmode 吗？
还是 mode shape 对设计变量过于"刚性"，Phase 2 就是不归路？

方法：
1. 5 个扰动设计 vs baseline (W10 tier2)
   - A1: H upper-left 4×4 +25%
   - A2: H lower-right 4×4 -25%
   - B1: θ upper half rows +π/4
   - B2: θ NE/SW 对角块 +π/3
   - C: H 中心 5×5 ×2 厚度（强扰动）
2. 每个跑 COMSOL eigfreq（30 modes）
3. 对每阶 eigenmode 计算 IC-likeness（与 Phase 1 一致）
4. 决策矩阵：
   - top-3 IC enrichment 是否变 >15%？
   - 是否有 NEW 模态进入 top-5？
   - composite (best 2 modes) 是否能超过 Phase 1 的 3.82×？
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image

from src.config import load_config
from src.scoring.recognisability_score import (
    chladni_powder_density,
    coverage_recall,
    recognisability_score_grid,
)
from src.comsol.credentials import ensure_comsol_credentials
from src.comsol.discovery import config_with_runtime_discovery
from src.comsol.export_parameters import export_candidate_for_comsol
from src.comsol.run_livelink import (
    DEFAULT_MATLAB_PATH,
    apply_comsol_server_environment,
    matlab_path_from_comsol_command,
    matlab_quote,
    run_command_streamed,
)
from src.comsol.server import ensure_comsol_server
from scripts.run_modal_calibration_probe import write_material_parameters_csv, write_dummy_actuator_csv, write_support_csv
from scripts.run_modal_calibration_w10design import write_theta_field_csv


def generate_perturbations(H_base: np.ndarray, theta_base: np.ndarray) -> dict[str, dict]:
    """Generate 5 perturbation designs."""
    grid = H_base.shape[0]
    perturbs = {}

    # Baseline (no change)
    perturbs["baseline"] = {"H": H_base.copy(), "theta": theta_base.copy(), "desc": "W10 tier2 unchanged"}

    # A1: H upper-left 4x4 +25%
    H = H_base.copy(); H[:4, :4] = np.clip(H[:4, :4] * 1.25, 0.5, 5.0)
    perturbs["A1_Hul_p25"] = {"H": H, "theta": theta_base.copy(), "desc": "H upper-left 4x4 +25%"}

    # A2: H lower-right 4x4 -25%
    H = H_base.copy(); H[-4:, -4:] = np.clip(H[-4:, -4:] * 0.75, 0.5, 5.0)
    perturbs["A2_Hlr_m25"] = {"H": H, "theta": theta_base.copy(), "desc": "H lower-right 4x4 -25%"}

    # B1: θ upper half rows + π/4
    th = theta_base.copy(); th[:grid//2, :] = th[:grid//2, :] + np.pi / 4
    perturbs["B1_th_upper_p45"] = {"H": H_base.copy(), "theta": th, "desc": "θ upper half +π/4"}

    # B2: θ NE/SW diagonal blocks + π/3
    th = theta_base.copy()
    half = grid // 2
    th[:half, half:] = th[:half, half:] + np.pi / 3  # NE
    th[half:, :half] = th[half:, :half] + np.pi / 3  # SW
    perturbs["B2_th_NESW_p60"] = {"H": H_base.copy(), "theta": th, "desc": "θ NE+SW blocks +π/3"}

    # C: H 中心 5x5 ×2 (大扰动)
    H = H_base.copy()
    c = grid // 2
    H[c-2:c+3, c-2:c+3] = np.clip(H[c-2:c+3, c-2:c+3] * 2.0, 0.5, 5.0)
    perturbs["C_Hcenter_x2"] = {"H": H, "theta": theta_base.copy(), "desc": "H center 5x5 ×2 (大扰动)"}

    return perturbs


def run_comsol_eigfreq_for_design(name: str, H: np.ndarray, theta: np.ndarray,
                                   plate_length_mm: float, material: dict, runtime_config: dict,
                                   stiffness_ratio: float = 12.0, shear_ratio: float = 1.5,
                                   n_modes: int = 30, freq_lower_hz: float = 10.0) -> Path:
    paths = {"candidates": Path(runtime_config["paths"]["candidates_dir"]),
             "comsol_exports": Path(runtime_config["paths"]["comsol_exports_dir"])}
    cand_dir = paths["candidates"] / f"phase2_decision_{name}"
    if cand_dir.exists():
        shutil.rmtree(cand_dir)
    cand_dir.mkdir(parents=True)
    np.savetxt(cand_dir / "H.csv", H, delimiter=",", fmt="%.6f")
    write_theta_field_csv(theta, plate_length_mm, cand_dir / "theta_field.csv")
    write_support_csv(cand_dir / "support_parameters.csv", clamp_radius_mm=8.0)
    write_dummy_actuator_csv(cand_dir / "actuator_parameters.csv")
    export_candidate_for_comsol(cand_dir, material)
    write_material_parameters_csv(material, stiffness_ratio, shear_ratio, cand_dir / "material_parameters.csv")

    comsol_config = runtime_config.get("comsol", {})
    matlab = str(comsol_config.get("matlab_path", DEFAULT_MATLAB_PATH))
    model = Path(comsol_config.get("model_path", "comsol_templates/Chladni_15x15_bound.mph"))
    runner_dir = Path("comsol_templates").resolve()
    export_dir = paths["comsol_exports"] / f"phase2_decision_{name}" / "eigenfrequency"
    export_dir.mkdir(parents=True, exist_ok=True)
    mli_path = matlab_path_from_comsol_command(comsol_config.get("comsol_command_path", ""))

    parts = []
    if mli_path: parts += [f"setenv('COMSOL_MLI_PATH',{matlab_quote(mli_path)})", f"addpath({matlab_quote(mli_path)})"]
    parts.append(f"addpath({matlab_quote(runner_dir)})")
    parts.append(f"run_chladni_eigenfrequency_orthotropic({matlab_quote(model.resolve())},{matlab_quote(cand_dir.resolve())},{matlab_quote(export_dir.resolve())},{n_modes},{freq_lower_hz})")
    cmd = [matlab, "-nosplash", "-noFigureWindows", "-sd", str(Path.cwd()), "-batch", "; ".join(parts)]
    log_path = export_dir / "livelink_eigenfrequency.log"
    rc, _ = run_command_streamed(cmd, log_path, timeout_s=600.0)
    if rc != 0:
        raise RuntimeError(f"COMSOL eigfreq failed for {name}; rc={rc}; see {log_path}")
    return export_dir


def compute_ic_likeness_per_mode(eig_dir: Path, target: np.ndarray, image_size: int, plate_length_mm: float, n_modes: int = 30) -> list[dict]:
    """For each eigenmode, compute IC-likeness enrichment & recall (broad metric)."""
    from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid
    arr = np.loadtxt(eig_dir / "eigenfrequencies.csv", delimiter=",", skiprows=1)
    if arr.ndim == 1: arr = arr.reshape(-1, 2)
    n_modes = min(n_modes, len(arr))
    freqs = arr[:n_modes, 1].astype(float)
    xy = np.loadtxt(eig_dir / "mode_xy.csv", delimiter=",", skiprows=1)
    x, y = xy[:, 0], xy[:, 1]
    rows = []
    for k in range(1, n_modes + 1):
        try:
            m = np.loadtxt(eig_dir / f"mode_{k:03d}.csv", delimiter=",", skiprows=1)
            if m.ndim == 1: m = m.reshape(-1, 2)
            amp = np.sqrt(m[:, 0] ** 2 + m[:, 1] ** 2)
            grid = downsample_comsol_xy_to_grid(x, y, amp, image_size, plate_length_mm)
            if grid.max() > 1e-30: grid = grid / grid.max()
            s = recognisability_score_grid(grid, target.astype(bool), sigma_rel=0.05, percentile=20.0)
            rec = float(coverage_recall(grid, target.astype(bool), percentile=20.0))
            rows.append({"mode": k, "freq_hz": float(freqs[k-1]),
                          "enrichment": float(s["enrichment_factor"]),
                          "recall": rec})
        except Exception as ex:
            rows.append({"mode": k, "freq_hz": float(freqs[k-1]),
                          "enrichment": float("nan"), "recall": float("nan"), "error": str(ex)})
    return rows


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--source-candidate", default="w10_ic_tier2_sr12")
    p.add_argument("--n-modes", type=int, default=30)
    p.add_argument("--image-size", type=int, default=256)
    p.add_argument("--output-dir", default="reports/sprint2_phase2_decision")
    p.add_argument("--skip-comsol", action="store_true", help="Reuse existing eigfreq exports.")
    return p.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)
    runtime_config, _, _ = config_with_runtime_discovery(config)
    plate_length_mm = float(config["project"]["plate_length_mm"])
    material = runtime_config.get("material", {})
    image_size = int(args.image_size)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load target
    target = np.load("data/processed_targets/target_binary.npy").astype(bool)
    if target.shape != (image_size, image_size):
        img = Image.fromarray((target.astype(np.uint8) * 255))
        img = img.resize((image_size, image_size), resample=Image.NEAREST)
        target = (np.array(img) > 127).astype(bool)

    # Load W10 tier2 baseline
    H_base = np.loadtxt(Path("candidates") / args.source_candidate / "H.csv", delimiter=",")
    theta_base = np.loadtxt(Path("candidates") / args.source_candidate / "theta_continuous_rad.csv", delimiter=",")

    # Generate perturbations
    perturbs = generate_perturbations(H_base, theta_base)
    print(f"Generated {len(perturbs)} designs (incl baseline):")
    for name, info in perturbs.items():
        print(f"  {name}: {info['desc']}")

    # Run COMSOL eigfreq for each
    if not args.skip_comsol:
        ensure_comsol_credentials(runtime_config)
        apply_comsol_server_environment(runtime_config)
        if not ensure_comsol_server(runtime_config, wait_s=60.0):
            raise RuntimeError("COMSOL server not reachable.")
        time.sleep(1.0)

    results = {}
    for name, info in perturbs.items():
        print(f"\n>>> Running COMSOL eigfreq for {name}...")
        eig_dir = Path("data/comsol_exports") / f"phase2_decision_{name}" / "eigenfrequency"
        if not args.skip_comsol or not (eig_dir / "eigenfrequencies.csv").exists():
            t0 = time.time()
            eig_dir = run_comsol_eigfreq_for_design(name, info["H"], info["theta"],
                                                      plate_length_mm, material, runtime_config,
                                                      n_modes=args.n_modes)
            print(f"  finished in {time.time()-t0:.1f}s")
        rows = compute_ic_likeness_per_mode(eig_dir, target, image_size, plate_length_mm, args.n_modes)
        rows_sorted = sorted([r for r in rows if not np.isnan(r["enrichment"])], key=lambda x: -x["enrichment"])
        results[name] = {
            "desc": info["desc"],
            "eig_dir": str(eig_dir),
            "all_modes": rows,
            "top5": rows_sorted[:5],
            "best_enrichment": float(rows_sorted[0]["enrichment"]) if rows_sorted else float("nan"),
            "best_2_mean_enrichment": float(np.mean([r["enrichment"] for r in rows_sorted[:2]])) if len(rows_sorted) >= 2 else float("nan"),
        }
        print(f"  top-3 IC-likeness modes for {name}:")
        for r in rows_sorted[:3]:
            print(f"    mode {r['mode']:3d} @ {r['freq_hz']:7.2f}Hz: enrich={r['enrichment']:.3f}  recall={r['recall']:.3f}")

    # Decision matrix
    baseline_best = results["baseline"]["best_enrichment"]
    baseline_best2 = results["baseline"]["best_2_mean_enrichment"]
    print(f"\n=== DECISION MATRIX ===")
    print(f"{'perturbation':<25} {'best_enrich':>11} {'Δ%':>8} {'best2_mean':>11} {'Δ%':>8}")
    for name, r in results.items():
        if name == "baseline": continue
        dpct = (r["best_enrichment"] - baseline_best) / baseline_best * 100
        d2pct = (r["best_2_mean_enrichment"] - baseline_best2) / baseline_best2 * 100
        print(f"{name:<25} {r['best_enrichment']:>11.3f} {dpct:>+7.1f}% {r['best_2_mean_enrichment']:>11.3f} {d2pct:>+7.1f}%")
    print(f"{'baseline':<25} {baseline_best:>11.3f} {'   0.0%':>8} {baseline_best2:>11.3f} {'   0.0%':>8}")

    # Verdict
    perturb_only = {n: r for n, r in results.items() if n != "baseline"}
    max_change_best = max(abs((r["best_enrichment"] - baseline_best) / baseline_best * 100) for r in perturb_only.values())
    max_change_top2 = max(abs((r["best_2_mean_enrichment"] - baseline_best2) / baseline_best2 * 100) for r in perturb_only.values())
    if max_change_best > 15 or max_change_top2 > 15:
        verdict = "GREEN"
        verdict_msg = f"H+θ 扰动能让 top-mode enrichment 变 {max_change_best:.0f}%，trust-region 有梯度信号可用，Phase 2 可行。"
    elif max_change_best > 5 or max_change_top2 > 5:
        verdict = "YELLOW"
        verdict_msg = f"H+θ 扰动只让 top enrichment 变 {max_change_best:.0f}%，trust-region 能挤出小幅提升，但天花板可能 ≤5×。"
    else:
        verdict = "RED"
        verdict_msg = f"H+θ 扰动几乎不动 top enrichment（max {max_change_best:.1f}%）；mode shape 对设计变量刚性，Phase 2 是不归路。"
    print(f"\n=== VERDICT: {verdict} ===\n{verdict_msg}")

    # Visualisation
    fig, axes = plt.subplots(len(results), 4, figsize=(16, 4 * len(results)))
    if axes.ndim == 1: axes = axes.reshape(1, -1)
    from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid
    for ri, (name, r) in enumerate(results.items()):
        # Col 0: H field
        axes[ri, 0].imshow(perturbs[name]["H"], cmap="viridis", origin="upper")
        axes[ri, 0].set_title(f"{name}\nH field (mm)")
        # Col 1: θ field
        axes[ri, 1].imshow(perturbs[name]["theta"], cmap="hsv", origin="upper", vmin=-np.pi, vmax=np.pi)
        axes[ri, 1].set_title("θ field (rad)")
        # Col 2: top-1 IC mode powder
        if r["top5"]:
            top = r["top5"][0]
            eig_dir = Path(r["eig_dir"])
            try:
                m = np.loadtxt(eig_dir / f"mode_{int(top['mode']):03d}.csv", delimiter=",", skiprows=1)
                if m.ndim == 1: m = m.reshape(-1, 2)
                xy = np.loadtxt(eig_dir / "mode_xy.csv", delimiter=",", skiprows=1)
                amp = np.sqrt(m[:, 0]**2 + m[:, 1]**2)
                grid = downsample_comsol_xy_to_grid(xy[:, 0], xy[:, 1], amp, image_size, plate_length_mm)
                if grid.max() > 1e-30: grid /= grid.max()
                d = chladni_powder_density(grid, sigma_rel=0.012)
                axes[ri, 2].imshow(d, cmap="hot", origin="upper")
                axes[ri, 2].set_title(f"top mode #{top['mode']} @ {top['freq_hz']:.0f}Hz\nenr={top['enrichment']:.3f}")
            except Exception:
                axes[ri, 2].text(0.5, 0.5, "err", ha="center", transform=axes[ri, 2].transAxes)
        # Col 3: top-2 RMS composite
        if len(r["top5"]) >= 2:
            try:
                m1 = np.loadtxt(eig_dir / f"mode_{int(r['top5'][0]['mode']):03d}.csv", delimiter=",", skiprows=1)
                m2 = np.loadtxt(eig_dir / f"mode_{int(r['top5'][1]['mode']):03d}.csv", delimiter=",", skiprows=1)
                if m1.ndim == 1: m1 = m1.reshape(-1, 2)
                if m2.ndim == 1: m2 = m2.reshape(-1, 2)
                xy = np.loadtxt(eig_dir / "mode_xy.csv", delimiter=",", skiprows=1)
                a1 = np.sqrt(m1[:, 0]**2 + m1[:, 1]**2); a2 = np.sqrt(m2[:, 0]**2 + m2[:, 1]**2)
                g1 = downsample_comsol_xy_to_grid(xy[:, 0], xy[:, 1], a1, image_size, plate_length_mm)
                g2 = downsample_comsol_xy_to_grid(xy[:, 0], xy[:, 1], a2, image_size, plate_length_mm)
                if g1.max() > 1e-30: g1 /= g1.max()
                if g2.max() > 1e-30: g2 /= g2.max()
                comp = np.sqrt(0.5 * (g1**2 + g2**2))
                if comp.max() > 1e-30: comp /= comp.max()
                s = recognisability_score_grid(comp, target.astype(bool), sigma_rel=0.05, percentile=20.0)
                rec = float(coverage_recall(comp, target.astype(bool), percentile=20.0))
                d = chladni_powder_density(comp, sigma_rel=0.012)
                axes[ri, 3].imshow(d, cmap="hot", origin="upper")
                axes[ri, 3].set_title(f"top-2 RMS composite\nenr={s['enrichment_factor']:.3f} rec={rec:.3f}")
            except Exception:
                axes[ri, 3].text(0.5, 0.5, "err", ha="center", transform=axes[ri, 3].transAxes)
        for c in range(4): axes[ri, c].axis("off") if c != 0 else None
        axes[ri, 0].axis("off"); axes[ri, 1].axis("off")
    plt.suptitle(f"Phase 2 decision experiment: H+θ perturbations vs baseline ({verdict})", fontsize=13, fontweight="bold")
    plt.tight_layout()
    fig.savefig(out_dir / "phase2_decision.png", dpi=120, bbox_inches="tight")
    plt.close(fig)

    # Save summary
    summary = {
        "verdict": verdict,
        "verdict_msg": verdict_msg,
        "baseline_best_enrichment": float(baseline_best),
        "baseline_best2_enrichment": float(baseline_best2),
        "max_change_best_pct": float(max_change_best),
        "max_change_top2_pct": float(max_change_top2),
        "per_perturbation": {name: {"desc": r["desc"], "top5": r["top5"], "best": r["best_enrichment"], "best_2_mean": r["best_2_mean_enrichment"]} for name, r in results.items()},
    }
    (out_dir / "phase2_decision_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nArtefacts:\n  {out_dir/'phase2_decision.png'}\n  {out_dir/'phase2_decision_summary.json'}")


if __name__ == "__main__":
    main()
