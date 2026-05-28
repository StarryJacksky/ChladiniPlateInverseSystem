"""Try alternative composite strategies on Phase 1's per-frequency forced responses.

Goals:
1. Score per-freq AND composite at both sigma_rel=0.05 (broad) and sigma_rel=0.012 (tight)
2. Try alternative composite strategies:
   - sum_amp²  (RMS, current Phase 1)
   - max_amp (preserve sharp features across frequencies)
   - min_amp (only retain features common to all freqs)
   - top-K subset combinations (find which subset of the 6 freqs gives best IC)
3. Also add 180Hz from the old sweep (which had enrich=3.14 individually) and check if mixing helps.
4. Output ranked alternatives table + visualisation of top 6 strategies.
"""
from __future__ import annotations

import json
import os
from itertools import combinations
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib.pyplot as plt

from src.config import load_config
from src.scoring.recognisability_score import (
    chladni_powder_density,
    coverage_recall,
    recognisability_score_grid,
)
from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid, resize_target_to_size


def score_both_sigmas(amp_grid: np.ndarray, target: np.ndarray) -> dict:
    out = {}
    for label, sig, pct in [("broad", 0.05, 20.0), ("tight", 0.012, 92.0)]:
        s = recognisability_score_grid(amp_grid, target.astype(bool), sigma_rel=sig, percentile=pct)
        r = float(coverage_recall(amp_grid, target.astype(bool), percentile=pct))
        out[label] = {"enrich": float(s["enrichment_factor"]), "recall": r,
                      "contrast": float(s["gaussian_contrast"]),
                      "composite_recog": float(s["composite_recognisability"])}
    return out


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


def composite_rms(amps: list[np.ndarray], weights: np.ndarray) -> np.ndarray:
    c = sum(float(w) * a**2 for w, a in zip(weights, amps))
    c = np.sqrt(np.clip(c, 0.0, None))
    return c / max(c.max(), 1e-30)


def composite_max(amps: list[np.ndarray]) -> np.ndarray:
    c = np.maximum.reduce(amps)
    return c / max(c.max(), 1e-30)


def composite_sumlinear(amps: list[np.ndarray], weights: np.ndarray) -> np.ndarray:
    c = sum(float(w) * a for w, a in zip(weights, amps))
    return c / max(c.max(), 1e-30)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase1-summary", default="reports/sprint2_section4_phase1/w10_ic_tier2_sr12/summary.json")
    ap.add_argument("--variant-prefix", default="s4p1")
    ap.add_argument("--candidate", default="w10_ic_tier2_sr12")
    ap.add_argument("--extra-freqs-source", default="w10_ic_tier2_sr12", help="Old sweep candidate for additional 180Hz-like freq.")
    ap.add_argument("--extra-freqs", default="180", help="Comma-separated extra freqs to include in composite search.")
    ap.add_argument("--output-dir", default=None, help="Override output dir; defaults to <phase1_summary parent>")
    args = ap.parse_args()
    config = load_config("config.yaml")
    plate_length_mm = float(config["project"]["plate_length_mm"])
    image_size = 256
    target_bin = np.load("data/processed_targets/target_binary.npy").astype(bool)
    target = resize_target_to_size(target_bin, image_size)

    # Load Phase 1 freqs
    summary = json.load(open(args.phase1_summary))
    phase1_amps = []
    phase1_meta = []
    for f, mi, w in zip(summary["drive_freqs_hz"], summary["drive_mode_indices"], summary["drive_weights"]):
        vid = f"{args.variant_prefix}_{args.candidate}_comsol_f{f:.1f}Hz".replace(".", "p")
        csv = Path("data/comsol_exports") / vid / "forced_response" / "forced_response.csv"
        amp = load_amp(csv, image_size, plate_length_mm)
        phase1_amps.append(amp)
        phase1_meta.append({"f": f, "mode": mi, "w": w})

    # Load extra reference freqs from a sweep (e.g. 180Hz "magic" off-resonance from tier2 sweep)
    extra_amps = []
    extra_labels = []
    for f_str in args.extra_freqs.split(","):
        f_val = float(f_str.strip())
        candidates_paths = [
            Path(f"data/comsol_exports/{args.extra_freqs_source}_comsol_f{f_val:.1f}Hz/forced_response/forced_response.csv".replace(".0Hz", "p0Hz")),
            Path(f"data/comsol_exports/{args.extra_freqs_source}_comsol_f{f_val:.1f}Hz/forced_response/forced_response.csv".replace(".", "p")),
        ]
        a = None
        for p in candidates_paths:
            if p.exists():
                a = load_amp(p, image_size, plate_length_mm)
                break
        if a is not None:
            extra_amps.append(a)
            extra_labels.append(f"ext{f_val:.0f}")
            print(f"  Loaded extra freq {f_val} from {p}")
    amp_180 = extra_amps[0] if extra_amps else None

    # Score each per-freq under BOTH sigmas
    print(f"\n=== Per-frequency forced response, scored at BOTH sigma=0.05 and sigma=0.012 ===")
    print(f"{'f_Hz':>7} {'mode':>5} | {'enr_broad':>9} {'rec_broad':>9} | {'enr_tight':>9} {'rec_tight':>9}")
    per_freq_full = []
    for amp, meta in zip(phase1_amps, phase1_meta):
        sc = score_both_sigmas(amp, target)
        per_freq_full.append({"f": meta["f"], "mode": meta["mode"], "w": meta["w"], "amp": amp, **sc})
        print(f"{meta['f']:>7.1f} {meta['mode']:>5} | {sc['broad']['enrich']:>9.3f} {sc['broad']['recall']:>9.3f} | {sc['tight']['enrich']:>9.3f} {sc['tight']['recall']:>9.3f}")
    if amp_180 is not None:
        sc = score_both_sigmas(amp_180, target)
        per_freq_full.append({"f": 180.0, "mode": "—", "w": 0.0, "amp": amp_180, **sc})
        print(f"{180.0:>7.1f} {'old':>5} | {sc['broad']['enrich']:>9.3f} {sc['broad']['recall']:>9.3f} | {sc['tight']['enrich']:>9.3f} {sc['tight']['recall']:>9.3f}")

    # === Composite strategies ===
    print(f"\n=== Composite strategies (broad metric) ===")
    weights_uniform = np.ones(len(phase1_amps)) / len(phase1_amps)
    weights_orig = np.array([m["w"] for m in phase1_meta])
    weights_enr_broad = np.array([s["broad"]["enrich"] for s in per_freq_full[:len(phase1_amps)]])
    weights_enr_broad = weights_enr_broad / weights_enr_broad.sum()
    weights_enr_tight = np.array([s["tight"]["enrich"] for s in per_freq_full[:len(phase1_amps)]])
    weights_enr_tight = weights_enr_tight / weights_enr_tight.sum()

    composites = {}
    composites["P1_orig_RMS"] = composite_rms(phase1_amps, weights_orig)
    composites["P1_uniform_RMS"] = composite_rms(phase1_amps, weights_uniform)
    composites["P1_enrW_RMS"] = composite_rms(phase1_amps, weights_enr_broad)
    composites["P1_uniform_SUM"] = composite_sumlinear(phase1_amps, weights_uniform)
    composites["P1_MAX"] = composite_max(phase1_amps)
    if amp_180 is not None:
        composites["P1+180_MAX"] = composite_max(phase1_amps + [amp_180])
        composites["just_180+62+87_MAX"] = composite_max([amp_180, phase1_amps[1], phase1_amps[5]])
        composites["just_180+50+87_SUM"] = composite_sumlinear([amp_180, phase1_amps[3], phase1_amps[5]], np.array([1/3]*3))

    # Search over all 3-subsets of (phase1 + 180Hz) for best MAX
    all_amps = phase1_amps + ([amp_180] if amp_180 is not None else [])
    all_labels = [f"{m['f']:.0f}" for m in phase1_meta] + (["180"] if amp_180 is not None else [])
    best_score_broad = -1.0
    best_sub_broad = None
    best_score_tight = -1.0
    best_sub_tight = None
    for r in (2, 3, 4):
        for sub in combinations(range(len(all_amps)), r):
            amps_sub = [all_amps[i] for i in sub]
            for combo_name, comp_fn in [("MAX", lambda a: composite_max(a)),
                                         ("RMS", lambda a: composite_rms(a, np.ones(len(a))/len(a)))]:
                c = comp_fn(amps_sub)
                sc = score_both_sigmas(c, target)
                # Combined score: harmonic mean of enrichment and recall to penalise low recall
                combo_score = (2 * sc["broad"]["enrich"] * sc["broad"]["recall"]) / max(sc["broad"]["enrich"] + sc["broad"]["recall"], 1e-30)
                if combo_score > best_score_broad:
                    best_score_broad = combo_score
                    best_sub_broad = (sub, combo_name, sc, c)
                tight_score = (2 * sc["tight"]["enrich"] * sc["tight"]["recall"]) / max(sc["tight"]["enrich"] + sc["tight"]["recall"], 1e-30)
                if tight_score > best_score_tight:
                    best_score_tight = tight_score
                    best_sub_tight = (sub, combo_name, sc, c)

    if best_sub_broad:
        sub, combo_name, sc, c = best_sub_broad
        labels = [all_labels[i] for i in sub]
        print(f"\nBest subset (broad metric): freqs={labels} via {combo_name} → broad: enr={sc['broad']['enrich']:.3f} rec={sc['broad']['recall']:.3f}  | tight: enr={sc['tight']['enrich']:.3f} rec={sc['tight']['recall']:.3f}")
        composites[f"BEST_BROAD_{combo_name}_{'-'.join(labels)}"] = c
    if best_sub_tight:
        sub, combo_name, sc, c = best_sub_tight
        labels = [all_labels[i] for i in sub]
        print(f"Best subset (tight metric): freqs={labels} via {combo_name} → broad: enr={sc['broad']['enrich']:.3f} rec={sc['broad']['recall']:.3f}  | tight: enr={sc['tight']['enrich']:.3f} rec={sc['tight']['recall']:.3f}")
        composites[f"BEST_TIGHT_{combo_name}_{'-'.join(labels)}"] = c

    # Score all named composites
    print(f"\n=== Composite leaderboard (sorted by broad enrichment) ===")
    print(f"{'name':<45} | {'enr_broad':>9} {'rec_broad':>9} | {'enr_tight':>9} {'rec_tight':>9}")
    rankings = []
    for name, c in composites.items():
        sc = score_both_sigmas(c, target)
        rankings.append({"name": name, **sc, "amp": c})
    rankings.sort(key=lambda x: -x["broad"]["enrich"])
    for r in rankings:
        print(f"{r['name']:<45} | {r['broad']['enrich']:>9.3f} {r['broad']['recall']:>9.3f} | {r['tight']['enrich']:>9.3f} {r['tight']['recall']:>9.3f}")

    # Visualisation: target + 6 per-freq + top 6 composites
    fig, axes = plt.subplots(3, 4, figsize=(16, 12))
    target_density = chladni_powder_density(target.astype(float), sigma_rel=0.012)
    axes[0, 0].imshow(target_density, cmap="hot", origin="upper")
    axes[0, 0].set_title("Target IC")
    axes[0, 0].axis("off")
    # 6 best per-freq (incl 180)
    top_perfreq = sorted(per_freq_full, key=lambda x: -x["broad"]["enrich"])[:7]
    for i, r in enumerate(top_perfreq[:7], start=1):
        ax = axes.flatten()[i]
        d = chladni_powder_density(r["amp"], sigma_rel=0.012)
        ax.imshow(d, cmap="hot", origin="upper")
        ax.set_title(f"f={r['f']:.0f} m{r['mode']}\nbr={r['broad']['enrich']:.2f}/{r['broad']['recall']:.2f}\nti={r['tight']['enrich']:.2f}/{r['tight']['recall']:.2f}", fontsize=8)
        ax.axis("off")
    # Top 4 composites
    for i, r in enumerate(rankings[:4], start=8):
        if i >= 12: break
        ax = axes.flatten()[i]
        d = chladni_powder_density(r["amp"], sigma_rel=0.012)
        ax.imshow(d, cmap="hot", origin="upper")
        ax.set_title(f"{r['name'][:25]}\nbr={r['broad']['enrich']:.2f}/{r['broad']['recall']:.2f}\nti={r['tight']['enrich']:.2f}/{r['tight']['recall']:.2f}", fontsize=8)
        ax.axis("off")
    plt.suptitle("Sprint 2 §4 Phase 1: composite strategy exploration", fontsize=12)
    plt.tight_layout()
    base_dir = Path(args.output_dir) if args.output_dir else Path(args.phase1_summary).parent
    base_dir.mkdir(parents=True, exist_ok=True)
    out = base_dir / "composite_exploration.png"
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\nWrote: {out}")

    # Save best composites
    np.save(out.with_name("phase1_orig_composite.npy"), composites["P1_orig_RMS"])
    if best_sub_broad:
        np.save(out.with_name("phase1_best_broad_composite.npy"), best_sub_broad[3])
    if best_sub_tight:
        np.save(out.with_name("phase1_best_tight_composite.npy"), best_sub_tight[3])
    report = {
        "scoring": {"broad": {"sigma_rel": 0.05, "percentile": 20.0}, "tight": {"sigma_rel": 0.012, "percentile": 92.0}},
        "per_freq": [{k: v for k, v in r.items() if k != "amp"} for r in per_freq_full],
        "composite_ranking": [{k: v for k, v in r.items() if k != "amp"} for r in rankings],
        "best_subset_broad": {"freqs": [all_labels[i] for i in best_sub_broad[0]], "combo": best_sub_broad[1], "scores": best_sub_broad[2]} if best_sub_broad else None,
        "best_subset_tight": {"freqs": [all_labels[i] for i in best_sub_tight[0]], "combo": best_sub_tight[1], "scores": best_sub_tight[2]} if best_sub_tight else None,
    }
    (out.with_name("composite_exploration.json")).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
