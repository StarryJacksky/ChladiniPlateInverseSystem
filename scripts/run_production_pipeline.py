"""CLI entry for the production inverse-design pipeline.

Examples:
    # full pipeline with default tier1 (sr=3) + Phase 2 (1 iter)
    .venv/bin/python scripts/run_production_pipeline.py --candidate-id production_demo_ic

    # surrogate-only fast preview (no COMSOL)
    .venv/bin/python scripts/run_production_pipeline.py --candidate-id demo --skip-comsol

    # custom material + skip phase 2
    .venv/bin/python scripts/run_production_pipeline.py --candidate-id demo \
        --stiffness-ratio 12.0 --shear-ratio 1.5 --skip-phase2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.optimisation.production_pipeline import (
    ProductionPipelineConfig,
    run_production_pipeline,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the end-to-end Chladni inverse-design production pipeline.")
    p.add_argument("--candidate-id", default="production_design")
    p.add_argument("--target-path", default="data/processed_targets/target_binary.npy")
    p.add_argument("--output-dir", default="reports/production")
    p.add_argument("--stiffness-ratio", type=float, default=3.0,
                     help="Material anisotropy E_par/E_perp (default 3.0 = CF-PETG tier1).")
    p.add_argument("--shear-ratio", type=float, default=1.0)
    p.add_argument("--w10-num-steps", type=int, default=300)
    p.add_argument("--w10-lr-h", type=float, default=0.05)
    p.add_argument("--phase1-top-k-modes", type=int, default=6)
    p.add_argument("--magic-off-resonance-hz", default="165.0",
                     help="Comma-separated extra off-resonance freqs (default tier1 magic 165).")
    p.add_argument("--phase2-max-iters", type=int, default=1)
    p.add_argument("--skip-phase2", action="store_true")
    p.add_argument("--skip-comsol", action="store_true",
                     help="Fast preview: surrogate only, no COMSOL.")
    p.add_argument("--multistart-n", type=int, default=1,
                     help="DEPRECATED: kept for compatibility. Since theta optimisation was "
                          "removed the W10 surrogate is deterministic, so N>1 is a no-op.")
    p.add_argument("--multistart-uplift-threshold", type=float, default=0.05,
                     help="DEPRECATED: kept for compatibility (multistart is now a no-op).")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    magic_freqs = tuple(float(s.strip()) for s in args.magic_off_resonance_hz.split(",") if s.strip())
    cfg = ProductionPipelineConfig(
        target_path=args.target_path,
        candidate_id=args.candidate_id,
        output_dir=args.output_dir,
        stiffness_ratio=args.stiffness_ratio,
        shear_ratio=args.shear_ratio,
        w10_num_steps=args.w10_num_steps,
        w10_lr_h=args.w10_lr_h,
        phase1_top_k_modes=args.phase1_top_k_modes,
        magic_off_resonance_hz=magic_freqs,
        phase2_max_iters=args.phase2_max_iters,
        skip_phase2=args.skip_phase2,
        skip_comsol=args.skip_comsol,
        multistart_n=args.multistart_n,
        multistart_uplift_threshold=args.multistart_uplift_threshold,
    )

    def progress_printer(event: dict) -> None:
        stage = event.get("stage", "?")
        msg = event.get("message", "")
        print(f"[{stage:>20}] {msg}", flush=True)

    result = run_production_pipeline(cfg, progress=progress_printer)
    print()
    print("=" * 80)
    print("PIPELINE FINAL")
    print("=" * 80)
    if result.get("stage_reached") == "surrogate_only":
        sm = result.get("surrogate_metrics", {})
        print(f"  Mode: surrogate-only")
        print(f"  Surrogate enrichment: {sm.get('enrichment', 0):.2f}×")
    else:
        p1 = result["phase1"]["best_composite"]
        print(f"  Phase 1 best composite: {p1['method']}({'+'.join(p1['subset'])})")
        print(f"    broad enr={p1['broad']['enrich']:.2f}× rec={p1['broad']['recall']:.2f}")
        print(f"    tight enr={p1['tight']['enrich']:.2f}× rec={p1['tight']['recall']:.2f}")
        bs = result["phase1"].get("best_single")
        if bs:
            print(f"  Phase 1 best SINGLE freq (heuristic): {bs['subset'][0]}Hz")
            print(f"    broad enr={bs['broad']['enrich']:.2f}× rec={bs['broad']['recall']:.2f}")
            print(f"    tight enr={bs['tight']['enrich']:.2f}× rec={bs['tight']['recall']:.2f}")
            print(f"    NOTE: a scalar score can't pick the most recognisable tone —")
            print(f"          eyeball all single frequencies in phase1_single_freq_gallery.png")
        if "phase2" in result:
            p2 = result["phase2"]
            print(f"  Phase 2: best iter {p2['best_iter']} → score {p2.get('best_score', 0):.3f} "
                    f"(enr {p2.get('best_enrichment', 0):.2f}× rec {p2.get('best_recall', 0):.2f})  "
                    f"{p2['improvement_pct']:+.1f}% over Phase 1  [mode={p2.get('score_mode', 'composite')}]")
    print(f"\n  Output: {result['output_dir']}")
    print(f"  Summary: {result.get('summary_path', '(not saved)')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
