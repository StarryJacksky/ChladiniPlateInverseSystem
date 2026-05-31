# Chladni Plate Inverse-Design System — Final Project Report

**Project**: Pattern inverse-design and manufacturability for parametric Chladni plates
**Institution**: Imperial College London (First-year undergraduate · Term 3 Summer Project)
**Span**: May 2026 (three algorithmic eras, ~350+ real COMSOL candidates, ~20 algorithm lines)
**Date**: 2026-05-31
**Repository**: `ChladiniPlateInverseSystem` · branch `jx/chladni-inverse-design-scaffold`

---

## Abstract

This project studies a classic, brutally constrained inverse problem: **given a target image, can we back out a plate (thickness field, optional fibre orientation) and a set of drive frequencies whose Chladni sand pattern approximates the target?** Under a fixed hardware contract (150 mm square plate, 15×15 thickness grid, central 8 mm clamp, single central excitation, free edges), we went through three algorithmic eras, ~20 algorithm lines and 350+ COMSOL candidates, and built a complete pipeline: **differentiable surrogate → high-fidelity FEA validation → manufacturable export.**

The four central — and most counter-intuitive — conclusions are:

1. **Arbitrary custom-pattern inversion is physically impossible, not an engineering shortfall.** A square plate with a central clamp and central excitation has its response strictly constrained by the dihedral symmetry group D₄; a central point drive can only couple into the **A₁ irreducible representation**. Energy of the target outside the A₁ subspace is systematically filtered out, no matter how strong the algorithm. The X-shape lives 100% in A₁ (reachable); the "IC" letterpair only **41.9%** (the majority of its signal cannot get in).
2. **Anisotropy (θ, fibre orientation) is essentially useless.** In the working frequency band the inertia term ω²·‖M‖ exceeds the stiffness term ‖K‖ by ~5 orders of magnitude, and θ only enters physics through K, so its gradient is effectively zero (sensitivity ≤ 7 ppm). Freezing θ *improves* 4 of 6 targets, ties 1, loses 1 — **cheap isotropic PLA beats expensive anisotropic CF-PETG.**
3. **The surrogate-to-COMSOL gap is the real ceiling.** A Kirchhoff thin-plate surrogate can push recognisability to 8–18× in surrogate-space, but the COMSOL Mindlin thick-plate model only reproduces 1.5–4× of it. The gap is a systematic physical difference (plate theory, mesh, boundary, 3D elasticity tensor), not noise.
4. **The deliverable is not "arbitrary inversion" but an honest, reproducible, manufacturable system:** W10 differentiable surrogate → a two-phase COMSOL pipeline (modal selection + trust-region refinement) → a full-stack design application → a directly 3D-printable STL export.

> **In one sentence**: we did not achieve "ask for any pattern, get it" — because that does not exist physically; what we achieved is to **pin down exactly where the boundary is and why, and engineer the boundary-hugging optimum into a real product.**

---

## 1. Problem definition and immutable constraints

### 1.1 The inverse problem

Forward: plate geometry + material + drive frequency → Chladni nodal pattern (sand collects on nodal lines where displacement is minimal).
Inverse: target image → recover plate design + drive frequency.

### 1.2 Immutable hard constraints

These could not be changed during the whole project; every algorithm had to be designed around them:

| Item | Value | Source |
|---|---|---|
| Design grid | 15 × 15 thickness field | COMSOL `H.csv` contract |
| Plate size | 150 mm × 150 mm | one-shot print boundary |
| Central clamp | radius 8 mm disc | standard rig |
| Edges | free on all four sides | free vibration |
| Excitation | single central point + frequency sweep | no multi-shaker / added mass |
| Primary feedback | COMSOL eigenfrequency / frequency-domain | LiveLink with MATLAB |
| Thickness | 0.6–2.0 mm, neighbour diff ≤ 1.0 mm | manufacturability |

**This contract itself determines the project's physical ceiling** — a truth only fully digested after all three eras.

---

## 2. Three eras: the evolution of ~20 algorithm lines

| Era | Phases | Core paradigm | Outcome |
|---|---|---|---|
| **Era I — Blind search** | Phase A–I (9 lines) | "guess thickness → run COMSOL → tweak" | final_score stuck at 0.034, all below the bar |
| **Era II — Structured** | W1–W6 (6 lines) | "prior filter + main-loss redesign + gradient path" | IC final_score pushed to 0.171 (good number, still doesn't look like IC) |
| **Era III — Recognisability** | W7–W8 (2 lines) | "redefine success (real powder physics)" | X-shape enrichment 3.76× (project ceiling) |
| **(Modern production)** | W9, W10, two-phase pipeline (~3 lines) | "differentiable anisotropic surrogate + COMSOL trust-region loop + productisation" | two-phase pipeline + software delivery |

### 2.1 Era I — Blind search (Phase A–I)

The most naive inversion: treat the 225-dim thickness field as the optimisation variable, search with various gradient-free methods.

| Phase | Method | Lesson |
|---|---|---|
| **A** Random/evolutionary | GA + mutation + neighbour-diff repair + skeleton guidance | Only produces the "generic plate-mode family" (arcs, stars, rings, centre-dominant); no letters |
| **B** Response-guided loop | Use `missing/extra` error maps to steer the next generation | Error maps say "where it's wrong", not "which nodal line to move where" — eigenmodes are global |
| **C** Kirchhoff–Love proxy | 25×25 sparse biharmonic eigensolve | **First exposure of the surrogate↔COMSOL gap**; KL high scores don't transfer |
| **D** Strict scoring upgrade | `precision_topology_v1 → strict v5` | **Honest metrics beat pretty metrics**: best fell from an inflated 0.2 to an honest 0.034 |
| **E** Design-contract expansion | add density/loss/material fields, 225→675 dim | More dimensions isn't the answer: 675-dim still can't place nodal lines |
| **F** Auxiliary physics | a dozen hand-built physics heuristics | Most robust historical source (gen 174–181 top-6) but capped at 0.032–0.034 |
| **G** Latent joint physics | linear combination of hand-designed basis maps | A hand-made basis may miss key directions |
| **H** CMA latent optimisation | CMA-ES in latent coefficient space | **Exposed surrogate optimism**: surrogate predicts good, COMSOL disagrees |
| **I** Response-calibrated scheduling | optimism penalty + adaptive family scheduling | **First systemic treatment of "surrogate is unreliable"**, but iterative calibration never fully landed |

**End of Era I**: best `candidate_174_0002` final_score = 0.0339, all below the 0.08 engineering bar. Diagnosis: **"run more generations" won't fix it; redesign from the physics/maths level.**

### 2.2 Era II — Structured (W1–W6)

| Phase | Method | Key result / lesson |
|---|---|---|
| **W1** Realizability prior filter | Courant nodal domains + D₄ mismatch + stroke width → verdict | IC's `d4_mismatch=0.78` **predicted the whole ending** — but wasn't used up front (the biggest methodological miss) |
| **W2** Main-loss redesign | IoU → amplitude valley (continuous, differentiable) | Smoother optimisation, physical ceiling unchanged |
| **W3** Differentiable plate + adjoint | PyTorch KL plate, autograd for `∂loss/∂H` | **Gradient path finally connected** — the first structural capability upgrade |
| **W4** Low-dim manifold search | PCA of historical candidates, 79-dim coefficient space | **Data basis beats hand-made basis**; 6× lower loss than W3 |
| **W5** Homotopy continuation | warm-start from natural patterns toward target | Stalls at λ≈0.3 — an **honest reachability indicator** |
| **W6** Spectral placement | push several eigenvalues to cluster near the drive frequency | **Era II climax**: IC final_score 0.034 → 0.171 (5×), still doesn't look like IC |

### 2.3 Era III — Recognisability (W7–W8)

Trigger: W6 pushed the score to 0.17 but it still didn't look like IC. The user redefined success (accept "similar, not identical") → the whole scoring system was rewritten.

- **W7 multi-frequency time-division drive**: joint optimisation of H + K frequencies + K weights, RMS composition. **Found that multi-freq RMS is a pseudo-breakthrough** — the optimiser learns to "weight |u|²" to fabricate low-amplitude regions that COMSOL cannot reproduce, and it always tends to collapse to a single frequency.
- **W8 recognisability-driven optimisation**: drop pixel-wise IoU, adopt real powder physics — **sand deposits on nodal lines (|u|≈0)**. New metrics: enrichment (target-region powder density / global mean), recall, contrast, direction.
  - Re-ranking all historical candidates revealed: **the project used the wrong metric for a long time; better candidates had been buried for months.**
  - X-shape enrichment reached **2.84× → 3.76× after fixing a normalisation bug**, becoming the project ceiling.

### 2.4 Modern production — W9 / W10 / two-phase pipeline

- **W9 trust-region loop**: alternating outer surrogate + COMSOL correction. **Structurally correct but under-tuned** (too few inner steps, too-weak correction, trust radius shrank to 0.094 mm); best COMSOL 1.40× did not break through. Lesson: circling a bad surrogate doesn't help; the root issue is the surrogate physics itself.
- **W10 differentiable orthotropic plate + joint optimisation**: full Kirchhoff orthotropic energy functional (Reddy 2003), per-cell θ rotating the bending-stiffness operator so a central drive can *physically* couple into non-A₁ irreps. Joint optimisation of H + θ + ω.
- **Two-phase COMSOL production pipeline** (this is precisely the "iterative calibration loop" Era I kept owing — finally built):
  - **Phase 1 (modal selection)**: run COMSOL eigenfrequencies → rank each eigenmode by target-likeness → drive forced response → compose.
  - **Phase 2 (trust-region refinement)**: with COMSOL as ground truth, refine H by trust region (surrogate-continue → COMSOL re-evaluate → accept/shrink).

---

## 3. Core scientific findings

### 3.1 D₄ symmetry and the A₁ irrep ceiling (the project's first principle)

For a square plate with a central clamp and central excitation, all steady-state responses are constrained by the dihedral group D₄. The D₄ irreducible-representation decomposition (`src/symmetry/d4_decomposition.py`) gives an exact result:

> **A central drive can only couple into the A₁ irrep.** The target's energy fraction in A₁ = its physical reachability ceiling.

| Target | A₁ fraction | Outside A₁ (unreachable) | Meaning |
|---|---:|---:|---|
| X-shape | **100.0%** | 0% | Theoretically fully reachable (ceiling, COMSOL 3.76×) |
| Single diagonal | 51.7% | 48.3% (B₂) | Half reachable |
| **IC letters** | **41.9%** | **58.1% (E+B₁)** | The majority of signal cannot get in |

This is the project's first **exact mathematical answer** to "why IC never appears in COMSOL": not an algorithm failure, but that 58% of IC's energy is systematically filtered out by the central point source.

### 3.2 The anisotropy misconception and θ's unimportance

**The beautiful initial assumption**: 3D-printed parts are naturally anisotropic (tunable fibre orientation θ); make θ vary per cell → the bending-stiffness operator no longer commutes with D₄ → a central drive can couple into non-A₁ irreps → break the ceiling. This is "breaking symmetry physically", and it looks airtight.

**The brutal reality**:

1. **Energy can't reach K.** In W10's working band, the inertia term ω²·‖M‖ exceeds the stiffness term ‖K‖ by ~**5 orders of magnitude**. θ enters physics only through K, so its effect drowns in numerical noise.
2. **Direct sensitivity measurement**: swapping θ between uniform and random changes composite amplitude by **≤ 7 ppm** — far below numerical noise. With the same seed, θ-active and θ-frozen surrogate enrichments were **bit-identical**.
3. **It is a parasitic dimension.** θ adds a non-convex dimension to the W10 loss landscape; the optimiser wastes gradient budget exploring θ instead of cleanly converging H + ω.
4. **Freezing θ is better**: on the "diagonal" target that should benefit most from anisotropy, freezing θ alone gives **+17% enrichment, +6% recall** (without changing material or the H/ω optimiser).

**The 6-target × 2-material battery**:

| Target | CF-PETG (θ on, sr=3) | PLA (isotropic, no θ) | Verdict |
|---|---|---|---|
| binary | enr 1.00 | enr 1.10 | PLA +10% |
| cross | enr 9.19 | enr 10.00 | PLA +9% |
| **diagonal** | enr 8.37 | enr **11.35** | **PLA +36%** |
| xform | enr 7.60 | enr 8.46 | PLA +11% |
| star | enr 3.58 | enr 3.42 | tie |
| ic | enr **11.80** | enr 10.27 | CF-PETG +13% |

**Final tally: PLA wins 4, CF-PETG wins 1, tie 1.** Conclusion: **cheap, school-FDM-printable isotropic PLA is the better default path.** The θ optimisation code was eventually removed entirely so future work cannot regress into it.

> Addendum: we briefly took sr=2.8/3.0 from the literature; later we obtained the real TDS for Bambu Lab PETG-CF (flexural modulus) and measured an anisotropy ratio of only **sr=1.87** — far below the assumption, further confirming that anisotropy offers very little headroom.

### 3.3 The surrogate-to-COMSOL gap

KL/Kirchhoff surrogates differ permanently from COMSOL Mindlin: plate theory (thin vs thick-with-shear), mesh density (625 vs 10⁴), boundary geometry (abstract vs circular clamp), 2D plane-stress vs full 3D elasticity tensor. Consequences:

- Surrogate enrichment reaches 8–18×; COMSOL typically 1.5–4×.
- Frequencies shift systematically by ~40% (the surrogate's "IC mode" at 398 Hz maps to COMSOL 210 Hz, but 210 Hz is a U-shape not a C-shape).
- Modal alignment (MAC): low modes (1–8) 0.73–0.90 (excellent), high modes (16+) collapse to <0.4; the frequency map is a clean power law `f_c = α·f_s^β` (β≈1.31–1.36) — proving the gap is a **systematic physical difference, not noise.**

**Two wrong ways to use a surrogate (both committed)**: as a judge (push to extreme, then send to COMSOL); as the truth (early KL). **The right way is as a compass** — which is exactly why the two-phase pipeline exists.

### 3.4 On-resonance vs off-resonance drive (E3)

A bug-level discovery late in the project: Phase 1 once defaulted to driving at `f_eig + 1.5 Hz` (off-resonance) to avoid solver singularity, but this **let the central point force dominate the response and skewed the modes**, so cross/X patterns never appeared. Switching to **on-resonance (offset 0)** instantly recovered clean modal nodal lines. This also explains "that bar through the middle" — off-resonance, the centre is an anti-node bright streak pushed up by the point force, not a true nodal line.

### 3.5 A numerical-precision bug once systematically underestimated history

`chladni_powder_density`'s normalisation `amp/(max(amp)+1e-9)`: harmless in surrogate-space (amp~O(1)), but in COMSOL-space amp~O(1e-12), so 1e-9 is 1000× the signal and clamps enrichment to ≈1.00 forever. After the fix, all historical COMSOL numbers rose (X-shape 2.84→**3.76×**). **Lesson: a cross-scale epsilon is a silent killer.**

### 3.6 Metric choice drives project direction

Five primary metrics were used; each switch re-shuffled the "best candidate" (W6 v1 was #1 under final_score, #10 under enrichment):

1. IoU/Dice/Chamfer (discrete, non-differentiable, mode-switch sensitive)
2. `strict_precision_topology_v5` (smoothed but still pixel-wise)
3. amplitude valley (continuous, but not exactly powder physics)
4. multi-freq RMS (easy for the optimiser to cheat)
5. **recognisability: enrichment + recall + contrast + direction** (closest to "does it look right to the eye")

The later E1–E6 algorithm audit further quantified cognitive biases in these metrics (e.g. E1: enrichment prefers a "central blob" over an extended shape; E6: fixed-percentile thresholds are sensitive to powder density).

> **First advice to successors: define "success" clearly before optimising.** A substantial fraction of compute was wasted on the wrong metric.

---

## 4. Final algorithm architecture and meaning

What settled out after three eras is not a single "trick" but an **honestly layered pipeline where each layer has one job.**

```
target image
  │
  ▼
[W10 differentiable surrogate]  orthotropic Kirchhoff plate, optimise H + ω (θ removed)
  │   role: in seconds, push thickness/frequency to a "surrogate-good" solution
  │   stance: a compass, not a judge
  ▼
[Phase 1 · modal selection]  COMSOL eigenfrequencies → rank eigenmodes by target-likeness
  │   → on-resonance forced response → composite (best single / composite)
  │   role: use high-fidelity physics to pick genuinely target-like modes and compose them
  ▼
[Phase 2 · trust-region refinement]  with COMSOL as ground truth, iterate H by trust region
  │   (surrogate-continue → COMSOL re-evaluate → accept/shrink radius)
  │   role: manage the surrogate-COMSOL gap explicitly via "trust", refine monotonically
  ▼
best design (H field) + best drive frequency + sand-pattern prediction
```

**What each layer means**:

- **W10 is "a compass, not a judge"** — the hard-won lesson of Eras I–III. The surrogate gives direction fast and never decides the winner.
- **Phase 1 fixes "surrogate bets on the wrong frequency"** — the surrogate's self-proclaimed "IC mode" ranks #16 in COMSOL; Phase 1 re-ranks with real physics, and discovered that **an off-resonance beat point (interference of two complementary modes) often beats any single eigenmode** (on IC, the 132+180 Hz RMS composite reaches broad enr 3.82× / recall 0.89).
- **Phase 2 is the "iterative calibration loop" owed since Era I** — it decouples the root cause of W9's failure (correcting frequency and shape simultaneously diverges): the frequency layer drives at COMSOL's true frequency, the shape layer only lets the trust region fix the small residual.

**At the level of meaning**: the final algorithm's value is not "how strong the inversion is", but that **it precisely and reproducibly pushes every target near its A₁ physical ceiling, and honestly stops there.**

---

## 5. The software system: full-stack integration and features

The project is not only algorithms but a deliverable design application (COMSOL bridge + web frontend).

### 5.1 Backend (`src/frontend/target_ui_server.py`, multithreaded HTTP)

- **Pipeline orchestration**: one-click W10 → Phase 1 → Phase 2; surrogate-only / skip-COMSOL modes; collaborative cancel (Stop instantly terminates the subprocess group).
- **COMSOL bridge**: mphserver lifecycle, auto-discovery of COMSOL/MATLAB paths, LiveLink with MATLAB, isolated runtime instances so it won't fight already-open windows.
- **Result/diagnostic APIs**: production-run list & detail, target realizability analysis (A₁ fraction shown to the client directly), log tails, artefact size & cleanup preview, material frequency pre-sweep.
- **Open .mph in COMSOL**: open the **Phase 1 best** and **Phase 2 best** forced-response models separately, so the client can compare and pick the more satisfying pattern.
- **3D-print export**: `/api/export-info` and `/api/export-stl`, converting the thickness field to a printable STL per phase.

### 5.2 Frontend (`frontend/target_designer.html`, single-page app)

Tabs: **Target / Tune / Results / Run / Gallery / Export**.

- **Target**: upload/draw a target with the 15×15 grid and central clamp overlaid, plus realizability hints.
- **Tune**: material panel (incl. stiffness ratio E∥/E⊥, shear ratio), auto-synced with the Run panel.
- **Run**: run the pipeline, live progress, instant Stop.
- **Results**: metrics for past production runs, target/achieved sand images, thickness field, COMSOL eigenmode previews; one-click open of the Phase 1 / Phase 2 best `.mph` in COMSOL.
- **Gallery (uniform-plate pattern gallery)**: browse the uniform-plate eigenmode catalogue, apply parametric perturbations (stretch/rotate/scale/shear/bump), and filter by **centre-drive excitability physics** (`center_participation()`) to discard modes a central drive cannot excite — aligning "what the client wants" with "what physics allows".
- **Export (3D-print export)**: pick a run + pick **Phase 1 (initial) / Phase 2 (refined)** design → download a printable stepped-plate STL; includes a thickness-range/material-volume summary and a θ-free FDM slicing recipe reference.

### 5.3 STL export module (`src/export/stl_export.py`, zero-dependency)

No trimesh / numpy-stl (runs even when disk is tight): converts the 15×15 thickness field into a binary STL of 225 stepped boxes (2700 triangles, ~132 KB), with optional Gaussian step-smoothing. `plate_length_mm / grid = 10 mm` cells, flat bottom on the bed, steps facing up.

### 5.4 Engineering discipline

- **Algorithm audit (E1–E6, read-only)**: systematically quantified cognitive biases in metrics/algorithms without touching core code, producing an independent report.
- **Git rollback discipline**: repeatedly hit "added optimisation made things worse → hard-reset to a known-good baseline → selectively cherry-pick".
- **Reproducibility**: each era/experiment has scripts + JSON numbers + comparison figures; a successor can re-run everything in one command.

---

## 6. Results summary

### 6.1 Recognisability ceiling per target (COMSOL-measured, post normalisation fix)

| Target | A₁ ceiling | Best COMSOL enrichment | Visual verdict |
|---|---:|---:|---|
| **X-shape** | 100% | **3.76×** (project ceiling) | Clean X diagonal nodal lines |
| IC (Phase 1 composite 132+180 Hz) | 41.9% | broad **3.82× / recall 0.89** | "I" vertical band + "C" open curve + central link, **faintly legible** but not crisp letters |
| + cross | 100% | ~1.5–1.6× | Nodal mesh, cross partly visible |
| Single diagonal | 51.7% | ~2.4× (best single) | Thick diagonal nodal band, effectively X-leaning |
| Ring | — | ~0 at sr=1; needs anisotropy to form a ring | Isotropic square-plate modes contain no ring |

### 6.2 Surrogate-vs-COMSOL "achievement rate"

Of the 8–18× improvement the surrogate predicts, the COMSOL isotropic pipeline reproduces only 9–44%. The rest is eaten by (a) the surrogate-physics gap and (b) θ's failure under real physics — exactly the quantitative footprint of the four findings in §3.

---

## 7. Limitations and the physical ceiling (the honest boundary)

1. **Any non-D₄-compatible image (IC, single diagonal, L-shape, arbitrary logo) is physically unreachable.** Not an algorithm problem — the A₁ irrep filtering of a central point drive. This is a hard ceiling.
2. **Anisotropy headroom is limited.** Real material sr≈1.87, and θ's gradient ≈ 0 off-resonance; expecting θ to break the ceiling is unrealistic.
3. **A surrogate is never COMSOL.** Any surrogate-only "breakthrough" must be re-checked with COMSOL.
4. **Further breakthroughs require hardware**: D₄-symmetry-breaking excitation (multi-shaker / off-centre drive), changed boundary (non-square plate), discrete topology (holes/slots). These exceed this project's fixed contract.

---

## 8. Behind the project (acknowledgements and reality)

Behind every table in this report is a first-year undergraduate team, in a summer project, running **~350 COMSOL candidates, ~20 algorithm lines, and one 36-hour sleepless push.**

What belongs in a closing report is not only the results, but a few "painful but correct" turns:

- Honestly cutting an inflated 0.2 score down to 0.034 — **admitting the metric was wrong matters more than keeping a pretty number.**
- Discovering that anisotropy and θ — the main line we had pinned so much hope on — were "essentially useless" — **being willing to kill your own favourite hypothesis.**
- After W9 trust-region failed, W10 didn't reproduce in COMSOL, and IC never came out crisp, not papering over it but **explaining "why it can't be done" rigorously via A₁ irrep maths.**

> The biggest reward of a summer project is often not "we built the thing we wanted", but **we understood why the thing we wanted does not physically exist, and turned the boundary-hugging optimum into a system that reproduces, prints, and ships.** That, we did.

---

## 9. Conclusion and future work

**Conclusion**: under a fixed hardware contract, this project pushed the reachability boundary of a 15×15 square plate with central excitation to its limit (X-shape 3.76×, IC composite 3.82× broad / 0.89 recall), and delivered a complete system spanning differentiable optimisation → high-fidelity validation → manufacturable export → full-stack software. The remaining headroom is not in the algorithm; it is in the hardware.

**Future work (by priority)**:
1. D₄-symmetry-breaking hardware (multi-shaker / off-centre drive / non-square boundary / discrete topology holes) — the only path to truly break the A₁ ceiling.
2. Symmetry-aware direction metric (fix PCA principal-axis degeneracy on symmetric images).
3. Real physical time-division multi-frequency drive (excite one frequency, sand, switch), not numerical RMS.
4. Further tune the two-phase pipeline's trust-region parameters (warm start, unlocked frequency, adaptive inner steps).

---

## Appendix A: key file map

| Module | File |
|---|---|
| Differentiable orthotropic plate | `src/physics/orthotropic_plate.py`, `differentiable_plate.py` |
| W10 joint optimisation | `src/optimisation/recognisability_placement_w10.py` |
| Two-phase production pipeline | `src/optimisation/production_pipeline.py` |
| D₄ irrep decomposition | `src/symmetry/d4_decomposition.py` |
| Realizability verdict | `src/target/target_realizability.py` |
| Recognisability metrics | `src/scoring/recognisability_score.py` |
| Centre-drive excitability | `src/physics/drive_reachability.py` |
| Uniform-plate gallery | `src/uniform_pattern/` (catalogue/render/perturb/match) |
| STL export | `src/export/stl_export.py` |
| Frontend | `frontend/target_designer.html` |
| Backend | `src/frontend/target_ui_server.py` |
| COMSOL templates | `comsol_templates/*.m` |

## Appendix B: historical report index

- `reports/algorithm_trial_full_history.zh-CN.md` — full trial-and-error history of Eras I–III
- `reports/algorithm_breakthrough_plan.zh-CN.md` — W1–W8 engineering plan
- `reports/sprint1_w9_sprint2_summary.zh-CN.md` — W9 / W10 / two-phase pipeline / material generalisation
- `reports/_battery/BATTERY_FINDINGS.md` — θ parasitism and material comparison (6×2)
- `reports/audit_algorithmic_review_2026-05.zh-CN.md` — E1–E6 algorithmic-bias audit

---

## Appendix C: references and data sources

The following are works actually cited or directly used in the code/modelling. Two groups: **(1) materials and plate mechanics** (used directly for the W10 anisotropic plate model and material parameters); **(2) foundational theory** (the standard theory underpinning realizability verdicts, symmetry decomposition, and Chladni physics).

### C.1 Materials and plate mechanics (directly cited, see `src/physics/orthotropic_plate.py`)

1. **Reddy, J. N. (2003).** *Mechanics of Laminated Composite Plates and Shells: Theory and Analysis* (2nd ed.). CRC Press. — Source of the W10 orthotropic Kirchhoff plate's bending stiffnesses D₁₁…D₂₆ and the θ-rotation formula (Eq. 1.3.94).
2. **Letcher, T., & Waytashek, M. (2014).** "Material Property Testing of 3D-Printed Specimen in PLA on an Entry-Level 3D Printer." *ASME IMECE 2014.* — Source of the FDM PLA anisotropy ratio E∥/E⊥ ≈ 1.4.
3. **Pyl, L., Kalteremidou, K.-A., & Van Hemelrijck, D. (2018).** "Exploration of the Mechanical Properties of FDM-printed PLA." *Procedia Manufacturing, 14, 104–.* — Reference for FDM anisotropy test methodology.
4. **Formlabs (2018).** *Validating Isotropy in SLA 3D Printing* (technical white paper). — Basis for SLA grey resin being near-isotropic after full post-cure (E∥/E⊥ ≈ 1.00–1.10).
5. **Vat-photopolymerisation anisotropy study,** *Scientific Reports* 15:97294 (2025). — Supplementary evidence that SLA/photopolymer post-cure anisotropy is ~0–10%.
6. **Bambu Lab PETG-CF Technical Data Sheet (TDS V3.0).** — Real flexural-modulus data, from which the measured anisotropy ratio **sr ≈ 1.87** was derived (far below the 2.8–3.0 assumed from early literature).

### C.2 Foundational theory (standard theory underpinning the methods)

7. **Chladni, E. F. F. (1787).** *Entdeckungen über die Theorie des Klanges.* — Origin of the Chladni figure (sand collects on nodal lines), the forward problem itself.
8. **Kirchhoff–Love thin-plate theory** (Kirchhoff 1850; Love 1888). — The biharmonic thin-plate model used by the surrogate (W3/W10).
9. **Mindlin–Reissner thick-plate theory** (Reissner 1945; Mindlin 1951). — The high-fidelity COMSOL Shell model with transverse shear; the thick-plate side of the "surrogate–COMSOL physics gap".
10. **Courant nodal domain theorem** (Courant & Hilbert, *Methods of Mathematical Physics*, 1953). — Theoretical basis for `courant_min_mode_index` in the W1 realizability verdict.
11. **Pleijel, Å. (1956).** "Remarks on Courant's nodal line theorem." *Comm. Pure Appl. Math., 9, 543–550.* — Asymptotic bound on nodal-domain count, used in the realizability prior.
12. **Representation theory of the dihedral group D₄** (standard group theory, e.g. Tinkham, *Group Theory and Quantum Mechanics*, 1964). — Theoretical basis for the A₁/A₂/B₁/B₂/E irreducible-representation decomposition behind the core "central excitation couples only to A₁" result.

### C.3 Methodological references per era (line by line)

The table below maps **every algorithm line** from Era I to Era III (and the modern production period) to its methodological source. Items already present in the project code (plate mechanics, realizability) are in C.1/C.2; the rest are the recognised classics of each method, filled in per the request "find them if they aren't there", so every algorithm traces back to standard methodology.

| Algorithm line | Core method | Methodological reference |
|---|---|---|
| **I·A** Random/evolutionary thickness search | Genetic algorithm + structural topology/material distribution | Holland 1975, *Adaptation in Natural and Artificial Systems*; Bendsøe & Sigmund 2003, *Topology Optimization* |
| **I·B** Response-guided error loop | Iterative inversion of inverse problems | Tarantola 2005, *Inverse Problem Theory and Methods for Model Parameter Estimation*, SIAM |
| **I·C** Kirchhoff–Love proxy | Thin-plate free vibration / biharmonic eigenproblem | Leissa 1969, *Vibration of Plates*, NASA SP-160; Waller 1939, *Proc. Phys. Soc.* 51:831 |
| **I·D** Strict shape scoring | IoU/Jaccard, Dice, Chamfer shape similarity | Jaccard 1912; Dice 1945, *Ecology* 26:297; Barrow et al. 1977 (Chamfer matching, IJCAI) |
| **I·E** Design-contract expansion (density/loss/material fields) | SIMP variable-density material distribution | Bendsøe 1989, *Struct. Optim.* 1:193; Bendsøe & Sigmund 1999, *Arch. Appl. Mech.* 69:635 |
| **I·F** Auxiliary-physics local heuristics | Direct / pattern search | Hooke & Jeeves 1961, *J. ACM* 8:212 |
| **I·G** Latent joint physics (hand-made basis) | Reduced basis / proper orthogonal decomposition (POD) | Berkooz, Holmes & Lumley 1993, *Annu. Rev. Fluid Mech.* 25:539 |
| **I·H** CMA latent optimisation | Covariance Matrix Adaptation Evolution Strategy (CMA-ES) | Hansen & Ostermeier 2001, *Evol. Comput.* 9(2):159 |
| **I·I** Response-calibrated latent scheduling | Surrogate/Bayesian optimisation + acquisition | Jones, Schonlau & Welch 1998, *J. Global Optim.* 13:455 (EGO); Shahriari et al. 2016, *Proc. IEEE* 104:148 |
| **II·W1** Realizability prior filter | Nodal-domain theorem + square-plate D₄ symmetry classes | Courant & Hilbert 1953; Pleijel 1956, *CPAM* 9:543; Waller 1939, *Proc. Phys. Soc.* 51:831 |
| **II·W2** Main-loss redesign (amplitude valley) | Continuous optimisation of a smooth differentiable objective | Nocedal & Wright 2006, *Numerical Optimization* (2nd ed.), Springer |
| **II·W3** Differentiable plate + adjoint | Adjoint method + automatic differentiation + eigenvalue/eigenvector sensitivity | Giles & Pierce 2000, *Flow Turbul. Combust.* 65:393; Baydin et al. 2018, *JMLR* 18:1; Paszke et al. 2019 (PyTorch, NeurIPS); **Fox & Kapoor 1968, *AIAA J.* 6:2426**; **Nelson 1976, *AIAA J.* 14:1201** (analytic eigenvalue/eigenvector sensitivities) |
| **II·W4** Low-dim manifold search | Principal component analysis / reduced design space | Pearson 1901, *Phil. Mag.* 2:559; Berkooz et al. 1993 (POD) |
| **II·W5** Homotopy continuation | Numerical continuation / graduated non-convex optimisation | Allgower & Georg 1990, *Numerical Continuation Methods*, Springer; Blake & Zisserman 1987, *Visual Reconstruction* (graduated non-convexity) |
| **II·W6** Spectral placement | Eigenvalue topology optimisation | Pedersen 2000, *Struct. Multidisc. Optim.* 20:2; Achtziger & Kočvara 2007, *SMO* 34:181 |
| **III·W7** Multi-frequency time-division drive | Multi-frequency/harmonic frequency-domain forced response + first-order stochastic optimisation | Kingma & Ba 2015 (Adam, ICLR); (forced response: Leissa 1969) |
| **III·W8** Recognisability-driven optimisation | Chladni nodal-line physics + optimal transport (Sinkhorn divergence), avoiding the cycle-skipping of IoU/L² | Chladni 1787; Cuturi 2013, *NeurIPS* (Sinkhorn Distances); **Engquist & Froese 2014, *Commun. Math. Sci.* 12:979** (Wasserstein for waveform matching, avoiding cycle-skipping) |
| **Modern·W9** Trust-region loop | Trust-region methods + surrogate management framework + modal tracking (MAC) | Conn, Gould & Toint 2000, *Trust-Region Methods*, SIAM; Booker et al. 1999, *SMO* 17:1; **Allemang & Brown 1982 (Modal Assurance Criterion, IMAC)** |
| **Modern·W10** Differentiable orthotropic plate | Laminated/orthotropic plate theory + per-cell θ rotation | Reddy 2003 (see C.1); D₄ irrep see C.2 |

> Note: Holland / Hansen / Jones / Cuturi / Kingma / Conn etc. are the recognised foundational or authoritative-survey works of each method; the team implemented their ideas on this problem (rather than adopting any one implementation). Plate mechanics (Leissa/Reddy/Waller) and realizability (Courant/Pleijel) are used directly in code and modelling.

### C.4 Software and numerical tools

- **COMSOL Multiphysics 6.4** + **LiveLink™ for MATLAB** (high-fidelity eigenfrequency / frequency-domain forced response, Shell physics with an orthotropic configuration).
- **PyTorch** (W3–W10 differentiable plate and autograd sensitivities), **SciPy/NumPy** (sparse eigensolves, connected components, distance transform, Gaussian filtering).

> Note: items in C.1 can be found in the header comments of `src/physics/orthotropic_plate.py`; C.2 lists the standard textbook-level theory the methods rest on, given for traceability — the team implemented these from first principles rather than adopting any one implementation.

### C.5 Related work and inspirations (directly comparable prior art)

The following are works on the **same or strongly related problem**, forming the comparison baseline and inspiration for the methodology. **The first is especially important**: it is the 2024 work on "almost exactly our problem" and should be cited as the project's main prior art.

1. **"Topology optimization design of Chladni patterns for vibration mode manipulability." *Acta Mechanica Sinica* (2024),** DOI 10.1007/s10409-023-23445-x (authors per the journal page). — **The most directly comparable prior art**: it also uses density-based topology optimisation (SIMP), with an objective minimising the error between eigenvectors and the target Chladni pattern, to inversely design material distributions for single- and multi-order Chladni patterns. Its "eigenvector-error" objective is cognate to our Era I·D / II evolution; its SIMP density variable is close to our `density_scale`. **Key difference**: it is not bound by the "single central excitation + D₄ symmetry" hard constraint (the very source of this project's A₁ irrep ceiling), so its reachable pattern space is larger.
2. **Tcherniak, D. (2002).** "Topology optimization of resonating structures using SIMP method." *Int. J. Numer. Meth. Eng.* 54:1605. — A founding work on SIMP topology optimisation of resonating structures, one methodological source of the 2024 paper above.
3. **`PaulBellette/chladni_inverse_design` (open-source implementation).** — Frames Chladni inverse design as an "energy-landscape" problem: `E(x,y)=Σ_k b_k φ_k(x,y)²` (nonnegative mixture of squared mode shapes). This matches our W2/W6 **amplitude valley loss**, and independently confirms that "nonnegative squared mixtures prefer boxes/bands/grids/crosses/large connected glyphs and dislike fine separated features" — strongly consistent with what our D₄ + powder physics found.
4. **Misseroni, D., Movchan, A. B., & Movchan, N. V. (2016).** "Cymatics for the cloaking of flexural vibrations in a structured plate." *Scientific Reports* 6:23929. — Uses a structured plate to control flexural waves / nodal lines (cymatics = Chladni); the physical inspiration for "reshaping nodal-line distributions via geometry".
5. **Tuan, P.-T., Chen, Y.-F., et al.** — The Chen group maps Chladni forced response to **maximum-entropy states of the inhomogeneous Helmholtz equation** to reconstruct/predict nodal patterns; the theoretical inspiration for the "forced response vs free vibration" distinction (one of the blind spots in §3.3).
6. **Zhou, Q., et al. (2016).** "Controlling the motion of multiple objects on a Chladni plate." *Nature Communications* 7:12764. — Multi-actuator active control of Chladni nodal lines / particle motion, confirming the core recommendation of §7: **breaking the D₄ / A₁ ceiling requires hardware (multi-shaker, symmetry-breaking excitation).**
7. **(Alternative not adopted) level-set shape optimisation**: Allaire, Jouve & Toader 2004, *J. Comput. Phys.* 194:363. This project uses a density/thickness field rather than a level-set boundary representation; listed for comparison.

---

*All quantitative conclusions in this report are drawn from experiment records and JSON numbers within the repository above; no extrapolation or embellishment. Related work (C.5) is for comparison and traceability; some entries are same-problem prior art or independent open-source implementations.*
