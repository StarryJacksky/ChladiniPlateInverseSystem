# Scripts Index / 脚本索引

All scripts are kept in the same directory to avoid breaking import paths. The categorisation below identifies what belongs to the **production pipeline** vs. **experimental/historical** code from the W1-W10 exploration phase.

为不破坏 import 路径，所有脚本仍在同一目录。下方按"生产 / 实验"分类，标记哪些属于最终生产流水线，哪些属于 W1-W10 探索阶段的实验脚本。

---

## 1. PRODUCTION PIPELINE / 生产流水线 (★ 推荐使用)

These are the scripts called (directly or transitively) by `run_production_pipeline.py` — the customer-facing one-click pipeline.

| Script | Role |
|---|---|
| **`run_production_pipeline.py`** | **★ Main entry. End-to-end inverse design (W10 → COMSOL eigfreq → Phase 1 → Phase 2).** |
| `run_w10_anisotropy.py` | W10 surrogate optimisation (joint H + θ with orthotropic plate). |
| `run_modal_calibration_w10design.py` | COMSOL eigenfrequency analysis for a W10 design. |
| `run_sprint2_section4_phase1.py` | Phase 1: IC-likeness mode ranking + forced response setup. |
| `run_sprint2_section4_phase2.py` | Phase 2 trust-region orchestrator (stand-alone). |
| `run_w10_comsol_validation.py` | COMSOL forced response runner used by Phase 1/2. |
| `explore_phase1_composite.py` | Composite (RMS/MAX/SUM) subset search over forced-response CSVs. |
| `finalize_phase1_deliverable.py` | Combine Phase 1 + magic frequencies into final composite. |
| `finalize_tier1_phase1.py` | Tier1 (sr=3) specialised finaliser. |
| `plot_phase2_finalize.py` | Render Phase 2 final summary panel. |
| `plot_phase2_iter_compare.py` | Compare Phase 2 iterations side-by-side. |
| `plot_tier1_finalize.py` | Render tier1 Phase 1 final panel + tier1 vs tier2. |
| `render_phase2_comsol_native.py` | High-fidelity COMSOL-native triangulation rendering. |

## 2. UI / SUPPORT / 启动与支撑

| Script | Role |
|---|---|
| `launch_chladni_studio.py` / `.sh` / `.command` / `.bat` | Launchers for the local UI server (`src/frontend/target_ui_server.py`). |
| `create_ic_target.py` | Generate the IC target binary (for demo runs). |
| `check_config_contract.py` / `check_design_contract.py` | Config / design schema sanity checks. |
| `check_docs_links.py` / `check_bilingual_comments.py` | Repo hygiene checks. |
| `check_local_quality.py` | Combined lint + smoke runner. |
| `check_artifact_cleanup.py` | UI artifact-retention test. |
| `check_discovery_fixtures.py` | COMSOL path-discovery test. |
| `check_python_smoke.py` | Python-side smoke test. |

## 3. EXPERIMENTAL — W1 → W9 (historical) / 实验脚本（W1-W9 已被 W10+Phase 2 取代）

Kept for full reproducibility of the 350+ trial history documented in `reports/algorithm_trial_full_history.zh-CN.md`. **Not part of the production path.**

| Script | Era |
|---|---|
| `run_w3_optimization.py`, `check_w3_smoke.py` | W3 — earliest grad-free smoke. |
| `run_w4_optimization.py`, `check_w4_smoke.py`, `build_design_manifold.py` | W4 — PCA manifold warm-starts. |
| `run_w5_homotopy.py`, `check_w5_smoke.py` | W5 — homotopy continuation. |
| `run_w6_spectral.py`, `check_w6_smoke.py`, `analyze_target_irrep.py`, `analyze_target_realizability.py` | W6 — irrep / realisability. |
| `run_w7_multifreq.py`, `check_w7_smoke.py` | W7 — multi-frequency. |
| `run_w8_recognisability.py`, `check_w8_smoke.py`, `analyze_w8_validation.py`, `rank_candidates_recognisable.py` | W8 — recognisability scoring. |
| `run_w9_trust_region.py`, `visualize_w9_run.py` | W9 — earliest trust-region (superseded by Phase 2). |
| `analyze_sprint1_validation.py`, `visualize_sprint1_status.py`, `visualize_w10_final.py` | Sprint 1 visualisation helpers. |
| `make_final_orthotropic_panel.py`, `compare_w10_tiers.py`, `compare_modal_calibration.py` | W10 comparison utilities. |
| `generalisation_check_materials.py` | Tier-1 vs Tier-2 generalisation study (drove tier1 election). |

## 4. EXPERIMENTAL — mosaic / topology / 各种 mosaic 与拓扑实验

| Script | Description |
|---|---|
| `run_mosaic_z_*.py` (subspace / direct_actuator / forced_response / projection) | Z-mosaic placement family. |
| `calibrate_mosaic_z_forced_response.py` | Mosaic-Z calibration. |
| `generate_mosaic_z_topology_primitives.py`, `generate_tags_candidates.py` | Candidate generators. |
| `materialize_topology_candidate.py` | Materialize abstract topology to design vars. |
| `analyze_freq_sweep.py` | Frequency-sweep analyser. |
| `rank_candidates.py` | Generic ranking. |
| `score_comsol_forced_response.py` | Standalone scoring of a single COMSOL CSV. |
| `run_comsol_frequency_sweep.py` | Raw COMSOL freq sweep. |
| `run_modal_calibration_probe.py` | Earlier modal calibration probe. |
| `run_w10_comsol_compare.py` | W10 comparison runner. |
| `diagnose_phase1.py` | Phase 1 mode-by-mode diagnostic. |
| `run_phase2_decision_experiment.py` | Phase 2 go/no-go probe. |
| `check_frequency_domain_validation_smoke.py`, `check_physical_filter_smoke.py` | Domain-specific smokes. |
| `quick_viz_smoke.py` | Quick visualisation smoke. |

## 5. COMSOL MATLAB / DEPRECATED PROBES / COMSOL MATLAB 与早期探针

| Script | Note |
|---|---|
| `parameterize_chladni_15x15.m`, `parameterize_chladni_9x9.m`, `bind_chladni_15x15_model.m`, `bind_chladni_9x9_model.m` | Original COMSOL MATLAB binding scripts. |
| `inspect_chladni_geometry_features.m`, `probe_chladni_faces.m`, `probe_chladni_fixed_edges.m` | COMSOL geometry probes. |
| `probe_comsol_model.py`, `probe_orthotropic_api.py`, `probe_orthotropic_emm1.py`, `probe_rotated_cs.py` | Early COMSOL API probes (kept for reference). |
| `sanity_check_orthotropic.py` | Orthotropic-plate sanity test. |
| `run_full_pipeline.py` | Earliest end-to-end pipeline (superseded by `run_production_pipeline.py`). |

---

## How to Run / 如何运行

```bash
# Customer / production:
.venv/bin/python scripts/run_production_pipeline.py --candidate-id my_run

# Historical reproducibility (e.g. reproduce W8):
.venv/bin/python scripts/run_w8_recognisability.py --help
```
