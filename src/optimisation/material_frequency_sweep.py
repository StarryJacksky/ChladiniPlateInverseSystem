"""Material magic-frequency pre-sweep (surrogate-only, ~10-30 s).

Given the customer's current material parameters (stiffness_ratio, shear_ratio
and the implicit density / Young's modulus / Poisson values from config.yaml),
perform a fast surrogate forced-response sweep on a bare uniform-thickness
plate (no W10 optimisation yet) and rank frequencies by IC-likeness against
the current saved target. The top-K frequencies become candidate
``magic_off_resonance_hz`` values for the production pipeline.

Use case:
- Customer calibrates the system to a real measured material (e.g. PLA
  sr=1.6) in the Tune → Material panel.
- Customer clicks "Pre-sweep magic freqs" before launching the full pipeline.
- The endpoint returns the top-K (default 3) best driving frequencies in
  ~20 s, written back into the Magic off-resonance Hz field of the Run panel.

Runtime: ~50 freq points × ~0.3 s/point on a 25×25 proxy grid ≈ 15 s on CPU.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
import torch

from src.physics.orthotropic_plate import OrthotropicPlate
from src.scoring.recognisability_score import (
    coverage_recall,
    recognisability_score_grid,
)


@dataclass
class MaterialSweepConfig:
    """Configuration for a material-aware magic-frequency pre-sweep."""

    stiffness_ratio: float = 3.0       # E_||/E_⊥; overrides config.material.stiffness_ratio
    shear_ratio: float = 1.0           # G/G_iso; overrides config.material.shear_ratio
    f_min_hz: float = 80.0             # Sweep lower bound
    f_max_hz: float = 1500.0           # Sweep upper bound
    n_points: int = 50                 # Number of frequencies in the sweep
    proxy_grid_size: int = 25          # Surrogate plate resolution (odd; clamped inside OrthotropicPlate)
    damping_ratio: float = 0.02        # Modal damping ratio
    top_k: int = 3                     # Number of best frequencies to surface
    sigma_rel: float = 0.05            # Powder Gaussian width
    percentile: float = 20.0           # Recall percentile
    score_resolution: int = 64         # Target/amplitude resolution for scoring (small for speed)


def _resize_binary_target(target_binary: np.ndarray, size: int) -> np.ndarray:
    """Nearest-neighbour resize of a boolean target to (size, size)."""
    if target_binary.shape == (size, size):
        return target_binary.astype(bool)
    from PIL import Image  # Lazy import (Pillow is already a project dep)
    img = Image.fromarray(target_binary.astype(np.uint8) * 255).resize((size, size), Image.NEAREST)
    return (np.array(img) > 127).astype(bool)


def _resize_amplitude(amp: np.ndarray, size: int) -> np.ndarray:
    """Nearest-neighbour resize of an amplitude grid to (size, size)."""
    if amp.shape == (size, size):
        return amp
    src_h, src_w = amp.shape
    yi = np.clip(np.round(np.linspace(0, src_h - 1, size)).astype(int), 0, src_h - 1)
    xi = np.clip(np.round(np.linspace(0, src_w - 1, size)).astype(int), 0, src_w - 1)
    return amp[np.ix_(yi, xi)]


def run_material_frequency_sweep(
    config: dict,
    target_binary: np.ndarray,
    sweep_config: MaterialSweepConfig,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Run a surrogate forced-response sweep and rank frequencies by IC-likeness.

    Parameters
    ----------
    config:
        The full ``config.yaml`` dict (must contain ``project``, ``thickness``,
        ``material`` sections).
    target_binary:
        Boolean target array of any shape (downsampled to ``score_resolution``
        internally).
    sweep_config:
        See ``MaterialSweepConfig``.
    progress:
        Optional callback ``({"index": i, "total": n, "frequency_hz": f}) → None``.

    Returns
    -------
    dict with keys: ``stiffness_ratio``, ``shear_ratio``, ``f_min_hz``,
    ``f_max_hz``, ``n_points``, ``top_k``, ``best_freqs`` (list[float]),
    ``best_freqs_str`` (comma-separated), ``best_rows`` (list[dict]),
    ``rows`` (full sweep table), ``duration_sec``.
    """
    t0 = time.time()

    plate = OrthotropicPlate(
        config,
        proxy_grid_size=int(sweep_config.proxy_grid_size),
        base_accel=1.0,
        default_damping=float(sweep_config.damping_ratio),
        reference_frequency_hz=0.5 * (float(sweep_config.f_min_hz) + float(sweep_config.f_max_hz)),
        stiffness_ratio=float(sweep_config.stiffness_ratio),
        shear_ratio=float(sweep_config.shear_ratio),
        dtype=torch.float64,
        device="cpu",
    )

    grid_size = int(config["project"]["grid_size"])
    thickness_cfg = config["thickness"]
    h_max = float(thickness_cfg["max_mm"])
    default_h = float(thickness_cfg.get("default_mm", h_max))

    # Bare uniform-thickness plate, θ = 0 (no W10 optimisation yet).
    H_design = torch.full((grid_size, grid_size), float(default_h), dtype=torch.float64)
    theta_design = torch.zeros((grid_size, grid_size), dtype=torch.float64)

    target_resized = _resize_binary_target(target_binary, int(sweep_config.score_resolution))

    freqs = np.linspace(
        float(sweep_config.f_min_hz),
        float(sweep_config.f_max_hz),
        int(sweep_config.n_points),
    )
    rows: list[dict] = []
    for i, f in enumerate(freqs):
        with torch.no_grad():
            amp_proxy = plate.amplitude_at_frequency(
                H_design,
                theta_design,
                torch.tensor(float(f), dtype=torch.float64),
                damping_ratio=float(sweep_config.damping_ratio),
            ).cpu().numpy()
        amp_image = _resize_amplitude(amp_proxy, int(sweep_config.score_resolution))
        try:
            scores = recognisability_score_grid(
                amp_image,
                target_resized,
                sigma_rel=float(sweep_config.sigma_rel),
                percentile=float(sweep_config.percentile),
            )
            rec = float(coverage_recall(
                amp_image,
                target_resized,
                percentile=float(sweep_config.percentile),
            ))
            rows.append({
                "frequency_hz": float(f),
                "enrichment": float(scores["enrichment_factor"]),
                "recall": rec,
                "composite": float(scores["composite_recognisability"]),
                "contrast": float(scores["gaussian_contrast"]),
            })
        except Exception:
            rows.append({
                "frequency_hz": float(f),
                "enrichment": float("nan"),
                "recall": float("nan"),
                "composite": float("nan"),
                "contrast": float("nan"),
            })
        if progress is not None and (i % 5 == 0 or i == len(freqs) - 1):
            try:
                progress({"index": i + 1, "total": int(sweep_config.n_points), "frequency_hz": float(f)})
            except Exception:
                pass

    valid = [r for r in rows if not np.isnan(r["enrichment"]) and not np.isnan(r["composite"])]
    valid.sort(key=lambda r: -float(r["composite"]))
    best_rows = _diversify_freqs(valid, top_k=int(sweep_config.top_k), min_gap_hz=30.0)
    best_freqs = [float(r["frequency_hz"]) for r in best_rows]

    return {
        "stiffness_ratio": float(sweep_config.stiffness_ratio),
        "shear_ratio": float(sweep_config.shear_ratio),
        "f_min_hz": float(sweep_config.f_min_hz),
        "f_max_hz": float(sweep_config.f_max_hz),
        "n_points": int(sweep_config.n_points),
        "top_k": int(sweep_config.top_k),
        "best_freqs": best_freqs,
        "best_freqs_str": ",".join(f"{f:.1f}" for f in best_freqs),
        "best_rows": best_rows,
        "rows": rows,
        "duration_sec": float(time.time() - t0),
    }


def _diversify_freqs(sorted_rows: list[dict], top_k: int, min_gap_hz: float) -> list[dict]:
    """Greedy picker: take the best composite, then iterate, skipping rows
    within ``min_gap_hz`` of any already-picked frequency.

    Avoids returning three adjacent points around a single peak.
    """
    if top_k <= 0 or not sorted_rows:
        return []
    picked: list[dict] = []
    for row in sorted_rows:
        f = float(row["frequency_hz"])
        if all(abs(f - float(p["frequency_hz"])) >= float(min_gap_hz) for p in picked):
            picked.append(row)
            if len(picked) >= top_k:
                break
    if len(picked) < top_k:
        # If diversity left us short, top up with the remaining best entries.
        for row in sorted_rows:
            if row in picked:
                continue
            picked.append(row)
            if len(picked) >= top_k:
                break
    return picked
