"""Material A/B smoke: how much does the (stiffness_ratio, shear_ratio) pair
affect W10's ability to fit the current target?

Holds everything else fixed (H init = mid-range, theta_seed=42, 80 steps).
Compares 4 cases:
  1. tier0_iso_PLA      sr=1.0 gr=1.0 E=3.5 GPa — school FDM PLA, isotropic
  2. tier0_iso_PETG     sr=1.0 gr=1.0 E=2.0 GPa — school FDM PETG
  3. tier1_cfpetg       sr=3.0 gr=1.0 E=3.7 GPa — current
  4. tier2_cf           sr=12.0 gr=1.0 E=3.7 GPa — surrogate ceiling
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


def main() -> None:
    config = load_config("config.yaml")
    target = load_target_binary(config)
    print(f"target: {int(target.sum())}/{target.size} pixels ({100*target.mean():.2f}% area)")
    print(f"plate: {config['project']['plate_length_mm']:.0f} mm × {config['project']['plate_length_mm']:.0f} mm × [{config['thickness']['min_mm']}–{config['thickness']['max_mm']}] mm")

    cases = [
        # label,                E_Pa,        sr,    gr,   rho
        ("tier0_iso_PLA",       3.5e9,       1.0,   1.0,  1240.0),
        ("tier0_iso_PETG",      2.0e9,       1.0,   1.0,  1270.0),
        ("tier1_cfpetg (current)", 3.7e9,    3.0,   1.0,  1300.0),
        ("tier2_continuous_cf", 3.7e9,       12.0,  1.0,  1300.0),
    ]

    out_root = PROJECT_ROOT / "reports" / "_material_smoke"
    out_root.mkdir(parents=True, exist_ok=True)
    results = []

    for label, E, sr, gr, rho in cases:
        print(f"\n========== {label}: E={E/1e9:.2f} GPa  sr={sr}  gr={gr}  ρ={rho} ==========")
        cfg = json.loads(json.dumps(config))  # deep copy via JSON roundtrip (safe for dicts)
        cfg["material"]["youngs_modulus_pa"] = float(E)
        cfg["material"]["density_kg_m3"] = float(rho)
        cfg["material"]["stiffness_ratio"] = float(sr)
        cfg["material"]["shear_ratio"] = float(gr)
        cfg["production"]["stiffness_ratio"] = float(sr)
        cfg["production"]["shear_ratio"] = float(gr)

        opt = W10AnisotropyConfig(
            num_steps=80,
            plateau_patience=200,
            theta_seed=42,
            # h_init_mm=None → mid-range (1.3 mm) — the fix
            stiffness_ratio=sr,
            shear_ratio=gr,
        )

        out_dir = out_root / label.replace(" ", "_").replace("(", "").replace(")", "")
        t0 = time.time()
        info = run_w10_anisotropy_placement(cfg, target, opt, out_dir)
        elapsed = time.time() - t0

        H = info.get("final_H_mm")
        if H is None:
            H_path = out_dir / "H.csv"
            if H_path.exists():
                H = np.loadtxt(H_path, delimiter=",")
        H = np.asarray(H, dtype=np.float64) if H is not None else np.zeros((15, 15))

        bm = info.get("best_surrogate_metrics", {}) or {}
        wd = info.get("weight_distribution", {}) or {}

        rec = {
            "label": label,
            "E_GPa": E / 1e9,
            "stiffness_ratio": sr,
            "shear_ratio": gr,
            "density_kg_m3": rho,
            "best_step": info.get("best_step"),
            "best_enrichment": bm.get("enrichment"),
            "best_recall": bm.get("recall"),
            "H_mean": float(H.mean()),
            "H_std": float(H.std()),
            "H_min": float(H.min()),
            "H_max": float(H.max()),
            "effective_freq_count": wd.get("effective_count"),
            "wallclock_s": elapsed,
        }
        results.append(rec)

        print(f"  best_step       = {rec['best_step']}")
        print(f"  best_enr        = {rec['best_enrichment']:.4f}")
        print(f"  best_recall     = {rec['best_recall']:.4f}")
        print(f"  H mean/std      = {rec['H_mean']:.3f} / {rec['H_std']:.3f} mm")
        print(f"  H range         = [{rec['H_min']:.3f}, {rec['H_max']:.3f}] mm")
        print(f"  eff freq count  = {rec['effective_freq_count']:.2f}")
        print(f"  wallclock       = {elapsed:.1f} s")

    print("\n========== Final comparison ==========")
    print(f"{'material':<28}{'E (GPa)':<10}{'sr':<6}{'best_enr':<12}{'best_rec':<12}{'H std':<10}{'eff_K':<8}")
    print("-" * 90)
    for r in results:
        print(f"{r['label']:<28}{r['E_GPa']:<10.2f}{r['stiffness_ratio']:<6.1f}"
              f"{r['best_enrichment']:<12.4f}{r['best_recall']:<12.4f}"
              f"{r['H_std']:<10.3f}{r['effective_freq_count']:<8.2f}")

    (out_root / "smoke_summary.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nWrote → {out_root}/smoke_summary.json")


if __name__ == "__main__":
    main()
