#!/usr/bin/env python3
"""CLI for the material-aware magic-frequency pre-sweep.

Quick standalone test of ``src.optimisation.material_frequency_sweep``. Useful
for smoke-testing before the UI calls the API endpoint, and for batch
calibration when the customer measures a new material.

Usage:
    python scripts/run_material_frequency_sweep.py \
        --stiffness-ratio 3.0 \
        --shear-ratio 1.0 \
        --target data/processed_targets/target_binary.npy \
        --f-min-hz 80 --f-max-hz 1500 --n-points 50 --top-k 3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config  # noqa: E402
from src.optimisation.material_frequency_sweep import (  # noqa: E402
    MaterialSweepConfig,
    run_material_frequency_sweep,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Material magic-frequency pre-sweep (surrogate-only).")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--target", default="data/processed_targets/target_binary.npy",
                        help="Path to target_binary.npy")
    parser.add_argument("--stiffness-ratio", type=float, default=3.0, help="E_||/E_⊥ ratio")
    parser.add_argument("--shear-ratio", type=float, default=1.0, help="G/G_iso ratio")
    parser.add_argument("--f-min-hz", type=float, default=80.0)
    parser.add_argument("--f-max-hz", type=float, default=1500.0)
    parser.add_argument("--n-points", type=int, default=50)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--proxy-grid-size", type=int, default=25)
    parser.add_argument("--score-resolution", type=int, default=64)
    parser.add_argument("--damping-ratio", type=float, default=0.02)
    parser.add_argument("--output-json", default=None, help="Optional path to dump the full sweep result as JSON")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = load_config(args.config)
    target_path = Path(args.target)
    if not target_path.exists():
        raise SystemExit(f"Target file not found: {target_path}. Draw and save a target in the UI first.")
    target = np.load(target_path).astype(bool)

    cfg = MaterialSweepConfig(
        stiffness_ratio=float(args.stiffness_ratio),
        shear_ratio=float(args.shear_ratio),
        f_min_hz=float(args.f_min_hz),
        f_max_hz=float(args.f_max_hz),
        n_points=int(args.n_points),
        top_k=int(args.top_k),
        proxy_grid_size=int(args.proxy_grid_size),
        score_resolution=int(args.score_resolution),
        damping_ratio=float(args.damping_ratio),
    )

    def _progress(info: dict) -> None:
        if info["index"] == 1 or info["index"] % 10 == 0 or info["index"] == info["total"]:
            print(f"  sweep {info['index']:>3}/{info['total']} @ {info['frequency_hz']:.1f} Hz")

    print(f"[sweep] target={target_path} (shape {target.shape}), sr={cfg.stiffness_ratio}, "
          f"shear={cfg.shear_ratio}, range [{cfg.f_min_hz}, {cfg.f_max_hz}] Hz × {cfg.n_points} points")
    result = run_material_frequency_sweep(config, target, cfg, progress=_progress)

    print(f"[sweep] done in {result['duration_sec']:.1f} s")
    print(f"[sweep] top-{cfg.top_k} best frequencies: {result['best_freqs_str']} Hz")
    print()
    print(f"  {'#':>2} {'freq Hz':>10} {'enrich':>8} {'recall':>7} {'compos':>8} {'contrast':>8}")
    for i, row in enumerate(result["best_rows"], 1):
        print(f"  {i:>2} {row['frequency_hz']:>10.1f} {row['enrichment']:>8.2f}× "
              f"{row['recall']:>7.2f} {row['composite']:>8.3f} {row['contrast']:>8.2f}×")

    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[sweep] wrote {out}")


if __name__ == "__main__":
    main()
