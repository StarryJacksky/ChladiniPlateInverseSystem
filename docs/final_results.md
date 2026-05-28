# Final Project Report / 项目最终成果报告

[Language / 语言](./final_results.md): Bilingual | [中文](./final_results.zh-CN.md) | [English](./final_results.en.md)

This is the canonical bilingual landing page for the final inverse-design results. Each section pairs the English text with its Chinese counterpart.
这是最终逆向设计成果的双语入口页。每一节中英对照。

> 350+ experiments → W10 + Phase 1 + Phase 2 pipeline → **4.85× broad enrichment / 3.94× tight enrichment** on tier1 CF-PETG (sr≈3), validated by COMSOL forced response.
> 350+ 次实验 → W10 + Phase 1 + Phase 2 流水线 → tier1 CF-PETG (sr≈3) 上达成 **4.85× 宽富集 / 3.94× 紧富集**（COMSOL 强迫响应验证）。

---

## 1. One-line conclusion / 一句话结论

Under the intrinsic physical constraints of a 15×15 grid and a single-centre actuator, this algorithm pushes the IC pattern's broad enrichment to **4.85×** (COMSOL-validated). That is close to the practical upper bound for asymmetric targets on a square-plate Chladni system; the remaining "doesn't quite look like IC" is a physical limitation, not an algorithmic failure.

在 15×15 网格、单中心激励的固有物理约束下，本算法把 IC 字母的 broad enrichment 推到 **4.85×**（COMSOL 验证），这接近了非对称目标在四方板 Chladni 物理体系下的实用上限；剩余的"看上去还不够像 IC"是物理本身的限制，而非算法的失败。

## 2. Final algorithm state / 算法最终状态

```
┌─────────────┐    ┌──────────────┐    ┌────────────────┐    ┌────────────────────┐    ┌──────────┐
│ User target │ → │ W10 surrogate │ → │ COMSOL eigfreq │ → │ Phase 1            │ → │ Phase 2  │
│ 用户目标    │    │ (joint H + θ │    │ (30 modes,     │    │ IC-likeness top-K +│    │ 信任域   │
│ (256×256    │    │  orthotropic)│    │  orthotropic   │    │ magic 165 Hz +     │    │ 1 iter   │
│  binary)    │    │ ≈ 300 steps  │    │  shell)        │    │ exhaustive subset  │    │ (可关)   │
└─────────────┘    └──────────────┘    └────────────────┘    └────────────────────┘    └──────────┘
```

See the language-specific report for the full breakdown of W10 / Phase 1 / Phase 2 / composite-search internals, the physical-boundary table, parameter tuning, and the artifact index.

完整的 W10 / Phase 1 / Phase 2 / 复合搜索内部细节、物理边界表、参数调节与产物索引请见对应语言版本。

- English deep dive: [final_results.en.md](./final_results.en.md)
- 中文完整报告: [final_results.zh-CN.md](./final_results.zh-CN.md)

## 3. Customer entry points / 客户使用入口

### UI path / UI 路径

```bash
.venv/bin/python -m src.frontend.target_ui_server
# Open http://127.0.0.1:8765 → "Run" tab → pick preset → click Run.
# 浏览器打开 http://127.0.0.1:8765 → "Run" 标签页 → 选预设 → 点 Run。
```

### CLI path / CLI 路径

```bash
.venv/bin/python scripts/run_production_pipeline.py --candidate-id my_customer_run
# --skip-comsol  : surrogate-only ~30 s preview / 仅 surrogate ~30 秒预览
# --skip-phase2  : saves ~30 minutes / 跳过 Phase 2，省约 30 分钟
```

## 4. Key artifact index / 关键产物索引

| Type / 类型 | Path / 路径 |
|---|---|
| Final H+θ design / 最终 H+θ 设计 | `candidates/phase2_iter1/` |
| Phase 2 visualisations / Phase 2 视觉化 | `reports/sprint2_section4_phase2/comsol_native_*.png` |
| Phase 1 visualisations / Phase 1 视觉化 | `reports/sprint2_section4_phase1_tier1/w10_ic_tier1_sr3_v2/tier1_vs_tier2_compare.png` |
| Trial full history / 试错全史 | `reports/algorithm_trial_full_history.en.md` / `.zh-CN.md` |
| Algorithm structure / 算法结构 | `reports/algorithm_logic_and_structure_explanation.md` |
| Reports index / 报告索引 | `reports/INDEX.md` |
| Candidates index / 候选索引 | `candidates/INDEX.md` |
| Scripts index / 脚本索引 | `scripts/INDEX.md` |

---

*This report reflects the algorithm state as of 2026-05-28. All experiments, candidates, and COMSOL data are preserved in place for audit.*
*本报告基于 2026-05-28 的算法状态。所有实验、候选、COMSOL 数据均原地保留供审查。*
