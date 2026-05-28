"""Probe COMSOL eigenfrequency on the ACTUAL W10 tier2 design (H+θ both vary), not nominal.

This tests whether the modal-calibration MAC pairing still holds when H and θ change.
If MAC remains high → calibration is robust → Sprint 2 §4 is feasible.
If MAC collapses → calibration is design-dependent → must use per-design re-calibration.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
    run_matlab_with_mphserver_retry,
)
from src.comsol.server import ensure_comsol_server
from src.config import load_config

from scripts.run_modal_calibration_probe import (
    write_dummy_actuator_csv,
    write_support_csv,
    write_material_parameters_csv,
)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--source-candidate", default="w10_ic_tier2_sr12")
    p.add_argument("--candidate-name", default="modal_calibration_w10_tier2")
    p.add_argument("--stiffness-ratio", type=float, default=12.0)
    p.add_argument("--shear-ratio", type=float, default=1.5)
    p.add_argument("--n-modes", type=int, default=30)
    p.add_argument("--freq-lower-hz", type=float, default=10.0)
    p.add_argument("--output-dir", default="reports/modal_calibration")
    return p.parse_args()


def write_theta_field_csv(theta_rad: np.ndarray, plate_length_mm: float, output_path: Path) -> None:
    grid = int(theta_rad.shape[0])
    cell_size_m = float(plate_length_mm) / 1000.0 / grid
    half_m = float(plate_length_mm) / 2000.0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for r in range(grid):
            y_m = +half_m - (r + 0.5) * cell_size_m
            for c in range(grid):
                x_m = -half_m + (c + 0.5) * cell_size_m
                f.write(f"{x_m:.6f} {y_m:.6f} {float(theta_rad[r, c]):.6f}\n")


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    runtime_config, _, _ = config_with_runtime_discovery(config)
    paths = {"candidates": Path(runtime_config["paths"]["candidates_dir"]), "comsol_exports": Path(runtime_config["paths"]["comsol_exports_dir"])}

    plate_length_mm = float(runtime_config["project"]["plate_length_mm"])
    material = runtime_config.get("material", {})

    src_dir = paths["candidates"] / args.source_candidate
    if not src_dir.exists():
        raise FileNotFoundError(f"source candidate {src_dir} missing")
    cand_dir = paths["candidates"] / args.candidate_name
    if cand_dir.exists():
        shutil.rmtree(cand_dir)
    cand_dir.mkdir(parents=True)

    # Copy the W10 optimised H field
    shutil.copy(src_dir / "H.csv", cand_dir / "H.csv")
    # Write theta_field.csv from the W10 optimised theta_continuous_rad.csv
    theta_rad = np.loadtxt(src_dir / "theta_continuous_rad.csv", delimiter=",")
    write_theta_field_csv(theta_rad, plate_length_mm, cand_dir / "theta_field.csv")

    write_support_csv(cand_dir / "support_parameters.csv", clamp_radius_mm=8.0)
    write_dummy_actuator_csv(cand_dir / "actuator_parameters.csv")
    export_candidate_for_comsol(cand_dir, material)
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
    runner_dir = Path("comsol_templates").resolve()
    export_dir = paths["comsol_exports"] / args.candidate_name / "eigenfrequency"
    export_dir.mkdir(parents=True, exist_ok=True)
    mli_path = matlab_path_from_comsol_command(comsol_config.get("comsol_command_path", ""))

    parts = []
    if mli_path: parts += [f"setenv('COMSOL_MLI_PATH',{matlab_quote(mli_path)})", f"addpath({matlab_quote(mli_path)})"]
    parts.append(f"addpath({matlab_quote(runner_dir)})")
    parts.append(
        f"run_chladni_eigenfrequency_orthotropic({matlab_quote(model.resolve())},{matlab_quote(cand_dir.resolve())},{matlab_quote(export_dir.resolve())},{int(args.n_modes)},{float(args.freq_lower_hz)})"
    )
    cmd = [matlab, "-nosplash", "-noFigureWindows", "-sd", str(Path.cwd()), "-batch", "; ".join(parts)]
    log_path = export_dir / "livelink_eigenfrequency.log"
    # 自动重试：失败 → 重置 mphserver → 再试（最多 retry_max_attempts 次） / Auto retry: on failure reset mphserver, then re-fire (up to retry_max_attempts)
    rc, _ = run_matlab_with_mphserver_retry(
        cmd, log_path, runtime_config,
        label=f"COMSOL eigfreq ({args.candidate_name})",
        timeout_s=7200.0,
    )
    if rc != 0: raise RuntimeError(f"MATLAB eigenfreq rc={rc}; see {log_path}")

    eig_csv = export_dir / "eigenfrequencies.csv"
    eigfreqs = np.loadtxt(eig_csv, delimiter=",", skiprows=1)
    if eigfreqs.ndim == 1: eigfreqs = eigfreqs.reshape(-1, 2)
    print(f"COMSOL W10-design eigenfrequencies (first 10):")
    for k in range(min(10, len(eigfreqs))):
        print(f"  mode {int(eigfreqs[k, 0]):3d}: {eigfreqs[k, 1]:.3f} Hz")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "candidate_name": args.candidate_name,
        "source_candidate": args.source_candidate,
        "material_summary": material_summary,
        "comsol_eigfreqs_hz": eigfreqs[:, 1].tolist(),
        "export_dir": str(export_dir),
    }
    (out_dir / f"{args.candidate_name}_comsol_eigfreqs.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
