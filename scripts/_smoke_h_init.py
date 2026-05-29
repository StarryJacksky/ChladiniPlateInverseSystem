"""H init smoke test: compare W10 with different default_mm values to determine
whether the upper-bound init is what's trapping the optimiser on this target.

For each default_mm ∈ {0.8, 1.3, 2.0} we run a 60-step W10 with all other
parameters held identical, then report final / best metrics + H-field stats.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.optimisation.recognisability_placement_w10 import (
    W10AnisotropyConfig,
    run_w10_anisotropy_placement,
)
from src.physics.plate_loss_adapter import load_target_binary


def _h_stats(H: np.ndarray, h_min: float, h_max: float) -> dict:
    return {
        "mean_mm": float(H.mean()),
        "std_mm": float(H.std()),
        "min_mm": float(H.min()),
        "max_mm": float(H.max()),
        "frac_saturated_high": float((H >= h_max - 1.0e-3).mean()),
        "frac_saturated_low": float((H <= h_min + 1.0e-3).mean()),
    }


def main() -> None:
    config = load_config("config.yaml")
    target = load_target_binary(config)
    print(f"target: {int(target.sum())}/{target.size} pixels ({100*target.mean():.2f}% area)")
    print()

    h_min = float(config["thickness"]["min_mm"])
    h_max = float(config["thickness"]["max_mm"])
    print(f"plate bounds: [{h_min}, {h_max}] mm")
    print()

    results = []
    out_root = PROJECT_ROOT / "reports" / "_h_init_smoke"
    out_root.mkdir(parents=True, exist_ok=True)

    # Now testing the new h_init_mm field. default_mm stays at config (2.0 mm
    # for center clamp). h_init_mm is varied to verify the fix works.
    test_cases = [
        ("h_init=None → mid (1.3)", None),
        ("h_init=0.8", 0.8),
        ("h_init=1.3", 1.3),
        ("h_init=2.0 (BAD)", 2.0),
    ]
    for label, h_init in test_cases:
        print(f"\n========== {label} ==========")
        cfg = dict(config)
        cfg["thickness"] = dict(config["thickness"])
        # default_mm UNCHANGED — that's the center clamp value

        opt = W10AnisotropyConfig(
            num_steps=60,
            plateau_patience=200,  # disable plateau for clean comparison
            theta_seed=42,
            h_init_mm=h_init,
        )

        label_safe = label.replace(" ", "_").replace("(", "").replace(")", "").replace("→", "to")
        out_dir = out_root / label_safe
        t0 = time.time()
        info = run_w10_anisotropy_placement(cfg, target, opt, out_dir)
        elapsed = time.time() - t0

        H = info.get("final_H_mm")
        if H is None:
            H_path = out_dir / "H.csv"
            if H_path.exists():
                H = np.loadtxt(H_path, delimiter=",")
        H = np.asarray(H, dtype=np.float64) if H is not None else np.zeros((15, 15))

        best_metrics = info.get("best_surrogate_metrics", {}) or {}
        weight_dist = info.get("weight_distribution", {}) or {}

        record = {
            "label": label,
            "h_init_mm_arg": h_init,
            "best_step": info.get("best_step"),
            "best_loss": info.get("best_loss"),
            "best_enrichment": best_metrics.get("enrichment"),
            "best_recall": best_metrics.get("recall"),
            "best_contrast": best_metrics.get("contrast"),
            "effective_freq_count": weight_dist.get("effective_count"),
            "h_stats": _h_stats(H, h_min, h_max),
            "wallclock_s": elapsed,
        }
        results.append(record)

        print(f"  best_step       = {record['best_step']}")
        print(f"  best_loss       = {record['best_loss']}")
        print(f"  best_enrichment = {record['best_enrichment']}")
        print(f"  H mean/std      = {record['h_stats']['mean_mm']:.3f} / "
              f"{record['h_stats']['std_mm']:.3f} mm")
        print(f"  H sat high/low  = {100*record['h_stats']['frac_saturated_high']:.1f}% / "
              f"{100*record['h_stats']['frac_saturated_low']:.1f}%")
        print(f"  eff freq count  = {record['effective_freq_count']}")
        print(f"  wallclock       = {elapsed:.1f} s")

    summary_path = out_root / "smoke_summary.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n\nWrote summary → {summary_path}")

    print("\n========== Comparison table ==========")
    print(f"{'label':<30}{'best_enr':<12}{'H mean':<10}{'H std':<10}{'sat_high':<10}{'eff_K':<10}")
    print("-" * 90)
    for r in results:
        h = r["h_stats"]
        print(f"{r['label']:<30}{r['best_enrichment'] or float('nan'):<12.4f}"
              f"{h['mean_mm']:<10.3f}{h['std_mm']:<10.3f}"
              f"{100*h['frac_saturated_high']:<9.1f}%{r['effective_freq_count'] or float('nan'):<10.2f}")


if __name__ == "__main__":
    main()
