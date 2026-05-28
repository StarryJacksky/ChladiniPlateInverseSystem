"""P0 fix verification: run W10 surrogate-only on 4 representative target shapes
under both the baseline and P0-fixed configs, then print a comparison table.

This is a one-shot diagnostic script (intentionally underscored / not part of
prod scripts). Run with: python scripts/_p0_verify_w10_arbitrary_targets.py

P0 修复验证：对 4 种代表性目标（细线星 / 字母 / 多连通点阵 / 实心块）
跑 baseline (原 W10) vs P0 (sigma 退火 + 目标膨胀) 的 surrogate-only 对比
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGETS_DIR = PROJECT_ROOT / "data" / "_p0_verify_targets"
OUTPUT_DIR = PROJECT_ROOT / "reports" / "_p0_verify"


def make_4pointed_star_outline(size: int = 256, thickness: int = 2) -> np.ndarray:
    """Thin 4-pointed star outline (closest to the user's actual target)."""
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r_outer = int(size * 0.40)
    r_inner = int(size * 0.10)
    pts = []
    for i in range(8):
        angle = (i * np.pi / 4) - np.pi / 2
        r = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + r * np.cos(angle), cy + r * np.sin(angle)))
    draw.polygon(pts, outline=255, fill=0, width=thickness)
    return np.array(img) > 127


def make_letter_C(size: int = 256, thickness: int = 22) -> np.ndarray:
    """Thick letter 'C' (representative of the old IC-style target — known to work)."""
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = int(size * 0.32)
    bbox = (cx - r, cy - r, cx + r, cy + r)
    draw.arc(bbox, start=30, end=330, fill=255, width=thickness)
    return np.array(img) > 127


def make_three_dots(size: int = 256, radius: int = 26) -> np.ndarray:
    """Three solid disks at 0°/120°/240° (multi-connected target)."""
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r_ring = int(size * 0.28)
    for i in range(3):
        angle = i * 2 * np.pi / 3 - np.pi / 2
        x = cx + r_ring * np.cos(angle)
        y = cy + r_ring * np.sin(angle)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    return np.array(img) > 127


def make_central_block(size: int = 256) -> np.ndarray:
    """Solid central rectangle (densest / easiest target)."""
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    half = size // 6
    cx, cy = size // 2, size // 2
    draw.rectangle((cx - half, cy - half, cx + half, cy + half), fill=255)
    return np.array(img) > 127


TARGETS = {
    "star_outline": make_4pointed_star_outline,
    "letter_C": make_letter_C,
    "three_dots": make_three_dots,
    "central_block": make_central_block,
}


def save_target(name: str, arr: np.ndarray) -> Path:
    TARGETS_DIR.mkdir(parents=True, exist_ok=True)
    npy_path = TARGETS_DIR / f"{name}.npy"
    np.save(npy_path, arr)
    preview_path = TARGETS_DIR / f"{name}_preview.png"
    Image.fromarray((arr * 255).astype(np.uint8)).save(preview_path)
    return npy_path


def run_w10(target_path: Path, candidate_id: str, *, baseline: bool, num_steps: int = 200) -> dict:
    """Run W10 surrogate-only and return its summary dict."""
    cmd = [
        sys.executable, str(PROJECT_ROOT / "scripts" / "run_w10_anisotropy.py"),
        "--config", str(PROJECT_ROOT / "config.yaml"),
        "--target", str(target_path),
        "--candidate-id", candidate_id,
        "--num-steps", str(num_steps),
        "--stiffness-ratio", "3.0",
        "--shear-ratio", "1.0",
        "--snapshot-every", "999999",
        "--num-frequencies", "6",
        "--f-min-hz", "120.0",
        "--f-max-hz", "1200.0",
    ]
    if baseline:
        # Baseline: explicitly disable annealing + dilation (matches pre-P0 behaviour)
        # sigma_anneal_start=None => not passed
        cmd.extend(["--target-dilation-px", "0"])
    else:
        # P0 fix: sigma 0.20 -> 0.05 over 100 steps, dilate 2 px
        cmd.extend([
            "--sigma-anneal-start", "0.20",
            "--sigma-anneal-steps", "100",
            "--target-dilation-px", "2",
        ])
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    t0 = time.time()
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, check=False)
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f"  [FAIL] {candidate_id}: returncode={result.returncode}")
        print(result.stderr[-1000:])
        return {"failed": True, "elapsed_s": elapsed, "stderr_tail": result.stderr[-500:]}
    summary_path = PROJECT_ROOT / "candidates" / candidate_id / "w10_optimization_summary.json"
    if not summary_path.exists():
        return {"failed": True, "elapsed_s": elapsed, "msg": "summary missing"}
    summary = json.loads(summary_path.read_text())
    surr = summary.get("best_surrogate_metrics", {})
    return {
        "failed": False,
        "elapsed_s": elapsed,
        "enrichment": float(surr.get("enrichment", 0.0)),
        "recall": float(surr.get("recall", 0.0)),
        "contrast": float(surr.get("contrast", 0.0)),
        "best_loss": float(summary.get("best_loss", float("nan"))),
        "frequencies_hz": summary.get("frequencies_hz", []),
        "weights": summary.get("weights", []),
        "effective_count": float(summary.get("weight_distribution", {}).get("effective_count", 0.0)),
        "summary_path": str(summary_path),
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    for name, factory in TARGETS.items():
        print(f"\n=== Target: {name} ===")
        arr = factory()
        target_path = save_target(name, arr)
        area_frac = float(arr.sum()) / float(arr.size)
        print(f"  pixels={int(arr.sum())} / {arr.size}  area_frac={area_frac:.2%}")

        print(f"  [baseline] running...")
        b = run_w10(target_path, candidate_id=f"_p0v_{name}_baseline", baseline=True, num_steps=200)
        print(f"  [baseline] enrichment={b.get('enrichment', 0):.3e}  recall={b.get('recall', 0):.3f}  elapsed={b.get('elapsed_s', 0):.1f}s")

        print(f"  [P0 fix]   running...")
        p = run_w10(target_path, candidate_id=f"_p0v_{name}_p0fix", baseline=False, num_steps=200)
        print(f"  [P0 fix]   enrichment={p.get('enrichment', 0):.3e}  recall={p.get('recall', 0):.3f}  elapsed={p.get('elapsed_s', 0):.1f}s")

        results[name] = {
            "area_frac": area_frac,
            "baseline": b,
            "p0_fix": p,
            "uplift_x": (float(p.get("enrichment", 0)) / max(float(b.get("enrichment", 0)), 1e-40)) if not b.get("failed") and not p.get("failed") else None,
        }

    out_json = OUTPUT_DIR / "p0_verify_results.json"
    out_json.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out_json}")

    print("\n" + "=" * 78)
    print(f"{'Target':<16} {'AreaFrac':>9} {'BaselineEnr':>14} {'P0EnrEnr':>14} {'Uplift':>10}")
    print("=" * 78)
    for name, r in results.items():
        b_enr = r["baseline"].get("enrichment", 0) if not r["baseline"].get("failed") else float("nan")
        p_enr = r["p0_fix"].get("enrichment", 0) if not r["p0_fix"].get("failed") else float("nan")
        uplift = r["uplift_x"]
        uplift_str = f"{uplift:.2e}x" if uplift is not None else "n/a"
        print(f"{name:<16} {r['area_frac']:>8.2%} {b_enr:>14.3e} {p_enr:>14.3e} {uplift_str:>10}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
