"""Sprint 2 §4 Phase 2 — Trust-region surrogate refinement on tier1 W10 design with COMSOL ground truth.

每次 outer iter：
  1. 从当前 (H_k, θ_k) 出发，调 W10 anisotropy 继续优化 K_inner 步（学习率随 trust-region 半径缩放）
  2. 跑 COMSOL eigfreq（30 modes）on new design
  3. 用 IC-likeness 选 top-6 + 加入 magic 165Hz off-resonance → COMSOL forced response
  4. 穷举 1-3 freq 组合 (RMS/MAX/SUM) → 找最佳复合 broad enrichment
  5. ρ = (E_new - E_baseline) / (E_surr_new - E_surr_baseline)
  6. 接受/拒绝 + 更新 trust radius (=LR scale)

Outputs:
  reports/sprint2_section4_phase2/iter_summary.json
  reports/sprint2_section4_phase2/iter_*_panel.png
  reports/sprint2_section4_phase2/phase2_final.png
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np

from src.config import load_config
from src.scoring.recognisability_score import (
    chladni_powder_density,
    coverage_recall,
    recognisability_score_grid,
)
from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid, resize_target_to_size


def load_amp_csv(csv_path: Path, image_size: int, plate_length_mm: float) -> np.ndarray:
    arr = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    if arr.shape[1] >= 4:
        amp = np.sqrt(arr[:, 2] ** 2 + arr[:, 3] ** 2)
    else:
        amp = np.abs(arr[:, 2])
    grid = downsample_comsol_xy_to_grid(arr[:, 0], arr[:, 1], amp, image_size, plate_length_mm)
    if grid.max() > 1e-30:
        grid = grid / grid.max()
    return grid


def composite(amps: list[np.ndarray], method: str) -> np.ndarray:
    stack = np.stack(amps, axis=0)
    if method == "RMS":
        c = np.sqrt(np.mean(stack ** 2, axis=0))
    elif method == "MAX":
        c = np.max(stack, axis=0)
    else:  # SUM
        c = np.sum(stack, axis=0)
    if c.max() > 1e-30:
        c = c / c.max()
    return c


def score_broad(amp: np.ndarray, target: np.ndarray) -> dict:
    s = recognisability_score_grid(amp, target.astype(bool), sigma_rel=0.05, percentile=20.0)
    r = float(coverage_recall(amp, target.astype(bool), percentile=20.0))
    return {"enrich": float(s["enrichment_factor"]), "recall": r, "contrast": float(s["gaussian_contrast"])}


def score_tight(amp: np.ndarray, target: np.ndarray) -> dict:
    s = recognisability_score_grid(amp, target.astype(bool), sigma_rel=0.012, percentile=92.0)
    r = float(coverage_recall(amp, target.astype(bool), percentile=92.0))
    return {"enrich": float(s["enrichment_factor"]), "recall": r}


def run_surrogate_refine(candidate_id: str, initial_H_csv: Path, initial_theta_csv: Path,
                          num_steps: int, lr_H: float, lr_theta: float, stiffness_ratio: float,
                          shear_ratio: float, sigma_rel: float = 0.05, target_path: str = "data/processed_targets/target_binary.npy") -> dict:
    """Call W10 surrogate to refine H. Returns the produced candidate's summary.

    Historical note: this used to refine H + θ, but θ optimisation was removed
    from W10 in 2026-05 (see BATTERY_FINDINGS.md). The ``initial_theta_csv``
    and ``lr_theta`` parameters are kept in the signature for back-compat but
    no longer forwarded to the W10 CLI. /
    历史注：曾用于 H+θ 联合微调；θ 优化已撤，θ 参数仅保留签名兼容
    """
    del initial_theta_csv, lr_theta  # silence linter; no longer wired into W10
    cmd = [
        ".venv/bin/python", "scripts/run_w10_anisotropy.py",
        "--candidate-id", candidate_id,
        "--num-steps", str(int(num_steps)),
        "--learning-rate-h", f"{float(lr_H)}",
        "--learning-rate-freq", "0.0",
        "--learning-rate-weight", "0.0",
        "--freeze-freq-first-steps", str(int(num_steps + 10)),
        "--initial-H", str(initial_H_csv),
        "--stiffness-ratio", f"{float(stiffness_ratio)}",
        "--shear-ratio", f"{float(shear_ratio)}",
        "--sigma-rel", f"{float(sigma_rel)}",
        "--target", target_path,
        "--snapshot-every", "999999",
    ]
    print("  $ " + " ".join(cmd[2:]))
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        raise RuntimeError(f"W10 surrogate refine failed rc={result.returncode}")
    out_path = PROJECT_ROOT / "candidates" / candidate_id / "w10_optimization_summary.json"
    return json.loads(out_path.read_text(encoding="utf-8"))


def run_comsol_eigfreq(candidate_id: str, stiffness_ratio: float, shear_ratio: float, n_modes: int = 30) -> Path:
    """Run COMSOL eigenfrequency on the candidate; return eigfreq export dir."""
    cmd = [
        ".venv/bin/python", "scripts/run_modal_calibration_w10design.py",
        "--source-candidate", candidate_id,
        "--candidate-name", f"phase2_eig_{candidate_id}",
        "--stiffness-ratio", f"{float(stiffness_ratio)}",
        "--shear-ratio", f"{float(shear_ratio)}",
        "--n-modes", str(int(n_modes)),
    ]
    print("  $ " + " ".join(cmd[2:]))
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        raise RuntimeError(f"COMSOL eigfreq failed rc={result.returncode}")
    return PROJECT_ROOT / "data" / "comsol_exports" / f"phase2_eig_{candidate_id}" / "eigenfrequency"


def compute_ic_likeness_per_mode(eig_dir: Path, target: np.ndarray, image_size: int, plate_length_mm: float, n_modes: int = 30) -> list[dict]:
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
            sb = score_broad(grid, target)
            rows.append({"mode": int(k), "freq_hz": float(freqs[k - 1]),
                          "enrichment": sb["enrich"], "recall": sb["recall"],
                          "ic_score": sb["enrich"] * sb["recall"]})
        except Exception as ex:
            rows.append({"mode": int(k), "freq_hz": float(freqs[k - 1]),
                          "enrichment": float("nan"), "recall": float("nan"), "ic_score": float("nan")})
    return rows


def run_comsol_forced_response(candidate_id: str, freqs_hz: list[float], variant_prefix: str,
                                 stiffness_ratio: float, shear_ratio: float, output_dir: str) -> list[Path]:
    """Run COMSOL forced response at the given freqs. Returns list of CSV paths."""
    fstr = ",".join(f"{f:.1f}" for f in freqs_hz)
    cmd = [
        ".venv/bin/python", "scripts/run_w10_comsol_validation.py",
        "--candidate", candidate_id,
        "--stiffness-ratio", f"{float(stiffness_ratio)}",
        "--shear-ratio", f"{float(shear_ratio)}",
        "--frequencies", fstr,
        "--top-n", str(len(freqs_hz)),
        "--variant-prefix", variant_prefix,
        "--material-mode", "orthotropic_shell",
        "--output-dir", output_dir,
    ]
    print("  $ " + " ".join(cmd[2:]))
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(result.stdout[-3000:])
        print(result.stderr[-3000:])
        raise RuntimeError(f"COMSOL forced response failed rc={result.returncode}")
    csv_paths = []
    for f in freqs_hz:
        vid = f"{variant_prefix}_{candidate_id}_comsol_f{f:.1f}Hz".replace(".", "p")
        p = PROJECT_ROOT / "data" / "comsol_exports" / vid / "forced_response" / "forced_response.csv"
        csv_paths.append(p)
    return csv_paths


def evaluate_design(candidate_id: str, target: np.ndarray, image_size: int, plate_length_mm: float,
                     stiffness_ratio: float, shear_ratio: float, variant_prefix: str, output_dir: str,
                     extra_magic_freqs_hz: tuple[float, ...] = (165.0,), top_k_modes: int = 6) -> dict:
    """Full pipeline: eigfreq -> select top-K modes -> forced response (+magic) -> composite search."""
    print(f"\n[evaluate_design] {candidate_id}")
    eig_dir = run_comsol_eigfreq(candidate_id, stiffness_ratio, shear_ratio)
    rows = compute_ic_likeness_per_mode(eig_dir, target, image_size, plate_length_mm)
    rows_valid = [r for r in rows if not np.isnan(r["enrichment"])]
    rows_valid.sort(key=lambda r: -r["ic_score"])
    top_rows = rows_valid[:top_k_modes]
    print(f"  top-{top_k_modes} IC-likeness modes:")
    for r in top_rows:
        print(f"    mode {r['mode']:3d} @ {r['freq_hz']:7.2f}Hz: enr={r['enrichment']:.3f} rec={r['recall']:.3f} ic={r['ic_score']:.3f}")

    drive_freqs = [r["freq_hz"] + 1.5 for r in top_rows]  # off-resonance offset
    drive_freqs.extend(extra_magic_freqs_hz)
    drive_freqs = list(dict.fromkeys(round(f, 1) for f in drive_freqs))  # dedupe, 1-dp
    print(f"  driving COMSOL forced response at {len(drive_freqs)} freqs: {drive_freqs}")

    csv_paths = run_comsol_forced_response(candidate_id, drive_freqs, variant_prefix, stiffness_ratio, shear_ratio, output_dir)

    amps = {}
    for f, p in zip(drive_freqs, csv_paths):
        if not p.exists():
            print(f"  WARN missing {p}")
            continue
        amps[f"{f:.0f}"] = load_amp_csv(p, image_size, plate_length_mm)

    # Per-freq individual scores
    per_freq = {}
    for label, amp in amps.items():
        sb = score_broad(amp, target)
        st = score_tight(amp, target)
        per_freq[label] = {"broad": sb, "tight": st}
        print(f"  freq {label}Hz: broad enr={sb['enrich']:.3f} rec={sb['recall']:.3f} | tight enr={st['enrich']:.3f} rec={st['recall']:.3f}")

    # Composite subset search up to k=3
    labels = list(amps.keys())
    records = []
    for k in range(1, 4):
        for sub in itertools.combinations(labels, k):
            for method in ["RMS", "MAX", "SUM"]:
                c = composite([amps[l] for l in sub], method)
                sb = score_broad(c, target)
                st = score_tight(c, target)
                records.append({"subset": sub, "method": method, "broad": sb, "tight": st})
    records.sort(key=lambda r: -r["broad"]["enrich"])
    best = records[0]
    sub_str = "+".join(best["subset"])
    print(f"  BEST composite {best['method']}({sub_str}): broad enr={best['broad']['enrich']:.3f} rec={best['broad']['recall']:.3f}")

    return {
        "candidate_id": candidate_id,
        "eig_dir": str(eig_dir),
        "top_modes": top_rows,
        "drive_freqs": drive_freqs,
        "per_freq": per_freq,
        "best_composite": {
            "subset": list(best["subset"]),
            "method": best["method"],
            "broad": best["broad"],
            "tight": best["tight"],
        },
        "top10_composites": [{"subset": list(r["subset"]), "method": r["method"], "broad": r["broad"], "tight": r["tight"]} for r in records[:10]],
    }


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--baseline-candidate", default="w10_ic_tier1_sr3_v2")
    p.add_argument("--stiffness-ratio", type=float, default=3.0)
    p.add_argument("--shear-ratio", type=float, default=1.0)
    p.add_argument("--max-iters", type=int, default=3)
    p.add_argument("--inner-steps", type=int, default=80)
    p.add_argument("--lr-h", type=float, default=0.025, help="Initial trust-region H LR (default 0.5 × original 0.05).")
    p.add_argument("--lr-theta", type=float, default=0.05, help="Initial trust-region θ LR (default 0.5 × original 0.10).")
    p.add_argument("--magic-freqs", default="165.0", help="Comma-separated magic off-resonance freqs to always include.")
    p.add_argument("--target-path", default="data/processed_targets/target_binary.npy")
    p.add_argument("--output-dir", default="reports/sprint2_section4_phase2")
    p.add_argument("--top-k-modes", type=int, default=6)
    p.add_argument("--image-size", type=int, default=256)
    return p.parse_args()


def main():
    args = parse_args()
    config = load_config("config.yaml")
    plate_length_mm = float(config["project"]["plate_length_mm"])
    out_dir = PROJECT_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load target
    target_bin = np.load(args.target_path).astype(bool)
    target = resize_target_to_size(target_bin, args.image_size)

    magic_freqs = tuple(float(x.strip()) for x in args.magic_freqs.split(",") if x.strip())

    # === Iter 0: Evaluate baseline ===
    print("=" * 80)
    print("ITER 0: BASELINE EVAL (tier1 W10 design)")
    print("=" * 80)
    baseline_result = evaluate_design(
        args.baseline_candidate, target, args.image_size, plate_length_mm,
        args.stiffness_ratio, args.shear_ratio,
        variant_prefix="p2it0", output_dir=str(out_dir / "iter_0"),
        extra_magic_freqs_hz=magic_freqs, top_k_modes=args.top_k_modes,
    )

    history = [{"iter": 0, "candidate_id": args.baseline_candidate, **baseline_result, "accepted": True}]
    best_so_far = baseline_result["best_composite"]["broad"]["enrich"]
    best_iter = 0
    print(f"\nBaseline COMSOL composite enrichment: {best_so_far:.3f}×")

    lr_h = float(args.lr_h)
    lr_theta = float(args.lr_theta)
    current_H_csv = PROJECT_ROOT / "candidates" / args.baseline_candidate / "H.csv"
    current_theta_csv = PROJECT_ROOT / "candidates" / args.baseline_candidate / "theta_continuous_rad.csv"
    accepted_candidate_id = args.baseline_candidate
    prev_surrogate_enr = None
    if baseline_result.get("top_modes"):
        # Surrogate baseline isn't directly comparable; use COMSOL composite for ρ instead.
        pass

    # === Outer iters ===
    for it in range(1, args.max_iters + 1):
        print("\n" + "=" * 80)
        print(f"ITER {it}: trust-region surrogate refine + COMSOL eval (lr_H={lr_h:.4f}, lr_θ={lr_theta:.4f})")
        print("=" * 80)
        cand_id = f"phase2_iter{it}"
        # Remove old candidate dir
        old_dir = PROJECT_ROOT / "candidates" / cand_id
        if old_dir.exists():
            shutil.rmtree(old_dir)

        surr_summary = run_surrogate_refine(
            cand_id, current_H_csv, current_theta_csv,
            num_steps=args.inner_steps, lr_H=lr_h, lr_theta=lr_theta,
            stiffness_ratio=args.stiffness_ratio, shear_ratio=args.shear_ratio,
            target_path=args.target_path,
        )

        surr_metrics = surr_summary.get("best_surrogate_metrics", {})
        print(f"  surrogate best: enrich={surr_metrics.get('enrichment'):.3f}× contrast={surr_metrics.get('contrast'):.3f}× recall={surr_metrics.get('recall', 0)*100:.1f}%")

        result = evaluate_design(
            cand_id, target, args.image_size, plate_length_mm,
            args.stiffness_ratio, args.shear_ratio,
            variant_prefix=f"p2it{it}", output_dir=str(out_dir / f"iter_{it}"),
            extra_magic_freqs_hz=magic_freqs, top_k_modes=args.top_k_modes,
        )
        new_enr = result["best_composite"]["broad"]["enrich"]
        prev_enr = history[-1]["best_composite"]["broad"]["enrich"]

        delta = new_enr - prev_enr
        rel = delta / max(abs(prev_enr), 1e-9)

        print(f"\n  Phase 2 iter{it}: COMSOL composite enrichment {prev_enr:.3f} → {new_enr:.3f} (Δ={delta:+.3f}, {rel*100:+.1f}%)")

        accepted = delta > 0
        # Trust-region update
        if delta > 0.10:
            lr_h *= 1.3
            lr_theta *= 1.3
            note = "expand TR"
        elif delta > 0:
            note = "keep TR"
        else:
            lr_h *= 0.5
            lr_theta *= 0.5
            note = "shrink TR"

        print(f"  decision: {'ACCEPT' if accepted else 'REJECT'} ({note}; new lr_H={lr_h:.4f}, lr_θ={lr_theta:.4f})")

        history.append({"iter": it, "candidate_id": cand_id,
                         "surrogate_enrichment": float(surr_metrics.get("enrichment", float("nan"))),
                         **result, "delta": float(delta), "rel": float(rel),
                         "accepted": bool(accepted), "lr_h_after": float(lr_h), "lr_theta_after": float(lr_theta)})

        if accepted:
            current_H_csv = PROJECT_ROOT / "candidates" / cand_id / "H.csv"
            current_theta_csv = PROJECT_ROOT / "candidates" / cand_id / "theta_continuous_rad.csv"
            accepted_candidate_id = cand_id
            if new_enr > best_so_far:
                best_so_far = new_enr
                best_iter = it

        if lr_h < 0.005:
            print("  trust radius too small; stopping early")
            break

    # === Final summary ===
    print("\n" + "=" * 80)
    print("PHASE 2 FINAL")
    print("=" * 80)
    print(f"  baseline (iter 0): {history[0]['best_composite']['broad']['enrich']:.3f}×")
    for h in history[1:]:
        flag = "✓" if h["accepted"] else "✗"
        print(f"  iter {h['iter']}: {h['best_composite']['broad']['enrich']:.3f}×  {flag}  cand={h['candidate_id']}")
    print(f"\n  BEST: iter {best_iter} → {best_so_far:.3f}× (vs baseline {history[0]['best_composite']['broad']['enrich']:.3f}×)")

    # Convert to JSON-serializable
    def to_native(o):
        if isinstance(o, dict):
            return {k: to_native(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [to_native(v) for v in o]
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        return o

    summary_path = out_dir / "phase2_summary.json"
    summary_path.write_text(json.dumps({
        "baseline_candidate": args.baseline_candidate,
        "stiffness_ratio": args.stiffness_ratio,
        "shear_ratio": args.shear_ratio,
        "magic_freqs_hz": list(magic_freqs),
        "best_iter": int(best_iter),
        "best_enrichment": float(best_so_far),
        "improvement_pct": float((best_so_far - history[0]["best_composite"]["broad"]["enrich"]) / history[0]["best_composite"]["broad"]["enrich"] * 100),
        "history": to_native(history),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nArtefacts: {summary_path}")


if __name__ == "__main__":
    main()
