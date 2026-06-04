# Future Improvement Directions (Handoff to Successors)

> An **errata and re-prioritization** of `paper/improvement_directions_en.tex` ("Five Algorithm Improvement Directions").
> Written after the project was closed, based on a round of decision experiments (2026-06), so that whoever picks this up does not re-invest in the wrong directions.
> Language: [中文](./future_directions_for_successors.zh-CN.md) ｜ [English](./future_directions_for_successors.en.md)

---

## 0. Why this document exists

The original "Five Directions" report centered its improvements on the **optimizer/scoring** side (scoring rebuild, geometry loss, frequency inner-loop, random restarts, center-artifact fix). A round of decision experiments before closeout showed that **none of the five directions address the project's real bottleneck** — namely, "the pattern COMSOL shows does not reproduce on the real plate." This document gives the validated diagnosis and re-orders the directions that actually matter.

## 1. One-sentence conclusion

> **The real bottleneck was never the optimization algorithm. It is that the entire pipeline validated itself *inside simulation* (surrogate → COMSOL, treating COMSOL as ground truth while never calibrating it against a real plate), and the optimizer was driven to physically non-reproducible off-resonance operating points.**
> Therefore "COMSOL has a figure, reality doesn't" is not a bug — it is the inevitable result of this methodology. The headline `4.85× enrichment` is a **simulation-internal number**, never anchored to reality.

## 2. Confidence grading (read this first)

Every claim below is tagged by source. **Do not treat estimates as conclusions.**

| Tag | Meaning | Confidence |
|---|---|---|
| [COMSOL-truth] | From COMSOL eigenfrequency / forced-response exports | High |
| [code-verified] | Confirmed by reading the source | High |
| [surrogate-est] | Computed with the 25×25 coarse surrogate; **needs COMSOL/physical check** | Medium |
| [needs-experiment] | Requires a real-plate experiment to confirm | Unverified |

Reproduction scripts: see §6.

## 3. Core diagnosis

### 3.1 "Jupiter" (the central blob/ring) is a permanent center-clamp artifact — not what you should worry about
[code-verified] The central 8 mm is clamped (`orthotropic_plate.py` `clamp_indices`/`expand_to_grid` zero the center DOFs), and the powder model `p = exp(-(|u|/ε)²)` (`amplitude_valley_score.py`, ε=0.08) reads "low amplitude" as "sand collects." So the center is mislabeled as the quietest spot. **As long as a relative-displacement field is plotted, Jupiter is there — on- or off-resonance** — which is why even recent, on-resonance deliverable .mph files show it.
- The original report's diagnosis of this mechanism is **correct**.
- But the real plate's center is **occupied by the clamp/bolt** and never forms a sand figure anyway, so Jupiter is a **visualization artifact** with no effect on the usable outer pattern. Production config `remove_center_region: true` already excludes the center in scoring — correct (cosmetic).
- ⚠️ The report's "proper fix" — switching to absolute displacement `u_abs = u_rel + a_base/ω²`, claiming "phantom sand auto-disappears" — is [surrogate-est] **empirically ineffective**: on the real production_design forward solve, center powder fraction actually rose from 31% to 46% and the outer pattern shifted by 14%. Reason: this design's dynamic amplification is only ~4, so the base term is not negligible. **Do not spend time on this "fix."**

### 3.2 Real root cause #1: systemic off-resonance driving
[COMSOL-truth] Scanning 32 "design ↔ COMSOL-eigenfrequency" pairs: **23 designs drive <50% of their energy off-resonance** (criterion: distance to nearest COMSOL eigenfrequency ≤ half-power bandwidth ζf, ζ=0.02, to count as on-resonance); many at 0–20%.
- Base `production_design` is only **4% on-resonance**: the dominant 165.4 Hz (weight 0.604, the report's "lucky frequency") is 2.87 bandwidths off the nearest mode; 1099 Hz (weight 0.289) is 25 bandwidths off; ~**36% of drive energy lands in the 800–1000 Hz "modal desert" with no eigenmodes at all**.
- Physical consequence: off-resonance → weak, multi-mode forced response → the genuine modal figure is faint (so the center artifact looks relatively prominent), and on the real plate (modes shifted by material/print differences) the same off-resonance frequencies give yet another weak/different response → **reality cannot reproduce COMSOL's relative-displacement figure**.
- Note: the refined iteration `production_design_p2it5` reaches **96% on-resonance** (sr=1.87), so late Phase-2 did converge toward resonance — but the highest-weight operating points still miss.

### 3.3 Why does the optimizer chase off-resonance? — It hits the physical ceiling
[code-verified][needs-experiment] Single center-point excitation + square D4 symmetry → only **symmetric (A1-family) modes are well-excited and reproducible**. Asymmetric targets like IC simply cannot be expressed by on-resonance symmetric modes. The optimizer scores "the relative-displacement figure looks like the target," so it is **structurally pushed** toward off-resonance operating points that "happen to look like IC" — points that are physically non-reproducible. **In other words, the pipeline "achieves IC" precisely by relying on non-reproducible off-resonance frequencies.** This is the root of the COMSOL↔reality gap. The report's "physical ceiling" section is directionally right but **badly underweights how central it is**.

### 3.4 Model self-consistency flaw: surrogate and COMSOL use different excitation
[code-verified] The surrogate uses **whole-plate base/inertial excitation** (`direct_forced_response`: `force = -M·base_accel`), while the COMSOL runner uses **Gaussian point actuators with position/amplitude/phase** (`run_chladni_forced_response.m`: `build_gaussian_force_expression` + `try_apply_shell_force`). These are not the same physical problem — the optimizer selects plates under physics A but validates under physics B. Production designs do use a single center actuator (matching the real rig), but this surrogate↔COMSOL inconsistency remains a hazard.

### 3.5 Material mismatch is a one-off, not systemic
[COMSOL-truth] Only **1 of 32 pairs** has inconsistent material: the stale base `production_design` (optimizer sr=1.0 isotropic vs COMSOL sr=1.67). All battery designs and production_design p2it1–p2it5 are consistent. **In the prior round I wrongly flagged this as a "second systemic root cause"; corrected here — it is just a stale file.**

## 4. The real improvement directions (priority order; the original report's sequence was wrong)

### Direction 0 (foundation, most important) — Close the "COMSOL → real plate" validation loop
**No step in the entire project** ever validated that COMSOL predicts the real plate. The first task for a successor: print a plate, **measure its real eigenfrequencies and mode shapes** (impact hammer / laser vibrometer, or swept-frequency sand-pattern photos), and fit COMSOL's material/boundary parameters to match. Until then, COMSOL is an **unvalidated judge** and every downstream number (including 4.85×) is unanchored. **Without this, every other improvement is a castle in the air.**

### Direction 1 — Make "physical reproducibility" a hard constraint
Evidence in §3.2. Successors should **drive only well-isolated eigenfrequencies** (spacing ≫ bandwidth, robust to calibration error) and **explicitly penalize off-resonance / dense-mode operating points** in the objective. Suggest a "reproducibility score = dynamic amplification × modal isolation"; reject designs below threshold no matter how well they match the target figure.
- [surrogate-est] For production_design, recommended isolated + on-resonance candidates (≤600 Hz, gap ≥ 4 bandwidths): **58 / 132 / 264 / 371 Hz**; avoid the 800–1000 Hz modal desert. Re-check exact values against COMSOL eigenfrequencies.

### Direction 2 — Face the physical ceiling honestly: change the targets, or change the physics
Evidence in §3.3. Choose one:
- (a) Restrict the target library to **physically reachable, symmetric / mode-expressible** patterns; or
- (b) **Change the physics** — multi-actuator phased array / distributed or edge excitation / asymmetric boundaries — to genuinely break the D4 symmetry constraint. The abandoned `mosaic_z` six-point phased-actuator line was actually a correct prototype of (b), **provided the real rig can do multi-point phased driving**.

### Direction 3 — Fix model self-consistency (not Jupiter)
Evidence in §3.4. First **unify the excitation model across surrogate / COMSOL / real rig** and verify the surrogate actually predicts COMSOL. For Jupiter, just **exclude the bolted center region** (already done); ignore the report's "absolute-displacement fix" (§3.1, tested ineffective).

### Direction 4 — Scoring rebuild (i.e. the report's Directions 1–4) comes LAST, not first
The report's proposals ("enrichment ≠ looks-like; use F_β / geometry loss / frequency inner-loop / random restarts") are **not wrong**, but the **sequence is wrong**: refining the score on an uncalibrated, off-resonance foundation merely optimizes a fiction more precisely. Refine scoring only after Directions 0–3 land and the judge is trustworthy.

## 5. Meta-lesson

**The project's biggest methodological flaw: it closed the loop entirely in simulation, treated COMSOL as ground truth, and never let "ground truth" face reality.**
The one line to leave successors: **build the experimental validation loop first, treat physical reproducibility as a hard constraint, and honestly accept that a center-point-excited square plate cannot form arbitrary asymmetric patterns.**

## 6. Reproduction

- Python env: `python` is not on PATH on this machine; the project uses the conda env **`comsol_env`** (`D:\python\anaconda\envs\comsol_env\python.exe`, has torch 2.12). Run from repo root: `$env:PYTHONPATH="."; & <python> scripts\<name>.py`. Always pass `encoding="utf-8"` when reading UTF-8 files (Windows defaults to GBK and errors).
- Decision-experiment scripts (read-only, `scripts/_decexp_*.py`):
  - `_decexp_center_artifact.py` / `_decexp_center_probe2.py` — quantify the Jupiter artifact (surrogate vs COMSOL fields).
  - `_decexp_standing_wave_purity.py` — standing-wave purity of COMSOL real/imag fields (=1.000, clean standing waves).
  - `_decexp_dir5_effectiveness.py` — effectiveness of Direction-5 "proper fix" (ineffective, 31%→46%).
  - `_decexp_amplification_sweep.py` — dynamic amplification vs frequency (design clusters on low-amplification freqs).
  - `_decexp_comsol_resonance_check.py` — drive freqs vs COMSOL eigenfrequencies (4% on-res + material mismatch).
  - `_decexp_step1_material_and_resonance.py` — material consistency over 32 pairs + on-resonance census + recommended freqs.
- Output figures and JSON in `reports/_decision_experiments/`.
- Key data: `reports/modal_calibration/*_comsol_eigfreqs.json` (COMSOL eigenfrequencies); each design's `frequencies_hz.csv`/`weights.csv`/`w10_optimization_summary.json`; `reports/.../comsol_forced_{real,imag}_grid.npy` (COMSOL complex fields).

> ⚠️ Note: the recommended frequencies in §4 Direction 1, the "fix is ineffective" in §3.1, and the amplification figures are **surrogate estimates**. Before the Direction-0 physical calibration is done, re-check them against COMSOL and then validate on a real plate.
