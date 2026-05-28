"""Post-hoc rebuild of Phase 2 "best" artifacts using the new composite score.

After fixing the Phase 2 collapse-acceptance bug (commit 92b7b73), runs
performed BEFORE the fix have already saved the wrong "winner" into
``phase2_best_composite_amp.npy`` / ``phase2_best_powder_*.npy``. This
script re-scores every iter in ``production_summary.json`` using the new
``enrich · √recall`` rule, identifies the correct winner, and rebuilds the
phase2_best_* npy files in place. Original npy + summary are backed up to
``*.bak.npy`` / ``*.bak.json`` for safe rollback.

Why not just re-run the pipeline?
  - Saves the 10-15 min COMSOL cost
  - No data transfer between machines (run locally on the box that has
    the original run on disk)

Limitations:
  - If the new winner is **iter 0** (Phase 1 baseline): trivial — copy
    ``phase1_best_*.npy`` over ``phase2_best_*.npy``. Works with only the
    output_dir's artifacts.
  - If the new winner is **iter > 0**: need the COMSOL exports for that
    iter under ``data/comsol_exports/prodp2it{N}_<candidate>_comsol_*Hz/``
    to recompose the amplitude. The script will detect and re-derive.
    If the exports are missing, the script bails with a clear message.

Usage:
    .venv/bin/python scripts/_phase2_rebuild_best_posthoc.py <output_dir>
    .venv/bin/python scripts/_phase2_rebuild_best_posthoc.py reports/production/run01
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def composite_score(bc: dict, mode: str = "composite") -> dict:
    """Mirror of ``src.optimisation.production_pipeline._phase2_score``."""
    broad = bc.get("broad", {}) or {}
    tight = bc.get("tight", {}) or {}
    be = float(broad.get("enrich", 0.0))
    br = float(broad.get("recall", 0.0))
    te = float(tight.get("enrich", 0.0))
    tr = float(tight.get("recall", 0.0))
    if mode == "enrich_only":
        score = be
    else:
        score = be * (max(br, 0.0) ** 0.5)
    return {"score": float(score), "broad_enrich": be, "broad_recall": br,
            "tight_enrich": te, "tight_recall": tr}


def downsample_csv_to_grid(csv_path: Path, image_size: int, plate_length_mm: float) -> np.ndarray:
    """Mirror of ``_load_amp_csv``: downsample COMSOL mesh nodes to regular grid."""
    from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid

    arr = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    x = arr[:, 0]; y = arr[:, 1]
    if arr.shape[1] >= 5:
        amp = arr[:, 4]
    elif arr.shape[1] >= 4:
        amp = np.sqrt(arr[:, 2] ** 2 + arr[:, 3] ** 2)
    else:
        amp = np.abs(arr[:, 2])
    return downsample_comsol_xy_to_grid(x, y, amp, image_size, plate_length_mm)


def rebuild_iter_amp(iter_record: dict, candidate_id: str, image_size: int, plate_length_mm: float) -> np.ndarray | None:
    """Rebuild a non-Phase-1 iter's composite amplitude from its COMSOL exports.

    Returns the amp array or None if the COMSOL exports for this iter are missing
    (e.g. data/comsol_exports/ wasn't synced to this machine).
    """
    bc = iter_record["best_composite"]
    subset = bc["subset"]
    method = bc.get("method", "RMS")
    iter_n = iter_record["iter"]
    prefix = f"prodp2it{iter_n}"

    drive_freqs = iter_record.get("drive_freqs", [])

    amps = []
    missing = []
    for f_label in subset:
        nearest = None
        for df in drive_freqs:
            if f"{int(round(df))}" == f_label:
                nearest = df
                break
        if nearest is None:
            try:
                nearest = float(f_label)
            except Exception:
                missing.append(f"unparseable freq '{f_label}'"); continue

        # Variant id pattern from production_pipeline._evaluate_design
        vid = f"{prefix}_{candidate_id}_comsol_f{nearest:.1f}Hz".replace(".", "p")
        csv = PROJECT_ROOT / "data" / "comsol_exports" / vid / "forced_response" / "forced_response.csv"
        if not csv.exists():
            missing.append(str(csv)); continue
        amp = downsample_csv_to_grid(csv, image_size, plate_length_mm)
        peak = float(np.max(np.abs(amp)))
        if peak > 0: amp = amp / peak
        amps.append(amp)

    if missing:
        print(f"  Missing COMSOL exports for iter {iter_n}:")
        for m in missing: print(f"    {m}")
        return None

    stack = np.stack(amps, axis=0)
    if method == "RMS":
        comp = np.sqrt(np.mean(stack ** 2, axis=0))
    elif method == "MAX":
        comp = np.max(stack, axis=0)
    else:
        comp = np.sum(stack, axis=0)
    return comp


def make_powder(amp: np.ndarray, sigma_rel: float) -> np.ndarray:
    """Mirror of chladni_powder_density."""
    peak = float(np.max(np.abs(amp)))
    if peak <= 0:
        return np.ones_like(amp, dtype=np.float32)
    norm = np.abs(amp) / peak
    return np.exp(-((norm / sigma_rel) ** 2)).astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser(description="Post-hoc rebuild Phase 2 best using composite score.")
    ap.add_argument("output_dir", type=str, help="Pipeline output dir (contains production_summary.json)")
    ap.add_argument("--image-size", type=int, default=64, help="Phase 1/2 grid image size used by the run.")
    ap.add_argument("--plate-length-mm", type=float, default=150.0)
    ap.add_argument("--dry-run", action="store_true", help="Only print what would change; don't write.")
    args = ap.parse_args()

    out = Path(args.output_dir).resolve()
    summary_path = out / "production_summary.json"
    if not summary_path.exists():
        print(f"ERROR: not found: {summary_path}")
        return 1

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    cand_id = summary.get("candidate_id")
    if "phase2" not in summary:
        print(f"ERROR: no phase2 block in {summary_path} (was this a surrogate-only run?)")
        return 1
    phase2 = summary["phase2"]
    history = phase2.get("history", [])
    if len(history) < 2:
        print(f"INFO: phase2 history has {len(history)} entries — nothing to re-pick.")
        return 0

    print(f"Candidate: {cand_id}")
    print(f"History entries: {len(history)}")
    print()

    print(f"{'iter':>5}  {'accepted':>9}  {'broad enr':>9}  {'broad rec':>9}  "
          f"{'enr_only':>9}  {'composite':>10}")
    print("-" * 70)
    enr_only_best_iter = 0
    enr_only_best_score = -math.inf
    comp_best_iter = 0
    comp_best_score = -math.inf
    for h in history:
        bc = h["best_composite"]
        s_enr = composite_score(bc, "enrich_only")
        s_comp = composite_score(bc, "composite")
        marker = "*" if h.get("accepted", False) else " "
        print(f"{h['iter']:>5}{marker}  {h.get('accepted', False)!s:>9}  "
              f"{s_comp['broad_enrich']:>9.3f}  {s_comp['broad_recall']:>9.3f}  "
              f"{s_enr['score']:>9.3f}  {s_comp['score']:>10.3f}")
        if h.get("accepted", False) or h["iter"] == 0:
            if s_enr["score"] > enr_only_best_score:
                enr_only_best_score = s_enr["score"]; enr_only_best_iter = h["iter"]
            if s_comp["score"] > comp_best_score:
                comp_best_score = s_comp["score"]; comp_best_iter = h["iter"]

    print()
    print(f"Old policy (enr_only)   best iter: {enr_only_best_iter}  score: {enr_only_best_score:.3f}")
    print(f"New policy (composite)  best iter: {comp_best_iter}  score: {comp_best_score:.3f}")

    if comp_best_iter == enr_only_best_iter:
        print("\nNo change — current artifacts already represent the new policy's winner.")
        return 0

    print()
    print(f"Action: rebuild Phase 2 best_* artifacts from iter {comp_best_iter}.")
    if args.dry_run:
        print("(dry-run; not writing)")
        return 0

    # --- 1. Source amp ---
    if comp_best_iter == 0:
        src_amp_path = out / "phase1_best_composite_amp.npy"
        if not src_amp_path.exists():
            print(f"ERROR: needed source not found: {src_amp_path}")
            return 2
        new_amp = np.load(src_amp_path)
        print(f"  source: {src_amp_path}  (Phase 1 baseline)")
    else:
        winner = next(h for h in history if h["iter"] == comp_best_iter)
        new_amp = rebuild_iter_amp(winner, cand_id, args.image_size, args.plate_length_mm)
        if new_amp is None:
            print()
            print("ERROR: cannot rebuild winning iter's amp because COMSOL exports are missing.")
            print("       Either copy data/comsol_exports/prodp2it<N>_*/ from the run host,")
            print("       or just re-run the pipeline (will pick up the fix automatically).")
            return 3
        print(f"  source: rebuilt from iter {comp_best_iter} COMSOL exports")

    # --- 2. Backup originals ---
    for fname in ["phase2_best_composite_amp.npy", "phase2_best_powder_broad.npy",
                  "phase2_best_powder_sharp.npy"]:
        f = out / fname
        if f.exists():
            bak = f.with_suffix(".bak.npy")
            shutil.copy2(f, bak)
            print(f"  backup: {f} -> {bak.name}")

    bak_summary = summary_path.with_suffix(".bak.json")
    shutil.copy2(summary_path, bak_summary)
    print(f"  backup: {summary_path.name} -> {bak_summary.name}")

    # --- 3. Write new artifacts ---
    np.save(out / "phase2_best_composite_amp.npy", new_amp)
    np.save(out / "phase2_best_powder_broad.npy", make_powder(new_amp, 0.05))
    np.save(out / "phase2_best_powder_sharp.npy", make_powder(new_amp, 0.025))
    print(f"  wrote: phase2_best_composite_amp.npy + powder broad/sharp")

    # --- 4. Update summary ---
    winner = next(h for h in history if h["iter"] == comp_best_iter)
    winner_bc = winner["best_composite"]
    winner_score = composite_score(winner_bc, "composite")
    baseline_score = composite_score(history[0]["best_composite"], "composite")["score"]

    phase2["score_mode"] = "composite"
    phase2["best_iter"] = int(comp_best_iter)
    phase2["best_score"] = float(comp_best_score)
    phase2["best_enrichment"] = float(winner_score["broad_enrich"])
    phase2["best_recall"] = float(winner_score["broad_recall"])
    phase2["baseline_score"] = float(baseline_score)
    phase2["improvement_pct"] = float((comp_best_score - baseline_score) / max(baseline_score, 1e-9) * 100)
    phase2["_posthoc_rebuilt_from_legacy_enr_only"] = True

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  updated: {summary_path}")

    print()
    print("Done. Reload the frontend / re-render any plots that pull from output_dir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
