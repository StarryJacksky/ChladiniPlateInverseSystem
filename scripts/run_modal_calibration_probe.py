"""Run COMSOL eigenfrequency analysis on a nominal orthotropic plate to bench-mark surrogate predictions.

Setup:
- Plate 150x150mm, 15x15 design grid (driven via project config)
- Uniform H = 2 mm everywhere
- theta = 0 rad everywhere (uniform fiber direction → orthotropic but globally aligned)
- Material: tier2 = E_iso 2e9, E1/E2 = 12, G/G_iso = 1.5
- Support: 8 mm clamp radius at centre
- No actuator (eigenfrequency only)
- Extract first 30 modes (frequency + shape)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))

import numpy as np

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
from src.config import load_config


def write_uniform_H_csv(grid: int, h_mm: float, output_path: Path) -> None:
    """Write H.csv at design grid resolution."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    H = np.full((grid, grid), float(h_mm), dtype=float)
    np.savetxt(output_path, H, delimiter=",", fmt="%.6f")


def write_uniform_theta_csv(grid: int, theta_rad: float, plate_length_mm: float, output_path: Path) -> None:
    """Write theta_field.csv (whitespace-separated x_m y_m theta_rad) for COMSOL Interpolation spreadsheet format."""
    cell_size_m = float(plate_length_mm) / 1000.0 / grid
    half_m = float(plate_length_mm) / 2000.0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for r in range(grid):
            y_m = +half_m - (r + 0.5) * cell_size_m
            for c in range(grid):
                x_m = -half_m + (c + 0.5) * cell_size_m
                f.write(f"{x_m:.6f} {y_m:.6f} {float(theta_rad):.6f}\n")


def write_support_csv(output_path: Path, center_x_mm: float = 0.0, center_y_mm: float = 0.0, clamp_radius_mm: float = 8.0) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write("center_x_mm,center_y_mm,clamp_radius_mm\n")
        f.write(f"{center_x_mm},{center_y_mm},{clamp_radius_mm}\n")


def write_dummy_actuator_csv(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write("id,x_mm,y_mm,amplitude,phase_deg\n")
        f.write("1,0.0,0.0,0.0,0.0\n")


def write_material_parameters_csv(material: dict, stiffness_ratio: float, shear_ratio: float, output_path: Path) -> dict[str, float]:
    E_iso = float(material["youngs_modulus_pa"])
    nu_iso = float(material["poisson_ratio"])
    density = float(material["density_kg_m3"])
    sr = float(stiffness_ratio)
    g_factor = float(shear_ratio)
    g_iso = E_iso / (2.0 * (1.0 + nu_iso))
    E1 = E_iso * np.sqrt(sr) if sr > 1.0 else E_iso
    E2 = E_iso / np.sqrt(sr) if sr > 1.0 else E_iso
    Ez = E2
    G12 = g_iso * g_factor
    rows = [
        ("mat_density", density, "kg/m^3"),
        ("mat_poisson_ratio", nu_iso, "1"),
        ("mat_youngs_modulus", E_iso, "Pa"),
        ("mat_thermal_conductivity", float(material.get("thermal_conductivity_w_mk", 0.2)), "W/(m*K)"),
        ("mat_heat_capacity", float(material.get("heat_capacity_j_kgk", 1500.0)), "J/(kg*K)"),
        ("mat_thermal_expansion", float(material.get("thermal_expansion_1_k", 8.0e-5)), "1/K"),
        ("mat_E1", E1, "Pa"),
        ("mat_E2", E2, "Pa"),
        ("mat_E_perp_z", Ez, "Pa"),
        ("mat_nu12", nu_iso, "1"),
        ("mat_nu23", nu_iso, "1"),
        ("mat_nu13", nu_iso, "1"),
        ("mat_G12", G12, "Pa"),
        ("mat_G23", g_iso, "Pa"),
        ("mat_G13", g_iso, "Pa"),
        ("mat_stiffness_ratio", sr, "1"),
        ("mat_shear_ratio", g_factor, "1"),
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write("name,value,unit\n")
        for name, value, unit in rows:
            f.write(f"{name},{float(value):.12g},{unit}\n")
    return {"E_iso": E_iso, "E1": E1, "E2": E2, "G12": G12, "G_iso": g_iso, "stiffness_ratio": sr, "shear_ratio": g_factor}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Modal calibration probe: COMSOL eigenfrequency on nominal orthotropic plate.")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--candidate-name", default="modal_calibration_nominal_orthotropic")
    p.add_argument("--H-mm", type=float, default=2.0, help="Uniform plate thickness in mm.")
    p.add_argument("--theta-rad", type=float, default=0.0, help="Uniform fiber direction (rad).")
    p.add_argument("--stiffness-ratio", type=float, default=12.0)
    p.add_argument("--shear-ratio", type=float, default=1.5)
    p.add_argument("--n-modes", type=int, default=30)
    p.add_argument("--freq-lower-hz", type=float, default=10.0)
    p.add_argument("--output-dir", default="reports/modal_calibration")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    runtime_config, _, _ = config_with_runtime_discovery(config)

    paths = {
        "candidates": Path(runtime_config["paths"]["candidates_dir"]),
        "comsol_exports": Path(runtime_config["paths"]["comsol_exports_dir"]),
    }

    plate_length_mm = float(runtime_config["project"]["plate_length_mm"])
    grid = int(runtime_config["project"]["grid_size"])  # 15
    material = runtime_config.get("material", {})

    cand_dir = paths["candidates"] / args.candidate_name
    if cand_dir.exists():
        shutil.rmtree(cand_dir)
    cand_dir.mkdir(parents=True)

    write_uniform_H_csv(grid, args.H_mm, cand_dir / "H.csv")
    write_uniform_theta_csv(grid, args.theta_rad, plate_length_mm, cand_dir / "theta_field.csv")
    write_support_csv(cand_dir / "support_parameters.csv", clamp_radius_mm=8.0)
    write_dummy_actuator_csv(cand_dir / "actuator_parameters.csv")
    export_candidate_for_comsol(cand_dir, material)
    # Write material AFTER export_candidate_for_comsol to override the 6-row default
    material_summary = write_material_parameters_csv(material, args.stiffness_ratio, args.shear_ratio, cand_dir / "material_parameters.csv")

    # Run COMSOL eigenfrequency
    ensure_comsol_credentials(runtime_config)
    apply_comsol_server_environment(runtime_config)
    if not ensure_comsol_server(runtime_config, wait_s=60.0):
        raise RuntimeError("COMSOL server is not reachable.")
    time.sleep(1.0)

    comsol_config = runtime_config.get("comsol", {})
    matlab = str(comsol_config.get("matlab_path", DEFAULT_MATLAB_PATH))
    model = Path(comsol_config.get("model_path", "comsol_templates/Chladni_15x15_bound.mph"))
    runner = Path("comsol_templates/run_chladni_eigenfrequency_orthotropic.m")
    runner_dir = runner.parent.resolve()
    export_dir = paths["comsol_exports"] / args.candidate_name / "eigenfrequency"
    export_dir.mkdir(parents=True, exist_ok=True)
    mli_path = matlab_path_from_comsol_command(comsol_config.get("comsol_command_path", ""))

    parts: list[str] = []
    if mli_path is not None:
        parts.append(f"setenv('COMSOL_MLI_PATH',{matlab_quote(mli_path)})")
        parts.append(f"addpath({matlab_quote(mli_path)})")
    parts.append(f"addpath({matlab_quote(runner_dir)})")
    parts.append(
        f"run_chladni_eigenfrequency_orthotropic({matlab_quote(model.resolve())},{matlab_quote(cand_dir.resolve())},{matlab_quote(export_dir.resolve())},{int(args.n_modes)},{float(args.freq_lower_hz)})"
    )
    batch = "; ".join(parts)
    command = [matlab, "-nosplash", "-noFigureWindows", "-sd", str(Path.cwd()), "-batch", batch]
    log_path = export_dir / "livelink_eigenfrequency.log"
    timeout_s = float(comsol_config.get("livelink_timeout_s", 7200))
    rc, _ = run_command_streamed(command, log_path, timeout_s=timeout_s)
    if rc != 0:
        raise RuntimeError(f"MATLAB eigenfrequency failed rc={rc}; see {log_path}")

    eig_csv = export_dir / "eigenfrequencies.csv"
    if not eig_csv.exists():
        raise FileNotFoundError(f"eigenfrequencies.csv not produced; see {log_path}")
    eigfreqs = np.loadtxt(eig_csv, delimiter=",", skiprows=1)
    if eigfreqs.ndim == 1:
        eigfreqs = eigfreqs.reshape(-1, 2)
    print(f"COMSOL eigenfrequencies (first 10):")
    for k in range(min(10, len(eigfreqs))):
        print(f"  mode {int(eigfreqs[k, 0]):3d}: {eigfreqs[k, 1]:.3f} Hz")
    print(f"  ... {len(eigfreqs)} total")

    # Save summary
    summary = {
        "candidate_name": args.candidate_name,
        "config": {
            "H_mm": float(args.H_mm),
            "theta_rad": float(args.theta_rad),
            "stiffness_ratio": float(args.stiffness_ratio),
            "shear_ratio": float(args.shear_ratio),
            "n_modes": int(args.n_modes),
            "freq_lower_hz": float(args.freq_lower_hz),
        },
        "material_summary": material_summary,
        "comsol_eigfreqs_hz": eigfreqs[:, 1].tolist(),
        "export_dir": str(export_dir),
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.candidate_name}_comsol_eigfreqs.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"summary: {out_dir / (args.candidate_name + '_comsol_eigfreqs.json')}")


if __name__ == "__main__":
    main()
