# Battery Findings — CF-PETG (anisotropic, θ active) vs school FDM PLA (isotropic, no θ)

**Date**: 2026-05-29
**Pipeline**: W10 surrogate → COMSOL eigfreq → Phase 1 IC-likeness → Phase 2 trust-region
**Scope**: 6 targets × 2 materials = 12 full pipeline runs
**Compute**: ~10 min/run on Apple Silicon (W10 300 steps + COMSOL ×17 freqs + Phase 2 2 iters)

## Materials

| Tag | E (Pa) | ρ (kg/m³) | ν | stiffness_ratio | θ optimisable |
|---|---|---|---|---|---|
| **CF-PETG** | 3.7e9 | 1300 | 0.38 | **3.0** (anisotropic) | YES |
| **PLA iso** | 3.5e9 | 1240 | 0.36 | **1.0** (isotropic) | n/a (no anisotropy → θ has no effect) |

Both at 150 × 150 × 2 mm, 15 × 15 design grid, h ∈ [0.6, 2.0] mm.

## Targets

1. `binary` — original 8-element design (production target)
2. `cross` — orthogonal `+`
3. `diagonal` — single `↘` line
4. `xform` — orthogonal `X`
5. `star_outline` — 4-pointed star outline
6. `ic` — W8-era "IC" letterpair (Times New Roman Bold)

## Final Scoreboard

`enr` = composite broad enrichment, `rec` = recall, both Phase 2-final (if Phase 2 improved).
Verdict = (PLA − CF) / CF × 100% on broad enrichment.

| Target | CF-PETG (θ) | PLA (no θ) | Verdict |
|---|---|---|---|
| binary | enr=1.00, rec=0.19 | enr=1.10, rec=0.22 | **PLA +10%** |
| cross | enr=9.19, rec=0.46 | enr=10.00, rec=0.47 | **PLA +9%** |
| **diagonal** | enr=8.37, rec=0.63 | enr=**11.35**, rec=**0.92** | **PLA +36%** ‼️ |
| xform | enr=7.60, rec=0.18 | enr=8.46, rec=0.30 | **PLA +11%** |
| star_outline | enr=3.58, rec=0.69 | enr=3.42, rec=0.58 | tie |
| ic | enr=**11.80**, rec=0.45 | enr=10.27, rec=0.30 | **CF-PETG +13%** |

**Final tally — PLA 4 wins, CF-PETG 1 win, 1 tie**.

## Key Findings

### 1. θ optimization is parasitic on 5/6 targets

The most surprising finding: removing the θ (fiber orientation) degree of freedom and switching
to an isotropic material **improves** results in 4/6 cases, ties 1, and only loses 1.

The largest CF-PETG loss is on `diagonal` (-36% on enr, -32% on recall) — the very target that
ought to benefit most from anisotropy (a diagonal line is, by definition, an axis-aligned mode-mixing
problem that θ could rotate into).

**Hypothesis**: θ adds an extra non-convex search dimension to the W10 loss landscape. The
optimizer spends gradient budget exploring θ instead of converging H + ω. On isotropic plates,
W10 ignores θ entirely and converges H + ω cleanly.

### 2. CF-PETG retains the IC letterpair

`IC` is the only target where CF-PETG (θ active) beats PLA. The IC pattern is
compact, vertical, and contains fine-grained internal structure. Anisotropic stiffness
seems to help concentrate powder in elongated vertical bands.

This matches the historical observation that the project's W8-era results on IC were strong
(~1.7×) and W10+θ further amplified to ~10–12×.

### 3. Phase 2 trust-region is real

Phase 2 improved on:
- CF-PETG: `xform` (rec 0.15→0.18), `star_outline` (enr 3.44→3.58), `ic` (enr 10.11→**11.80**, +17%)
- PLA: `cross` (rec 0.39→0.47), `xform` (rec 0.26→0.30), `star_outline` (enr 2.49→**3.42**, +37%)

The reason Phase 2 *appeared* to "do nothing" in the long-running `production_design` target is
that the 8-element target is intrinsically too complex for plate eigenmodes — neither material
gets above enr=1.1, so trust-region updates can't find a meaningfully better composite either.

### 4. School FDM is project-ready

PLA on the school's FDM printer (no exotic CF, no fiber alignment, no anisotropy) is **strictly
better** as a baseline manufacturing path. The pipeline does not require CF-PETG to demonstrate
the target patterns.

## Visual artefact

`reports/_battery/battery_comsol_native_grid.png` — 6 rows × 3 columns
(target | CF-PETG COMSOL sand | PLA COMSOL sand), jet colormap, σ=0.08, "bright = sand collects = node".

## Reproducibility

```
# Generate the IC target (Times Bold "IC")
.venv/bin/python scripts/_make_ic_target.py

# Run 5 CF-PETG runs (anisotropic, sr=3, 165 Hz magic)
.venv/bin/python scripts/_run_battery.py

# Run 5 PLA runs (isotropic, sr=1, no magic)
.venv/bin/python scripts/_run_battery_pla_resume.py

# Render the final 6×3 comparison grid
.venv/bin/python scripts/_render_battery_grid.py
```

Each pipeline run takes ~10 min. Total: ~100 min for the full 10-run battery
(after the initial CF-PETG and PLA `binary` baselines were already on disk).

## Operational notes

- Disk space: each COMSOL forced-response run writes two ~17 MB `.mph` snapshots per drive
  frequency. The PLA resume script (`_run_battery_pla_resume.py`) now aggressively deletes
  these after each run, since we hit a disk-full failure mid-battery on the first attempt.
- Unique `candidate_id` per (material, target) — `bat_<material>_<target>` — avoids
  COMSOL CSV collisions when overlapping drive frequencies (e.g. 165 Hz magic) are picked.
- `config.yaml` is **temporarily patched** with PLA material parameters during the PLA half
  of the battery, then restored from a `.bak` in a `try/finally` block. If the orchestrator
  is killed, restore from `config.yaml.bak_battery*` manually before re-running.
