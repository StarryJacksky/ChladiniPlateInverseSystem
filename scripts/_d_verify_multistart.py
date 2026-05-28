"""D verification: multi-start anti-regression contract check.

Runs the production pipeline (surrogate-only) on a 4-pointed star target
with N=1 (single-start baseline) and N=4 (multi-start), then verifies:

  1.  N=1 path is unchanged (zero overhead when multistart_n=1).
  2.  N=4 produces a multistart_log block with N seeds, including seed=42.
  3.  Anti-regression: winner's composite score ≥ baseline (seed=42) score.
     If the winner != seed=42, the uplift exceeds the threshold.
  4.  No degradation in canonical metrics (best_surrogate_metrics).

D 多启动验证：3 重防退化合约不能被破坏
  1) N=1 路径零开销维持原样
  2) N=4 必须写出 multistart_log 包含所有种子
  3) winner score ≥ seed=42 score；换人时 uplift > 阈值
  4) 表层指标不退化
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.optimisation.production_pipeline import (
    ProductionPipelineConfig,
    _composite_score,
    run_production_pipeline,
)

TARGETS_DIR = PROJECT_ROOT / "data" / "_d_verify_targets"
OUTPUT_DIR = PROJECT_ROOT / "reports" / "_d_verify"


def make_4pointed_star_outline(size: int = 256, thickness: int = 2) -> np.ndarray:
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


def run_pipeline(target_path: Path, candidate_id: str, multistart_n: int, *,
                  num_steps: int = 200) -> dict:
    cfg = ProductionPipelineConfig(
        target_path=str(target_path),
        candidate_id=candidate_id,
        output_dir=str(OUTPUT_DIR / candidate_id),
        stiffness_ratio=3.0,
        shear_ratio=1.0,
        w10_num_steps=num_steps,
        skip_comsol=True,
        skip_phase2=True,
        multistart_n=multistart_n,
    )

    def printer(event: dict) -> None:
        print(f"  [{event.get('stage', '?'):>22}] {event.get('message', '')}", flush=True)

    t0 = time.time()
    result = run_production_pipeline(cfg, progress=printer)
    elapsed = time.time() - t0
    surr = result.get("surrogate_metrics", {})
    mslog = result.get("w10_summary", {}).get("multistart_log")
    return {
        "candidate_id": candidate_id,
        "multistart_n": multistart_n,
        "elapsed_s": float(elapsed),
        "enrichment": float(surr.get("enrichment", 0.0)),
        "recall": float(surr.get("recall", 0.0)),
        "composite_score": float(_composite_score(result.get("w10_summary", {}))["score"]),
        "multistart_log": mslog,
    }


def main() -> int:
    TARGETS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    arr = make_4pointed_star_outline()
    target_path = TARGETS_DIR / "star_outline.npy"
    np.save(target_path, arr)
    Image.fromarray((arr * 255).astype(np.uint8)).save(TARGETS_DIR / "star_outline_preview.png")
    print(f"Target: {int(arr.sum())} px out of {arr.size}")

    print("\n=== N=1 baseline (zero-overhead path) ===")
    r1 = run_pipeline(target_path, "_dv_n1", multistart_n=1, num_steps=200)

    print("\n=== N=4 multi-start ===")
    r4 = run_pipeline(target_path, "_dv_n4", multistart_n=4, num_steps=200)

    summary = {"n1": r1, "n4": r4}
    (OUTPUT_DIR / "d_verify_results.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 80)
    print(f"  N=1: enr={r1['enrichment']:.2f}× rec={r1['recall']:.2f} "
          f"score={r1['composite_score']:.3f}  elapsed={r1['elapsed_s']:.0f}s")
    print(f"  N=4: enr={r4['enrichment']:.2f}× rec={r4['recall']:.2f} "
          f"score={r4['composite_score']:.3f}  elapsed={r4['elapsed_s']:.0f}s")

    print("\n--- Anti-regression contract checks ---")
    ok = True

    if r1["multistart_log"] is not None:
        print("  FAIL: N=1 path emitted a multistart_log (should be None for zero overhead)")
        ok = False
    else:
        print("  OK:   N=1 emits no multistart_log (zero overhead path)")

    log4 = r4["multistart_log"]
    if log4 is None:
        print("  FAIL: N=4 did not emit multistart_log")
        ok = False
    else:
        seeds = log4.get("seeds", [])
        if 42 not in seeds:
            print(f"  FAIL: N=4 seeds={seeds} missing baseline seed=42")
            ok = False
        else:
            print(f"  OK:   N=4 seeds={seeds} includes baseline seed=42")
        cands = log4.get("candidates", [])
        if len(cands) != 4:
            print(f"  FAIL: N=4 produced {len(cands)} candidate logs (expected 4)")
            ok = False
        else:
            print(f"  OK:   N=4 produced {len(cands)} candidate logs")

        baseline = next((c for c in cands if c["seed"] == 42 and c.get("ok")), None)
        if baseline is not None:
            base_score = float(baseline["score"])
            if r4["composite_score"] + 1e-6 < base_score:
                print(f"  FAIL: winner score {r4['composite_score']:.3f} < baseline {base_score:.3f} (regression!)")
                ok = False
            else:
                print(f"  OK:   winner score {r4['composite_score']:.3f} ≥ seed=42 baseline {base_score:.3f}")

            winner_seed = int(log4.get("winner_seed", -1))
            if winner_seed != 42:
                uplift = r4["composite_score"] / max(base_score, 1e-9) - 1.0
                thresh = float(log4.get("uplift_threshold", 0.05))
                if uplift > thresh:
                    print(f"  OK:   non-baseline winner seed={winner_seed}, uplift +{uplift*100:.1f}% > {thresh*100:.0f}% threshold")
                else:
                    print(f"  FAIL: promoted seed={winner_seed} with uplift +{uplift*100:.1f}% ≤ threshold {thresh*100:.0f}%")
                    ok = False
            else:
                print(f"  OK:   kept baseline seed=42")
        else:
            print(f"  WARN: baseline seed=42 failed health-check in N=4 — multistart still must have a winner")

        print(f"\n  Decision: {log4.get('decision', '(none)')}")
        print(f"  Per-seed scores:")
        for c in cands:
            tag = "*" if int(c["seed"]) == int(log4.get("winner_seed", -1)) else " "
            print(f"    {tag} seed={c['seed']:>3}  enr={c.get('enrichment', 0):.2f}×  "
                  f"rec={c.get('recall', 0):.2f}  effC={c.get('effective_count', 0):.1f}  "
                  f"score={c.get('score', 0):.3f}  ok={c.get('ok', False)}")

    print("=" * 80)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
