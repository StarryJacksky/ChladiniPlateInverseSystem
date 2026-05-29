"""Render side-by-side comparison: CF-PETG baseline vs PLA isotropic.

Reads both production_summary.json files plus the powder/composite .npy fields,
prints a metric table, and writes a comparison PNG.

Usage:
    .venv/bin/python scripts/_compare_pla_vs_cfpetg.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "reports" / "production" / "production_design"
PLA = ROOT / "reports" / "production_pla" / "production_design"
OUT = ROOT / "reports" / "_material_comparison"
OUT.mkdir(parents=True, exist_ok=True)


def load_summary(d: Path) -> dict:
    p = d / "production_summary.json"
    if not p.exists():
        print(f"[missing] {p}")
        sys.exit(1)
    return json.loads(p.read_text())


def take(s: dict, *keys, default=None):
    cur = s
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def summarize(label: str, s: dict) -> dict:
    row = {
        "label": label,
        "sr": s.get("stiffness_ratio"),
        "gr": s.get("shear_ratio"),
        "stage": s.get("stage_reached"),
        "surrogate_enr": take(s, "surrogate_metrics", "enrichment"),
        "surrogate_rec": take(s, "surrogate_metrics", "recall"),
        "p1_broad_enr": take(s, "phase1", "best_composite", "broad", "enrich"),
        "p1_broad_rec": take(s, "phase1", "best_composite", "broad", "recall"),
        "p1_tight_enr": take(s, "phase1", "best_composite", "tight", "enrich"),
        "p1_tight_rec": take(s, "phase1", "best_composite", "tight", "recall"),
        "p1_subset":    take(s, "phase1", "best_composite", "subset"),
        "p2_best_iter": take(s, "phase2", "best_iter"),
        "p2_best_score": take(s, "phase2", "best_score"),
        "p2_best_enr":  take(s, "phase2", "best_enrichment"),
        "p2_best_rec":  take(s, "phase2", "best_recall"),
        "p2_improv":    take(s, "phase2", "improvement_pct"),
        "wall_surr":    take(s, "wallclock_seconds", "surrogate"),
        "wall_p1":      take(s, "wallclock_seconds", "phase1"),
        "wall_p2":      take(s, "wallclock_seconds", "phase2"),
    }
    return row


def fmt(v, w=8, p=3):
    if v is None:
        return f"{'—':<{w}}"
    if isinstance(v, float):
        return f"{v:<{w}.{p}f}"
    return f"{str(v):<{w}}"


def print_table(rows: list[dict]) -> None:
    print()
    print("=" * 100)
    print(f"{'metric':<26}" + "".join(f"{r['label']:<25}" for r in rows))
    print("-" * 100)
    fields = [
        ("stiffness_ratio (sr)",     "sr", 8, 1),
        ("shear_ratio (gr)",          "gr", 8, 1),
        ("stage_reached",             "stage", 14, 0),
        ("surrogate.enrichment",      "surrogate_enr", 10, 3),
        ("surrogate.recall",          "surrogate_rec", 10, 3),
        ("phase1 broad.enrich  ★",    "p1_broad_enr",  10, 3),
        ("phase1 broad.recall  ★",    "p1_broad_rec",  10, 3),
        ("phase1 tight.enrich",       "p1_tight_enr",  10, 3),
        ("phase1 tight.recall",       "p1_tight_rec",  10, 3),
        ("phase1 subset",             "p1_subset",     16, 0),
        ("phase2 best_iter",          "p2_best_iter",  10, 0),
        ("phase2 best_score",         "p2_best_score", 10, 3),
        ("phase2 best.enrich",        "p2_best_enr",   10, 3),
        ("phase2 best.recall",        "p2_best_rec",   10, 3),
        ("phase2 improvement %",      "p2_improv",     10, 2),
        ("wallclock surrogate (s)",   "wall_surr",     10, 1),
        ("wallclock phase1 (s)",      "wall_p1",       10, 1),
        ("wallclock phase2 (s)",      "wall_p2",       10, 1),
    ]
    for label, k, w, p in fields:
        line = f"{label:<26}"
        for r in rows:
            line += fmt(r[k], w, p) + " " * (25 - w)
        print(line)
    print("=" * 100)


def load_powder(d: Path, stage: str, kind: str = "broad"):
    """stage: phase1 | phase2; kind: broad | sharp | composite_amp"""
    p = d / f"{stage}_best_powder_{kind}.npy"
    if not p.exists():
        p = d / f"{stage}_best_{kind}.npy"
    if not p.exists():
        return None
    return np.load(p)


def render_comparison(target: np.ndarray, baseline_p1, baseline_p2, pla_p1, pla_p2,
                      title_baseline: str, title_pla: str, out_path: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(13, 9))

    axes[0, 0].imshow(target, cmap="gray_r")
    axes[0, 0].set_title("Target")
    axes[0, 0].axis("off")
    axes[0, 1].imshow(baseline_p1 if baseline_p1 is not None else np.zeros_like(target), cmap="afmhot")
    axes[0, 1].set_title(f"{title_baseline}\nPhase 1 powder (broad)")
    axes[0, 1].axis("off")
    axes[0, 2].imshow(baseline_p2 if baseline_p2 is not None else np.zeros_like(target), cmap="afmhot")
    axes[0, 2].set_title(f"{title_baseline}\nPhase 2 powder (broad)")
    axes[0, 2].axis("off")

    axes[1, 0].imshow(target, cmap="gray_r")
    axes[1, 0].set_title("Target")
    axes[1, 0].axis("off")
    axes[1, 1].imshow(pla_p1 if pla_p1 is not None else np.zeros_like(target), cmap="afmhot")
    axes[1, 1].set_title(f"{title_pla}\nPhase 1 powder (broad)")
    axes[1, 1].axis("off")
    axes[1, 2].imshow(pla_p2 if pla_p2 is not None else np.zeros_like(target), cmap="afmhot")
    axes[1, 2].set_title(f"{title_pla}\nPhase 2 powder (broad)")
    axes[1, 2].axis("off")

    fig.suptitle("Material A/B: CF-PETG (sr=3.0) vs school FDM PLA (sr=1.0, no θ)", fontsize=14)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print(f"[wrote] {out_path}")


def main() -> int:
    baseline = load_summary(BASELINE)
    pla = load_summary(PLA)
    rows = [summarize("CF-PETG (sr=3.0)", baseline),
            summarize("PLA iso (sr=1.0)", pla)]
    print_table(rows)

    target_path = BASELINE / "target_resized.npy"
    target = np.load(target_path) if target_path.exists() else np.zeros((256, 256))
    b_p1 = load_powder(BASELINE, "phase1", "broad")
    b_p2 = load_powder(BASELINE, "phase2", "broad")
    p_p1 = load_powder(PLA, "phase1", "broad")
    p_p2 = load_powder(PLA, "phase2", "broad")
    render_comparison(target, b_p1, b_p2, p_p1, p_p2,
                      "CF-PETG  sr=3.0", "PLA iso  sr=1.0",
                      OUT / "pla_vs_cfpetg.png")

    (OUT / "comparison.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"[wrote] {OUT / 'comparison.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
