# Candidates Index / 候选索引

This directory contains **932 candidate designs** generated across the entire 350+ experiment project history. Nothing has been deleted — the index below identifies the **best validated design**, key experimental milestones, and where the bulk historical search candidates live.

本目录保留**全部 932 个候选设计**（覆盖项目 350+ 次实验全过程）。**没有任何删除**——下方索引标明**最佳验证设计**、关键实验里程碑，以及大规模历史搜索候选的位置。

---

## 1. ★ FINAL DELIVERED DESIGN / 最终交付设计

| Path | Why it matters |
|---|---|
| **`phase2_iter1/`** | **★ Best validated design.** Phase 2 trust-region iteration 1 on tier1 CF-PETG (sr=3). Achieves 4.85× broad enrichment (+9.8% vs Phase 1 baseline) in COMSOL forced response. Contains `H.csv`, `theta_continuous_rad.csv`, `frequencies_hz.csv`, `weights.csv`, `w10_optimization_summary.json`. |
| `phase2_iter2/`, `phase2_iter3/` | Phase 2 follow-up iterations (rejected by trust-region — kept for trajectory audit). |
| `w10_ic_tier1_sr3_v2/` | Phase 1 baseline (iteration 0) tier1 design — input to Phase 2. 4.42× broad enrichment. |
| `w10_ic_tier2_sr12/` | Phase 1 baseline tier2 design (sr=12) — superseded by tier1 after generalisation study. 3.82× broad enrichment. |

## 2. COMSOL VALIDATION EXPORTS / COMSOL 验证导出

Per-frequency forced-response data tied to specific designs. Heavy disk usage.

| Pattern | Meaning |
|---|---|
| `p2it1_phase2_iter1_comsol_f*Hz/` | **★ Phase 2 final design × 7-9 driving freqs (final composite source).** |
| `p2it0_w10_ic_tier1_sr3_v2_comsol_f*Hz/` | Phase 2 baseline × selected freqs. |
| `p2it2_*`, `p2it3_*` | Phase 2 iter 2 / 3 forced-response variants. |
| `s4p1t1_w10_ic_tier1_sr3_v2_comsol_f*Hz/` | Sprint 2 §4 Phase 1 tier1 forced response. |
| `s4p1_w10_ic_tier2_sr12_comsol_f*Hz/` | Sprint 2 §4 Phase 1 tier2 forced response. |
| `offres_tier1_w10_ic_tier1_sr3_v2_comsol_f*Hz/` | Off-resonance sweep on tier1 (discovered the magic 165 Hz). |
| `w10_ic_tier2_sr12_comsol_f*Hz/` | Initial tier2 frequency sweep. |

## 3. SPRINT 2 PHASE 2 DECISION EXPERIMENT / Phase 2 决策实验

The 5 perturbation probes that proved Phase 2 was a viable direction (not a dead-end).

| Path | Perturbation |
|---|---|
| `phase2_decision_baseline/` | Baseline (no perturbation). |
| `phase2_decision_A1_Hul_p25/` | H upper-left thickness +25%. |
| `phase2_decision_A2_Hlr_m25/` | H lower-right thickness −25%. |
| `phase2_decision_B1_th_upper_p45/` | θ upper-half rotated +45°. |
| `phase2_decision_B2_th_NESW_p60/` | θ NESW diagonal +60°. |
| `phase2_decision_C_Hcenter_x2/` | Central thickness doubled. |

## 4. MODAL CALIBRATION / 模态校准

| Path | Purpose |
|---|---|
| `modal_calibration_nominal_orthotropic/` | Nominal-design orthotropic eigenfrequency reference. |
| `modal_calibration_w10_tier1/` | W10 tier1 modal calibration. |
| `modal_calibration_w10_tier2/` | W10 tier2 modal calibration. |
| `phase2_eig_phase2_iter*/` | Phase 2 per-iteration eigenfrequency dumps (used by IC-likeness selector). |
| `phase2_eig_w10_ic_tier1_sr3_v2/` | Phase 2 baseline eigfreq. |

## 5. FINAL COMPARISON BUNDLES / 最终对比包

| Path | Contents |
|---|---|
| `final_compare_baseline_w8_f*Hz/` | W8 baseline forced response for comparison panels. |
| `final_compare_w10_tier1_sr3_f*Hz/` | W10 tier1 comparison data. |
| `final_compare_w10_tier2_sr12_f*Hz/` | W10 tier2 comparison data. |

## 6. HISTORICAL SEARCH / 历史搜索 (610 random/GA/Bayesian candidates)

**610** entries matching `candidate_NNN_NNNN/` — the GA + Bayesian + KL search candidates produced during W3 → W8. Each is a self-contained design (H.csv + parameters + metadata). Use `ranked_candidates_unified.csv` to navigate.

| Path | Purpose |
|---|---|
| `candidate_000_*` through `candidate_307_*` | Generation 0-307 random / GA candidates. |
| `ranked_candidates.csv`, `ranked_candidates_unified.csv` | Leaderboard CSVs across all generations. |

## 7. MOSAIC-Z EXPERIMENTS / mosaic-Z 系列 (19 entries)

Z-mosaic placement candidates from the W7 mosaic-Z exploration.

| Pattern | Description |
|---|---|
| `mosaic_z_candidate_151_calibrated_six_f*` | Calibrated 6-actuator at various freqs. |
| `mosaic_z_candidate_151_direct_*` | Direct-actuator variants (eight_safe, six, six_sigma5, six_sigma8). |
| `mosaic_z_candidate_151_fixed810_six_v1` | Fixed-frequency 810 Hz variant. |

## 8. UI / SMOKE TEST ARTIFACTS / UI 与冒烟测试产物

| Path | Description |
|---|---|
| `production_design/` | Most recent production-pipeline run from UI/CLI. |
| `smoke_pipeline_test/` | Pipeline smoke test (surrogate-only, low-step). |

---

## How to Use the Final Design / 使用最终设计

```bash
# Inspect the best validated design (Phase 2 iter 1):
ls candidates/phase2_iter1/
cat candidates/phase2_iter1/w10_optimization_summary.json

# H thickness map + θ orientation field are in:
#   candidates/phase2_iter1/H.csv          (15×15 mm)
#   candidates/phase2_iter1/theta_continuous_rad.csv  (15×15 rad)
#   candidates/phase2_iter1/frequencies_hz.csv  (6 frequencies)
#   candidates/phase2_iter1/weights.csv     (6 amplitude weights)
```

See `../README.md` and `../docs/final_results.zh-CN.md` for context.
