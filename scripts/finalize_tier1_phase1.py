"""Finalize tier1 Phase 1: combine Phase 1 freqs + off-resonance sweep, find best composite.

Mirrors explore_phase1_composite.py logic but with multi-source extras.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import os
Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

from src.config import load_config
from src.scoring.recognisability_score import (
    chladni_powder_density,
    coverage_recall,
    recognisability_score_grid,
)
from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid, resize_target_to_size


def load_amp(csv_path: Path, image_size: int, plate_length_mm: float) -> np.ndarray:
    arr = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    if arr.shape[1] >= 4:
        amp = np.sqrt(arr[:, 2]**2 + arr[:, 3]**2)
    else:
        amp = np.abs(arr[:, 2])
    grid = downsample_comsol_xy_to_grid(arr[:, 0], arr[:, 1], amp, image_size, plate_length_mm)
    if grid.max() > 1e-30:
        grid = grid / grid.max()
    return grid


def score(amp: np.ndarray, target: np.ndarray, sigma_rel: float, percentile: float, plate_length_mm: float) -> dict:
    s = recognisability_score_grid(amp, target.astype(bool), sigma_rel=sigma_rel, percentile=percentile)
    r = float(coverage_recall(amp, target.astype(bool), percentile=percentile))
    return {
        "enrich": float(s["enrichment_factor"]),
        "recall": r,
        "contrast": float(s["gaussian_contrast"]),
        "composite_recog": float(s["composite_recognisability"]),
    }


def combine(amps: list[np.ndarray], method: str) -> np.ndarray:
    stack = np.stack(amps, axis=0)
    if method == "RMS":
        return np.sqrt(np.mean(stack**2, axis=0))
    if method == "MAX":
        return np.max(stack, axis=0)
    if method == "SUM":
        return np.sum(stack, axis=0)
    raise ValueError(method)


def main():
    config = load_config("config.yaml")
    plate_length_mm = float(config["project"]["plate_length_mm"])
    image_size = 256
    target_bin = np.load("data/processed_targets/target_binary.npy").astype(bool)
    target = resize_target_to_size(target_bin, image_size)

    BROAD = dict(sigma_rel=0.05, percentile=20.0)
    TIGHT = dict(sigma_rel=0.012, percentile=92.0)

    # === TIER1 sources ===
    p1_summary = json.load(open("reports/sprint2_section4_phase1_tier1/w10_ic_tier1_sr3_v2/summary.json"))
    freqs_dict = {}

    for f, mi, w in zip(p1_summary["drive_freqs_hz"], p1_summary["drive_mode_indices"], p1_summary["drive_weights"]):
        vid = f"s4p1t1_w10_ic_tier1_sr3_v2_comsol_f{f:.1f}Hz".replace(".", "p")
        csv = Path("data/comsol_exports") / vid / "forced_response" / "forced_response.csv"
        if not csv.exists():
            print(f"  missing {csv}")
            continue
        print(f"  loading {csv.name}")
        amp = load_amp(csv, image_size, plate_length_mm)
        label = f"{f:.0f}_t1p1"
        freqs_dict[label] = {"amp": amp, "f": float(f), "src": "tier1_phase1", "mode": int(mi)}

    for f_val in [140.0, 165.0, 240.0, 270.0]:
        vid = f"offres_tier1_w10_ic_tier1_sr3_v2_comsol_f{f_val:.1f}Hz".replace(".", "p")
        csv = Path("data/comsol_exports") / vid / "forced_response" / "forced_response.csv"
        if not csv.exists():
            print(f"  missing {csv}")
            continue
        amp = load_amp(csv, image_size, plate_length_mm)
        label = f"{f_val:.0f}_t1or"
        freqs_dict[label] = {"amp": amp, "f": float(f_val), "src": "tier1_offres", "mode": None}

    # Per-freq table
    print(f"\n=== Per-frequency forced response (tier1 design) ===")
    print(f"{'label':>12} {'src':>14} {'mode':>5} | {'enr_broad':>9} {'rec_broad':>9} | {'enr_tight':>9} {'rec_tight':>9}")
    for label, d in freqs_dict.items():
        b = score(d["amp"], target, plate_length_mm=plate_length_mm, **BROAD)
        t = score(d["amp"], target, plate_length_mm=plate_length_mm, **TIGHT)
        d["broad"] = b
        d["tight"] = t
        m = d["mode"] if d["mode"] is not None else "—"
        print(f"{label:>12} {d['src']:>14} {str(m):>5} | {b['enrich']:>9.3f} {b['recall']:>9.3f} | {t['enrich']:>9.3f} {t['recall']:>9.3f}")

    # Now exhaustive subset search up to 3-tuple, with RMS / MAX / SUM (limit to manage runtime)
    labels = list(freqs_dict.keys())
    amps_arr = {l: freqs_dict[l]["amp"] for l in labels}

    composite_records = []
    total = 0
    for k in range(1, 4):
        for subset in itertools.combinations(labels, k):
            amps_sub = [amps_arr[l] for l in subset]
            for method in ["RMS", "MAX", "SUM"]:
                comp = combine(amps_sub, method)
                b = score(comp, target, plate_length_mm=plate_length_mm, **BROAD)
                composite_records.append({
                    "subset": subset,
                    "method": method,
                    "broad": b,
                })
                total += 1
    print(f"  evaluated {total} composites")

    composite_records.sort(key=lambda r: r["broad"]["enrich"], reverse=True)

    print(f"\n=== Top 15 composites (broad enrichment) ===")
    print(f"{'rank':>4} {'method':>4} {'subset':<60} | {'enr_broad':>9} {'rec_broad':>9}")
    for i, r in enumerate(composite_records[:15], 1):
        sub_str = "+".join(r["subset"])
        print(f"{i:>4} {r['method']:>4} {sub_str:<60} | {r['broad']['enrich']:>9.3f} {r['broad']['recall']:>9.3f}")

    # Save best composite
    out_dir = Path("reports/sprint2_section4_phase1_tier1/w10_ic_tier1_sr3_v2")
    out_dir.mkdir(parents=True, exist_ok=True)

    best = composite_records[0]
    best_amps = [amps_arr[l] for l in best["subset"]]
    best_comp = combine(best_amps, best["method"])
    np.save(out_dir / "tier1_best_composite.npy", best_comp)
    print(f"  saved best composite npy")
    tight_score = score(best_comp, target, plate_length_mm=plate_length_mm, **TIGHT)

    # Visualize: target + uniform-p1-tier1 + best tier1 composite
    p1_uniform = combine([freqs_dict[l]["amp"] for l in labels if "_t1p1" in l], "RMS")
    p1_uniform_score = score(p1_uniform, target, plate_length_mm=plate_length_mm, **BROAD)
    p1_uniform_tight = score(p1_uniform, target, plate_length_mm=plate_length_mm, **TIGHT)
    print(f"  uniform scored")

    dens_uni = chladni_powder_density(p1_uniform, sigma_rel=0.05)
    dens_best = chladni_powder_density(best_comp, sigma_rel=0.05)
    np.save(out_dir / "tier1_density_uniform.npy", dens_uni)
    np.save(out_dir / "tier1_density_best.npy", dens_best)
    print(f"  saved density npys (skipping matplotlib for now)")

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

    summary_out = {
        "p1_uniform_rms": {"broad": p1_uniform_score, "tight": p1_uniform_tight},
        "best_composite": {
            "subset": list(best["subset"]),
            "method": best["method"],
            "broad": best["broad"],
            "tight": tight_score,
        },
        "all_top15": [{"subset": list(r["subset"]), "method": r["method"], "broad": r["broad"]} for r in composite_records[:15]],
        "per_freq": {l: {"f": d["f"], "src": d["src"], "mode": d["mode"], "broad": d["broad"], "tight": d["tight"]} for l, d in freqs_dict.items()},
    }
    with open(out_dir / "tier1_finalize.json", "w") as f:
        json.dump(to_native(summary_out), f, indent=2)
    print(f"\nSaved: {out_dir / 'tier1_finalize.png'}")
    print(f"Saved: {out_dir / 'tier1_finalize.json'}")


if __name__ == "__main__":
    main()
