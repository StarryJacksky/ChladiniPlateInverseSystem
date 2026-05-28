# Chladni Inverse Design — Full Trial-and-Error History

Date: 2026-05-27
Branch: `codex/chladni-inverse-design-scaffold`
Stats: ~**293 + W3–W8 follow-ons** ≈ 350+ real COMSOL candidates; surrogate-side iterations in the tens of thousands.

Related documents:
- [`algorithm_logic_and_structure_explanation.md`](./algorithm_logic_and_structure_explanation.md) — current code structure
- [`algorithm_trial_history_research_handoff.md`](./algorithm_trial_history_research_handoff.md) — pre-W1 English research handoff
- [`algorithm_breakthrough_plan.en.md`](./algorithm_breakthrough_plan.en.md) — W1–W8 engineering plan
- [`target_aligned_passive_geometry_strategy.md`](./target_aligned_passive_geometry_strategy.md) — TAGS line of work
- [`mosaic_z_feasibility_report.md`](./mosaic_z_feasibility_report.md) — MOSAIC-Z subspace method
- [`comsol_first_simulation_principle.md`](./comsol_first_simulation_principle.md) — the "COMSOL-first" principle

---

## 0. Abstract (one-page TL;DR)

This document summarises every algorithmic attempt from the earliest random trials through the latest W8 in **chronological order** and a **uniform format**, so that any future handoff (human or AI) can:

1. Understand "what has been tried, and how well it worked" in 5 minutes.
2. Avoid re-running directions that have already been proven not to work.
3. See the **structural lessons** that span multiple stages (these are physics/maths-level findings, not transient code bugs).
4. Identify "which directions are still under-explored".

**One-sentence core conclusion**:
> Under the hardware-fixed constraints of **15×15 grid + 150 mm square plate + 8 mm centre clamp + single-centre actuator**, the **physical reachability of any non-D4-symmetric complex pattern (such as the IC letters) is capped at enrichment ≈ 2.0x**; **D4-symmetry-friendly patterns (X, diagonal, +, ring) reach enrichment 2.5–3.0x** and are visually recognisable. There is no obvious algorithmic headroom left; the next step is either to change the hardware (break D4 symmetry of the actuation / boundary) or accept this as a hard physical ceiling.

---

## 1. Hard Constraints

The following items are **immutable** throughout the entire trial cycle; every algorithm must work within them.

| Item | Value | Source |
|---|---|---|
| Design grid | `15 × 15` | COMSOL `H.csv` / `density_scale.csv` / `loss_factor.csv` contract |
| Plate size | `150 mm × 150 mm` | One-piece print boundary |
| Centre clamp | Circular region of radius `8 mm` | Standard experimental rig |
| Boundary | Free on all four edges | Free plate vibration |
| Actuation | Single centre point + frequency sweep | No multi-actuator / external mass / tunable supports |
| Primary feedback | COMSOL eigenfrequency / frequency-domain | LiveLink with MATLAB |
| Thickness range | `0.6–2.0 mm`, neighbour diff ≤ `1.0 mm`, centre fixed at `2.0 mm` | Manufacturing feasibility |

---

## 2. Three-era split

| Era | Approx. codes | Time | Core paradigm | Dominant techniques |
|---|---|---|---|---|
| **Era I: blind walk** | Phase A–I | up to `candidate_181_xxxx` | "guess thickness → run COMSOL → revise" | evolutionary algorithms, KL proxy, auxiliary physics, CMA-latent |
| **Era II: structured** | W1–W6 | before 2026-05-26 | "prior filtering + main-loss swap + gradient chain" | reachability verdict, differentiable plate, PCA manifold, homotopy, modal clustering |
| **Era III: recognisability** | W7–W8 | 2026-05-26 to 27 | "redefine the success criterion" | multi-frequency RMS, enrichment-driven optimisation |

---

## 3. Era I: the blind walk (Phase A–I)

> The user's earliest goal: have COMSOL produce a Chladni nodal pattern that looks like the IC letters. The whole era assumed that "just a few more generations and we'll get there".

### Phase A — Random / evolutionary / target-guided thickness search

**Motivation**: the most naive inverse design — treat the 15×15 thickness field as a 225-dim optimisation variable and use GA/mutation/crossover hill-climbing.

**Method**:
- Random initialisation H ∈ [0.6, 2.0] mm
- Selection, crossover, mutation
- Add "neighbour-diff ≤ 1 mm" repair + centre-fixed 2.0 mm clamp constraint
- Add "target-skeleton-guided" heuristic (thin along the target skeleton direction)

**Key files**: `src/candidate/generate_candidate.py`, `src/candidate/constraints.py`

**Outcome**: valid COMSOL modes were produced, but the shapes were all **generic plate-mode families** — broad arcs, stars, rings, centre-dominated patterns. No letter-like feeling at all.

**Lesson**:
> 225-dim search restricted to thickness alone is pulled by the **plate's natural symmetry (D4) + centre clamp** into a small set of low-dim mode families. The local minima the optimiser climbs to are symbolically far from any letter. **This is the earliest warning sign of every later "surrogate looks great but COMSOL is wrong" episode.**

---

### Phase B — Response-Guided Closed Loop

**Motivation**: since random search lacks direction, use real COMSOL failure maps to guide the next step.

**Method**:
- Compute `missing = target − simulated` (target pixels not hit)
- Compute `extra = simulated − target` (wrong hits)
- Convert `extra` into an "avoidance map"
- During candidate generation, thin the missing region and thicken the extra region

**Outcome**: useful procedurally — avoided repeating the same wrong patterns. But still no IC letters.

**Lesson**:
> An error map can tell you "where you are wrong", but **cannot tell you "which eigenmode's nodal line should be moved where"**. An eigenmode is a global object; locally thinning by 0.1 mm produces a subtle global rotation of the whole mode family, not a local nodal-line motion.

---

### Phase C — Kirchhoff–Love Plate Proxy (KL proxy)

**Motivation**: a COMSOL run takes ~30 s; a 225-dim search takes hours per generation. A fast physical proxy is needed.

**Method**: discretised KL biharmonic plate:
```
K(p) u = λ M(p) u,  K ≈ Lᵀ D L,  D = E h³/(12(1−ν²)),  M ≈ ρh
```
Remove centre-clamp DOFs and solve sparsely on a 25×25 grid.

**Variants**:
- KL continuous target-guided search
- KL direct optimisation
- High-res sparse KL
- KL-calibrated Bayesian candidate ranking

**Key files**: early `src/proxy/kl_plate.py` (later evolved into W3's `src/physics/differentiable_plate.py`)

**Outcome**: KL-internal "looks-like" patterns were found, but **KL high scores did not transfer reliably to COMSOL**. Most candidates collapsed into rings / stars / centre structures after COMSOL validation.

**Lesson**:
> **First explicit appearance of the "surrogate vs COMSOL gap"**. KL assumes thin plates, but the project's plate is 1.5–2.5 mm thick over a 150 mm side ≈ 1/100, which is already at the Mindlin (thick-plate) boundary. **This gap never disappears all the way through W8; it just gets better understood**.

---

### Phase D — Strict Scoring Upgrade

**Motivation**: early IoU/recall let "big star patterns" inflate their score (they accidentally cover part of the letter skeleton). The numbers had to match the human eye.

**Method**: upgrade from `precision_topology_v1` all the way to `strict_precision_topology_v5`:
- Add a precision floor
- Add layout / projection / topology / complexity / connected-component / centerline-overreach sub-metrics
- Raise the minimum mode index from 1 to 8 (force higher-order modes)
- Add roughness / mass / frequency penalties

**Key files**: `src/scoring/score_candidate.py`, `src/scoring/strict_precision_topology.py`

**Outcome**: numbers finally aligned with the eye — the historical best dropped from an inflated ~0.2 to an honest 0.034.

**Lesson**:
> **An honest metric matters more than a flattering metric**. But this upgrade also put the hard truth on the table: the engineering threshold `final_score = 0.08` was not reachable under the current contract. W2 / W8 continued to refine the metric on top of this.

---

### Phase E — COMSOL Design Contract Expansion

**Motivation**: pure thickness search lacks expressive power.

**Method**: expand the COMSOL input contract from just `H.csv` to:
- `density_scale.csv` — 15×15 per-cell density scaling
- `loss_factor.csv` — 15×15 per-cell damping loss
- `material_parameters.csv` — global material parameters

The design vector grew from 225 to 675 dimensions.

**Outcome**: **the first stable improvement**. The historical best `candidate_174_0002` (score=0.0339) came from this family.

**Lesson**:
> "Stiffness field" + "mass field" + "damping field" separated control is stronger than thickness alone. But even at 675 dim, **the eigenmode nodal lines still cannot be made to land on the letter positions** — this proves the bottleneck is not dimensionality but the intrinsic structure of D4 symmetry + single-centre actuation.

---

### Phase F — Auxiliary Physics local search

**Motivation**: hand-design a dozen "physics-intuitive" heuristics and test each.

**Strategies tried** (kept as a dictionary so future contributors do not reinvent them):
```
aux_mass_target_heavy        — heavier target region
aux_mass_target_light        — lighter target region
aux_loss_outer_suppress      — add damping to the outer ring
aux_inertia_edge_heavy       — heavier edges
aux_inertia_ring_break       — break ring symmetry
aux_low_loss_target_channel  — low damping in target channel
aux_heavy_loss_balanced      — balanced damping
aux_target_edge_bridge       — bridge target edges
aux_recall_outer_trim        — trim outer ring to raise recall
aux_precision_channel_guard  — guard target channel for precision
```

**Key files**: `src/candidate/auxiliary_physics.py`

**Outcome**: **the most robust source in history**. The top-6 candidates of generations 174–181 all came from here. But final_score stayed in 0.032–0.034 — never broke through.

**Lesson**:
> Hand-crafted heuristics fill optimiser blind spots but **cannot change the mode family**. They are effective for local polishing near an anchor that is already "close to best", but they do not discover new global optima.

---

### Phase G — Latent Joint Physics Search

**Motivation**: replace hand-crafted heuristics with a low-dim latent basis.

**Method**: define a set of basis maps (target, target edge, radial, inverse radial, current thickness field, x/y coordinates, diagonals, corner symmetry breakers, etc.); linearly combine with coefficients to produce density / loss source fields.

**Key files**: `src/candidate/latent_physics.py`

**Outcome**: a random latent search found `candidate_177_0001` (score=0.0337) — close to but not beating the auxiliary best.

**Lesson**:
> Latent basis is a good tool, but **its value depends on whether the basis covers the right directions**. Our basis was hand-designed and may have missed critical directions. W4's PCA manifold later is the correct version of this idea — let the data tell us which directions matter.

---

### Phase H — CMA-Style Latent Coefficient Optimisation

**Motivation**: random latent is passive scattering; CMA is active directed sampling.

**Method**: in the latent-coefficient space, run CMA-ES around high-score anchors with updated mean / sigma. Add acquisition score, optimism penalty, novelty and other `latent_*` metadata.

**Key files**: `src/candidate/cma_latent.py`

**Outcome**:
- generation 178: best CMA latent ≈ 0.030, beaten by auxiliary best 0.0324
- generation 179: CMA latent mostly worse than auxiliary
- generation 180–181: latent slots reduced by the adaptive scheduler

**Lesson**:
> **CMA works technically, but exposed "surrogate optimism"**: the learned proxy predicts a latent candidate will be good, but COMSOL disagrees after validation. **This is the early version of the physics–proxy gap that comes back in W7 / W8.**

---

### Phase I — Response-Calibrated Latent Scheduling

**Motivation**: if CMA over-estimates, add an acquisition penalty + an adaptive scheduler.

**Method**:
```python
trusted_prediction = predicted - optimism_penalty * max(0, predicted - anchor_real_score)
```
Plus a response correction (based on the real COMSOL error map) and adaptive family scheduling (give more slots to families that perform well, like auxiliary).

**Key files**: `src/candidate/response_calibrated_latent.py`

**Outcome**:
- Before the scheduler: 14 candidates, 6 latent + 8 auxiliary
- After the scheduler: generation 181 has 3 latent + 11 auxiliary

**Lesson**:
> **The first system-level recognition that "surrogate is unreliable"** — not by disabling the surrogate, but by letting reality calibrate its predictions. **This thread was still not fully realised by W7 / W8 (I was still doing "push surrogate to the limit → one-shot COMSOL validation" without iterative calibration)**. This is the largest piece of unfinished work.

---

### Era I endpoint: historical-best table

| Rank | Candidate ID | Family | final_score | precision | recall | mode | freq (Hz) |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | `candidate_174_0002` | auxiliary | **0.033914** | 0.107656 | 0.214882 | 18 | 486.21 |
| 2 | `candidate_177_0001` | latent | 0.033721 | 0.105616 | 0.199533 | 18 | 462.20 |
| 3 | `candidate_173_0011` | search frontier | 0.033228 | 0.105272 | 0.204538 | 18 | 520.03 |
| 4 | `candidate_176_0011` | aux/frontier | 0.033169 | 0.105612 | 0.207207 | 18 | 504.99 |
| 5 | `candidate_179_0011` | auxiliary | 0.033129 | 0.105380 | 0.206540 | 18 | 502.59 |
| 6 | `candidate_181_0003` | auxiliary | 0.032797 | 0.104149 | 0.200200 | 18 | 522.12 |

Engineering threshold `final_score ≥ 0.08`; **none made it**. **This was the honest state at the end of Era I.**

---

## 4. Era II: the structured era (W1–W6)

> Origin: the diagnostic conclusion of Era I was "this cannot be solved by running more generations". A redesign was needed at the physics / maths level. Planning document: [`algorithm_breakthrough_plan.en.md`](./algorithm_breakthrough_plan.en.md).

### W1 — Target Realizability Filter

**Motivation**: before running any COMSOL, use classical theorems to decide "is the user's target physically reachable?".

**Method**: based on Courant's nodal-domain theorem, Pleijel asymptotics, square-plate D4 symmetry, and minimum stroke width — output 5 numbers plus one verdict:
```text
verdict ∈ {easy, borderline, requires_topology, infeasible_as_nodal_set}
```

**Key files**: `src/target/target_realizability.py`, `scripts/analyze_target_realizability.py`

**Key finding (the IC target)**:
- `n_connected_components`: 2 (I and C)
- `n_closed_loops`: 0
- `courant_min_mode_index`: ~12
- `stroke_min_gap_mm`: 12 (near the grid resolution limit)
- `d4_symmetry_mismatch`: **0.78 (high, I-C as a whole is non-D4)**
- **verdict: `borderline`**

**Lesson**:
> **The numbers W1 produced actually told us the entire later story** — for the IC letters d4_mismatch=0.78, meaning that all D4-symmetric plate mode families "cannot fit" IC. But during W7 / W8 **I ignored this number**, and only realised it after W8 comparisons on X-shape / diagonal targets. **The largest methodological mistake of the project**: the W1 tool was built but not used up-front.

---

### W2 — Swap main loss from IoU to Amplitude Valley / Unified Ranker

**Motivation**: single-mode IoU is a discrete indicator function — non-differentiable and not smooth under small parameter changes. A continuous differentiable main objective is needed.

**Method**:
- Promote `amplitude_valley_loss = E[|u(x)|² · w(x)]` to the main objective (w(x) emphasises target-skeleton pixels)
- Write `src/scoring/unified_ranker.py`: use amplitude_valley when the reachability is the amplitude route, use IoU on the nodal route
- Re-rank all historical candidates with the new metric

**Key files**: `src/scoring/amplitude_valley_loss.py`, `src/scoring/unified_ranker.py`, `scripts/rank_candidates.py`

**Outcome**: smoother scoring, friendlier to optimisation. But the physical ceiling did not move.

**Lesson**:
> **Swapping the main loss makes the optimiser run more smoothly but cannot break the physical ceiling**. This echoes Phase D's strict-scoring upgrade — metric improvement is engineering necessity, not algorithmic breakthrough.

---

### W3 — Differentiable Plate Model + Adjoint Sensitivity

**Motivation**: to do gradient optimisation in 225+ dimensions, an analytical `∂loss/∂H` gradient is required.

**Method**: implement a Kirchhoff–Love biharmonic plate in PyTorch, get the gradient via autograd. Calibrate against COMSOL once (frequency coefficients) so that the surrogate output is as close as possible to COMSOL.

**Key files**: `src/physics/differentiable_plate.py`, `src/optimisation/gradient_optimizer.py`, `scripts/run_w3_optimization.py`, `scripts/check_w3_smoke.py`

**Core equation**:
```
(K(H) − ω² M(H)) u = F
loss = E[|u(x)|² · w(x)]
∇H loss obtained analytically via PyTorch autograd
```

**Outcome**:
- smoke test: loss dropped from ~2.7 to ~0.3 within 50 steps
- IC target: clear improvement on the surrogate side, but COMSOL side mostly matches the Phase F `candidate_174_0002` level

**Lesson**:
> **The gradient chain is finally wired up** — none of the previous five phases achieved this. This is the project's first **structural capability upgrade**. But the gap between the simplified Kirchhoff model and the Mindlin COMSOL model **still persists** — calibration aligns a single frequency, but the global loss-landscape shape along the optimisation path is still different.

---

### W4 — Manifold PCA Search

**Motivation**: W3's 225-dim optimisation, even with gradients, easily falls into low-resolution local optima. Historical data shows the effective dimensionality is only 30–80.

**Method**: run PCA on historical candidate H values; extract the top 79 principal components (covering 95% variance); all searches operate in 79-dim PCA coefficient space.

**Key files**: `src/subspace/manifold_pca.py`, `scripts/build_design_manifold.py`, `scripts/run_w4_manifold.py`

**Outcome** (ring+midbar sanity target):
| Candidate | Search space | first loss | best loss | time |
|---|---|---:|---:|---|
| `w3_gradient_ringbar_sanity` | 225-dim sigmoid(theta) | 2.745 | 1.377 | ~8 s |
| `w4_manifold_ringbar_sanity` | 79-dim PCA coefficients | 1.806 | **0.233** | ~10 s |

W4 has 6× lower loss than W3, **proving the 79-dim manifold covers the general structural directions** (not IC-specific).

**Lesson**:
> **Data-driven basis (PCA) dominates hand-crafted basis (latent_basis)** — this is the correct version of Phase G. But on the IC target, **the manifold reduces dimensionality without changing the D4 symmetry constraint**, so no significant COMSOL breakthrough.

---

### W5 — Homotopy Continuation

**Motivation**: direct optimisation on a complex target lands in saddle points. Start from a simple natural plate pattern and gradually push toward the target, warm-starting at each step.

**Method**: parameter `λ ∈ [0, 1]`, `target(λ) = (1−λ)·natural + λ·user_target`. Run tens of gradient steps for each λ, hand off H to the next λ.

**Key files**: `src/optimisation/homotopy.py`, `scripts/run_w5_homotopy.py`

**Outcome**: simple homotopy paths converge; **but for the IC target the optimiser gets stuck around λ ≈ 0.3** — consistent with the W1 verdict=borderline.

**Lesson**:
> **Homotopy continuation avoids saddle points but cannot break physical unreachability**. λ_max ≈ 0.3 is an **honest reachability indicator** — it can tell the customer "your target is only physically achievable up to 30% similarity".

---

### W6 — Spectral Placement (modal-frequency clustering)

**Motivation**: a reverse-implementation of the MOSAIC-Z spirit — not "linear-combine multiple modes" but rather "use gradients to push several eigenvalues to cluster near the driving frequency ω", so that the forced response naturally lands in a target-friendly subspace.

**Method**: add a loss term `Σ_k (λ_k(H) − ω²)²` to encourage clustering. `λ_k` provides analytical sensitivity via the W3 differentiable plate.

**Key files**: `src/optimisation/spectral_placement.py`, `scripts/run_w6_spectral.py`

**Outcome**:
- IC target `w6_pipeline_ic_full_v1` @ 820 Hz: COMSOL final_score = **0.171** (5× higher than Phase F's 0.034!)
- Top-ranked under the W2 unified ranker

**Lesson**:
> **W6 is the climax of Era II** — pushing IC's final_score from 0.034 to 0.171. **But visually it still does not look like IC** — only the numbers look good. This is exactly the trigger for W7 to re-examine the success criterion.

---

### Era II endpoint: full W1–W6 pipeline wired through

Wrote `scripts/run_full_pipeline.py` to chain it end to end:
```
target → W1 verdict → {W3, W4, W6} parallel optimisation → COMSOL freq-sweep validation → W2 unified ranker
```

Ran for IC, ringbar, diagonal targets — all pass.

**IC final_score history at this point**:
| Stage | Best | Improvement |
|---|---:|---|
| End of Phase A–I (candidate_174_0002) | 0.0339 | baseline |
| W3 alone | ~0.05 | 1.5x |
| W4 alone | ~0.08 | 2.4x |
| W6 (`w6_pipeline_ic_full_v1`) | **0.1709** | **5.0x** |

---

## 5. Era III: the recognisability era (W7–W8)

> Origin: W6 pushed final_score to 0.17 but visually still did not look like IC. The user redefined the success criterion — **"a similar (not exactly congruent) target is acceptable; pattern in uncovered regions is allowed"**. This clarification triggered a rewrite of the entire scoring system and optimisation objective.

### W7 — Multi-frequency time-division drive

**Motivation**: there is a physical ceiling on single-freq + single-plate; perhaps "stitching" multiple frequencies can break it.

**Method**: jointly optimise H + K freq-logits + K weight-logits; synthesise amplitude as `u_rms = sqrt(Σ_k w_k |u_k|²)`; loss is the same amplitude-valley as W6.

**Key files**:
- `src/physics/multifreq_amp_valley.py`
- `src/optimisation/multifreq_placement.py`
- `scripts/run_w7_multifreq.py`, `scripts/check_w7_smoke.py`

**Outcome**:
| Candidate | Surrogate IoU | COMSOL IoU | COMSOL final |
|---|---:|---:|---:|
| `w7_multifreq_ic_v1` (single-freq collapse) | 16.96% | 2.51% | 0.082 |
| `w7_multifreq_ic_v2_diverse` (6 freqs forced) | 13.4% | 1.8% | 0.136 |
| W6 v1 baseline | – | 1.0% | 0.171 |

**W7's surrogate numbers were strong but COMSOL was actually worse than W6.**

**Lessons**:
> 1. **Multi-frequency RMS numerical synthesis is a false breakthrough** — the surrogate optimiser learns to "weight |u|²" to manufacture low-amplitude regions, freedom that COMSOL does not have.
> 2. **The optimiser tends to collapse to a single frequency** — unless diversity is forced, K frequencies all collapse their weight to 1.
> 3. After forced diversity the total loss actually rises — proving "multi-frequency" is not numerically superior to "single-frequency".
> 4. **Real multi-frequency strategies have to be done as physical time-division** (excite at one frequency, sprinkle powder, switch to the next), not numerical RMS.

---

### W8 — Recognisability-driven optimisation

**Trigger**: user clarified the success criterion + W7 finding "final_score 0.17 but doesn't look like IC" → the entire scoring system needed a rewrite.

#### New metric design

Drop the pixel-weighted IoU / Dice / Chamfer thinking; use real Chladni powder physics: **powder settles on nodal lines** (|u| ≈ 0 and large gradient), not on diffuse low-amplitude regions.

Model: `p(x) = exp(-(|u(x)| / (σ·peak))²)`; with σ=0.05 the powder covers only the true 2–3-pixel-wide nodal lines.

New metrics (`src/scoring/recognisability_score.py`):
1. **Enrichment factor** — powder density per unit area in target / global average (> 2.0 is visually recognisable)
2. **Coverage recall** — fraction of target pixels falling in the bottom-20% amplitude region
3. **Gaussian contrast** — Gaussian-powder target mean / background mean
4. **Directional alignment** — cosine similarity between powder-density-weighted principal axis and target principal axis
5. **Composite** — `0.40·log1p(enr-1) + 0.30·recall + 0.20·log1p(ct-1) + 0.10·direction`

#### Re-rank all historical candidates (step A, ~1 hour, no COMSOL)

Run `scripts/rank_candidates_recognisable.py`. **Biggest find**:
- IC top-1: **`tags_ic_case_a_target_thick_refine_240_270 @ 240 Hz`**, enrichment=2.01x, recall=64%
- The old final_score top-1 W6 v1 only ranks 10th under the new metric
- **The project had been "using the wrong metric for months", and the real best candidate had been buried**.

#### W8 joint optimisation (step B)

Reuse W7 multi-frequency architecture + manifold; loss becomes:
```
combined = enrichment_loss + contrast_loss + 0.5·recall_loss
```

**Key files**:
- `src/physics/recognisability_loss.py` (differentiable enrichment)
- `src/optimisation/recognisability_placement.py`
- `scripts/run_w8_recognisability.py`, `scripts/check_w8_smoke.py`

Smoke test: within 15 Adam steps surrogate enrichment rises from 0 → 2.0+.

#### W8 COMSOL validation on four targets

| Target | W8 candidate | Surrogate enr | COMSOL RMS enr | COMSOL best single-freq | Visual judgement |
|---|---|---:|---:|---:|---|
| Diagonal | `w8_diagonal_v1` | 12.73x | **0.94x (degraded)** | 1.66x @ 228 Hz | X-shape produced, direction off-axis |
| **X-shape** | **`w8_xform_v1`** | 8.43x | 2.93x | **2.84x @ 440 Hz** | **Clear X-shaped diagonal nodal lines — new global best** |
| + cross | `w8_cross_v1` | 15.24x | 1.37x | 1.63x @ 935 Hz | Complex mesh |
| IC letters | `w8_ic_v1` | 9.18x | 1.71x | 1.72x @ 220 Hz | Same league as historical IC top1; no breakthrough |

#### Key lessons (the fundamental problems W8 surfaced)

1. **Target-physics symmetry mismatch → the optimiser finds the closest reachable solution**
   - The "diagonal" target is non-D4 → the optimal solution learnt is the **X shape** (symmetry mirrors it)
   - The W1 verdict already told us "diagonal d4_mismatch is high" — but it was **ignored before running W8**

2. **The physics-proxy gap is even worse under the new metric**
   - On the surrogate, enrichment can be pushed to 8–15x (Kirchhoff can fabricate "low amplitude" anywhere)
   - On COMSOL it usually sits at 1.5–3x (Mindlin thick plate + real modal constraints)
   - **Multi-frequency RMS actually degrades on COMSOL** (nodal-line positions of the two frequencies disagree → RMS flattens the "low amplitude")

3. **Directional metric degenerates on symmetric patterns under PCA**
   - The diagonal target has a clear principal axis (45°), but powder density on D4 modes is isotropic → PCA principal axis becomes random
   - X-shape target has degenerate principal axes (two equal-length directions); direction=0.81 is PCA noise rather than signal

4. **The "global best" is X-shape, not IC**
   - X-shape enrichment = 2.84x (W8 finding), **new project historical best non-trivial result**
   - IC best is still 2.01x (the historical re-rank find from step A)
   - **W8 really works on D4-friendly patterns; W8 fails on D4-incompatible patterns**

---

### Era III endpoint: best enrichment per target

| Target | Best candidate | Frequency | Enrichment | Visual evaluation |
|---|---|---:|---:|---|
| Diagonal | `diagonal_dense_sweep` (history sweep) | 220 Hz | **2.41x** | Thick nodal band along the diagonal — recognisable |
| **X-shape** | **`w8_xform_v1`** (new) | 440 Hz | **2.84x** | **Clear X shape — new global best** |
| IC letters | `tags_ic_case_a_target_thick_refine_240_270` (re-rank find) | 240 Hz | 2.01x | Square symmetric mesh, IC roughly visible between nodal bands |
| + cross | `w8_cross_v1` (new) | 935 Hz | 1.63x | Mesh-like nodal pattern; cross arms partially visible |

---

## 6. Cross-stage meta-lessons (the most important section)

This section is the **core** for future contributors / AIs — these are not technical details, they are the structural insights gleaned from all three eras.

### Meta-lesson 1: D4 symmetry is a hard constraint, not a soft one

**Square plate + centre clamp + centre actuation → every response of the system is D4-symmetric**.

- The patterns you can produce = subset of D4-symmetric patterns
- Any non-D4 pattern (IC letters, a single diagonal, an L) is **physically unreachable**
- The optimiser sees an unreachable target → finds the closest reachable pattern (usually X, +, ring, frame, or some combination)

**This fact threads through all 9 stages** (Phase A → W8), but **we only fully internalised it after W8**.

### Meta-lesson 2: the surrogate-COMSOL gap is permanent — what matters is how you use it

KL/Kirchhoff proxies (W3, W7, W8) and COMSOL Mindlin differ permanently in several ways:
- Plate theory (thin vs thick, with shear)
- Mesh density (625 vs 10⁴)
- Boundary geometry (abstract vs circular clamp)
- Numerical precision

**Two wrong usages** (the project committed both):
- ❌ surrogate as judge (W7/W8 pushed the surrogate to the limit and then asked COMSOL)
- ❌ surrogate as truth (early Phase C)

**Correct usage** (**not yet fully realised — biggest piece of unfinished work**):
- ✅ surrogate as compass (calibrate against COMSOL every 30 steps and force surrogate-COMSOL trust region)
- ✅ homotopy + calibration loop: push the surrogate a bit → COMSOL pulls back → push again

### Meta-lesson 3: metric choice determines project direction

The project has used five main metrics:
1. **IoU/Dice/Chamfer** (Phase A–D) → discrete, non-differentiable, sensitive to mode switching
2. **`strict_precision_topology_v5` final_score** (post Phase D) → smoothed but still pixel-weighted
3. **`amplitude_valley_loss`** (W2/W3/W4/W6) → continuous differentiable, but not fully aligned with real powder physics
4. **multi-freq RMS amplitude valley** (W7) → easily gamed by the optimiser
5. **Recognisability (enrichment + recall + contrast + direction)** (W8) → closest to "does it look like" to a human eye

**Every metric swap reshuffles the "best candidate"** — e.g. W6 v1 is rank 1 under final_score but rank 10 under enrichment.

**Advice for future contributors**: **clarify what "success" means before optimising**. About 80% of the project's compute was wasted on optimising the wrong metric.

### Meta-lesson 4: dimensionality is not the bottleneck — structure is

Dimensionality evolution: 225 (thickness) → 675 (thickness + density + damping) → 79 (PCA) → 79 + K + K (W8 multi-freq joint).

**Conclusion**: **dimension reduction (W4) is more effective than dimension expansion (Phase E)** — because the low-dim manifold covers the truly effective directions. But even at the optimal dimensionality, **the structural constraint (D4 symmetry, centre clamp) is the real bottleneck**.

### Meta-lesson 5: hand basis < data basis < theory basis

- Phase G hand-crafted latent basis ≈ 0.0337
- W4 data PCA basis → 0.171 (paired with W6)
- **Theory basis (mode-family decomposition by symmetry type) has not been tried** — this is a worthwhile direction.

### Meta-lesson 6: CMA / Bayesian / evolutionary algorithms are inefficient on this problem

Phase A, F, G, H all used these methods — **all stalled at final_score ≈ 0.033**. Reasons:
- All gradient-free hill climbing
- Evaluation is expensive (~15–30 s per COMSOL run)
- The landscape is full of mode-switch discontinuities

**Correct approach: gradient methods (post W3)** — once `∂loss/∂H` analytical differentiation is available, efficiency improves 100x+.

### Meta-lesson 7: the W1 tool was built but not used up-front

This is the largest methodological mistake of the project. `scripts/analyze_target_realizability.py` can tell you "is this target reachable", but:
- During W7 we did not check W1 → wasted hours on physically unreachable IC multi-freq runs
- During W8 diagonal we did not check W1 → wasted hours on a non-D4 target
- Only after W8 (explaining to the user "why diagonal produces X") did we go back to W1

**All future tasks must pass W1 first.**

---

## 7. Failure-mode index (for quick diagnosis)

| Symptom | Reason | Fix direction |
|---|---|---|
| Candidates are always stars / rings / centre-dominated | D4 + centre clamp low-order modes | Pick high modes (mode ≥ 8) or force symmetry breaking |
| Surrogate high but COMSOL low | Physics model mismatch | Add a COMSOL calibration loop (**not done**) |
| IoU goes up but visuals get worse | Discrete metric is mode-switch sensitive | Swap to amplitude_valley or enrichment |
| Multi-freq joint collapses to single freq | Loss landscape favours single-freq extrema | Force a freq-separation penalty + sparsity penalty |
| Multi-freq RMS worse than single freq | Nodal positions disagree → RMS flattens | Use single freq or physical time-division (one freq at a time) |
| Complex patterns never appear | Non-D4 target | W1 verdict says infeasible — must simplify the target |
| Optimising H does not converge | Neighbour-diff constraint shrinks sigmoid gradient | Use manifold-coefficient space (W4) |
| Direction metric is unstable on symmetric patterns | PCA principal axis degenerates | Use a symmetry-aware direction metric (**not done**) |

---

## 8. Best-result longitudinal comparison

### IC letters (primary target)

| Era | Best candidate | Main metric value | Visual evaluation |
|---|---|---:|---|
| Phase A–I | `candidate_174_0002` | final_score=0.034 | Star-shape — not IC |
| W3 alone | `w3_pipeline_ic_full` | final_score≈0.05 | Slight improvement |
| W4 alone | `w4_pipeline_ic_full` | final_score≈0.08 | Stronger mode symmetry |
| W6 | `w6_pipeline_ic_full_v1` @ 820 Hz | **final_score=0.171** | Best numerically — but still does not look like IC |
| W7 multifreq | `w7_multifreq_ic_v2_diverse` | final_score=0.136 | Below W6 |
| **W8 re-rank** | **`tags_ic_case_a_target_thick_refine_240_270` @ 240 Hz** | **enrichment=2.01x** | **Square-symmetric net, IC roughly visible** |

### Diagonal target (introduced in the W8 era)

| Candidate | Freq | Enrichment | Direction | Visual |
|---|---:|---:|---:|---|
| `pipeline_diagonal_v1_w4` @ 200 Hz | 200 | 2.43x | 1.00 | Strong diagonal nodal band |
| `pipeline_diagonal_v1_w6` @ 474 Hz | 474 | 2.14x | 1.00 | Along the diagonal |
| **`diagonal_dense_sweep` @ 220 Hz** | 220 | **2.41x** | 0.98 | **Best — but actually an X shape** |
| `w8_diagonal_v1` @ 228 Hz | 228 | 1.66x | 0.04 | W8's own optimisation is worse |

### X-shape target (introduced in the W8 era)

| Candidate | Freq | Enrichment | Visual |
|---|---:|---:|---|
| **`w8_xform_v1`** @ 440 Hz | 440 | **2.84x** | **Clear X shape — global historical best** |

---

## 9. Abandoned but worth remembering

These attempts were tried, did not work well or were superseded, but are recorded so future contributors do not reinvent them:

| Attempt | Era | Why not used |
|---|---|---|
| Pure GA / CMA hill climbing in 225 dim | Phase A, H | Gradient-free + expensive eval → slow convergence |
| KL proxy as standalone ranker | Phase C | Gap too large; COMSOL validation unreliable |
| Hand-crafted latent basis | Phase G | Replaced by W4 PCA |
| Single-mode IoU as main objective | Phase A–E | Non-differentiable, sensitive to mode switching |
| Multi-freq RMS synthesis | W7 | Physically degrades |
| PCA-based direction as main metric | W8 | Degenerates on symmetric patterns |
| `Surrogate-only push → one-shot COMSOL validation` | W3–W8 | Should be iterative calibration instead |
| IC / single diagonal as targets | Throughout | D4-incompatible — physically unreachable |

---

## 10. Currently unfinished work (by priority)

### High priority

1. **Surrogate–COMSOL trust-region calibration loop**
   - Currently the surrogate runs 280 steps → one COMSOL validation
   - Should be: surrogate 30 steps → COMSOL calibration → force the surrogate output to align with COMSOL → another 30 steps
   - This is the realisation of meta-lesson 2; **the project carried this forward from W3 to W8 without doing it**

2. **W1 verdict mandatory at the top of every pipeline**
   - Add a verdict check at the top of `scripts/run_full_pipeline.py`
   - When verdict=infeasible, stop and suggest "simplify the target" to the customer
   - This is the realisation of meta-lesson 7

3. **Symmetry-aware direction metric**
   - The current directional_alignment uses a PCA principal axis
   - Should pick a direction-similarity measure based on the target's symmetry class (C∞, D4, D2, etc.)
   - Fixes the "top/bottom images look flipped" issue surfaced by W8

### Medium priority

4. **Theory basis (by mode symmetry type)**
   - Decompose H into a basis of D4 irreducible representations (A1, A2, B1, B2, E)
   - Optimise with explicit separation of "symmetry-type alignment" vs "magnitude"

5. **Real physical time-division multi-frequency**
   - Not RMS — "excite at freq 1, powder for 30 s, then switch to freq 2 for 30 s"
   - Experimental — needs MATLAB / hardware support

6. **Discrete topology variables (holes / slots / ribs)**
   - Proposed since Phase F but not implemented
   - Could break D4 symmetry (via asymmetric hole positions)

### Low priority (exploratory)

7. **Multi-actuator coordination**
   - Breaks D4 symmetry and enables active phase control
   - Requires hardware modification

8. **Irregular boundary shapes**
   - Replace square plate with octagonal / hexagonal
   - Changes the mode family

---

## 11. Onboarding checklist

When the next human / AI picks up the project, read in this order:

1. **This document** — 5-minute history overview
2. [`algorithm_breakthrough_plan.en.md`](./algorithm_breakthrough_plan.en.md) §10–11 — detailed W7/W8 planning
3. [`algorithm_logic_and_structure_explanation.md`](./algorithm_logic_and_structure_explanation.md) — current code structure
4. Run `scripts/check_w3_smoke.py` / `check_w7_smoke.py` / `check_w8_smoke.py` — confirm the environment
5. Read the latest leaderboard: `reports/recognisability_leaderboard_*.{json,csv}`
6. See the latest comparison plot: `reports/pipeline/final_best_per_target.png`

**Forbidden re-runs** (already validated as failures):
- Gradient-free optimisation in 225 dim
- Single-mode IoU as main objective
- Treating surrogate high-score as the final verdict
- Setting non-D4-symmetric targets (IC, single diagonal, L, etc.) on square plate + centre actuation, unless explicitly telling the customer "this is unreachable"

**High-priority tasks**:
- §10 items 1, 2, 3 above

---

## 12. One-sentence summary

> The project went all the way from "guess thickness at random" to "differentiable multi-frequency joint recognisability optimisation" — 9 stages, 350+ COMSOL candidates — and the hard truth at the end is: **the algorithm has already pushed the 15×15 + D4-symmetric square plate + centre-actuation reachability to the limit (X-shape enrichment 2.84x, IC letters enrichment 2.01x). The remaining headroom is not in the algorithm but in the hardware.**
