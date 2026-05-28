"""Material generalisation check — does tier2 (sr=12) really help ALL targets, or only IC?

For 4 target patterns × 3 material tiers (sr=1, 3, 12), run surrogate-only W10 and report:
- Best surrogate enrichment
- Best surrogate recall
- Which sr wins for each target

Targets:
  T1: IC (current, asymmetric letters)         — should prefer high sr
  T2: Circle ring (D4-symmetric)               — should NOT need high sr
  T3: Plus sign "+" (D4-symmetric)             — should NOT need high sr  
  T4: Letter "A" (asymmetric, no curves)        — should benefit from high sr

If sr=12 wins for ALL → tier2 is a generic upgrade (recommend universally)
If sr=12 wins only for asymmetric → recommend per-target (need a material selector in UI)
If sr=12 loses to sr=1 for symmetric → tier2 is NOT pattern-agnostic; need to warn user
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont


IMAGE_SIZE = 256


def make_circle_ring(size: int = IMAGE_SIZE) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size]
    cx = cy = size / 2.0
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    r_outer = size * 0.32
    r_inner = size * 0.22
    mask = (r >= r_inner) & (r <= r_outer)
    return mask.astype(np.uint8)


def make_plus_sign(size: int = IMAGE_SIZE) -> np.ndarray:
    img = np.zeros((size, size), dtype=np.uint8)
    cx = cy = size // 2
    arm_h = size // 12  # half-width
    arm_l = size // 3   # half-length
    img[cy - arm_h:cy + arm_h, cx - arm_l:cx + arm_l] = 1
    img[cy - arm_l:cy + arm_l, cx - arm_h:cx + arm_h] = 1
    return img


def make_letter(letter: str, size: int = IMAGE_SIZE) -> np.ndarray:
    pil = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(pil)
    # Try to use a reasonable system font
    font = None
    for fp in ["/System/Library/Fonts/Helvetica.ttc",
               "/System/Library/Fonts/Supplemental/Arial.ttf",
               "/Library/Fonts/Arial.ttf"]:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, int(size * 0.7))
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), letter, font=font)
    w = bbox[2] - bbox[0]; h = bbox[3] - bbox[1]
    draw.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), letter, fill=255, font=font)
    arr = np.array(pil) > 127
    return arr.astype(np.uint8)


def generate_targets(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = {
        "IC": Path("data/processed_targets/target_binary.npy"),  # use existing
        "Circle": out_dir / "target_circle.npy",
        "Plus": out_dir / "target_plus.npy",
        "A": out_dir / "target_letterA.npy",
    }
    if not targets["Circle"].exists():
        np.save(targets["Circle"], make_circle_ring())
    if not targets["Plus"].exists():
        np.save(targets["Plus"], make_plus_sign())
    if not targets["A"].exists():
        np.save(targets["A"], make_letter("A"))
    print(f"Targets:")
    for name, p in targets.items():
        t = np.load(p)
        print(f"  {name}: {p}  pixels_on={int(t.sum())}/{t.size}")
    return targets


def run_w10_single(target_name: str, target_path: Path, sr: float, num_steps: int = 150,
                    output_dir: Path = Path("reports/generalisation_check")) -> dict:
    """Run W10 surrogate optimisation for a single (target, sr) and return best metrics."""
    candidate_id = f"gencheck_{target_name}_sr{sr:g}"
    candidate_out = output_dir / candidate_id
    candidate_out.mkdir(parents=True, exist_ok=True)
    cmd = [
        ".venv/bin/python", "scripts/run_w10_anisotropy.py",
        "--target", str(target_path.resolve()),
        "--candidate-id", candidate_id,
        "--output-dir", str(candidate_out),
        "--num-steps", str(num_steps),
        "--stiffness-ratio", str(sr),
        "--shear-ratio", "1.5" if sr > 3 else "1.0",
        "--num-frequencies", "6",
        "--f-min-hz", "120",
        "--f-max-hz", "1200",
        "--learning-rate-h", "0.05",
        "--learning-rate-theta", "0.10",
        "--snapshot-every", "300",  # disable intermediate snapshots
        "--theta-init-mode", "random",
        "--theta-seed", "42",
    ]
    print(f"\n>>> Running W10 for {target_name} sr={sr}...")
    t0 = __import__("time").time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  FAILED: rc={res.returncode}")
        print(res.stdout[-500:])
        print(res.stderr[-500:])
        return {"error": True, "rc": res.returncode, "stderr": res.stderr[-500:]}
    dt = __import__("time").time() - t0
    print(f"  done in {dt:.1f}s")
    # Read summary
    summary_path = candidate_out / "w10_optimization_summary.json"
    if not summary_path.exists():
        return {"error": True, "msg": "no summary.json"}
    summary = json.load(open(summary_path))
    m = summary.get("best_surrogate_metrics", {})
    return {
        "target": target_name,
        "sr": float(sr),
        "best_surrogate_enrichment": float(m.get("enrichment", 0.0)),
        "best_surrogate_contrast": float(m.get("contrast", 0.0)),
        "best_surrogate_recall": float(m.get("recall", 0.0)),
        "best_step": int(summary.get("best_step", 0)),
        "elapsed_s": float(dt),
        "candidate_id": candidate_id,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--num-steps", type=int, default=150, help="W10 steps per run.")
    p.add_argument("--output-dir", default="reports/generalisation_check")
    p.add_argument("--targets", default="IC,Circle,Plus,A", help="Comma-separated target names.")
    p.add_argument("--sr-values", default="1.0,3.0,12.0", help="Comma-separated stiffness ratios.")
    p.add_argument("--skip-existing", action="store_true", help="Skip runs whose summary.json already exists.")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target_dir = out_dir / "targets"
    targets = generate_targets(target_dir)

    sr_list = [float(s) for s in args.sr_values.split(",")]
    target_names = [t.strip() for t in args.targets.split(",")]

    results = []
    for tn in target_names:
        if tn not in targets:
            print(f"Skipping unknown target {tn}")
            continue
        for sr in sr_list:
            sjson = out_dir / f"gencheck_{tn}_sr{sr:g}" / "w10_optimization_summary.json"
            if args.skip_existing and sjson.exists():
                summary = json.load(open(sjson))
                m = summary.get("best_surrogate_metrics", {})
                results.append({
                    "target": tn, "sr": float(sr),
                    "best_surrogate_enrichment": float(m.get("enrichment", 0.0)),
                    "best_surrogate_contrast": float(m.get("contrast", 0.0)),
                    "best_surrogate_recall": float(m.get("recall", 0.0)),
                    "best_step": int(summary.get("best_step", 0)),
                    "candidate_id": f"gencheck_{tn}_sr{sr:g}",
                    "skipped_existing": True,
                })
                continue
            r = run_w10_single(tn, targets[tn], sr, num_steps=args.num_steps, output_dir=out_dir)
            results.append(r)

    # === Summarise ===
    print(f"\n{'='*70}")
    print(f"{'target':<10} {'sr':>6} | {'enrich':>8} {'recall':>8}  {'contrast':>9}  best@step")
    print(f"{'-'*70}")
    by_target = {}
    for r in results:
        if r.get("error"):
            print(f"{r['target']:<10} {r['sr']:>6.1f} | ERROR")
            continue
        print(f"{r['target']:<10} {r['sr']:>6.1f} | {r['best_surrogate_enrichment']:>8.2f}× {r['best_surrogate_recall']*100:>7.1f}%  {r['best_surrogate_contrast']:>8.2f}×  {r['best_step']}")
        by_target.setdefault(r["target"], []).append(r)

    # Decision table
    print(f"\n=== PER-TARGET BEST sr ===")
    print(f"{'target':<10} {'best_sr':>8} {'enrich':>8}  {'2nd_best_sr':>12} {'enrich':>8}")
    verdicts = {}
    for tn, rows in by_target.items():
        rows_valid = [r for r in rows if not r.get("error")]
        if not rows_valid: continue
        rows_sorted = sorted(rows_valid, key=lambda x: -x["best_surrogate_enrichment"])
        best = rows_sorted[0]; second = rows_sorted[1] if len(rows_sorted) > 1 else None
        verdicts[tn] = {"best_sr": best["sr"], "best_enrich": best["best_surrogate_enrichment"]}
        s_line = f"{tn:<10} {best['sr']:>8.1f} {best['best_surrogate_enrichment']:>7.2f}×"
        if second:
            s_line += f"  {second['sr']:>12.1f} {second['best_surrogate_enrichment']:>7.2f}×"
        print(s_line)

    best_srs = set(v["best_sr"] for v in verdicts.values())
    if len(best_srs) == 1:
        verdict = f"UNIVERSAL: sr={best_srs.pop()} wins for ALL targets → material is pattern-agnostic"
    elif all(v["best_sr"] >= 3 for v in verdicts.values()):
        verdict = "HIGH-SR GENERIC: tier1/tier2 always beat sr=1 → high sr is generic upgrade"
    else:
        symmetric_targets = ["Circle", "Plus"]
        sym_best_srs = [verdicts[t]["best_sr"] for t in symmetric_targets if t in verdicts]
        asym_best_srs = [verdicts[t]["best_sr"] for t in verdicts if t not in symmetric_targets]
        if sym_best_srs and asym_best_srs and max(sym_best_srs) < max(asym_best_srs):
            verdict = "TARGET-AWARE: high sr only helps asymmetric targets; symmetric prefer low sr"
        else:
            verdict = "MIXED: best sr varies; material should be per-target"

    print(f"\n=== VERDICT ===\n{verdict}")

    # Bar chart
    fig, ax = plt.subplots(1, 2, figsize=(14, 5))
    target_names_avail = list(by_target.keys())
    sr_vals = sorted(sr_list)
    width = 0.25
    x = np.arange(len(target_names_avail))
    for i, sr in enumerate(sr_vals):
        ys = [next((r["best_surrogate_enrichment"] for r in by_target[t] if abs(r["sr"] - sr) < 0.01 and not r.get("error")), 0) for t in target_names_avail]
        ax[0].bar(x + i * width - width, ys, width, label=f"sr={sr:g}")
    ax[0].set_xticks(x); ax[0].set_xticklabels(target_names_avail)
    ax[0].set_ylabel("Best surrogate enrichment ×")
    ax[0].set_title("Surrogate enrichment vs sr per target")
    ax[0].axhline(1.0, color="k", lw=0.5)
    ax[0].legend()
    ax[0].grid(alpha=0.3, axis="y")

    for i, sr in enumerate(sr_vals):
        ys = [next((r["best_surrogate_recall"]*100 for r in by_target[t] if abs(r["sr"] - sr) < 0.01 and not r.get("error")), 0) for t in target_names_avail]
        ax[1].bar(x + i * width - width, ys, width, label=f"sr={sr:g}")
    ax[1].set_xticks(x); ax[1].set_xticklabels(target_names_avail)
    ax[1].set_ylabel("Best surrogate recall %")
    ax[1].set_title("Surrogate recall vs sr per target")
    ax[1].legend()
    ax[1].grid(alpha=0.3, axis="y")

    plt.suptitle(f"Material generalisation: does tier2 (sr=12) help all targets?\n{verdict}", fontsize=11)
    plt.tight_layout()
    fig.savefig(out_dir / "generalisation_check.png", dpi=130, bbox_inches="tight")
    plt.close(fig)

    (out_dir / "generalisation_check_summary.json").write_text(json.dumps({
        "verdict": verdict,
        "per_target_best": verdicts,
        "results": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nArtefacts:\n  {out_dir/'generalisation_check.png'}\n  {out_dir/'generalisation_check_summary.json'}")


if __name__ == "__main__":
    main()
