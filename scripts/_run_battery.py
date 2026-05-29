"""Run the production pipeline across the target × material battery.

Battery (10 new runs, sequential, ~9 min each ≈ 90 min total):

    targets:    cross, diagonal, xform, star_outline, ic    (5)
    materials:  cf-petg (sr=3, default cfg), pla (sr=1, iso, school FDM)

Note: target_binary (the 8-element pattern, current production target) is
already done for both materials, so we don't repeat it.

For PLA we temporarily patch config.yaml material (E, ρ, ν), then restore.

Outputs land at:
    reports/_battery/<material>/<target>/production_design/
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
BACKUP = PROJECT_ROOT / "config.yaml.bak_battery"


TARGETS = [
    # (label, .npy path relative to project root)
    ("cross",        "data/processed_targets/target_cross.npy"),
    ("diagonal",     "data/processed_targets/target_diagonal.npy"),
    ("xform",        "data/processed_targets/target_xform.npy"),
    ("star_outline", "data/_d_verify_targets/star_outline.npy"),
    ("ic",           "data/processed_targets/target_ic.npy"),
]

# 2 material presets. Each entry:
#   (label, stiffness_ratio, shear_ratio, magic_freqs_csv, optional config patches)
MATERIALS = [
    ("cfpetg", 3.0, 1.0, "165.0", None),  # current default, no config patch
    ("pla",    1.0, 1.0, "",      {"density_kg_m3": 1240, "youngs_modulus_pa": 3500000000, "poisson_ratio": 0.36}),
]


def patch_material(text: str, patch: dict[str, float]) -> str:
    if "density_kg_m3" in patch:
        text = re.sub(r"^(\s*density_kg_m3:\s*)\d+(\.\d+)?",
                       rf"\g<1>{patch['density_kg_m3']}", text, count=1, flags=re.MULTILINE)
    if "youngs_modulus_pa" in patch:
        text = re.sub(r"^(\s*youngs_modulus_pa:\s*)[\d.eE+\-]+",
                       rf"\g<1>{int(patch['youngs_modulus_pa'])}", text, count=1, flags=re.MULTILINE)
    if "poisson_ratio" in patch:
        text = re.sub(r"^(\s*poisson_ratio:\s*)[\d.]+",
                       rf"\g<1>{patch['poisson_ratio']}", text, count=1, flags=re.MULTILINE)
    return text


def run_one(target_label: str, target_path: str,
             mat_label: str, sr: float, gr: float, magic: str,
             cfg_patch: dict | None, log_dir: Path) -> dict:
    """Run a single pipeline configuration; return summary dict."""
    out_dir = PROJECT_ROOT / "reports" / "_battery" / mat_label / target_label
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{mat_label}_{target_label}.log"

    # Unique candidate_id avoids COMSOL forced_response CSV collisions across runs
    # (different runs may pick the same drive freq, e.g. 165 Hz magic). /
    # 唯一 candidate_id 防 COMSOL CSV 互覆盖
    unique_id = f"bat_{mat_label}_{target_label}"
    cmd = [
        ".venv/bin/python", "-u", "scripts/run_production_pipeline.py",
        "--candidate-id", unique_id,
        "--target-path", target_path,
        "--output-dir", str(out_dir.relative_to(PROJECT_ROOT)),
        "--stiffness-ratio", str(sr),
        "--shear-ratio", str(gr),
        "--magic-off-resonance-hz", magic,
    ]
    print(f"\n  >> [{mat_label} × {target_label}] launching", flush=True)
    print(f"     log: {log_file}", flush=True)
    t0 = time.time()
    with log_file.open("wb") as fp:
        rc = subprocess.call(cmd, cwd=str(PROJECT_ROOT), stdout=fp, stderr=subprocess.STDOUT)
    elapsed = time.time() - t0
    summary_path = out_dir / unique_id / "production_summary.json"
    result = {
        "material": mat_label,
        "target": target_label,
        "candidate_id": unique_id,
        "rc": rc,
        "wallclock_s": round(elapsed, 1),
        "summary_path": str(summary_path),
    }
    if summary_path.exists():
        try:
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
        except Exception as e:
            result["parse_error"] = str(e)
    print(f"     done rc={rc} wall={elapsed:.0f}s  → "
          f"enr={result.get('p1_broad_enr')}  rec={result.get('p1_broad_rec')}", flush=True)
    return result


def main() -> int:
    log_dir = PROJECT_ROOT / "reports" / "_battery" / "_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    overall_t0 = time.time()

    if BACKUP.exists():
        print(f"[abort] backup exists: {BACKUP}", flush=True)
        return 2

    shutil.copy(CONFIG, BACKUP)
    original_cfg = CONFIG.read_text()
    print(f"[backup] config.yaml → config.yaml.bak_battery", flush=True)

    try:
        for mat_label, sr, gr, magic, cfg_patch in MATERIALS:
            print(f"\n========== MATERIAL: {mat_label} (sr={sr}, gr={gr}) ==========", flush=True)
            if cfg_patch is not None:
                CONFIG.write_text(patch_material(original_cfg, cfg_patch))
                print(f"[patched] {cfg_patch}", flush=True)
            else:
                CONFIG.write_text(original_cfg)
                print(f"[unpatched] config.yaml restored to default for {mat_label}", flush=True)

            for target_label, target_path in TARGETS:
                result = run_one(target_label, target_path, mat_label, sr, gr, magic, cfg_patch, log_dir)
                all_results.append(result)
                # write partial results after each run so user sees progress
                out_json = PROJECT_ROOT / "reports" / "_battery" / "battery_results.json"
                out_json.write_text(json.dumps({
                    "elapsed_total_s": round(time.time() - overall_t0, 1),
                    "n_done": len(all_results),
                    "n_total": len(MATERIALS) * len(TARGETS),
                    "results": all_results,
                }, indent=2, ensure_ascii=False))

    finally:
        shutil.copy(BACKUP, CONFIG)
        BACKUP.unlink()
        print(f"\n[restore] config.yaml restored, backup removed", flush=True)

    total = time.time() - overall_t0
    print(f"\n==================== BATTERY DONE ====================", flush=True)
    print(f"Total wall: {total/60:.1f} min  ({len(all_results)}/{len(MATERIALS)*len(TARGETS)} runs)", flush=True)
    print(f"Results: reports/_battery/battery_results.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
