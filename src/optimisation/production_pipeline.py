"""Production pipeline — full inverse design from target → final COMSOL composite.

Pipeline stages:
  S1. Prepare target (from PNG/NPY)
  S2. W10 surrogate optimisation (joint H + θ on tier1 CF-PETG sr≈3)
  S3. COMSOL eigenfrequency analysis (30 modes)
  S4. Phase 1: select top-K IC-likeness modes + user magic off-resonance freqs
  S5. COMSOL forced response at selected freqs
  S6. Exhaustive composite subset search → best (RMS/MAX/SUM up to k=3)
  S7. Optional Phase 2 trust-region (refine H+θ from S2, re-run S3-S6)
  S8. Package final deliverables (H.csv, θ.csv, summary.json, composite npy, density npy, visualisation)

This is the customer-facing path. Returns a dict with all key metrics + artefact paths.
"""
from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _config_get(cfg: dict, key: str, default: Any) -> Any:
    """Read a key from the `production:` section of config.yaml; fall back to default."""
    return cfg.get("production", {}).get(key, default)


def build_default_pipeline_config(config_yaml_path: str | Path = "config.yaml",
                                     overrides: dict | None = None) -> "ProductionPipelineConfig":
    """Construct a ProductionPipelineConfig from config.yaml production: section, allowing per-call overrides."""
    from src.config import load_config

    config = load_config(str(config_yaml_path))
    overrides = overrides or {}

    def take(key: str, default: Any) -> Any:
        if key in overrides:
            return overrides[key]
        return _config_get(config, key, default)

    magic_raw = take("magic_off_resonance_hz", [165.0])
    if isinstance(magic_raw, str):
        magic = tuple(float(x.strip()) for x in magic_raw.split(",") if x.strip())
    else:
        magic = tuple(float(x) for x in magic_raw)

    return ProductionPipelineConfig(
        candidate_id=str(take("default_candidate_id", "production_design")),
        stiffness_ratio=float(take("stiffness_ratio", 3.0)),
        shear_ratio=float(take("shear_ratio", 1.0)),
        w10_num_steps=int(take("w10_num_steps", 300)),
        w10_lr_h=float(take("w10_lr_h", 0.05)),
        w10_lr_theta=float(take("w10_lr_theta", 0.10)),
        w10_num_frequencies=int(take("w10_num_frequencies", 6)),
        w10_f_min_hz=float(take("w10_f_min_hz", 120.0)),
        w10_f_max_hz=float(take("w10_f_max_hz", 1200.0)),
        phase1_top_k_modes=int(take("phase1_top_k_modes", 6)),
        phase1_off_resonance_hz=float(take("phase1_off_resonance_hz", 1.5)),
        magic_off_resonance_hz=magic,
        eig_n_modes=int(take("eig_n_modes", 30)),
        phase2_max_iters=int(take("phase2_max_iters", 1)),
        phase2_inner_steps=int(take("phase2_inner_steps", 80)),
        phase2_lr_h_init=float(take("phase2_lr_h_init", 0.025)),
        phase2_lr_theta_init=float(take("phase2_lr_theta_init", 0.05)),
        skip_phase2=bool(overrides.get("skip_phase2", False)),
        skip_comsol=bool(overrides.get("skip_comsol", False)),
    )


@dataclass
class ProductionPipelineConfig:
    """Configuration for the end-to-end inverse-design pipeline."""

    target_path: str = "data/processed_targets/target_binary.npy"
    candidate_id: str = "production_design"
    output_dir: str = "reports/production"

    # Material (defaults to tier1 CF-PETG — best generalising material per generalisation_check_v2)
    stiffness_ratio: float = 3.0
    shear_ratio: float = 1.0

    # W10 surrogate hyper-params
    w10_num_steps: int = 300
    w10_lr_h: float = 0.05
    w10_lr_theta: float = 0.10
    w10_num_frequencies: int = 6
    w10_f_min_hz: float = 120.0
    w10_f_max_hz: float = 1200.0

    # Phase 1 selection
    phase1_top_k_modes: int = 6
    phase1_off_resonance_hz: float = 1.5
    magic_off_resonance_hz: tuple[float, ...] = (165.0,)
    eig_n_modes: int = 30

    # Phase 2 trust-region (set max_iters=0 to skip)
    phase2_max_iters: int = 1
    phase2_inner_steps: int = 80
    phase2_lr_h_init: float = 0.025
    phase2_lr_theta_init: float = 0.05

    # Scoring
    image_size: int = 256

    # Run-control
    skip_phase2: bool = False
    skip_comsol: bool = False  # if True, surrogate-only (for fast preview)


def _emit(progress: Callable[[dict], None] | None, stage: str, message: str, **extra) -> None:
    if progress is not None:
        try:
            progress({"stage": stage, "message": message, **extra})
        except Exception:
            pass


def _run_subprocess(cmd: list[str], cwd: Path, label: str) -> subprocess.CompletedProcess:
    try:
        res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"{label} could not start because the executable was not found: {cmd[0]!r}. "
            f"Full command: {' '.join(cmd)}"
        ) from exc
    if res.returncode != 0:
        tail = ("\n".join(res.stdout.splitlines()[-25:]) + "\n" + "\n".join(res.stderr.splitlines()[-25:]))[-4000:]
        raise RuntimeError(f"{label} failed (rc={res.returncode}):\n{tail}")
    return res


def _run_w10_surrogate(cfg: ProductionPipelineConfig, project_root: Path, progress=None,
                         initial_H_csv: Path | None = None, initial_theta_csv: Path | None = None,
                         candidate_id: str | None = None, num_steps: int | None = None,
                         lr_h: float | None = None, lr_theta: float | None = None) -> dict:
    """Run W10 surrogate optimisation. Returns its summary dict."""
    cand_id = candidate_id or cfg.candidate_id
    cmd = [
        sys.executable, "scripts/run_w10_anisotropy.py",
        "--candidate-id", cand_id,
        "--num-steps", str(int(num_steps if num_steps is not None else cfg.w10_num_steps)),
        "--learning-rate-h", f"{float(lr_h if lr_h is not None else cfg.w10_lr_h)}",
        "--learning-rate-theta", f"{float(lr_theta if lr_theta is not None else cfg.w10_lr_theta)}",
        "--num-frequencies", str(int(cfg.w10_num_frequencies)),
        "--f-min-hz", f"{float(cfg.w10_f_min_hz)}",
        "--f-max-hz", f"{float(cfg.w10_f_max_hz)}",
        "--stiffness-ratio", f"{float(cfg.stiffness_ratio)}",
        "--shear-ratio", f"{float(cfg.shear_ratio)}",
        "--target", cfg.target_path,
        "--snapshot-every", "999999",
    ]
    if initial_H_csv is not None:
        cmd.extend(["--initial-H", str(initial_H_csv)])
    if initial_theta_csv is not None:
        cmd.extend(["--initial-theta-rad", str(initial_theta_csv)])
    _emit(progress, "surrogate", f"Running W10 surrogate ({int(num_steps or cfg.w10_num_steps)} steps)", candidate_id=cand_id)
    _run_subprocess(cmd, project_root, label=f"W10 surrogate ({cand_id})")
    summary_path = project_root / "candidates" / cand_id / "w10_optimization_summary.json"
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _run_comsol_eigfreq(cfg: ProductionPipelineConfig, project_root: Path, candidate_id: str, progress=None) -> Path:
    """Run COMSOL eigenfrequency analysis. Returns eigfreq export dir."""
    eig_name = f"prod_eig_{candidate_id}"
    cmd = [
        sys.executable, "scripts/run_modal_calibration_w10design.py",
        "--source-candidate", candidate_id,
        "--candidate-name", eig_name,
        "--stiffness-ratio", f"{float(cfg.stiffness_ratio)}",
        "--shear-ratio", f"{float(cfg.shear_ratio)}",
        "--n-modes", str(int(cfg.eig_n_modes)),
    ]
    _emit(progress, "comsol_eigfreq", f"Running COMSOL eigenfrequency ({cfg.eig_n_modes} modes)")
    _run_subprocess(cmd, project_root, label=f"COMSOL eigfreq ({candidate_id})")
    return project_root / "data" / "comsol_exports" / eig_name / "eigenfrequency"


def _compute_ic_likeness_per_mode(eig_dir: Path, target: np.ndarray, image_size: int, plate_length_mm: float, n_modes: int) -> list[dict]:
    from src.scoring.recognisability_score import (
        coverage_recall,
        recognisability_score_grid,
    )
    from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid

    arr = np.loadtxt(eig_dir / "eigenfrequencies.csv", delimiter=",", skiprows=1)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 2)
    n_modes = min(n_modes, len(arr))
    freqs = arr[:n_modes, 1].astype(float)
    xy = np.loadtxt(eig_dir / "mode_xy.csv", delimiter=",", skiprows=1)
    rows = []
    for k in range(1, n_modes + 1):
        try:
            m = np.loadtxt(eig_dir / f"mode_{k:03d}.csv", delimiter=",", skiprows=1)
            if m.ndim == 1:
                m = m.reshape(-1, 2)
            amp = np.sqrt(m[:, 0] ** 2 + m[:, 1] ** 2)
            grid = downsample_comsol_xy_to_grid(xy[:, 0], xy[:, 1], amp, image_size, plate_length_mm)
            if grid.max() > 1e-30:
                grid = grid / grid.max()
            s = recognisability_score_grid(grid, target.astype(bool), sigma_rel=0.05, percentile=20.0)
            r = float(coverage_recall(grid, target.astype(bool), percentile=20.0))
            rows.append({"mode": int(k), "freq_hz": float(freqs[k - 1]),
                         "enrichment": float(s["enrichment_factor"]), "recall": r,
                         "ic_score": float(s["enrichment_factor"]) * r})
        except Exception:
            rows.append({"mode": int(k), "freq_hz": float(freqs[k - 1]),
                         "enrichment": float("nan"), "recall": float("nan"), "ic_score": float("nan")})
    return rows


def _select_phase1_drive_freqs(rows: list[dict], cfg: ProductionPipelineConfig) -> list[float]:
    rows_valid = [r for r in rows if not np.isnan(r["ic_score"])]
    rows_valid.sort(key=lambda r: -r["ic_score"])
    top_rows = rows_valid[:cfg.phase1_top_k_modes]
    drive = [r["freq_hz"] + cfg.phase1_off_resonance_hz for r in top_rows]
    drive.extend(cfg.magic_off_resonance_hz)
    drive = list(dict.fromkeys(round(f, 1) for f in drive))
    return drive


def _run_comsol_forced_response(cfg: ProductionPipelineConfig, project_root: Path, candidate_id: str,
                                  freqs_hz: list[float], variant_prefix: str, progress=None) -> list[Path]:
    fstr = ",".join(f"{f:.1f}" for f in freqs_hz)
    output_dir = f"reports/production/_comsol_{variant_prefix}"
    cmd = [
        sys.executable, "scripts/run_w10_comsol_validation.py",
        "--candidate", candidate_id,
        "--stiffness-ratio", f"{float(cfg.stiffness_ratio)}",
        "--shear-ratio", f"{float(cfg.shear_ratio)}",
        "--frequencies", fstr,
        "--top-n", str(len(freqs_hz)),
        "--variant-prefix", variant_prefix,
        "--material-mode", "orthotropic_shell",
        "--output-dir", output_dir,
    ]
    _emit(progress, "comsol_forced", f"Running COMSOL forced response at {len(freqs_hz)} freqs", freqs=freqs_hz)
    _run_subprocess(cmd, project_root, label=f"COMSOL forced response ({candidate_id})")
    csv_paths = []
    for f in freqs_hz:
        vid = f"{variant_prefix}_{candidate_id}_comsol_f{f:.1f}Hz".replace(".", "p")
        csv_paths.append(project_root / "data" / "comsol_exports" / vid / "forced_response" / "forced_response.csv")
    return csv_paths


def _load_amp_csv(csv_path: Path, image_size: int, plate_length_mm: float) -> np.ndarray:
    from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid

    arr = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    if arr.shape[1] >= 4:
        amp = np.sqrt(arr[:, 2] ** 2 + arr[:, 3] ** 2)
    else:
        amp = np.abs(arr[:, 2])
    grid = downsample_comsol_xy_to_grid(arr[:, 0], arr[:, 1], amp, image_size, plate_length_mm)
    if grid.max() > 1e-30:
        grid = grid / grid.max()
    return grid


def _composite(amps: list[np.ndarray], method: str) -> np.ndarray:
    stack = np.stack(amps, axis=0)
    if method == "RMS":
        c = np.sqrt(np.mean(stack ** 2, axis=0))
    elif method == "MAX":
        c = np.max(stack, axis=0)
    else:
        c = np.sum(stack, axis=0)
    if c.max() > 1e-30:
        c = c / c.max()
    return c


def _score_amp(amp: np.ndarray, target: np.ndarray) -> dict:
    from src.scoring.recognisability_score import coverage_recall, recognisability_score_grid

    sb = recognisability_score_grid(amp, target.astype(bool), sigma_rel=0.05, percentile=20.0)
    rb = float(coverage_recall(amp, target.astype(bool), percentile=20.0))
    st = recognisability_score_grid(amp, target.astype(bool), sigma_rel=0.012, percentile=92.0)
    rt = float(coverage_recall(amp, target.astype(bool), percentile=92.0))
    return {
        "broad": {"enrich": float(sb["enrichment_factor"]), "recall": rb,
                  "contrast": float(sb["gaussian_contrast"])},
        "tight": {"enrich": float(st["enrichment_factor"]), "recall": rt,
                  "contrast": float(st["gaussian_contrast"])},
    }


def _exhaustive_composite_search(amps: dict[str, np.ndarray], target: np.ndarray, max_k: int = 3) -> list[dict]:
    labels = list(amps.keys())
    records = []
    for k in range(1, max_k + 1):
        for sub in itertools.combinations(labels, k):
            for method in ["RMS", "MAX", "SUM"]:
                c = _composite([amps[l] for l in sub], method)
                s = _score_amp(c, target)
                records.append({"subset": list(sub), "method": method, **s})
    records.sort(key=lambda r: -r["broad"]["enrich"])
    return records


def _evaluate_design(cfg: ProductionPipelineConfig, project_root: Path, candidate_id: str,
                       variant_prefix: str, target: np.ndarray, plate_length_mm: float, progress=None) -> dict:
    """Run COMSOL eigfreq + Phase 1 + forced response + composite search for a candidate."""
    eig_dir = _run_comsol_eigfreq(cfg, project_root, candidate_id, progress=progress)
    rows = _compute_ic_likeness_per_mode(eig_dir, target, cfg.image_size, plate_length_mm, cfg.eig_n_modes)
    drive_freqs = _select_phase1_drive_freqs(rows, cfg)
    csvs = _run_comsol_forced_response(cfg, project_root, candidate_id, drive_freqs, variant_prefix, progress=progress)
    amps = {}
    for f, p in zip(drive_freqs, csvs):
        if p.exists():
            amps[f"{f:.0f}"] = _load_amp_csv(p, cfg.image_size, plate_length_mm)

    if not amps:
        raise RuntimeError(f"No forced-response CSVs found for {candidate_id}")

    per_freq = {}
    for label, amp in amps.items():
        per_freq[label] = _score_amp(amp, target)

    records = _exhaustive_composite_search(amps, target, max_k=3)
    best = records[0]
    best_amp = _composite([amps[l] for l in best["subset"]], best["method"])

    return {
        "candidate_id": candidate_id,
        "eig_dir": str(eig_dir),
        "top_modes": sorted([r for r in rows if not np.isnan(r["ic_score"])], key=lambda r: -r["ic_score"])[:cfg.phase1_top_k_modes],
        "drive_freqs": drive_freqs,
        "per_freq": per_freq,
        "best_composite": best,
        "best_composite_amp": best_amp,
        "top10_composites": [{k: v for k, v in r.items() if k != "best_composite_amp"} for r in records[:10]],
    }


def _to_native(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _to_native(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_to_native(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    return o


def run_production_pipeline(cfg: ProductionPipelineConfig, project_root: Path | None = None,
                              progress: Callable[[dict], None] | None = None) -> dict:
    """End-to-end inverse design pipeline. Returns deliverables dict."""
    project_root = project_root or PROJECT_ROOT
    from src.config import load_config

    config = load_config(str(project_root / "config.yaml"))
    plate_length_mm = float(config["project"]["plate_length_mm"])

    output_dir = project_root / cfg.output_dir / cfg.candidate_id
    output_dir.mkdir(parents=True, exist_ok=True)

    _emit(progress, "start", f"Pipeline start (sr={cfg.stiffness_ratio}, candidate={cfg.candidate_id})")

    # === S1: Load target ===
    target_path = project_root / cfg.target_path
    if not target_path.exists():
        raise FileNotFoundError(f"Target not found at {target_path}; run prepare-target first.")
    target_bin = np.load(target_path).astype(bool)
    if target_bin.shape != (cfg.image_size, cfg.image_size):
        from PIL import Image
        timg = Image.fromarray(target_bin.astype(np.uint8) * 255).resize((cfg.image_size, cfg.image_size), Image.NEAREST)
        target = np.array(timg) > 127
    else:
        target = target_bin
    np.save(output_dir / "target_resized.npy", target)
    _emit(progress, "target", f"Target loaded ({int(target.sum())} pixels)")

    # === S2: W10 surrogate ===
    _emit(progress, "surrogate_start", "Running W10 surrogate optimisation")
    t0 = time.time()
    w10_summary = _run_w10_surrogate(cfg, project_root, progress=progress)
    elapsed_surr = time.time() - t0
    surr_metrics = w10_summary.get("best_surrogate_metrics", {})
    _emit(progress, "surrogate_done", f"W10 done in {elapsed_surr:.0f}s; surrogate enr={surr_metrics.get('enrichment', 0):.2f}×",
          surrogate_metrics=surr_metrics)

    # Copy initial H+θ into output dir
    cand_dir = project_root / "candidates" / cfg.candidate_id
    for fname in ["H.csv", "theta_continuous_rad.csv", "theta_continuous_deg.csv",
                  "frequencies_hz.csv", "weights.csv", "w10_optimization_summary.json"]:
        src_file = cand_dir / fname
        if src_file.exists():
            shutil.copy2(src_file, output_dir / fname)

    if cfg.skip_comsol:
        result = {
            "candidate_id": cfg.candidate_id,
            "output_dir": str(output_dir),
            "stage_reached": "surrogate_only",
            "stiffness_ratio": cfg.stiffness_ratio,
            "shear_ratio": cfg.shear_ratio,
            "surrogate_metrics": surr_metrics,
            "w10_summary": w10_summary,
        }
        summary_path = output_dir / "production_summary.json"
        summary_path.write_text(json.dumps(_to_native(result), indent=2, ensure_ascii=False), encoding="utf-8")
        result["summary_path"] = str(summary_path)
        _emit(progress, "done", "Surrogate-only mode (skip_comsol=True); done.", summary_path=str(summary_path))
        return result

    # === S3-S6: Phase 1 evaluation on initial design ===
    _emit(progress, "phase1_start", "Phase 1: COMSOL eigfreq + Phase 1 selection + forced response + composite search")
    t1 = time.time()
    p1_result = _evaluate_design(cfg, project_root, cfg.candidate_id,
                                    variant_prefix="prodp1", target=target,
                                    plate_length_mm=plate_length_mm, progress=progress)
    elapsed_p1 = time.time() - t1
    _emit(progress, "phase1_done",
          f"Phase 1 done in {elapsed_p1:.0f}s; best composite = {p1_result['best_composite']['broad']['enrich']:.2f}× broad",
          best_composite=p1_result["best_composite"])

    # Save Phase 1 deliverables
    np.save(output_dir / "phase1_best_composite_amp.npy", p1_result["best_composite_amp"])
    from src.scoring.recognisability_score import chladni_powder_density
    np.save(output_dir / "phase1_best_powder_broad.npy", chladni_powder_density(p1_result["best_composite_amp"], sigma_rel=0.05))
    np.save(output_dir / "phase1_best_powder_sharp.npy", chladni_powder_density(p1_result["best_composite_amp"], sigma_rel=0.025))

    final = {
        "candidate_id": cfg.candidate_id,
        "output_dir": str(output_dir),
        "stiffness_ratio": cfg.stiffness_ratio,
        "shear_ratio": cfg.shear_ratio,
        "stage_reached": "phase1",
        "surrogate_metrics": surr_metrics,
        "phase1": {k: v for k, v in p1_result.items() if k != "best_composite_amp"},
        "wallclock_seconds": {"surrogate": elapsed_surr, "phase1": elapsed_p1},
    }

    # === S7: Phase 2 trust-region (optional) ===
    if not cfg.skip_phase2 and cfg.phase2_max_iters > 0:
        _emit(progress, "phase2_start", f"Phase 2 trust-region ({cfg.phase2_max_iters} iters)")
        history = [{"iter": 0, "candidate_id": cfg.candidate_id, "best_composite": p1_result["best_composite"], "accepted": True}]
        best_enr = p1_result["best_composite"]["broad"]["enrich"]
        best_iter = 0
        best_amp = p1_result["best_composite_amp"]

        lr_h = cfg.phase2_lr_h_init
        lr_theta = cfg.phase2_lr_theta_init
        cur_H = cand_dir / "H.csv"
        cur_theta = cand_dir / "theta_continuous_rad.csv"

        for it in range(1, cfg.phase2_max_iters + 1):
            t2 = time.time()
            iter_cand = f"{cfg.candidate_id}_p2it{it}"
            old = project_root / "candidates" / iter_cand
            if old.exists():
                shutil.rmtree(old)
            _emit(progress, "phase2_iter_start", f"iter {it}/{cfg.phase2_max_iters}: surrogate continue (lr_H={lr_h:.4f}, lr_θ={lr_theta:.4f})", iter=it)
            _run_w10_surrogate(cfg, project_root, progress=progress,
                                initial_H_csv=cur_H, initial_theta_csv=cur_theta,
                                candidate_id=iter_cand, num_steps=cfg.phase2_inner_steps,
                                lr_h=lr_h, lr_theta=lr_theta)
            res = _evaluate_design(cfg, project_root, iter_cand,
                                     variant_prefix=f"prodp2it{it}", target=target,
                                     plate_length_mm=plate_length_mm, progress=progress)
            new_enr = res["best_composite"]["broad"]["enrich"]
            prev_enr = history[-1]["best_composite"]["broad"]["enrich"]
            delta = new_enr - prev_enr
            accepted = delta > 0
            if delta > 0.10:
                lr_h *= 1.3
                lr_theta *= 1.3
            elif delta <= 0:
                lr_h *= 0.5
                lr_theta *= 0.5
            history.append({"iter": it, "candidate_id": iter_cand,
                            "best_composite": res["best_composite"], "delta": float(delta),
                            "accepted": bool(accepted),
                            "wallclock_s": float(time.time() - t2)})
            if accepted:
                cur_H = project_root / "candidates" / iter_cand / "H.csv"
                cur_theta = project_root / "candidates" / iter_cand / "theta_continuous_rad.csv"
                if new_enr > best_enr:
                    best_enr = new_enr
                    best_iter = it
                    best_amp = res["best_composite_amp"]
            _emit(progress, "phase2_iter_done",
                  f"iter {it}: {prev_enr:.2f}× → {new_enr:.2f}× ({'ACCEPT' if accepted else 'REJECT'})",
                  iter=it, delta=delta, accepted=accepted)
            if lr_h < 0.005:
                break

        np.save(output_dir / "phase2_best_composite_amp.npy", best_amp)
        np.save(output_dir / "phase2_best_powder_broad.npy", chladni_powder_density(best_amp, sigma_rel=0.05))
        np.save(output_dir / "phase2_best_powder_sharp.npy", chladni_powder_density(best_amp, sigma_rel=0.025))

        final["stage_reached"] = "phase2"
        final["phase2"] = {
            "history": history,
            "best_iter": int(best_iter),
            "best_enrichment": float(best_enr),
            "improvement_pct": float((best_enr - history[0]["best_composite"]["broad"]["enrich"]) / history[0]["best_composite"]["broad"]["enrich"] * 100),
        }

    # === S8: Final summary JSON ===
    summary_path = output_dir / "production_summary.json"
    summary_path.write_text(json.dumps(_to_native(final), indent=2, ensure_ascii=False), encoding="utf-8")
    _emit(progress, "done", f"Pipeline complete. Best enrichment = {final.get('phase2', {}).get('best_enrichment', p1_result['best_composite']['broad']['enrich']):.2f}×",
          summary_path=str(summary_path))
    final["summary_path"] = str(summary_path)
    return final
