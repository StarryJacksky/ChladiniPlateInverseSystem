"""Run COMSOL orthotropic shell validation for W10 candidates.

For each W10 candidate directory (containing H.csv, theta_continuous_rad.csv,
frequencies_hz.csv, weights.csv), this script:

1. Creates a frequency variant directory per drive frequency.
2. Exports theta_field.csv (COMSOL Interpolation in spreadsheet format).
3. Writes orthotropic material parameters (E_parallel/E_perp, G_pp, nu_xy)
   into material_parameters.csv.
4. Invokes the orthotropic MATLAB runner via LiveLink.
5. Collects each frequency's forced response into the canonical export tree.
6. Computes a weighted composite amplitude and recognisability metrics
   versus the IC target (using fixed numerical-stability scoring fns).

Outputs:
- candidates/<candidate>_comsol_f<fHz>/ for each frequency variant
- reports/w10_comsol_validation/<candidate>/composite.npy + summary.json
"""
from __future__ import annotations

import argparse
import csv
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
    DEFAULT_FORCED_RUNNER_PATH,
    DEFAULT_MATLAB_PATH,
    apply_comsol_server_environment,
    build_forced_matlab_batch,
    matlab_path_from_comsol_command,
    matlab_quote,
    run_command_streamed,
)
from src.comsol.server import ensure_comsol_server
from src.config import load_config
from src.scoring.recognisability_score import (
    chladni_powder_density,
    coverage_recall,
    recognisability_score_grid,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run COMSOL orthotropic validation for a W10 candidate.")
    parser.add_argument("--candidate", required=True, help="W10 candidate dir name under candidates/.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--baseline-candidate", default="", help="Reference baseline candidate to clone non-W10 files from (actuator/support/topology). Defaults to mosaic_z_candidate_151_calibrated_six_v1.")
    parser.add_argument("--stiffness-ratio", type=float, required=True, help="E_parallel / E_perp; overrides W10 summary value if provided.")
    parser.add_argument("--shear-ratio", type=float, required=True, help="G12 / G_iso; overrides W10 summary value if provided.")
    parser.add_argument("--frequencies", default="", help="Comma-separated frequencies (Hz). Default: top-N from W10 weights.")
    parser.add_argument("--top-n", type=int, default=3, help="Run only the top-N weighted frequencies (default 3).")
    parser.add_argument("--damping-ratio", type=float, default=0.02)
    parser.add_argument("--force-sigma-mm", type=float, default=200.0, help="Spatial width of Gaussian load in mm. Default 200mm (>>plate 150mm) approximates uniform pressure / base acceleration.")
    parser.add_argument("--use-uniform-actuator", action="store_true", default=True, help="Override baseline's 6-actuator pattern with a single center wide-Gaussian to mimic W10 surrogate's base acceleration.")
    parser.add_argument("--image-size", type=int, default=256, help="Composite grid size (default 256).")
    parser.add_argument("--output-dir", default="reports/w10_comsol_validation")
    parser.add_argument("--variant-prefix", default="", help="Suffix appended to the candidate's frequency variant dirs.")
    parser.add_argument("--force-run", action="store_true", help="Re-run COMSOL even if forced_response.csv exists.")
    parser.add_argument("--skip-comsol", action="store_true", help="Skip MATLAB invocation; only re-compute composite + metrics from existing exports.")
    parser.add_argument("--material-mode", choices=["isotropic_equivalent", "orthotropic_shell", "isotropic_baseline"], default="isotropic_equivalent", help="Material model: isotropic_equivalent uses E_eff=(E1+E2)/2; orthotropic_shell attempts COMSOL Shell orthotropic (best-effort); isotropic_baseline uses original E_iso.")
    return parser.parse_args()


def project_paths(config: dict) -> dict[str, Path]:
    return {
        "candidates": Path(config["paths"]["candidates_dir"]),
        "comsol_exports": Path(config["paths"]["comsol_exports_dir"]),
        "processed_targets": Path(config["paths"]["processed_targets_dir"]),
    }


def baseline_files() -> list[str]:
    return [
        "actuator_parameters.csv",
        "support_parameters.csv",
        "topology_primitives.csv",
        "design_variable_parameters.csv",
    ]


def write_uniform_actuator_csv(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write("id,x_mm,y_mm,amplitude,phase_deg\n")
        f.write("1,0.0,0.0,1.0,0.0\n")


def write_theta_field_csv(theta_rad: np.ndarray, plate_length_mm: float, output_path: Path) -> None:
    grid = int(theta_rad.shape[0])
    if theta_rad.shape != (grid, grid):
        raise ValueError(f"theta_rad must be square, got {theta_rad.shape}")
    cell_size_m = float(plate_length_mm) / 1000.0 / grid
    half_m = float(plate_length_mm) / 2000.0
    rows: list[tuple[float, float, float]] = []
    for r in range(grid):
        y_m = +half_m - (r + 0.5) * cell_size_m
        for c in range(grid):
            x_m = -half_m + (c + 0.5) * cell_size_m
            rows.append((x_m, y_m, float(theta_rad[r, c])))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for x_m, y_m, t in rows:
            f.write(f"{x_m:.6f} {y_m:.6f} {t:.6f}\n")


def write_material_parameters_csv(
    material: dict,
    stiffness_ratio: float,
    shear_ratio: float,
    material_mode: str,
    output_path: Path,
) -> dict[str, float]:
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
    nu12 = nu_iso
    nu13 = nu_iso
    nu23 = nu_iso
    if material_mode == "isotropic_baseline":
        E_for_runner = E_iso
    elif material_mode == "isotropic_equivalent":
        E_for_runner = float((E1 + E2) / 2.0)
    else:
        E_for_runner = E_iso
    rows = [
        ("mat_density", density, "kg/m^3"),
        ("mat_poisson_ratio", nu_iso, "1"),
        ("mat_youngs_modulus", E_for_runner, "Pa"),
        ("mat_thermal_conductivity", float(material.get("thermal_conductivity_w_mk", 0.2)), "W/(m*K)"),
        ("mat_heat_capacity", float(material.get("heat_capacity_j_kgk", 1500.0)), "J/(kg*K)"),
        ("mat_thermal_expansion", float(material.get("thermal_expansion_1_k", 8.0e-5)), "1/K"),
        ("mat_E1", E1, "Pa"),
        ("mat_E2", E2, "Pa"),
        ("mat_E_perp_z", Ez, "Pa"),
        ("mat_nu12", nu12, "1"),
        ("mat_nu23", nu23, "1"),
        ("mat_nu13", nu13, "1"),
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
    return {
        "E_iso_pa": E_iso,
        "E_for_runner_pa": E_for_runner,
        "E1_pa": E1,
        "E2_pa": E2,
        "G12_pa": G12,
        "G_iso_pa": g_iso,
        "stiffness_ratio": sr,
        "shear_ratio": g_factor,
        "material_mode": material_mode,
    }


def write_frequency_csv(path: Path, drive_frequency_hz: float, damping_ratio: float, force_sigma_mm: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["drive_frequency_hz", "damping_ratio", "force_sigma_mm"])
        writer.writeheader()
        writer.writerow({
            "drive_frequency_hz": float(drive_frequency_hz),
            "damping_ratio": float(damping_ratio),
            "force_sigma_mm": float(force_sigma_mm),
        })


def clone_w10_variant(
    source_dir: Path,
    baseline_dir: Path,
    target_dir: Path,
    drive_frequency_hz: float,
    damping_ratio: float,
    force_sigma_mm: float,
    stiffness_ratio: float,
    shear_ratio: float,
    material: dict,
    plate_length_mm: float,
    material_mode: str,
    use_orthotropic_runner: bool,
    use_uniform_actuator: bool,
) -> dict[str, float]:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)
    if source_dir.is_dir() and (source_dir / "H.csv").exists():
        shutil.copy(source_dir / "H.csv", target_dir / "H.csv")
    if use_orthotropic_runner:
        theta_path = source_dir / "theta_continuous_rad.csv"
        if theta_path.exists():
            theta_rad = np.loadtxt(theta_path, delimiter=",")
            write_theta_field_csv(theta_rad, plate_length_mm, target_dir / "theta_field.csv")
    for filename in baseline_files():
        src = baseline_dir / filename
        if src.exists():
            shutil.copy(src, target_dir / filename)
    if use_uniform_actuator:
        write_uniform_actuator_csv(target_dir / "actuator_parameters.csv")
    export_candidate_for_comsol(target_dir, material)
    material_summary = write_material_parameters_csv(
        material,
        stiffness_ratio=stiffness_ratio,
        shear_ratio=shear_ratio,
        material_mode=material_mode,
        output_path=target_dir / "material_parameters.csv",
    )
    write_frequency_csv(target_dir / "frequency_parameters.csv", drive_frequency_hz, damping_ratio, force_sigma_mm)
    metadata = {
        "source_w10_candidate": source_dir.name,
        "baseline_candidate": baseline_dir.name,
        "drive_frequency_hz": float(drive_frequency_hz),
        "stiffness_ratio": float(stiffness_ratio),
        "shear_ratio": float(shear_ratio),
        "material_mode": material_mode,
        "use_orthotropic_runner": bool(use_orthotropic_runner),
        **material_summary,
    }
    (target_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return material_summary


def run_matlab_forced_response(runtime_config: dict, candidate_dir: Path, export_dir: Path, use_orthotropic_runner: bool) -> int:
    comsol_config = runtime_config.get("comsol", {})
    matlab = str(comsol_config.get("matlab_path", DEFAULT_MATLAB_PATH))
    model = Path(comsol_config.get("model_path", "comsol_templates/Chladni_15x15_bound.mph"))
    if use_orthotropic_runner:
        runner_name = "run_chladni_forced_response_orthotropic"
        runner = Path("comsol_templates/run_chladni_forced_response_orthotropic.m")
    else:
        runner_name = "run_chladni_forced_response"
        runner = Path(comsol_config.get("forced_response_runner_path", DEFAULT_FORCED_RUNNER_PATH))
    runner_dir = runner.parent.resolve()
    mli_path = matlab_path_from_comsol_command(comsol_config.get("comsol_command_path", ""))
    parts: list[str] = []
    if mli_path is not None:
        parts.append(f"setenv('COMSOL_MLI_PATH',{matlab_quote(mli_path)})")
        parts.append(f"addpath({matlab_quote(mli_path)})")
    parts.append(f"addpath({matlab_quote(runner_dir)})")
    parts.append(
        f"{runner_name}({matlab_quote(model.resolve())},{matlab_quote(candidate_dir.resolve())},{matlab_quote(export_dir.resolve())})"
    )
    batch = "; ".join(parts)
    command = [matlab, "-nosplash", "-noFigureWindows", "-sd", str(Path.cwd()), "-batch", batch]
    log_path = export_dir / "livelink_forced_response.log"
    timeout_s = float(comsol_config.get("livelink_timeout_s", 7200))
    returncode, _ = run_command_streamed(command, log_path, timeout_s=timeout_s)
    return returncode


def downsample_to_grid(samples_x: np.ndarray, samples_y: np.ndarray, values: np.ndarray, image_size: int, plate_length_mm: float) -> np.ndarray:
    half_m = float(plate_length_mm) / 2000.0
    edges = np.linspace(-half_m, half_m, image_size + 1)
    col_idx = np.clip(np.searchsorted(edges, samples_x, side="right") - 1, 0, image_size - 1)
    row_idx_from_bottom = np.clip(np.searchsorted(edges, samples_y, side="right") - 1, 0, image_size - 1)
    row_idx = image_size - 1 - row_idx_from_bottom
    accum = np.zeros((image_size, image_size), dtype=np.complex128)
    counts = np.zeros((image_size, image_size), dtype=np.int64)
    np.add.at(accum, (row_idx, col_idx), values)
    np.add.at(counts, (row_idx, col_idx), 1)
    safe_counts = np.where(counts > 0, counts, 1)
    grid = accum / safe_counts
    if (counts == 0).any():
        ys, xs = np.where(counts == 0)
        from scipy.ndimage import binary_dilation
        mask = counts > 0
        filled = grid.copy()
        for _ in range(6):
            if not (counts == 0).any():
                break
            expanded = binary_dilation(mask)
            new_cells = expanded & ~mask
            if not new_cells.any():
                break
            for r, c in zip(*np.where(new_cells)):
                rmin, rmax = max(r - 1, 0), min(r + 2, image_size)
                cmin, cmax = max(c - 1, 0), min(c + 2, image_size)
                neighborhood = filled[rmin:rmax, cmin:cmax]
                neighborhood_mask = mask[rmin:rmax, cmin:cmax]
                if neighborhood_mask.any():
                    filled[r, c] = neighborhood[neighborhood_mask].mean()
                    mask[r, c] = True
            grid = filled
        grid = filled
    return grid


def load_forced_response_csv(response_csv: Path, image_size: int, plate_length_mm: float) -> np.ndarray:
    rows = []
    with response_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            x = float(row.get("x", row.get("X", "0")))
            y = float(row.get("y", row.get("Y", "0")))
            wr = float(row.get("w_real", row.get("real_uz", "0")))
            wi = float(row.get("w_imag", row.get("imag_uz", "0")))
            rows.append((x, y, complex(wr, wi)))
    if not rows:
        raise RuntimeError(f"Empty forced response CSV: {response_csv}")
    arr = np.array(rows, dtype=object)
    xs = np.array([float(r[0]) for r in rows], dtype=np.float64)
    ys = np.array([float(r[1]) for r in rows], dtype=np.float64)
    ws = np.array([complex(r[2]) for r in rows], dtype=np.complex128)
    return downsample_to_grid(xs, ys, ws, image_size, plate_length_mm)


def composite_rms(complex_fields: list[np.ndarray], weights: np.ndarray) -> np.ndarray:
    weights = np.asarray(weights, dtype=np.float64)
    weights = weights / max(float(np.sum(weights)), 1.0e-30)
    squared = np.zeros_like(complex_fields[0], dtype=np.float64)
    for w_complex, weight in zip(complex_fields, weights):
        squared += float(weight) * np.abs(w_complex).astype(np.float64) ** 2
    composite = np.sqrt(np.clip(squared, 0.0, None))
    return composite


def evaluate_metrics(target_binary: np.ndarray, composite_amp: np.ndarray, image_size: int) -> dict[str, float]:
    image_target = target_binary
    if image_target.shape != composite_amp.shape:
        from PIL import Image
        tgt = Image.fromarray((image_target.astype(np.uint8) * 255))
        tgt = tgt.resize((image_size, image_size), resample=Image.NEAREST)
        image_target = (np.array(tgt) > 127).astype(bool)
    powder = chladni_powder_density(composite_amp, sigma_rel=0.05)
    scores = recognisability_score_grid(composite_amp, image_target, sigma_rel=0.05, percentile=20.0)
    recall = coverage_recall(composite_amp, image_target, percentile=20.0)
    return {
        "enrichment_factor": float(scores["enrichment_factor"]),
        "coverage_recall": float(recall),
        "gaussian_contrast": float(scores["gaussian_contrast"]),
        "directional_alignment": float(scores["directional_alignment"]),
        "composite_recognisability": float(scores["composite_recognisability"]),
        "powder_max": float(np.max(powder)),
        "powder_mean": float(np.mean(powder)),
    }


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)
    paths = project_paths(runtime_config)
    candidates_dir = paths["candidates"]
    comsol_exports_dir = paths["comsol_exports"]
    plate_length_mm = float(runtime_config["project"]["plate_length_mm"])
    image_size = int(args.image_size)

    source_w10 = candidates_dir / args.candidate
    if not source_w10.exists():
        raise FileNotFoundError(f"W10 candidate not found: {source_w10}")
    baseline_id = args.baseline_candidate or "mosaic_z_candidate_151_calibrated_six_v1"
    baseline_dir = candidates_dir / baseline_id
    if not baseline_dir.exists():
        raise FileNotFoundError(f"Baseline candidate not found: {baseline_dir}")

    target_array_path = paths["processed_targets"] / "target_binary.npy"
    target_binary = np.load(target_array_path).astype(bool)

    summary_json_path = source_w10 / "w10_optimization_summary.json"
    summary_data = json.loads(summary_json_path.read_text(encoding="utf-8"))
    all_freqs = list(summary_data.get("frequencies_hz", []))
    all_weights = list(summary_data.get("weights", []))
    if not all_freqs:
        freqs_array = np.loadtxt(source_w10 / "frequencies_hz.csv", delimiter=",", skiprows=1)
        weights_array = np.loadtxt(source_w10 / "weights.csv", delimiter=",", skiprows=1)
        all_freqs = freqs_array.tolist()
        all_weights = weights_array.tolist()

    if args.frequencies:
        freqs = [float(x.strip()) for x in args.frequencies.split(",") if x.strip()]
        weights = [
            float(all_weights[all_freqs.index(min(all_freqs, key=lambda f: abs(f - freq)))]) for freq in freqs
        ]
    else:
        order = np.argsort(np.array(all_weights))[::-1]
        top_idx = sorted(order[: max(1, int(args.top_n))])
        freqs = [float(all_freqs[i]) for i in top_idx]
        weights = [float(all_weights[i]) for i in top_idx]
    print(f"Running W10 candidate {args.candidate} at frequencies={freqs} weights={weights}")

    material = runtime_config.get("material", {})

    output_dir = Path(args.output_dir) / args.candidate
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_comsol:
        ensure_comsol_credentials(runtime_config)
        apply_comsol_server_environment(runtime_config)
        if not ensure_comsol_server(runtime_config, wait_s=60.0):
            raise RuntimeError("COMSOL server is not reachable.")
        time.sleep(1.0)

    use_orthotropic_runner = bool(args.material_mode == "orthotropic_shell")
    variant_results: list[dict] = []
    complex_fields: list[np.ndarray] = []
    material_summary: dict[str, float] = {}
    for freq, weight in zip(freqs, weights):
        variant_id = f"{args.candidate}_comsol_f{freq:.1f}Hz".replace(".", "p")
        if args.variant_prefix:
            variant_id = f"{args.variant_prefix}_{variant_id}"
        target_dir = candidates_dir / variant_id
        material_summary = clone_w10_variant(
            source_dir=source_w10,
            baseline_dir=baseline_dir,
            target_dir=target_dir,
            drive_frequency_hz=float(freq),
            damping_ratio=float(args.damping_ratio),
            force_sigma_mm=float(args.force_sigma_mm),
            stiffness_ratio=float(args.stiffness_ratio),
            shear_ratio=float(args.shear_ratio),
            material=material,
            plate_length_mm=plate_length_mm,
            material_mode=args.material_mode,
            use_orthotropic_runner=use_orthotropic_runner,
            use_uniform_actuator=bool(args.use_uniform_actuator),
        )
        export_dir = comsol_exports_dir / variant_id / "forced_response"
        export_dir.mkdir(parents=True, exist_ok=True)
        response_csv = export_dir / "forced_response.csv"
        if args.force_run or not response_csv.exists() or not args.skip_comsol:
            if args.skip_comsol and response_csv.exists():
                pass
            else:
                t0 = time.time()
                rc = run_matlab_forced_response(runtime_config, target_dir, export_dir, use_orthotropic_runner)
                elapsed = time.time() - t0
                if rc != 0:
                    raise RuntimeError(f"MATLAB failed for {variant_id} (rc={rc}); see {export_dir/'livelink_forced_response.log'}")
                print(f"  freq={freq:.1f}Hz weight={weight:.3f} done in {elapsed:.1f}s")
        if not response_csv.exists():
            raise FileNotFoundError(f"Missing forced_response.csv after run: {response_csv}")
        amp_grid = load_forced_response_csv(response_csv, image_size, plate_length_mm)
        complex_fields.append(amp_grid)
        variant_results.append({
            "variant_id": variant_id,
            "frequency_hz": float(freq),
            "weight": float(weight),
            "response_csv": str(response_csv),
            "field_max_abs": float(np.max(np.abs(amp_grid))),
        })

    composite_amp = composite_rms(complex_fields, np.array(weights))
    metrics = evaluate_metrics(target_binary, composite_amp, image_size)
    np.save(output_dir / "composite_amplitude.npy", composite_amp)
    summary = {
        "candidate": args.candidate,
        "baseline_candidate": baseline_id,
        "stiffness_ratio": float(args.stiffness_ratio),
        "shear_ratio": float(args.shear_ratio),
        "material_mode": args.material_mode,
        "material_summary": material_summary,
        "image_size": image_size,
        "frequencies_hz": freqs,
        "weights": weights,
        "variants": variant_results,
        "metrics": metrics,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"summary written to {summary_path}")


if __name__ == "__main__":
    main()
