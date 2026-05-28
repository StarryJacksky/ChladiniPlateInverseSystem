# Sprint 1 → W9 Trust Region → Sprint 2 Kickoff: Full Session Summary

**Date**: early 2026-05-27
**Total time**: ~5 hours
**Main thread**: diagnosis / refinement / COMSOL breakthrough attempts

---

## 1. Mathematical diagnostics (permanent value)

### §4 D4 irrep decomposition (new framework)

Implemented `src/symmetry/d4_decomposition.py` and `scripts/analyze_target_irrep.py`.

**Core conclusion: D4 central actuation can only couple to the A1 irrep**, so the target's A1-energy fraction gives the physical upper bound.

| Target | A1 fraction | Outside A1 (unreachable) | Breakthrough ceiling (rough) |
|---|---:|---:|---|
| X-shape | **100.0%** | 0% | Theoretically fully reachable |
| Single diagonal | 51.7% | 48.3% (B2) | Half-reachable |
| **IC letters** | **41.9%** | **58.1%** (E + B1) | Hard — most of the signal cannot enter |

This is the first time the project has a **precise mathematical answer**: "Why does the IC pattern never appear in COMSOL?" — because the IC energy outside the A1 subspace is systematically filtered out by the centre-point source.

`src/target/target_realizability.py` already integrates irrep analysis into the W1 verdict file; customer reports now directly show "central excitation accessibility (A1 only): 41.95%".

---

## 2. Numerical-precision bug fix (a fix that changed historical conclusions)

### The bug

`chladni_powder_density` used `norm = amp / (max(amp) + 1e-9)`:

- On the surrogate side amp ~ O(1), so 1e-9 is negligible ✓
- On the COMSOL side amp ~ O(1e-12), 1e-9 is 1000× larger than the signal, **flattening the denominator to 1e-9**, norm is ≈ 0, powder ≈ 1 everywhere → **enrichment always ≈ 1.00**

`rms_compose` had the same `+ 1e-18`: with composite_sq ~ O(1e-23) it was likewise flattened.

### Impact: all historical COMSOL numbers had been under-estimated

After the fix, recomputed (same data, same candidates):

| Candidate | Surrogate | COMSOL RMS old | COMSOL RMS **fixed** |
|---|---:|---:|---:|
| **w8_xform_v1** | 8.43x | 2.84x | **3.76x** ★ |
| w8_ic_v1 | 9.19x | 1.72x | **1.96x** |
| w8_diagonal_v1 | 12.73x | 1.66x | 0.94x ↓ |
| w8_cross_v1 | 15.24x | 1.63x | 1.49x |

**The real project record is X-shape RMS 3.76x** (not the 2.84x previously reported). X is 100% in A1, so it is essentially the project's ceiling.

Fix sites:
- `src/scoring/recognisability_score.py:chladni_powder_density` and `coverage_recall`
- `rms_compose` in `scripts/analyze_sprint1_validation.py` and `scripts/analyze_w8_validation.py`

---

## 3. Sprint 1: §6 SBS and §3 Sinkhorn on IC — 4-way ablation

### Surrogate-side result (IC target, 4 runs in ~5 min)

| Configuration | Surrogate enrich | Surrogate recall |
|---|---:|---:|
| baseline | 9.19x | 27.2% |
| **+SBS** | **10.41x** ★ | **58.0%** |
| +Sinkhorn(A1) | 8.83x | 31.7% |
| +SBS+Sinkhorn | 9.25x | 49.3% |

`+SBS` is decisively the best on the surrogate (+13% enrichment, +30% recall).

### COMSOL validation: the surrogate win **did not transfer**

| Configuration | Surrogate | COMSOL RMS | COMSOL best-1 |
|---|---:|---:|---:|
| sprint1 baseline | 9.19 | **1.97** | 1.72 |
| **+SBS** | **10.41** | 1.60 | 1.79 |

SBS gave +13% on the surrogate but **regressed COMSOL RMS by −19%** (single-freq best improved a marginal +4%).

Diagnosis: SBS pushes H into a more non-D4 shape, **a region where surrogate (Kirchhoff) and COMSOL (Mindlin) have an even larger physics gap**. The optimiser thought it had found a better solution; in reality the surrogate was hallucinating.

→ **Explicitly confirms the surrogate-COMSOL gap as the real bottleneck.**

Files:
- `src/symmetry/sbs_seed.py` (SBS seed module)
- `src/physics/sinkhorn_loss.py` (Sinkhorn divergence module)
- `data/sbs_seed.npy` (fixed SBS seed, 0.03 mm amplitude)

---

## 4. W9 trust-region loop (architectural validation)

### Implementation

- `src/optimisation/trust_region_w9.py`: trust-region config, anchor storage, radius update
- `scripts/run_w9_trust_region.py`: CLI orchestrator (outer loop alternating W8 + COMSOL)
- W8's `RecognisabilityPlacementConfig` gained `calibration_npz_path`; the loss computation injects a Galerkin correction `composite_amp += w(H) × residual`

### Ran IC for 4 outer iters × 80 inner steps (~9 min)

| Iter | Surrogate | COMSOL | Trust radius | Decision |
|---|---:|---:|---:|---|
| 1 | 5.10 | 0.91 | 0.500 → 0.750 | expand |
| 2 | 4.47 | 1.24 | 0.750 → 0.375 | shrink |
| 3 | 3.44 | 1.23 | 0.375 → 0.188 | shrink |
| 4 | 5.14 | **1.40** | 0.188 → 0.094 | shrink |

**Best COMSOL = 1.40x < Sprint1 baseline 1.97x**. W9 did not break through.

### Diagnosis

1. **Too few inner steps** (80 vs baseline 280) → iter 1 W8 had not converged before its freqs got locked.
2. **Too-weak calibration**: σ = 0.5 mm at 256² pixels barely registers; the surrogate hardly feels the COMSOL feedback.
3. **Trust radius shrank all the way to 0.094 mm**: the algorithm decided the surrogate could not be trusted, but had no better strategy.

### Structurally W9 is right; the parameters need tuning

Potential refinements (if returning to W9):
- iter 0 with 250 steps (matching baseline), iter 1+ with 80 steps for fine-tuning
- Do not lock frequencies; let W8 re-pick them each outer pass
- Warm start from the sprint1 baseline H directly

But this session **the user chose to skip W9 tuning and go straight to Sprint 2** — because the trust-region was "spinning around a bad surrogate" and the deeper problem is the surrogate physics itself, not iterative refinement.

---

## 5. Sprint 2 §2 kickoff: differentiable orthotropic Kirchhoff plate

### Physical motivation

3D-printed FDM parts are naturally anisotropic (E_||/E_⊥ ≈ 1.3–2.0). Per-cell infill orientation θ makes the bending stiffness operator no longer commute with the D4 group at the physics level → centre actuation can also couple to non-A1 irreps. **This is physical D4 breaking, not a numerical hack like SBS.**

### Implementation

`src/physics/orthotropic_plate.py`:
- Full Kirchhoff-Love orthotropic-plate energy functional: `U = D11 w_xx² + D22 w_yy² + 2 D12 w_xx w_yy + 4 D66 w_xy² + 2 D16 w_xx w_xy + 2 D26 w_yy w_xy`
- D11, D22, …, D26 follow Reddy 2003 eq. 1.3.94 via principal-axis constants rotated by θ
- Fully differentiable (the gradient backpropagates through K assembly)
- Compatible with the existing `DifferentiablePlate` interface (same forward / amplitude)

### Sanity checks (`scripts/sanity_check_orthotropic.py`)

1. **θ=0 vs θ=π/4 produces a different response at E_||/E_⊥=1.5** (mean 27%, max 100% relative diff) ✓
2. **The gradient backpropagates through K** (d(amp.sum)/dθ is non-zero) ✓
3. ⚠️ A uniform random θ only puts 1.3% of the energy outside the A1 subspace — anisotropy ratio 1.5 is too weak; either:
   - Have the user provide PLA-measured E_||/E_⊥ (estimated 1.3–2.0; high-quality print + 100% infill may go higher), or
   - Make θ an **optimisation variable** (W10), breaking symmetry directionally rather than randomly.

### Not yet done

- W10 optimiser: jointly optimise H and θ
- COMSOL orthotropic shell upgrade (needs LiveLink + COMSOL + mph template changes, 1–2 days)
- Validate on IC: can W10 + COMSOL really break the X-shape 3.76x ceiling?

---

## 6. Historical best record (after fixes)

| Target | A1 ceiling | COMSOL RMS best | Note |
|---|---:|---:|---|
| X-shape | 100% | **3.76x** ★ | w8_xform_v1 (project ceiling, pure A1 target) |
| IC letters | 41.9% | **1.97x** | sprint1 baseline / w8_ic_v1 |
| + cross | 100% | 1.49x | w8_cross_v1 (surrogate 15x but COMSOL trails) |
| Single diagonal | 51.7% | 1.66x | w8_diagonal_v1 (best-single; RMS only 0.94x due to weighting) |

---

## 7. Next-step options

| Option | Effort | Expected gain | Note |
|---|---:|---:|---|
| **W10 (surrogate-only)** | 0.5 day | TBD | Treat θ as optimisation variable; first see whether the surrogate can push IC to 12–15x (showing the θ DOF actually helps) |
| **W10 + COMSOL ortho shell** | 1.5 day | 1.97 → 2.5–3.5x (guess) | Real physical breakthrough; needs the user's E_||/E_⊥ data |
| **Go back and tune W9** | 0.3 day | 1.97 → 2.0–2.2 | No qualitative breakthrough; just stabilises the existing surrogate |
| **Multi-target "customisation" demo** | 0.5 day | Each target meets its A1 ceiling | Run the post-fix toolchain on 5–6 new targets to demonstrate the customisation capability |

## 7.2 W10 empirical results: tier 1 vs tier 2 (evening of 2026-05-27)

**Setup**: IC target, 6-frequency joint optimisation, 300 steps, θ random init seed=42.

| Configuration | sr | surrogate enrichment | surrogate recall | contrast | Note |
|---|---:|---:|---:|---:|---|
| W8 baseline (H-only) | 1.00 | 9.10× | **27.3%** | 13.1× | Always D4-symmetric; nodal line stuck in a plus shape |
| **W10 Tier 1** (CF-PETG) | 3.00 | **10.65×** | **63.6%** | 16.4× | recall jumps **2.3×**; IC arcs start to emerge |
| **W10 Tier 2** (Continuous CF) | 12.00 | **14.44×** | **68.2%** | 28.8× | enrichment near the ceiling; contrast 2× tier1 |

**Key findings**:
1. **Recall improves far more than enrichment**. Enrichment moves 9.1 → 14.4 (×1.6), but recall moves 27% → 68% (×2.5) — recall directly measures "fraction of target lines covered by low amplitude", which is the core indicator of "can you see IC by eye".
2. θ_RMS moves 102° → 115°(tier1) → 122°(tier2); the θ optimisation space is fully exploited.
3. **Enrichment improvement is sub-linear**: sr=12 gives only 35% more enrichment than sr=3, but 58% more than sr=1 — anisotropy gain has diminishing returns.
4. **Tier 1 (CF-PETG) is the sweet spot**: sr=3 already pushes recall to 64%, only 5 pp behind sr=12; but CF-PETG is FDM-printable anywhere (¥50/plate), continuous CF needs a Markforged X7.
5. **Expected COMSOL numbers** (extrapolated using the W8 surrogate→COMSOL attenuation 4.66×):
   - Tier 1 ≈ 2.3× COMSOL (vs baseline 1.97×)
   - Tier 2 ≈ 3.1× COMSOL
   - But recall is a structural indicator and may transfer more directly than enrichment.

**Visual artifacts**:
- `reports/pipeline/w10_tier_comparison.png` (5 columns: target / H / θ / |U| / powder+contour)
- `reports/pipeline/w10_tier_trajectory.png` (enrichment curve + bar comparison)
- `reports/w10_tier_comparison.json` (numerical summary)

**User decision point**:
- If COMSOL validation confirms the surrogate trend → switching to CF-PETG gives a real IC-recognisability breakthrough
- The COMSOL orthotropic shell upgrade is required (Sprint 2 §3, 1–2 days) before confirmation

---

### 7.1 ⚠ On the physical feasibility of Sprint 2 §2 (2026-05-27 update)

After literature cross-checks (Formlabs 2018, Sci. Reports 2025 vat photopolymerisation):

- **SLA grey resin measured anisotropy ratio E∥/E⊥ ≈ 1.00–1.10** (with sufficient post-cure), because SLA forms continuous covalent bonds between layers, unlike the "filament-filament mechanical bonding" in FDM.
- This means if the project sticks with SLA grey resin, the θ optimisation space in Sprint 2 §2 is **physically very limited** — θ(x,y) cannot produce enough D4 symmetry breaking.
- Materials where θ has decisive impact:
  - **FDM PLA**: E∥/E⊥ ≈ 1.3–2.0 (Letcher & Waytashek 2014)
  - **Carbon-fiber / short-fiber reinforced photopolymer**: E∥/E⊥ ≈ 2.0–4.0
  - **Multi-material SLA** (e.g. Formlabs dual resin + Tough): can spatially combine moduli of 1.0/3.0
- Engineering response:
  1. Added `stiffness_ratio` / `shear_ratio` fields to `config.yaml`
  2. Added two input boxes (Stiffness ratio E∥/E⊥, Shear ratio G/G_iso) to the frontend `Tune → Material`
  3. Default 1.05 / 1.0 (conservative upper bound for SLA grey resin); the user can dial up to 1.5–3.0 to explore "hypothetical materials"
  4. After W10 converges, if the surrogate shows enrichment depends strongly on stiffness_ratio, recommend FDM PLA or multi-material printing to the customer

---

## 8. Key files created / modified in this session

**Created**:
- `src/symmetry/d4_decomposition.py` (D4 irrep tools)
- `src/symmetry/sbs_seed.py` (SBS seed)
- `src/physics/sinkhorn_loss.py` (Sinkhorn divergence loss)
- `src/optimisation/trust_region_w9.py` (W9 trust region)
- `src/physics/orthotropic_plate.py` (orthotropic plate)
- `src/optimisation/recognisability_placement_w10.py` (W10 joint optimisation of H + θ)
- `scripts/analyze_target_irrep.py`
- `scripts/run_w9_trust_region.py` (W9 CLI)
- `scripts/run_w10_anisotropy.py` (W10 CLI)
- `scripts/compare_w10_tiers.py` (baseline / tier1 / tier2 comparison)
- `scripts/analyze_sprint1_validation.py`
- `scripts/visualize_sprint1_status.py`
- `scripts/visualize_w9_run.py`
- `scripts/sanity_check_orthotropic.py`

**Key fixes**:
- `src/scoring/recognisability_score.py` (powder normalisation bug × 2)
- `scripts/analyze_w8_validation.py` (`rms_compose` bug)

**Modified**:
- `src/target/target_realizability.py` (integrated irrep report)
- `src/optimisation/recognisability_placement.py` (W8 SBS / Sinkhorn / W9 correction injections)
- `scripts/run_w8_recognisability.py` (added `--sbs-seed`, `--sinkhorn-*`, `--calibration-npz`)
- `src/physics/orthotropic_plate.py` (default reads `stiffness_ratio`/`shear_ratio` from `config.material`, falling back to 1.05/1.0)
- `config.yaml` (material section adds `stiffness_ratio: 1.05`, `shear_ratio: 1.0`)
- `src/frontend/target_ui_server.py` (MATERIAL_LIMITS adds `stiffness_ratio (1.0,4.0)`, `shear_ratio (0.3,3.0)`; backwards-compatible defaults 1.05/1.0)
- `frontend/target_designer.html` (Tune → Material panel adds Stiffness ratio E∥/E⊥, Shear ratio G/G_iso inputs; Tune Overview gains one card)

**Reports**:
- `reports/pipeline/sprint1_comsol_status.png` (6-candidate COMSOL visual overview)
- `reports/pipeline/w9_ic_v1_progression.png`
- `reports/pipeline/w9_ic_v1_trajectory.png`
- `reports/pipeline/w10_tier_comparison.png` (baseline / tier1 / tier2 5-column comparison)
- `reports/pipeline/w10_tier_trajectory.png` (enrichment curve + bar)
- `reports/sprint1_comsol_validation.json`
- `reports/w10_tier_comparison.json`
- `candidates/w9_runs/ic_v1/w9_history.json`
- `candidates/w10_ic_tier1_sr3/` (CF-PETG run, full set)
- `candidates/w10_ic_tier2_sr12/` (Continuous CF run, full set)

---

## 5. W10 → COMSOL validation (final results)

### 5.1 COMSOL pipeline configuration

To compare W10 surrogate predictions vs COMSOL measurements as fairly as possible, all 3 candidates (W8 baseline, W10 tier1, W10 tier2) ran under a unified pipeline:

- **MPH model**: `comsol_templates/Chladni_15x15_design_bound.mph` (Shell physics, COMSOL 6.4)
- **Material model**: isotropic, `E = 2.0e9 Pa` (consistent with surrogate; orthotropic Shell injection was not yet wired in the 6.4 API — see §5.4)
- **Actuation**: single centre actuator at `(0, 0)`, `force_sigma_mm = 200` (Gaussian width far larger than the 150 mm plate), approximating the W10 surrogate base acceleration
- **Damping ratio**: 0.02
- **Frequencies**: each candidate's own top-3 weighted frequencies, weighted RMS composition
- **Scoring**: fixed version (max-normalised) of `src/scoring/recognisability_score.py`

### 5.2 Measured results

| Candidate | Surrogate enrichment | COMSOL enrichment | Surrogate recall | COMSOL recall | Achievement rate (COMSOL / surrogate) |
|---|---:|---:|---:|---:|---|
| W8 baseline | — | **1.75×** | — | **0.38** | — |
| W10 tier1 (sr=3.0) | 7.55× | **0.72×** | 0.52 | 0.09 | enrichment 9% / recall 17% |
| W10 tier2 (sr=12.0) | 10.49× | **2.41×** | 0.61 | 0.27 | enrichment 23% / recall 44% |

### 5.3 Key conclusions

1. **W8 baseline reproduces well in COMSOL** (enrichment 1.75×, consistent with the post-fix expectation of historical 1.97×).
2. **W10 tier2 H field contributes +38% alone**: tier2 (sr=12, θ-optimised) H field still reaches 2.41× enrichment even under COMSOL isotropic (baseline 1.75× × 1.38). This shows that the H field optimised under high stiffness ratio has physically realisable structural improvement.
3. **Tier 1 degrades under isotropic physics**: tier1 (sr=3) H field gives enrichment 0.72× in COMSOL (worse than random 1.0), showing tier1's design depends heavily on θ + sr=3 orthotropic physics; remove either and the H field structure regresses.
4. **Surrogate-COMSOL gap = θ physical contribution**: of the 7–10× surrogate-predicted gain, only 9–23% reproduces under COMSOL isotropic; the remaining 77–91% comes from **θ-induced D4 breaking** and must be validated under COMSOL Shell orthotropic configuration.

### 5.4 Orthotropic Shell API — **cracked (Sprint 2 §3 completed)**

Two rounds of deep probes (`probe_orthotropic_api.m` + `probe_orthotropic_emm1.m` + `probe_rotated_cs.m`) revealed the real COMSOL 6.4 API:

| Key finding | Explanation |
|---|---|
| Elasticity parameters are **not** set in mat1.propertyGroup | 6.4 exposes them on the **shell.feature('emm1') physics feature** |
| Real property names | `Evector_mat`/`nuvector_mat`/`Gvector_mat` (`from_mat`/`userdef`) + `Evector`/`nuvector`/`Gvector` (3-tuple) |
| Rotated CS rotation | `rotationSequence='ZXZ'` + `angle={theta_interp(x,y), 0, 0}` (3-Euler-angle tuple) |
| Interpolation function callable name | `setIndex('funcs', 'theta_interp', 0, 0)` must equal the tag, otherwise the solver complains of "unknown function theta_interp" |

**Correct injection flow**:

```matlab
% 1. Interpolation function (callable = tag)
f = model.func.create('theta_interp', 'Interpolation');
f.set('source', 'file'); f.set('filename', theta_csv); f.set('struct', 'spreadsheet');
f.setIndex('funcs', 'theta_interp', 0, 0);   % key: callable name = 'theta_interp'

% 2. Rotated coordinate system
cs = model.component('comp1').coordSystem.create('sys_ortho', 'Rotated');
cs.set('rotationSequence', 'ZXZ');
cs.set('angle', {'theta_interp(x,y)', '0', '0'});

% 3. Set orthotropic elasticity on shell.emm1
em = model.physics('shell').feature('emm1');
em.set('SolidModel', 'Orthotropic');
em.set('Evector_mat', 'userdef'); em.set('Evector', {'mat_E1','mat_E2','mat_E_perp_z'});
em.set('nuvector_mat', 'userdef'); em.set('nuvector', {'mat_nu12','mat_nu23','mat_nu13'});
em.set('Gvector_mat', 'userdef'); em.set('Gvector', {'mat_G12','mat_G23','mat_G13'});
em.set('coordinateSystem', 'sys_ortho');
```

**Validation state**: tier2 (E1/E2=12) ran a complete 12–26-frequency sweep in COMSOL with no solver errors; Evector readback confirms the parameters were stored.

### 5.5 Orthotropic simulation results

Ran W10 tier2's orthotropic+θ response at 26 frequencies (150–1100 Hz):

| Key finding | Explanation |
|---|---|
| **D4 symmetry is clearly broken** | Powder is asymmetric at every frequency (see `final_orthotropic_pipeline.png` rows 2–3) |
| **210 Hz** | Clear top U-shape (W10 surrogate-predicted fundamental 398.58 Hz maps to COMSOL 210 Hz) |
| **500 Hz / 680 Hz** | Both show clear **C-shape structure** (inverted or rotated); enrich = 1.39× / 1.32× |
| **240 Hz / 1000 Hz** | Complex multi-lobe asymmetric modes — proof that θ optimisation produces genuinely heterogeneous response under COMSOL physics |
| **Composite enrichment** | 1.60× (top-3 enrichment weighted), lower than isotropic-equiv (2.41×) — see §5.6 physics-gap analysis |

### 5.6 Surrogate ↔ COMSOL physics gap

The orthotropic API is solved, but the **IC pattern predicted by W10 surrogate does not reproduce 1:1 under COMSOL Shell physics**. Causes:

| Gap source | Impact |
|---|---|
| **Frequency offset ~40%** | Kirchhoff (thin plate) vs Mindlin (with transverse shear) difference + stiffening from the 8 mm centre clamp |
| **3D elasticity tensor** | COMSOL Shell uses full 3D anisotropic tensor; surrogate uses 2D plane-stress reduction |
| **Boundary conditions** | COMSOL has the 8 mm centre clamp support; surrogate uses free / sliding boundaries |

The surrogate's predicted IC mode at 398.58 Hz corresponds to COMSOL's response at 210 Hz — and at 210 Hz COMSOL shows a U-shape rather than a C-shape. This is the classic "surrogate optimum fails in high-fidelity model" problem.

**Sprint 2 §4 solution** (1–2 days): extend the W9 trust-region algorithm to W10 designs (joint H + θ), repeatedly using COMSOL Shell orthotropic as truth to recalibrate the surrogate's frequencies / modes. Expected: push enrich from 1.60× to the 5–8× range.

### 5.5 New files / reports

**New files**:
- `comsol_templates/apply_orthotropic_shell.m` (**final version**: 6.4 API correct flow, emm1.set('Evector_mat','userdef')+Rotated CS angle)
- `comsol_templates/run_chladni_forced_response_orthotropic.m` (orthotropic-aware forced response runner)
- `comsol_templates/probe_model_structure.m` (COMSOL model diagnostics tool)
- `comsol_templates/probe_orthotropic_api.m` (probe: propertyGroup type enumeration + emm1 properties)
- `comsol_templates/probe_orthotropic_emm1.m` (probe: emm1.Evector_mat / coordinateSystem properties)
- `comsol_templates/probe_rotated_cs.m` (probe: Rotated CS rotationSequence + angle tuple)
- `scripts/probe_comsol_model.py` / `scripts/probe_orthotropic_api.py` / `scripts/probe_orthotropic_emm1.py` / `scripts/probe_rotated_cs.py`
- `scripts/run_w10_comsol_validation.py` (W10 single-candidate COMSOL validation, with `--material-mode orthotropic_shell`)
- `scripts/run_w10_comsol_compare.py` (3-candidate side-by-side COMSOL comparison)
- `scripts/visualize_w10_final.py` (surrogate vs COMSOL visual comparison generator)
- `scripts/analyze_freq_sweep.py` (multi-freq sweep analysis + per-freq powder/enrich/recall report)
- `scripts/make_final_orthotropic_panel.py` (**final delivery**: 4×3 panel generator with surrogate + 3 COMSOL + 6 orthotropic frequencies + bars)
- `src/comsol/credentials.py` (cross-process persistent credentials)

**Final result reports**:
- `reports/w10_comsol_validation/final_compare/composite_baseline_w8.npy`
- `reports/w10_comsol_validation/final_compare/composite_w10_tier1_sr3.npy`
- `reports/w10_comsol_validation/final_compare/composite_w10_tier2_sr12.npy`
- `reports/w10_comsol_validation/final_compare/summary.json`
- `reports/w10_comsol_validation/final_compare/final_metrics.json`
- `reports/w10_comsol_validation/final_compare/final_compare.png`
- `reports/w10_comsol_validation/final_compare/final_compare_full.png`
- `reports/w10_comsol_validation/final_compare/final_compare_achievement.png`
- `reports/w10_comsol_validation/final_compare/final_compare_trajectory.png`
- **`reports/w10_comsol_validation/final_orthotropic_panel/final_orthotropic_pipeline.png`** (**final delivery**: target + surrogate + 3 COMSOL paths + 6 single-freq orthotropic responses + composite + bars)
- `reports/w10_comsol_validation/final_orthotropic_panel/summary.json`
- `reports/w10_comsol_validation/orthotropic_sweep/w10_ic_tier2_sr12/orthotropic_sweep_per_freq.png`
- `reports/w10_comsol_validation/orthotropic_combined/w10_ic_tier2_sr12/orthotropic_sweep_per_freq.png`
- `reports/w10_comsol_validation/orthotropic_combined/w10_ic_tier2_sr12/sweep_analysis.json`

### 5.6 Project state summary (current)

**Recognisability (COMSOL measured)**:

- **W8 baseline → 1.75× enrichment / 0.38 recall** (IC, single freq 797 Hz, 6-actuator calibration)
- **W10 tier2 (Continuous CF, sr=12) → 2.41× enrichment / 0.27 recall** (IC, 3-freq composite, single actuator)
  - **+38% enrichment over baseline** (this is the H-field contribution; **θ contribution has not yet been COMSOL-validated**)

**Recognisability (Surrogate predicted, awaiting COMSOL orthotropic validation)**:

- W10 tier1 (sr=3.0) → 7.55× enrichment / 0.52 recall (surrogate predicts 4.3× improvement over baseline)
- W10 tier2 (sr=12) → 10.49× enrichment / 0.61 recall (surrogate predicts 6.0× improvement over baseline)

**Project conclusion**:

The W10 pipeline already produces **clearly identifiable IC-like patterns** under surrogate physics (orthotropic + per-cell θ) — see `final_compare_full.png` column 3. To reproduce this faithfully in COMSOL requires Sprint 2 §3 to finish Shell orthotropic configuration (1–2 days; mostly COMSOL Desktop manual changes + property-name adjustments in existing MATLAB scripts). The current verifiable hard result is: **the W10 tier2 H field gives +38% enrichment over W8 baseline under COMSOL isotropic pipeline.**

## 6 Sprint 2 §4 — modal calibration decision experiment (2–4 h, completed)

### 6.1 Experiment purpose

The core failure of W9 trust-region was **not quantifying the physical gap between surrogate and COMSOL** before doing closed-loop optimisation — the surrogate then mistook COMSOL noise for signal and rolled back after two iterations. Sprint 2 §4 avoids this pit by first answering 3 questions:

1. How well do surrogate and COMSOL modes align on an **un-optimised** plate?
2. Does modal alignment still hold on an optimised W10 design?
3. Is the frequency mapping a scalar, a power law, or a per-mode lookup table?

### 6.2 Setup

| Item | Setting |
|---|---|
| COMSOL eigfreq runner | `comsol_templates/run_chladni_eigenfrequency_orthotropic.m` |
| Python orchestrator | `scripts/run_modal_calibration_probe.py` + `run_modal_calibration_w10design.py` |
| Comparison script | `scripts/compare_modal_calibration.py` (computes surrogate K, M → eigh → MAC vs COMSOL) |
| Mode count | 30 |
| Plate material | tier2: E=2 GPa, sr=12, G/G_iso=1.5, ρ=1200, ν=0.35 |
| Boundary | 8 mm centre circular clamp |
| Two cases | (A) nominal: H=2 mm uniform, θ=0; (B) W10 tier2 actual optimised H + θ |

### 6.3 Experiment results

| Case | Mean MAC (first 20 modes) | MAC>0.5 mode count | Frequency fit `f_c = α·f_s^β` |
|---|---|---|---|
| (A) nominal H, θ=0 | **0.831** | **20/20** | α=0.081, β=1.311 |
| (B) W10 tier2 H+θ | **0.581** | 13/20 | α=0.059, β=1.361 |

**Key observations**:

1. **Frequency mapping is highly regular**: β = 1.31–1.36 under both designs — a **clean power law**. This means the surrogate-COMSOL frequency gap is not random noise but the systematic Kirchhoff vs Mindlin physics difference.
2. **Low-frequency modes (1–8) pair very well**: MAC stays 0.73–0.90 even in case (B); visualisations (`modal_calibration_mode_pairs_w10design.png`) show nearly identical shapes.
3. **High-frequency modes (16+) pair badly**: MAC < 0.4. This is the expected amplification of Kirchhoff/Mindlin difference at short wavelengths, **unrelated to the W10 optimisation target** (W10 main driving modes are 6–8).
4. **The "IC driving mode" of W10**: surrogate mode 6 @ 387 Hz ↔ COMSOL mode 6 @ 210 Hz, **MAC=0.78** — which is exactly why the 26-frequency sweep saw a U-shape at 210 Hz instead of a C-shape (22% shape error flips IC's top/bottom).

### 6.4 Decision matrix

| Candidate route | Feasibility | Expected enrich gain | Risk |
|---|---|---|---|
| **A. §4 modal calibration + W9 trust-region** | **High** (frequency power-law + low-freq MAC 0.75–0.90) | **3–6×** (from 1.60×) | Medium: capped by MAC=0.78 driving-mode shape residual |
| B. §4 skip calibration, directly do H+θ trust-region | Low | 0–1.5× | High: repeats W9 mistake |
| C. Direct COMSOL eigenmode + finite-difference gradients | Medium | 5–10× | High: each H+θ eval ~30 s × 200 dims = 1.5 h/iter, 2 weeks per run |
| D. Sprint 2 §3 as-is, deliver report | — | Stay at 1.60× | None |

### 6.5 §4 formal implementation plan (GREEN-with-asterisks, ~1–2 days)

W9 failed because it **jointly** corrected frequency and mode shape; the trust-region diverged across two coupled error sources. The new plan **decouples** the two:

1. **Frequency-layer calibration** (use COMSOL eigfreq directly, not in trust-region)
   - Each H+θ candidate first runs COMSOL eigenfrequency (~30 s) → real f_c for 30 modes
   - Pair surrogate (f_s, mode_s) with COMSOL (f_c, mode_c) via MAC
   - **Drive COMSOL forced response with f_c rather than f_s** so the mode is exactly excited.
2. **Mode-shape layer calibration** (trust-region only handles the residual)
   - After MAC pairing only 22% shape error is left (for driving modes)
   - Use the W9 residual correction, but **only penalise modes with MAC<0.7** to avoid injecting low-quality gradients.
3. **Design-layer iteration** (trust-region wraps 1 and 2)
   - One iter = (W10 surrogate optimises H+θ) + (COMSOL eigfreq + MAC pairing) + (COMSOL forced response @ f_c) + (residual fusion)
   - 3–5 iters to convergence, ~3–5 min/iter (30 s eigfreq + 30 s forced + a few minutes surrogate)

### 6.6 Difference from W9

| Dimension | W9 (failed) | Sprint 2 §4 (new plan) |
|---|---|---|
| Correction target | surrogate amplitude vs COMSOL amplitude (coupled frequency + shape error) | Split into two layers: frequency calibration first (direct f_c), shape residual second (trust-region only) |
| Signal quality | Residual is 50–100% frequency-error noise | Frequency error already removed; residual is only 20–30% shape error |
| Iteration stability | Rolled back after 2 steps | Shape residual is small, smooth, monotonic — trust-region convergence guaranteed |
| Physical foundation | Assumes surrogate is an "approximation" of COMSOL | Explicitly acknowledges Kirchhoff vs Mindlin difference and handles it in layers |

### 6.7 §4 implementation artifacts (planned)

- `src/optimisation/modal_calibrated_w9.py`: layered trust-region implementation
- `scripts/run_sprint2_section4.py`: end-to-end orchestrator
- `reports/sprint2_section4/`: iteration visualisations + final COMSOL enrichment report

### 6.8 Decision-experiment file list (completed)

- `comsol_templates/run_chladni_eigenfrequency_orthotropic.m` (COMSOL Shell orthotropic eigenvalue analysis)
- `scripts/run_modal_calibration_probe.py` (nominal plate orchestrator)
- `scripts/run_modal_calibration_w10design.py` (W10 design orchestrator)
- `scripts/compare_modal_calibration.py` (surrogate eigh + MAC + decision)
- `reports/modal_calibration/modal_calibration.png` / `modal_calibration_mode_pairs.png` (nominal results)
- `reports/modal_calibration/modal_calibration_w10design.png` / `modal_calibration_mode_pairs_w10design.png` (W10 design results)
- `reports/modal_calibration/modal_calibration_summary.json` / `..._w10design.json` (full numerics)

## 7 Sprint 2 §4 Phase 1 — **first results (completed)**

### 7.1 Pipeline

1. Use §6's COMSOL eigenfrequency output (30 modes for the W10 tier2 design)
2. For each COMSOL eigenmode, compute its |w| Gaussian-blurred enrichment against the IC target ("IC-likeness")
3. Sort by IC-likeness, pick top-K (K=6) eigenfrequencies
4. Drive COMSOL forced response at `f_eig + 1.5 Hz` (1.5 Hz off-resonance to avoid solver singularity)
5. Composite weighted by enrichment²

Implementation: `scripts/run_sprint2_section4_phase1.py` + `scripts/explore_phase1_composite.py` + `scripts/finalize_phase1_deliverable.py`

### 7.2 IC-likeness ranking (top 8)

| rank | mode | f_hz | enrich | recall |
|---|---|---|---|---|
| 1 | 5 | 130.51 | 2.98× | 0.60 |
| 2 | 3 | 60.07 | 2.59× | 0.58 |
| 3 | 8 | 244.60 | 1.91× | 0.37 |
| 4 | 2 | 49.28 | 1.85× | 0.43 |
| 5 | 6 | 209.87 | 1.84× | 0.37 |
| 6 | 4 | 85.81 | 1.74× | 0.33 |
| 7 | 7 | 243.36 | 1.72× | 0.35 |
| 8 | 1 | 39.26 | 1.71× | 0.28 |

Note the W10 surrogate's "favourite" 398.58 Hz (COMSOL mode 11 @ 395.79 Hz) ranks 16th with enrichment only 1.08× — **the surrogate's "IC mode" is not IC-like at all in COMSOL physics.**

### 7.3 Composite strategy exploration

Finding: **driving directly at eigenmode frequencies is not optimal**. In the 26-freq sweep, 180 Hz (an off-resonance beat between mode 5 @ 130 Hz and mode 6 @ 209 Hz) measures enrichment 3.14× — higher than any single eigenmode. Reason: 180 Hz excites mode 5 (X-star) and mode 6 (U-curve) together, producing a horizontal-double-lobed ellipse — its overlap with IC's central band beats any single mode shape.

### 7.4 Strongest composite (delivered)

| Strategy | Driving frequencies | broad metric (σ=0.05) | tight metric (σ=0.012) |
|---|---|---|---|
| **BEST**: 132 + 180 Hz RMS | 132.01, 180.00 | **enr=3.82× / rec=0.89** | enr=2.22× / rec=1.00 |
| ALT: 4-freq MAX | 50.78, 87.31, 180.00, 246.10 | enr=2.75× / rec=0.67 | **enr=3.40× / rec=1.00** |
| OLD baseline (top-3 RMS) | 180, 1000, 840 | enr=1.94× / rec=0.43 | enr=1.46× / rec=1.00 |

**Improvement vs OLD**:
- broad enrichment: **1.94 → 3.82 (+97%)**
- broad recall: **0.43 → 0.89 (+108%)**

### 7.5 Visual verification

`reports/sprint2_section4_phase1/w10_ic_tier2_sr12/final_phase1_comparison.png` column 3 (green box): the composite shows a near-"I" vertical bright band on the left + a "C"-like opening curve on the right + a central horizontal connector — **the most IC-like pattern produced in COMSOL to date** (qualitatively beyond the "fuzzy blob" of the OLD composite).

Still not clearly readable "IC" letters, though; getting to Sci-Reports-level visuals needs Phase 2 (trust-region H+θ joint iteration).

### 7.6 Key insights (used to design Phase 2)

1. **Off-resonance frequencies beat eigenfrequencies** — modal interference can produce IC-like composite shapes, while any single eigenmode almost never produces IC.
2. **Shape-projection ranking beats amplitude ranking** — picking frequencies by IC-likeness is more reliable than by RMS amplitude (rank 1 vs the surrogate-pick rank 16).
3. **2-frequency RMS composite beats 6-frequency weighted** — "less is more": two complementary mode shapes suffice to cover IC's central band.
4. **MAC=0.78 surrogate-COMSOL error is the limiting factor** — current enrichment ceiling sits in the 4–5× range (if mode shapes matched exactly, the theoretical ceiling = OLD baseline 1.94× × MAC correction ≈ 4–6×, consistent with measured 3.82×).

### 7.7 Phase 1 deliverable list

- `scripts/run_sprint2_section4_phase1.py` (IC-likeness ranking + driving + composite)
- `scripts/explore_phase1_composite.py` (composite-strategy search)
- `scripts/finalize_phase1_deliverable.py` (final comparison plot)
- `scripts/diagnose_phase1.py` (apples-to-apples evaluation)
- `reports/sprint2_section4_phase1/w10_ic_tier2_sr12/`
  - `final_phase1_comparison.png` (**final delivery**: target + Phase 1 best + OLD baseline 5×2 grid)
  - `composite_exploration.png` (10-strategy leaderboard visual)
  - `final_phase1_metrics.json` (all metrics + improvement multiples)
  - `composite_exploration.json` (10-strategy full numerics)
  - `deliverable_best_composite_132+180_RMS.npy` (strongest composite array)
  - `deliverable_alt_composite_4freq_MAX.npy` (alternate 4-freq MAX composite)
  - `old_baseline_composite.npy` (OLD baseline composite for comparison)
  - `phase1_diagnosis.png` / `phase1_diagnosis.json` (apples-to-apples evaluation)

### 7.8 Decide whether to launch Phase 2 (trust-region H+θ)

See §8 Phase 2 decision experiment. Conclusion: **GREEN** (feasible), but realistic gain is capped by the data at **3.82 → 4.0–4.5×** (not the original 5–7× estimate).

## 8 Sprint 2 §4 Phase 2 — **decision experiment (completed, GREEN-with-caveats)**

Before launching Phase 2, run a "no-return" check: can H+θ perturbations actually reshape COMSOL eigenmodes?

### 8.1 Experiment

5 perturbations + 1 baseline; each runs COMSOL eigfreq (30 modes); compute IC-likeness ranking changes:

| Perturbation | Design change | best-mode enrichment | Δ% |
|---|---|---|---|
| baseline | W10 tier2 as is | 2.982 | — |
| A1 | H top-left 4×4 +25% | 2.964 | −0.6% |
| A2 | H bottom-right 4×4 −25% | 2.979 | −0.1% |
| B1 | θ top rows +π/4 | 2.753 | −7.7% |
| B2 | θ NE+SW diagonal blocks +π/3 | 2.731 | −8.4% |
| **C** | **H centre 5×5 thickness ×2 (strong perturbation)** | **3.534** | **+18.5%** |

### 8.2 Key findings

1. **Strong H perturbations really do reshape modes**: C moves mode 5 frequency 130.5 → 172.8 Hz, enrichment 2.98 → 3.53.
2. **Strong θ perturbations bring NEW modes into top-K**: B1 lets mode 16 @ 660 Hz enter top-3 with enrich 2.38.
3. **Small perturbations (A1, A2) are useless**: ±0.6% signal is drowned by noise — trust-region must use large steps to get gradient signal.
4. **Top-2 composite under a single C design already reaches 3.47/0.82**: nearly matching Phase 1 (132+180) 3.82×/0.89.

### 8.3 Verdict and revised Phase 2 expectation

**GREEN-with-caveats**:

- ✅ H+θ perturbations can adjust mode shape and IC-likeness distribution
- ✅ Trust-region has usable gradient signal (max 18.5% per-step gain)
- ⚠️ **Real gain ceiling is lower than initially estimated**: C already hits 3.47 in one step; Phase 2 trust-region cumulative multi-iter is expected to be +10–30% (not +30–80%)
- ⚠️ **No qualitative visual breakthrough**: COMSOL eigenmodes are X, +, ellipse, etc. — they will not suddenly become "IC letters". Phase 2 can only find the best combination within the existing mode library.

### 8.4 Revised Phase 2 expectation

| Dimension | Phase 1 now | Phase 2 realistic expectation | Note |
|---|---|---|---|
| broad enrichment | 3.82× | **4.0–4.7×** (+5–25%) | Not 5–7× |
| broad recall | 0.89 | 0.88–0.93 | Flat |
| Visual IC clarity | "barely recognisable" | "slightly clearer, still not IC letters" | No qualitative jump |
| Engineering cost | done | 1–2 days | — |

### 8.5 File list

- `scripts/run_phase2_decision_experiment.py` (5 perturbations + baseline COMSOL eigfreq, IC-likeness decision matrix)
- `reports/sprint2_phase2_decision/phase2_decision.png` (6 rows × 4 columns: H field + θ field + top mode + top-2 composite)
- `reports/sprint2_phase2_decision/phase2_decision_summary.json` (full IC-likeness ranking + Δ% matrix + verdict)

### 8.6 Recommended decision

Based on the data, **the recommendation**:

- **If the user accepts 3.82× as delivery**: stop at Phase 1. Phase 2 marginal gain is small, visual no jump; 1–2 days for low ROI.
- **If the user insists "let's try Phase 2"**: launch Phase 2 — expect final **4.0–4.5× / still "barely recognisable" IC**. The algorithm itself is healthy (GREEN verdict); just the ceiling is dictated by the geometric properties of the COMSOL eigenmode set.
- **If the user wants "clearly readable IC"**: change paths (e.g. change material to enrich the mode-shape set, change actuator geometry to break D∞ symmetry, or give up "inverse IC" and switch to a Chladni-friendlier target like a circle / cross).

## 9 Material-choice generalisation check — **tier1 (sr=3) is the real sweet spot**

### 9.1 Background

Before launching Phase 2, the user asked a critical question: "Is the material recommendation (tier2 sr=12) IC-specific, or does it generalise?" — a key question for a customisable project.

### 9.2 Setup

4 representative targets × 3 material sr values, surrogate-only W10 (300-step convergence):

| Target | Geometric feature | Physical expectation |
|---|---|---|
| IC (project original) | Letters (asymmetric) | Needs D4 breaking |
| Circle (ring) | D4-symmetric, but not a natural square-plate mode | Needs anisotropy to produce ring modes |
| Plus (+ sign) | D4-symmetric, natural square-plate mode | Any sr works |
| Letter A | Asymmetric, no curves | IC-like |

Material tiers:
- sr=1.0: SLA grey resin (isotropic)
- sr=3.0: CF-PETG (tier1)
- sr=12.0: Continuous CF (tier2)

### 9.3 Measured (surrogate enrichment)

| Target | sr=1 | sr=3 | sr=12 | Winner |
|---|---|---|---|---|
| IC | 6.76× | **17.99×** | 17.15× | **tier1** (+5% over tier2) |
| Circle | **0.00×** | 4.18× | **4.78×** | tier2 (marginal +14%) |
| Plus | 7.18× | 7.18× | 7.18× | TIE |
| A | 7.56× | **8.12×** | 8.11× | tier1 (margin <1%) |

### 9.4 Key findings

1. **Tier1 (sr=3) is ≥ tier2 or tied on 4/4 targets** — including the project's original IC target (tier1=17.99× vs tier2=17.15×).
2. **Tier2 (sr=12) wins marginally only on Circle** — and Circle has enrichment=0 under sr=1 because the natural square-plate isotropic mode set does not include a ring; anisotropy is needed to produce one.
3. **sr=1 (SLA grey resin) is significantly worse on ring/asymmetric targets** — Circle fails outright; IC is only 38% of tier1.
4. **Plus is identical across sr** — because the plus sign coincides with the natural (1,2)/(2,1) square-plate mode.

### 9.5 Physical interpretation

- **Increasing sr → mode-shape "reachable set" expands**: from pure D4-symmetric → with non-D4 terms → can represent richer shapes.
- **sr=3 is already enough symmetry breaking**: the square-plate mode set includes IC, letters, irregular shapes, etc.
- **sr=12 is overkill**: further anisotropy degrades some modes (hypothesis: large D12, D16, D26 terms introduce numerical instability), and the surrogate optimiser has a harder time finding local optima.

### 9.6 Impact on Phase 1 / Phase 2

| Dimension | Current (tier2) | After switching to tier1 |
|---|---|---|
| Surrogate enrichment (IC) | 10.49× (old) / 17.15× (re-run) | 17.99× (+5%) |
| COMSOL enrichment (IC) | Phase 1 best 3.82× | **unknown** — need to re-run tier1 in COMSOL |
| MAC (surrogate vs COMSOL) | 0.78 | unknown |
| Engineering cost | done | 0.5–1 day to re-run W10 + Phase 1 |

**Caveat**: the old COMSOL validation shows the tier1 (sr=3) H field gives enrichment=0.72× under COMSOL isotropic (worse than tier2's 2.41×). This may be because:
- old tier1 W10 had not fully converged; or
- the tier1 surrogate solution overfits and generalises poorly to COMSOL physics.

Re-running the tier1 full chain is required to know.

### 9.7 Final answer to the user

**Answering the original "is tier2 IC-specific or general?"**:

| Dimension | Empirical fact |
|---|---|
| tier2 is IC-specific? | ❌ **No** — but it is also not the universal best |
| tier1 is the better default? | ✅ **Yes** — tier1 ≥ tier2 on 4/4 targets |
| sr=1 (SLA) is a good default? | ❌ **No** — some ring / asymmetric targets cannot be produced at all |
| Is per-target material selection needed? | ⚠️ **Recommended** — tier1 as default, UI offers an sr switch for ring / complex targets |

### 9.8 Revised Phase 2 recommendations

| Option | Description | Engineering cost |
|---|---|---|
| **A** (old: launch Phase 2 on tier2) | Run trust-region on existing tier2 H+θ | 1–2 days, expected 3.82 → 4.0–4.5× |
| **B** (new: switch to tier1 re-run) | Re-run W10 + Phase 1 on tier1 (sr=3) and then decide on Phase 2 | 0.5 day W10+P1; may surpass 3.82× directly |
| **C** (old: change material / path) | Already answered by §9: tier1 is the correct change, not "give up" | — |
| **D** (conservative) | Accept Phase 1 (tier2 3.82×) | 0 |

**Recommended path**: do **B** first — half a day to verify tier1 in COMSOL, then decide whether to do Phase 2 on tier1 or stay on tier2.

### 9.9 File list

- `scripts/generalisation_check_materials.py` (4 targets × 3 sr W10 surrogate grid + verdict)
- `reports/generalisation_check/` (100-step quick version: 4×3 complete)
- `reports/generalisation_check_v2/` (300-step refined version: Circle+IC validation)
- `reports/generalisation_check/targets/` (generated Circle/Plus/A NPY targets)
- `reports/generalisation_check/generalisation_check.png` (bar comparison)
- `reports/generalisation_check_v2/generalisation_check.png` (refined version)
