"""Resume battery — PLA-only side (5 runs).

Adds disk-space guard between runs and aggressive .mph cleanup AFTER each run
to avoid the disk-full failure we hit on the first attempt.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PROJECT_ROOT / "config.yaml"
BACKUP = PROJECT_ROOT / "config.yaml.bak_battery_resume"
COMSOL_DIR = PROJECT_ROOT / "data" / "comsol_exports"


TARGETS = [
    ("cross",        "data/processed_targets/target_cross.npy"),
    ("diagonal",     "data/processed_targets/target_diagonal.npy"),
    ("xform",        "data/processed_targets/target_xform.npy"),
    ("star_outline", "data/_d_verify_targets/star_outline.npy"),
    ("ic",           "data/processed_targets/target_ic.npy"),
]

PLA_PATCH = {"density_kg_m3": 1240, "youngs_modulus_pa": 3500000000, "poisson_ratio": 0.36}
MIN_FREE_GB = 3.0  # abort if less than this is available before a new run


def patch_material(text: str, patch: dict[str, float]) -> str:
    text = re.sub(r"^(\s*density_kg_m3:\s*)\d+(\.\d+)?",
                   rf"\g<1>{patch['density_kg_m3']}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^(\s*youngs_modulus_pa:\s*)[\d.eE+\-]+",
                   rf"\g<1>{int(patch['youngs_modulus_pa'])}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^(\s*poisson_ratio:\s*)[\d.]+",
                   rf"\g<1>{patch['poisson_ratio']}", text, count=1, flags=re.MULTILINE)
    return text


def disk_free_gb() -> float:
    usage = shutil.disk_usage(str(PROJECT_ROOT))
    return usage.free / (1024 ** 3)


def cleanup_mph_files() -> int:
    """Delete .mph snapshots in data/comsol_exports (keep CSVs). Return count deleted."""
    count = 0
    for p in COMSOL_DIR.rglob("*.mph"):
        try:
            p.unlink()
            count += 1
        except Exception:
            pass
    return count


def run_one(target_label: str, target_path: str, log_dir: Path) -> dict:
    unique_id = f"bat_pla_{target_label}"
    out_dir = PROJECT_ROOT / "reports" / "_battery" / "pla" / target_label
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"pla_{target_label}.log"
    cmd = [
        ".venv/bin/python", "-u", "scripts/run_production_pipeline.py",
        "--candidate-id", unique_id,
        "--target-path", target_path,
        "--output-dir", str(out_dir.relative_to(PROJECT_ROOT)),
        "--stiffness-ratio", "1.0",
        "--shear-ratio",     "1.0",
        "--magic-off-resonance-hz", "",
    ]
    print(f"\n  >> [pla × {target_label}] launching", flush=True)
    print(f"     log:  {log_file}", flush=True)
    print(f"     free: {disk_free_gb():.2f} GB", flush=True)
    t0 = time.time()
    with log_file.open("wb") as fp:
        rc = subprocess.call(cmd, cwd=str(PROJECT_ROOT), stdout=fp, stderr=subprocess.STDOUT)
    elapsed = time.time() - t0

    # Aggressive .mph cleanup after each run
    deleted = cleanup_mph_files()
    print(f"     cleanup: {deleted} mph files removed → free now {disk_free_gb():.2f} GB", flush=True)

    summary_path = out_dir / unique_id / "production_summary.json"
    result = {
        "material": "pla", "target": target_label, "candidate_id": unique_id, "rc": rc,
        "wallclock_s": round(elapsed, 1), "summary_path": str(summary_path),
    }
    if summary_path.exists():
        s = json.loads(summary_path.read_text())
        p1 = (s.get("phase1") or {}).get("best_composite") or {}
        p2 = s.get("phase2") or {}
        result.update({
            "p1_broad_enr": (p1.get("broad") or {}).get("enrich"),
            "p1_broad_rec": (p1.get("broad") or {}).get("recall"),
            "p1_tight_enr": (p1.get("tight") or {}).get("enrich"),
            "p1_tight_rec": (p1.get("tight") or {}).get("recall"),
            "p1_subset":    p1.get("subset"),
            "p2_best_iter": p2.get("best_iter"),
            "p2_enr":       p2.get("best_enrichment"),
            "p2_rec":       p2.get("best_recall"),
        })
    print(f"     done rc={rc} wall={elapsed:.0f}s  → enr={result.get('p1_broad_enr')}  rec={result.get('p1_broad_rec')}", flush=True)
    return result


def main() -> int:
    log_dir = PROJECT_ROOT / "reports" / "_battery" / "_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if BACKUP.exists():
        print(f"[abort] backup exists: {BACKUP}", flush=True); return 2

    shutil.copy(CONFIG, BACKUP)
    original_cfg = CONFIG.read_text()
    CONFIG.write_text(patch_material(original_cfg, PLA_PATCH))
    print(f"[patched] config → PLA (ρ=1240, E=3.5 GPa, ν=0.36)", flush=True)

    all_results = []
    overall_t0 = time.time()
    try:
        for target_label, target_path in TARGETS:
            free = disk_free_gb()
            if free < MIN_FREE_GB:
                print(f"\n[abort] disk free {free:.2f} GB < {MIN_FREE_GB} GB; refusing to start new run", flush=True)
                break
            result = run_one(target_label, target_path, log_dir)
            all_results.append(result)
            # Save partial progress after each run
            out_json = PROJECT_ROOT / "reports" / "_battery" / "battery_pla_resume.json"
            out_json.write_text(json.dumps({
                "elapsed_total_s": round(time.time() - overall_t0, 1),
                "n_done": len(all_results), "n_total": len(TARGETS),
                "results": all_results,
            }, indent=2, ensure_ascii=False))
    finally:
        shutil.copy(BACKUP, CONFIG)
        BACKUP.unlink()
        print(f"\n[restore] config.yaml restored, backup removed", flush=True)
        # Final cleanup pass
        deleted = cleanup_mph_files()
        print(f"[final cleanup] {deleted} mph removed → free {disk_free_gb():.2f} GB", flush=True)

    print(f"\n==================== PLA RESUME DONE ====================", flush=True)
    print(f"Total wall: {(time.time()-overall_t0)/60:.1f} min  ({len(all_results)}/{len(TARGETS)})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
