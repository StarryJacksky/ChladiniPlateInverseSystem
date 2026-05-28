# Reports Index / 报告索引

This directory holds **every experiment, validation run, and analysis** produced during the project (350+ iterations of inverse-design exploration). Nothing is deleted — items below are categorised so the final deliverables are easy to locate while the full experimental history remains available for audit / submission.

本目录保留项目全过程的**所有实验、验证与分析产物**（350+ 次逆向设计探索）。**没有任何删除**——下方按"最终交付 / 关键里程碑 / 实验全史"分类，便于查找最终成果，同时完整保留实验过程供审查与提交。

---

## 1. FINAL DELIVERABLES / 最终交付

The customer-facing pipeline + validated SOTA results.

| Path | Description |
|---|---|
| `sprint2_section4_phase2/` | **★ Best validated result.** Phase 2 trust-region final results: 4.85× broad enrichment / 3.94× tight enrichment on tier1 CF-PETG (sr=3). Includes COMSOL-native renderings (`comsol_native_*.png`), iteration trajectory (`phase2_final.png`, `iter1_vs_iter3_compare.png`). |
| `sprint2_section4_phase1_tier1/` | Phase 1 results on tier1 (sr=3): identifies the magic 165 Hz off-resonance frequency that drives Phase 2 success. Includes `tier1_vs_tier2_compare.png`. |
| `production/` | Output directory used by `scripts/run_production_pipeline.py` for new customer-driven runs. |
| `generalisation_check_v2/` | The material-tier analysis that elected tier1 CF-PETG as the best generalising material. |

## 2. KEY MILESTONES / 关键里程碑

| Path | Description |
|---|---|
| `algorithm_trial_full_history.zh-CN.md` | **★ Complete 350+ trial log** (W1 → W10 + Phase 1/2). |
| `algorithm_breakthrough_plan.en.md`, `algorithm_breakthrough_plan.zh-CN.md` | Strategic plan that produced W10. |
| `algorithm_logic_and_structure_explanation.md` | Architectural overview of the surrogate + Phase 1/2 pipeline. |
| `engineering_plan.md` | Original sprint planning document. |
| `remaining_work_plan.zh-CN.md` | Post-validation roadmap. |
| `sprint1_w9_sprint2_summary.zh-CN.md` | Bridge document between W9 surrogate-only era and Sprint 2 trust-region era. |
| `sprint2_phase2_decision/` | Phase 2 go/no-go analysis. |
| `sprint2_section4_phase1/` | Phase 1 on tier2 (sr=12, before tier-switch). |

## 3. EXPERIMENTAL HISTORY / 实验全史

Earlier W-series workflow outputs, COMSOL validations, manifold studies, and feasibility checks. **Retain for reproducibility and submission.**

| Path | Era | Notes |
|---|---|---|
| `w3_smoke/` | W3 | Earliest end-to-end smoke test. |
| `w8_comsol_validation.json` | W8 | Initial multifrequency placement validation. |
| `w10_comsol_validation/` | W10 | First sr=12 / sr=3 W10 surrogate→COMSOL bridging. |
| `w10_tier_comparison.json` | W10 | Tier-1 vs Tier-2 quantitative comparison. |
| `target_realizability_*.json` | W6-W8 | Per-target realisability analyses. |
| `recognisability_leaderboard_*.{csv,json}` | W7 | IC + diagonal multi-objective leaderboards. |
| `tags_physical_*.{csv,md}` | W6 | Physical-filter tagging exploration. |
| `homotopy/`, `irrep_decompositions/`, `mosaic_z*/`, `frequency_domain_validation/`, `modal_calibration/`, `pipeline/`, `figures/`, `sanity_targets/` | Various | Intermediate analyses + figures. |
| `design_manifold_pca*.{json,npz}` | W4 | PCA on design manifold for warm-starts. |
| `chladni_*boundary_mapping.csv`, `chladni_baseline_*` | W1-W2 | COMSOL boundary / baseline studies. |
| `comsol_*.{md,json}` | W2 | COMSOL audit + calibration documentation. |
| `target_aligned_passive_geometry_strategy.md` | W5 | Passive geometry approach (deprecated for active). |
| `feasibility_report.json`, `leaderboard.json`, `mosaic_z_feasibility_report.md` | Various | Standalone reports. |

---

## How to Reproduce the Final Result / 如何复现最终结果

```bash
# Surrogate-only fast preview (~30 s):
.venv/bin/python scripts/run_production_pipeline.py --candidate-id demo --skip-comsol

# Full pipeline with W10 + COMSOL eigfreq + Phase 1 + Phase 2 (~2 h on M3 with COMSOL LiveLink):
.venv/bin/python scripts/run_production_pipeline.py --candidate-id customer_run_01

# From the UI: open the "Run" tab → "Production Pipeline" panel → click "Run Production Pipeline"
```

See `../README.md` and `../docs/final_results.zh-CN.md` for full instructions and physical-limit discussion.
