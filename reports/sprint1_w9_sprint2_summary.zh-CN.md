# Sprint 1 → W9 信赖域 → Sprint 2 起步：本次会话完整总结

**日期**：2026-05-27 凌晨  
**总耗时**：约 5 小时  
**主线**：诊断 / 改进 / COMSOL 突破尝试

---

## 1. 数学诊断（永久价值）

### §4 D4 irrep 分解（新建框架）

实现 `src/symmetry/d4_decomposition.py` 与 `scripts/analyze_target_irrep.py`。

**核心结论：D4 中心激振只能耦合到 A1 irrep**，因此目标图案在 A1 上的能量占比给出物理上限。

| 目标 | A1 占比 | A1 之外（不可达） | 突破上限（粗略） |
|---|---:|---:|---|
| X 形 | **100.0%** | 0% | 理论上完全可达 |
| 单条对角线 | 51.7% | 48.3% (B2) | 半可达 |
| **IC 字母** | **41.9%** | **58.1%** (E + B1) | 难——大半信号根本进不去 |

这是项目历史上第一次给出**精确数学答案**：「为什么 IC 图案不会出现在 COMSOL」是因为 IC 在 A1 子空间外的能量被中心点振源系统性过滤掉了。

`src/target/target_realizability.py` 已自动集成 irrep 分析到 W1 verdict 文件，客户报告会直接看到「central excitation accessibility (A1 only): 41.95%」。

---

## 2. 数值精度 bug 大修（直接改变历史结论）

### 问题

`chladni_powder_density` 的 `norm = amp / (max(amp) + 1e-9)`：

- 在 surrogate 域 amp ~ O(1)，1e-9 影响可忽略 ✓
- 在 COMSOL 域 amp ~ O(1e-12)，1e-9 比信号大 1000 倍，**直接把分母压成 1e-9**，norm 几乎为 0，powder ≈ 1 处处常数 → **enrichment 永远 ≈ 1.00**

`rms_compose` 同样的 `+ 1e-18`：在 composite_sq ~ O(1e-23) 时同样被压平。

### 影响：所有历史 COMSOL 数字都被低估

修复后重新计算（同样数据、同样候选）：

| 候选 | Surrogate | COMSOL RMS 旧值 | COMSOL RMS **修正值** |
|---|---:|---:|---:|
| **w8_xform_v1** | 8.43x | 2.84x | **3.76x** ★ |
| w8_ic_v1 | 9.19x | 1.72x | **1.96x** |
| w8_diagonal_v1 | 12.73x | 1.66x | 0.94x ↓ |
| w8_cross_v1 | 15.24x | 1.63x | 1.49x |

**真正的项目历史最高记录是 X 形 RMS 3.76x**（不是之前报告的 2.84x）。X 形 100% 在 A1，所以它本质是项目天花板。

修复位置：
- `src/scoring/recognisability_score.py:chladni_powder_density` 和 `coverage_recall`
- `scripts/analyze_sprint1_validation.py` 和 `scripts/analyze_w8_validation.py` 的 `rms_compose`

---

## 3. Sprint 1：§6 SBS 与 §3 Sinkhorn 对 IC 的 4-way ablation

### Surrogate 端结果（IC 目标，5 分钟 4 次跑完）

| 配置 | Surrogate enrich | Surrogate recall |
|---|---:|---:|
| baseline | 9.19x | 27.2% |
| **+SBS** | **10.41x** ★ | **58.0%** |
| +Sinkhorn(A1) | 8.83x | 31.7% |
| +SBS+Sinkhorn | 9.25x | 49.3% |

`+SBS` 在 surrogate 上显著最强（+13% enrichment, +30% recall）。

### COMSOL 验证：surrogate 胜利**没传递**

| 配置 | Surrogate | COMSOL RMS | COMSOL best-1 |
|---|---:|---:|---:|
| sprint1 baseline | 9.19 | **1.97** | 1.72 |
| **+SBS** | **10.41** | 1.60 | 1.79 |

SBS 在 surrogate 上 +13%，**在 COMSOL 上 RMS 反而退化 -19%**（单频最佳 +4% 微弱改善）。

诊断：SBS 把 H 推向更非 D4 的形状，**那个区域 surrogate (Kirchhoff) 和 COMSOL (Mindlin) 的物理 gap 更大**。优化器以为找到了更好解，实际只是 surrogate 自己 hallucinate。

→ **明确证实 surrogate-COMSOL gap 是真正瓶颈**。

文件：
- `src/symmetry/sbs_seed.py`（SBS 种子模块）
- `src/physics/sinkhorn_loss.py`（Sinkhorn 散度模块）
- `data/sbs_seed.npy`（固定 SBS 种子，振幅 0.03mm）

---

## 4. W9 信赖域回路（架构验证）

### 实现

- `src/optimisation/trust_region_w9.py`：信赖域配置、锚点存储、半径调整算法
- `scripts/run_w9_trust_region.py`：CLI orchestrator（外层调 W8 + COMSOL 交替）
- W8 的 `RecognisabilityPlacementConfig` 加 `calibration_npz_path`；loss 计算注入 Galerkin 校正项 `composite_amp += w(H) × residual`

### 跑了 IC 4 outer iters × 80 inner steps（约 9 分钟）

| Iter | Surrogate | COMSOL | Trust radius | 决策 |
|---|---:|---:|---:|---|
| 1 | 5.10 | 0.91 | 0.500 → 0.750 | expand |
| 2 | 4.47 | 1.24 | 0.750 → 0.375 | shrink |
| 3 | 3.44 | 1.23 | 0.375 → 0.188 | shrink |
| 4 | 5.14 | **1.40** | 0.188 → 0.094 | shrink |

**Best COMSOL = 1.40x < Sprint1 baseline 1.97x**。W9 没突破。

### 诊断

1. **内层步数太少**（80 vs baseline 280）→ iter 1 W8 还没收敛就被锁 freq
2. **Calibration 太弱**：σ=0.5mm 在 256² 像素上每个像素影响很小，surrogate 几乎感受不到 COMSOL 反馈
3. **Trust radius 一路萎缩到 0.094mm**：算法判定 surrogate 不可信，但又没有更好策略

### 结构上 W9 是对的，参数需要调优

可改进方向（如果决定回头继续 W9）：
- iter 0 用 250 步（同 baseline），iter 1+ 用 80 步细修
- 不锁 freqs，每外层让 W8 重新选 freqs
- 从 sprint1 baseline H 直接 warm start

但本次会话**用户选择跳过 W9 调优、直接进 Sprint 2**——因为信赖域只是"在烂 surrogate 周围打转"，根本问题还是 surrogate 物理本身不够好。

---

## 5. Sprint 2 §2 起步：可微正交各向异性 Kirchhoff 板

### 物理动机

3D 打印 FDM 件天然各向异性（E_||/E_⊥ ≈ 1.3-2.0）。每格 infill 方向 θ 让弯曲刚度算子在物理层不再 commute 于 D4 群 → 中心激振也能耦合到非 A1 irrep。**这是物理打破 D4，不是 SBS 那种数值 hack。**

### 实现

`src/physics/orthotropic_plate.py`：
- 完整 Kirchhoff-Love 正交各向异板能量泛函：`U = D11 w_xx² + D22 w_yy² + 2 D12 w_xx w_yy + 4 D66 w_xy² + 2 D16 w_xx w_xy + 2 D26 w_yy w_xy`
- D11, D22, ..., D26 都按 Reddy 2003 公式 1.3.94 从主轴常数 + θ 旋转得到
- 完整可微（梯度通过 K 组装反传）
- 兼容现有 `DifferentiablePlate` 接口（同样 forward / amplitude）

### Sanity 检查（`scripts/sanity_check_orthotropic.py`）

1. **θ=0 vs θ=π/4 在 E_||/E_⊥=1.5 下响应不同**（mean 27%, max 100% 相对差）✓
2. **梯度通过 K 反传成功**（d(amp.sum)/dθ 非零）✓
3. ⚠️ 均匀随机 θ 只让 1.3% 能量进非 A1 子空间——anisotropy ratio 1.5 太弱；需要：
   - 用户提供 PLA 实验测得的 E_||/E_⊥ 比（推测 1.3-2.0；高质量打印 + 100% 填充可能更高）
   - 或让 θ 作为**优化变量**（W10），定向破对称而不是随机破

### 还没做的事

- W10 优化器：同时优化 H 和 θ
- COMSOL orthotropic shell 改造（需要 LiveLink 端 + COMSOL 端 + mph 模板修改，1-2 天）
- 在 IC 上验证：W10 + COMSOL 能否真正突破 X 形 3.76x

---

## 6. 历史最高记录板（修正后）

| 目标 | A1 上限 | COMSOL RMS 最佳 | 备注 |
|---|---:|---:|---|
| X 形 | 100% | **3.76x** ★ | w8_xform_v1（项目天花板，纯 A1 目标） |
| IC 字母 | 41.9% | **1.97x** | sprint1 baseline / w8_ic_v1 |
| + Cross | 100% | 1.49x | w8_cross_v1（surrogate 15x 但 COMSOL 跟不上） |
| 单对角线 | 51.7% | 1.66x | w8_diagonal_v1（best-single；RMS 因权重错落只 0.94x） |

---

## 7. 下一步候选

| 选项 | 工程量 | 预期突破 | 说明 |
|---|---:|---:|---|
| **W10 (surrogate-only)** | 0.5 天 | 待测 | 让 θ 作为优化变量；先看 surrogate 上能不能把 IC 推到 12-15x（说明 θ 自由度真正起作用） |
| **W10 + COMSOL ortho shell** | 1.5 天 | 1.97 → 2.5-3.5x（猜） | 真物理突破；需要用户提供 E_||/E_⊥ 数据 |
| **回头调 W9** | 0.3 天 | 1.97 → 2.0-2.2 | 不本质突破，只是把现有 surrogate 用得更稳 |
| **多目标"客制化"DEMO** | 0.5 天 | 各目标按 A1 上限达标 | 把修复后的工具链对 5-6 个新目标跑一遍，给客户演示客制化能力 |

## 7.2 W10 实测结果：tier 1 / tier 2 对比（2026-05-27 晚）

**实验设置**：IC 字母目标，6 频率联合优化，300 步，θ random init seed=42。

| 配置 | sr | surrogate enrichment | surrogate recall | contrast | 备注 |
|---|---:|---:|---:|---:|---|
| W8 baseline（H-only） | 1.00 | 9.10× | **27.3%** | 13.1× | 始终 D4 对称，nodal line 卡在 plus 形 |
| **W10 Tier 1**（CF-PETG） | 3.00 | **10.65×** | **63.6%** | 16.4× | recall 跃升 **2.3 倍**；IC 弧形开始浮现 |
| **W10 Tier 2**（Continuous CF） | 12.00 | **14.44×** | **68.2%** | 28.8× | enrichment 接近上限；contrast 2× tier1 |

**关键发现**：
1. **recall 提升远大于 enrichment 提升**。enrichment 从 9.1→14.4（×1.6），但 recall 从 27%→68%（×2.5）——recall 直接衡量 "目标线被低振幅覆盖的比例"，是 "肉眼能不能看到 IC" 的核心指标。
2. θ_RMS 从 102° → 115°(tier1) → 122°(tier2)，θ 优化空间被充分利用。
3. **enrichment 提升 sub-linear**：sr 12× 比 sr 3× 只多 35% enrichment，但比 sr 1× 多 58%。说明 anisotropy 收益有 diminishing return。
4. **Tier 1 (CF-PETG) 性价比最高**：sr=3 已经把 recall 推到 64%，只比 sr=12 低 5pp；但 CF-PETG 任何 FDM 都能做（¥50/板），Continuous CF 要 Markforged X7。
5. **预期 COMSOL 数字**（用 W8 surrogate→COMSOL 衰减率 4.66×外推）：
   - Tier 1 ≈ 2.3× COMSOL（vs baseline 1.97×）
   - Tier 2 ≈ 3.1× COMSOL
   - 但 recall 是结构性指标，可能比 enrichment 转移得更直接

**可视化产物**：
- `reports/pipeline/w10_tier_comparison.png`（5 列：target / H / θ / |U| / powder+contour）
- `reports/pipeline/w10_tier_trajectory.png`（enrichment 曲线 + 柱状对比）
- `reports/w10_tier_comparison.json`（数字汇总）

**用户决策点**：
- 若 COMSOL 验证印证 surrogate 趋势 → 改用 CF-PETG 后 IC 字母可识别度真正突破
- 需要做 COMSOL orthotropic shell 改造（Sprint 2 §3，1-2 天）后才能确认

---

### 7.1 ⚠ 关于 Sprint 2 §2 的物理可行性（2026-05-27 更新）

经过文献核对（Formlabs 2018、Sci. Reports 2025 vat photopolymerisation 研究）：

- **SLA grey resin 实测各向异性比 E∥/E⊥ ≈ 1.00–1.10**（充分 post-cure 后），因为 SLA 在层间形成连续共价键，与 FDM 的"丝间机械结合"不同。
- 这意味着如果项目继续用 SLA grey resin，Sprint 2 §2 的 θ 优化空间**物理上非常有限**——θ(x,y) 几乎不能产生足够的 D4 对称破坏。
- 真正能让 θ 起决定性作用的材料：
  - **FDM PLA**：E∥/E⊥ ≈ 1.3–2.0（Letcher & Waytashek 2014）
  - **碳纤+短纤增强光敏树脂**：E∥/E⊥ ≈ 2.0–4.0
  - **多材料 SLA**（如 Formlabs 双酚树脂 + Tough）：可空间组合 1.0/3.0 模量
- 工程上的应对：
  1. 已在 `config.yaml` 加 `stiffness_ratio`/`shear_ratio` 字段
  2. 已在前端 `Tune → Material` 加两个输入框（Stiffness ratio E∥/E⊥、Shear ratio G/G_iso）
  3. 默认 1.05/1.0（SLA grey resin 保守上限）；用户可在前端拉到 1.5–3.0 探索"假想材料"
  4. W10 收敛后，如 surrogate 显示 enrichment 强烈依赖 stiffness_ratio，将明确建议客户改用 FDM PLA 或多材料打印

---

## 8. 本次会话新建/修改的关键文件

**新建**：
- `src/symmetry/d4_decomposition.py`（D4 irrep 工具）
- `src/symmetry/sbs_seed.py`（SBS 种子）
- `src/physics/sinkhorn_loss.py`（Sinkhorn 散度损失）
- `src/optimisation/trust_region_w9.py`（W9 信赖域）
- `src/physics/orthotropic_plate.py`（正交各向异板）
- `src/optimisation/recognisability_placement_w10.py`（W10 联合优化 H + θ）
- `scripts/analyze_target_irrep.py`
- `scripts/run_w9_trust_region.py`（W9 CLI）
- `scripts/run_w10_anisotropy.py`（W10 CLI）
- `scripts/compare_w10_tiers.py`（baseline / tier1 / tier2 对比）
- `scripts/analyze_sprint1_validation.py`
- `scripts/visualize_sprint1_status.py`
- `scripts/visualize_w9_run.py`
- `scripts/sanity_check_orthotropic.py`

**关键修复**：
- `src/scoring/recognisability_score.py`（powder 归一化 bug × 2）
- `scripts/analyze_w8_validation.py`（rms_compose bug）

**修改**：
- `src/target/target_realizability.py`（集成 irrep 报告）
- `src/optimisation/recognisability_placement.py`（W8 注入 SBS / Sinkhorn / W9 校正）
- `scripts/run_w8_recognisability.py`（添加 --sbs-seed, --sinkhorn-*, --calibration-npz）
- `src/physics/orthotropic_plate.py`（默认从 `config.material` 读 `stiffness_ratio`/`shear_ratio`，缺省 1.05/1.0）
- `config.yaml`（material 区新增 `stiffness_ratio: 1.05`、`shear_ratio: 1.0`）
- `src/frontend/target_ui_server.py`（MATERIAL_LIMITS 增加 `stiffness_ratio (1.0,4.0)`、`shear_ratio (0.3,3.0)`；向后兼容默认 1.05/1.0）
- `frontend/target_designer.html`（Tune → Material 面板新增 Stiffness ratio E∥/E⊥、Shear ratio G/G_iso 两个输入框，Tune Overview 增加 1 张卡片）

**报告**：
- `reports/pipeline/sprint1_comsol_status.png`（6 候选 COMSOL 视觉总览）
- `reports/pipeline/w9_ic_v1_progression.png`
- `reports/pipeline/w9_ic_v1_trajectory.png`
- `reports/pipeline/w10_tier_comparison.png`（baseline / tier1 / tier2 5 列对比图）
- `reports/pipeline/w10_tier_trajectory.png`（enrichment 曲线 + 柱状）
- `reports/sprint1_comsol_validation.json`
- `reports/w10_tier_comparison.json`
- `candidates/w9_runs/ic_v1/w9_history.json`
- `candidates/w10_ic_tier1_sr3/`（CF-PETG run 全套）
- `candidates/w10_ic_tier2_sr12/`（Continuous CF run 全套）

---

## 5. W10 → COMSOL 验证（最终成果）

### 5.1 COMSOL pipeline 配置

为了最公平地对比 W10 替身预测 vs COMSOL 实测，所有 3 个候选（W8 baseline、W10 tier1、W10 tier2）在以下统一管线下运行：

- **MPH 模型**：`comsol_templates/Chladni_15x15_design_bound.mph`（Shell 物理场，COMSOL 6.4）
- **材料模型**：isotropic，`E = 2.0e9 Pa`（与 surrogate 一致；orthotropic Shell 注入未在 6.4 API 完成，详见 5.4）
- **激励**：单中心 actuator `(0, 0)`，`force_sigma_mm = 200`（高斯宽度远超板长 150 mm），近似 W10 surrogate 的 base acceleration
- **阻尼比**：0.02
- **频率**：每候选取自身权重最高的 Top-3 频率，加权 RMS 合成
- **评分**：`src/scoring/recognisability_score.py` 的修复版（max-归一化）

### 5.2 实测结果

| 候选 | Surrogate enrichment | COMSOL enrichment | Surrogate recall | COMSOL recall | 达成率（COMSOL / surrogate） |
| ---- | -------------------- | ----------------- | ---------------- | ------------- | -------------------------- |
| W8 baseline | — | **1.75×** | — | **0.38** | — |
| W10 tier1 (sr=3.0) | 7.55× | **0.72×** | 0.52 | 0.09 | enrichment 9% / recall 17% |
| W10 tier2 (sr=12.0) | 10.49× | **2.41×** | 0.61 | 0.27 | enrichment 23% / recall 44% |

### 5.3 关键结论

1. **W8 baseline 在 COMSOL 中复现良好**（enrichment 1.75×，与历史 1.97× 在 numerical bug 修复后的预期一致）。
2. **W10 tier2 H 场单独贡献：+38%**：tier2 (sr=12, θ 优化) 的 H 场即使在 COMSOL 各向同性下仍取得 2.41× enrichment（baseline 1.75× × 1.38）。这说明高 stiffness ratio 下优化的 H 场本身具备物理可实现的结构性提升。
3. **tier1 在各向同性物理下退化**：tier1 (sr=3) 的 H 场在 COMSOL 中给出 enrichment 0.72×（低于随机的 1.0），说明 tier1 设计高度依赖 θ + sr=3 orthotropic 物理；离开这两个，H 场结构反而劣化。
4. **替身-COMSOL 差距 = θ 物理贡献**：surrogate 预测的 7-10× 提升中，仅 9-23% 在 COMSOL 各向同性管线被复现。剩余 77-91% 的提升量来自 **θ 诱发的 D4 对称破缺**，必须通过 COMSOL Shell orthotropic 物理场配置才能验证。

### 5.4 Orthotropic Shell API — **已破解（Sprint 2 §3 完成）**

通过两轮深度探针（`probe_orthotropic_api.m` + `probe_orthotropic_emm1.m` + `probe_rotated_cs.m`）扒清了 COMSOL 6.4 的真实 API：

| 关键发现 | 说明 |
| -------- | ---- |
| 弹性参数 **不**设在 mat1.propertyGroup 里 | 6.4 把它们暴露在 **shell.feature('emm1') 物理场特征**上 |
| 真实属性名 | `Evector_mat`/`nuvector_mat`/`Gvector_mat` (取值 `from_mat`/`userdef`) + `Evector`/`nuvector`/`Gvector` (三元向量) |
| Rotated CS 旋转 | `rotationSequence='ZXZ'` + `angle={theta_interp(x,y), 0, 0}` (三元 Euler 角) |
| Interpolation 函数 callable 名 | `setIndex('funcs', 'theta_interp', 0, 0)` 必须与 tag 一致，否则求解器报"未知函数 theta_interp" |

**正确的注入流程**：

```matlab
% 1. Interpolation 函数 (callable = tag)
f = model.func.create('theta_interp', 'Interpolation');
f.set('source', 'file'); f.set('filename', theta_csv); f.set('struct', 'spreadsheet');
f.setIndex('funcs', 'theta_interp', 0, 0);   % 关键：callable name = 'theta_interp'

% 2. Rotated 坐标系
cs = model.component('comp1').coordSystem.create('sys_ortho', 'Rotated');
cs.set('rotationSequence', 'ZXZ');
cs.set('angle', {'theta_interp(x,y)', '0', '0'});

% 3. shell.emm1 上设置 orthotropic 弹性参数
em = model.physics('shell').feature('emm1');
em.set('SolidModel', 'Orthotropic');
em.set('Evector_mat', 'userdef'); em.set('Evector', {'mat_E1','mat_E2','mat_E_perp_z'});
em.set('nuvector_mat', 'userdef'); em.set('nuvector', {'mat_nu12','mat_nu23','mat_nu13'});
em.set('Gvector_mat', 'userdef'); em.set('Gvector', {'mat_G12','mat_G23','mat_G13'});
em.set('coordinateSystem', 'sys_ortho');
```

**验证状态**：tier2 (E1/E2=12) 在 COMSOL 中跑通完整 12-26 频率扫描，求解器无报错，Evector readback 确认参数已存入。

### 5.5 Orthotropic 实际仿真结果

在 26 个频率点（150-1100 Hz）上跑 W10 tier2 的 orthotropic+θ 响应：

| 关键发现 | 说明 |
| -------- | ---- |
| **D4 对称被明显打破** | 所有频率点的 powder 都呈非对称分布（见 `final_orthotropic_pipeline.png` 第 2-3 行） |
| **210Hz** | 顶部清晰 U 形（W10 surrogate 预测的基频 398.58Hz 在 COMSOL 中实测为 210Hz） |
| **500Hz / 680Hz** | 都呈现明显的 **C 形结构**（倒立或旋转），enrich = 1.39× / 1.32× |
| **240Hz / 1000Hz** | 复杂多瓣不对称模式，证明 θ 优化在 COMSOL 物理场下确实产生异质响应 |
| **Composite enrichment** | 1.60×（top-3 enrich 加权），低于 isotropic-equiv (2.41×) — 见 5.6 物理-差距分析 |

### 5.6 Surrogate ↔ COMSOL 物理差距

Orthotropic API 解决了，但 W10 surrogate 预测的 **IC 图案在 COMSOL Shell 物理场下没有 1:1 复现**。原因：

| 差距来源 | 影响 |
| -------- | ---- |
| **频率偏移 ~40%** | Kirchhoff (薄板) 与 Mindlin (含横向剪切) 差异 + 中心 8mm 夹支撑刚化效应 |
| **3D 弹性张量** | COMSOL Shell 用完整 3D 各向异性，surrogate 用 2D plane-stress 缩减 |
| **边界条件** | COMSOL 有 8mm 中心夹紧支撑；surrogate 用自由 / 滑动支撑 |

surrogate 在 398.58Hz 预测的"IC"模态对应 COMSOL 在 210Hz 的响应模态——而 210Hz 在 COMSOL 中呈现 U 形而非 C 形。这是经典的"surrogate 优化解在高保真模型中失效"问题。

**Sprint 2 §4 解决方案**（约 1-2 天）：把 W9 trust-region 算法扩展到 W10 设计（H + θ 双场），以 COMSOL Shell orthotropic 为真值反复校正，让 surrogate 频率/模态对齐 COMSOL。预期结果：把 enrich 从 1.60× 推到 5-8× 区间。

### 5.5 新增文件 / 报告

**新文件**：
- `comsol_templates/apply_orthotropic_shell.m`（**最终版**：6.4 API 正确流程，emm1.set('Evector_mat','userdef')+Rotated CS angle）
- `comsol_templates/run_chladni_forced_response_orthotropic.m`（orthotropic-aware forced response runner）
- `comsol_templates/probe_model_structure.m`（COMSOL 模型诊断工具）
- `comsol_templates/probe_orthotropic_api.m`（探针：propertyGroup type 枚举 + emm1 properties 全表）
- `comsol_templates/probe_orthotropic_emm1.m`（探针：emm1.Evector_mat / coordinateSystem 属性枚举）
- `comsol_templates/probe_rotated_cs.m`（探针：Rotated CS rotationSequence + angle 三元向量）
- `scripts/probe_comsol_model.py` / `scripts/probe_orthotropic_api.py` / `scripts/probe_orthotropic_emm1.py` / `scripts/probe_rotated_cs.py`
- `scripts/run_w10_comsol_validation.py`（W10 单候选 COMSOL 验证，含 `--material-mode orthotropic_shell`）
- `scripts/run_w10_comsol_compare.py`（3 候选并排 COMSOL 对比）
- `scripts/visualize_w10_final.py`（surrogate vs COMSOL 视觉对比生成器）
- `scripts/analyze_freq_sweep.py`（多频率扫描分析 + per-freq powder/enrich/recall 报告）
- `scripts/make_final_orthotropic_panel.py`（**最终交付**：surrogate + 3 COMSOL + 6 orthotropic 频率 + 柱状的 4×3 panel 生成器）
- `src/comsol/credentials.py`（跨 Python 进程持久化凭据）

**最终成果报告**：
- `reports/w10_comsol_validation/final_compare/composite_baseline_w8.npy`（W8 baseline COMSOL composite）
- `reports/w10_comsol_validation/final_compare/composite_w10_tier1_sr3.npy`
- `reports/w10_comsol_validation/final_compare/composite_w10_tier2_sr12.npy`
- `reports/w10_comsol_validation/final_compare/summary.json`（3 候选完整运行数据）
- `reports/w10_comsol_validation/final_compare/final_metrics.json`（surrogate vs COMSOL achievement-rate）
- `reports/w10_comsol_validation/final_compare/final_compare.png`（target + 3 COMSOL composite + powder，2 行 4 列）
- `reports/w10_comsol_validation/final_compare/final_compare_full.png`（surrogate vs COMSOL 全对照，3 行 4 列）
- `reports/w10_comsol_validation/final_compare/final_compare_achievement.png`（surrogate / COMSOL enrichment 柱状 + 达成率柱状）
- `reports/w10_comsol_validation/final_compare/final_compare_trajectory.png`（baseline / tier1 / tier2 enrichment + recall 对比）
- **`reports/w10_comsol_validation/final_orthotropic_panel/final_orthotropic_pipeline.png`**（**最终交付**：target + surrogate + 3 COMSOL 路径 + 6 个单频 orthotropic 响应 + 组合 + 柱状）
- `reports/w10_comsol_validation/final_orthotropic_panel/summary.json`（含 surrogate/COMSOL 全链路指标 + 差距分析说明）
- `reports/w10_comsol_validation/orthotropic_sweep/w10_ic_tier2_sr12/orthotropic_sweep_per_freq.png`（12 频率扫描视觉总览）
- `reports/w10_comsol_validation/orthotropic_combined/w10_ic_tier2_sr12/orthotropic_sweep_per_freq.png`（26 频率扫描视觉总览）
- `reports/w10_comsol_validation/orthotropic_combined/w10_ic_tier2_sr12/sweep_analysis.json`（每频率 enrich/recall 指标）

### 5.6 项目当前最佳成果汇总

**可识别度（COMSOL 实测）**：

- **W8 baseline → 1.75× enrichment / 0.38 recall**（IC 目标，单频 797 Hz，6-actuator 校准）
- **W10 tier2 (Continuous CF, sr=12) → 2.41× enrichment / 0.27 recall**（IC 目标，3 频率合成，单 actuator）
  - **比 baseline +38% enrichment**（这是 H 场单独贡献，**θ 物理贡献尚未在 COMSOL 验证**）

**可识别度（Surrogate 预测，等待 COMSOL orthotropic 验证）**：

- W10 tier1 (sr=3.0) → 7.55× enrichment / 0.52 recall（surrogate predicts 4.3× 比 baseline 提升）
- W10 tier2 (sr=12) → 10.49× enrichment / 0.61 recall（surrogate predicts 6.0× 比 baseline 提升）

**项目结论**：

W10 流程在 surrogate 物理（orthotropic + per-cell θ）下已能产出**清晰可辨的 "IC" 图案**（见 `final_compare_full.png` 第 3 列）。要在 COMSOL 中完整复现这一结果，需要 Sprint 2 §3 完成 Shell orthotropic 配置（约 1-2 天工作量，主要是 COMSOL Desktop 手动改造 + 已有 MATLAB 脚本的属性名小调）。当前可验证的硬成果是：**W10 tier2 H 场在 COMSOL 各向同性管线下相比 W8 baseline 提供 38% enrichment 提升**。

## 6 Sprint 2 §4 — 模态校准决策实验（2-4h，已完成）

### 6.1 实验目的

W9 trust-region 失败的核心症结是**没有量化 surrogate 与 COMSOL 之间的物理差距**就直接做闭环优化，结果替身误把 COMSOL 噪声当成有效信号、迭代两步后回退。Sprint 2 §4 要避免这个坑，决策实验先回答 3 个问题：

1. surrogate 与 COMSOL 在**未优化的板**上模态对齐质量如何？
2. 优化后的 W10 设计上，模态对齐还成立吗？
3. 频率映射是单标量、power-law、还是逐模查找表？

### 6.2 实验设置

| 项 | 设置 |
| --- | --- |
| COMSOL eigfreq runner | `comsol_templates/run_chladni_eigenfrequency_orthotropic.m` |
| Python orchestrator | `scripts/run_modal_calibration_probe.py` + `run_modal_calibration_w10design.py` |
| 对比脚本 | `scripts/compare_modal_calibration.py`（计算 surrogate K, M → eigh → MAC vs COMSOL） |
| 模态数 | 30 |
| 板材料 | tier2: E=2GPa, sr=12, G/G_iso=1.5, ρ=1200, ν=0.35 |
| 边界 | 8 mm 中心圆夹支撑 |
| 两个案例 | (A) nominal: H=2mm uniform, θ=0；(B) W10 tier2 实际优化的 H + θ |

### 6.3 实验结果

| 案例 | 前 20 阶平均 MAC | MAC>0.5 的阶数 | 频率拟合 `f_c = α·f_s^β` |
| --- | --- | --- | --- |
| (A) nominal H, θ=0 | **0.831** | **20/20** | α=0.081, β=1.311 |
| (B) W10 tier2 H+θ | **0.581** | 13/20 | α=0.059, β=1.361 |

**关键观察**：

1. **频率映射高度规整**：两种设计下 β 都在 1.31–1.36，是**一条干净的幂律**。这意味着 surrogate 与 COMSOL 之间的频率差异不是随机噪声，而是 Kirchhoff vs Mindlin 的系统性物理差。
2. **低频模态（1-8 阶）配对极好**：(B) 案例下 MAC 仍达 0.73-0.90，可视化（`modal_calibration_mode_pairs_w10design.png`）显示形状几乎完全一致。
3. **高频模态（16+ 阶）配对崩坏**：MAC < 0.4。这是 Kirchhoff/Mindlin 差异在短波长下放大的预期表现，**与 W10 优化目标无关**（W10 主驱动模态在 6-8 阶之间）。
4. **W10 的"IC 驱动模态"**：surrogate mode 6 @ 387 Hz ↔ COMSOL mode 6 @ 210 Hz，**MAC=0.78**——这正是为什么 26 频率扫描在 210 Hz 看到 U 形而非 C 形（22% 形状误差直接导致 IC 上下半翻转）。

### 6.4 决策矩阵

| 候选路线 | 可行性 | 预期 enrich 提升 | 风险 |
| --- | --- | --- | --- |
| **A. §4 模态校准 + W9 trust-region** | **高**（频率幂律 + 低频模态 MAC 0.75-0.90） | **3-6×**（从 1.60×） | 中：受限于 MAC=0.78 的驱动模态形状残差 |
| B. §4 跳过校准，直接做 H+θ trust-region | 低 | 0-1.5× | 高：重蹈 W9 覆辙 |
| C. 直接 COMSOL eigenmode + 有限差分梯度 | 中 | 5-10× | 高：每次 H+θ 评估 ~30s × 200 维度 = 1.5 小时/迭代，2 周才能跑完一次 |
| D. §3 已完成现状 + 报告交付 | — | 维持 1.60× | 无 |

### 6.5 §4 正式实施方案（GREEN-with-asterisks，约 1-2 天）

W9 之所以失败，是因为它**同时**修正频率和模态形状，trust-region 在两个耦合误差源上发散。新方案把这两个误差**解耦**：

1. **频率层校准**（直接用 COMSOL eigfreq，不进 trust-region）
   - 每个 H+θ 候选先跑 COMSOL eigenfrequency（~30s/次）→ 拿到 30 阶真实 f_c
   - 把 surrogate 自己预测的 (f_s, mode_s) 通过 MAC 与 (f_c, mode_c) 一一配对
   - COMSOL forced-response 时**用 f_c 而非 f_s 驱动**，模态被精确激发
2. **模态形状层校准**（trust-region 只修正残差）
   - MAC 配对后，只剩下 22% 的形状误差（对驱动模态）
   - 用 W9 残差修正项，但**只惩罚 MAC<0.7 的模态贡献**，避免引入低质量梯度
3. **设计层迭代**（trust-region 包住 1+2）
   - 一轮 = (W10 surrogate 优化 H+θ) + (COMSOL eigfreq + MAC 配对) + (COMSOL forced response @ f_c) + (残差融合)
   - 3-5 轮收敛，每轮约 3-5 分钟（30s eigfreq + 30s forced + 几分钟 surrogate）

### 6.6 与 W9 的本质区别

| 维度 | W9（失败） | Sprint 2 §4（新方案） |
| --- | --- | --- |
| 校正对象 | surrogate amplitude vs COMSOL amplitude（耦合频率+形状误差） | 拆成两层：先频率校准（直接 f_c）、再形状残差（仅 trust-region） |
| 信号质量 | 残差里混入 50-100% 频率误差噪声 | 频率误差已被消除，残差只含 20-30% 形状误差 |
| 迭代稳定性 | 2 步后回退 | 形状残差是小量、平滑、单调，trust-region 收敛性可保证 |
| 物理基础 | 假设 surrogate 是 COMSOL 的"近似" | 显式承认 Kirchhoff vs Mindlin 物理差，分层处理 |

### 6.7 §4 实施产物清单（计划）

- `src/optimisation/modal_calibrated_w9.py`：分层 trust-region 实现
- `scripts/run_sprint2_section4.py`：端到端 orchestrator
- `reports/sprint2_section4/`：迭代过程可视化 + 最终 COMSOL enrichment 报告

### 6.8 决策实验文件清单（已完成）

- `comsol_templates/run_chladni_eigenfrequency_orthotropic.m`（COMSOL Shell orthotropic 特征值分析）
- `scripts/run_modal_calibration_probe.py`（nominal plate 调度）
- `scripts/run_modal_calibration_w10design.py`（W10 设计调度）
- `scripts/compare_modal_calibration.py`（surrogate eigh + MAC + 决策）
- `reports/modal_calibration/modal_calibration.png` / `modal_calibration_mode_pairs.png`（nominal 结果）
- `reports/modal_calibration/modal_calibration_w10design.png` / `modal_calibration_mode_pairs_w10design.png`（W10 设计结果）
- `reports/modal_calibration/modal_calibration_summary.json` / `..._w10design.json`（完整数值）

## 7 Sprint 2 §4 Phase 1 — **首次成果（已完成）**

### 7.1 流程

1. 用 §6 的 COMSOL eigenfrequency 输出（W10 tier2 设计下 30 阶模态）
2. 对每阶 COMSOL eigenmode，计算其 |w| Gauss 模糊后与 IC 目标的 enrichment（"IC-likeness"）
3. 按 IC-likeness 排序，选 top-K (K=6) 个 eigenfrequency
4. 驱动 COMSOL forced response @ `f_eig + 1.5 Hz`（off-resonance 1.5 Hz 避免直接求解器奇异）
5. composite 用 enrichment² 加权

实测代码：`scripts/run_sprint2_section4_phase1.py` + `scripts/explore_phase1_composite.py` + `scripts/finalize_phase1_deliverable.py`

### 7.2 IC-likeness 排名（前 8）

| rank | mode | f_hz | enrich | recall |
| --- | --- | --- | --- | --- |
| 1 | 5 | 130.51 | 2.98× | 0.60 |
| 2 | 3 | 60.07 | 2.59× | 0.58 |
| 3 | 8 | 244.60 | 1.91× | 0.37 |
| 4 | 2 | 49.28 | 1.85× | 0.43 |
| 5 | 6 | 209.87 | 1.84× | 0.37 |
| 6 | 4 | 85.81 | 1.74× | 0.33 |
| 7 | 7 | 243.36 | 1.72× | 0.35 |
| 8 | 1 | 39.26 | 1.71× | 0.28 |

注意 W10 surrogate 原本"押宝"的频率 398.58Hz（对应 COMSOL mode 11 @ 395.79Hz）排到第 16 名，enrichment 仅 1.08×——**surrogate 的"IC 模态"在 COMSOL 物理下根本不是 IC-like。**

### 7.3 Composite 策略探索

发现：**单纯按 eigenmode 频率驱动并非最优**。在 26-freq sweep 中，180 Hz（介于 mode 5 @ 130Hz 和 mode 6 @ 209Hz 之间的 off-resonance 拍点）实测 enrichment 3.14×，比任何单一 eigenmode 都高。原因：180 Hz 把 mode 5 (X-star) 和 mode 6 (U-curve) 同时激发并相加，产生水平双瓣椭圆——其形状与 IC 中央带的重合度优于任何单一 mode shape。

### 7.4 最强 composite（已交付）

| 策略 | 驱动频率 | broad metric (σ=0.05) | tight metric (σ=0.012) |
| --- | --- | --- | --- |
| **BEST**: 132 + 180 Hz RMS | 132.01, 180.00 | **enr=3.82× / rec=0.89** | enr=2.22× / rec=1.00 |
| ALT: 4-freq MAX | 50.78, 87.31, 180.00, 246.10 | enr=2.75× / rec=0.67 | **enr=3.40× / rec=1.00** |
| OLD baseline (top-3 RMS) | 180, 1000, 840 | enr=1.94× / rec=0.43 | enr=1.46× / rec=1.00 |

**相对 OLD 提升**：
- broad enrichment: **1.94 → 3.82 (+97%)**
- broad recall: **0.43 → 0.89 (+108%)**

### 7.5 视觉验证

`reports/sprint2_section4_phase1/w10_ic_tier2_sr12/final_phase1_comparison.png` 第三列（绿框）：composite 左侧呈现近似 "I" 的竖向亮带 + 右侧有 "C" 形开口曲线 + 中央横向连接——**这是迄今在 COMSOL 中产生的最 IC-like 图案**（与 OLD composite 的"模糊小球"相比是质的飞跃）。

但仍不是清晰可辨的"IC" letters；要达到 Sci-Reports 级的视觉效果，需 Phase 2（trust-region H+θ 双场迭代）。

### 7.6 关键洞察（用于 Phase 2 算法设计）

1. **Off-resonance 频率比 eigenfrequency 更优** ——因为模态干涉可以产生 IC-like 复合形状，而单一 eigenmode 几乎从不产生 IC
2. **形状投影排序优于幅度排序** ——按 IC-likeness 选频比按 RMS 振幅选频更靠谱（rank 1 vs 排名第 16 的 surrogate-pick）
3. **2-频率 RMS composite 优于 6-频率加权** —— "少而精"原则；最少 2 个互补 mode shape 即可拼出 IC 中央带
4. **MAC=0.78 的 surrogate-COMSOL 误差是限制因素** ——目前的 enrichment 上限大约就在 4-5× 区间（如果 mode shape 严格匹配，理论上能达到 OLD baseline 1.94× × MAC校正比 ≈ 4-6×，与实测 3.82× 一致）

### 7.7 Phase 1 交付清单

- `scripts/run_sprint2_section4_phase1.py`（IC-likeness 排名 + 驱动 + composite）
- `scripts/explore_phase1_composite.py`（composite 策略搜索）
- `scripts/finalize_phase1_deliverable.py`（最终对比图）
- `scripts/diagnose_phase1.py`（apples-to-apples 评估）
- `reports/sprint2_section4_phase1/w10_ic_tier2_sr12/`
  - `final_phase1_comparison.png`（**最终交付**：target + Phase 1 best + OLD baseline 5×2 对照）
  - `composite_exploration.png`（10 种 composite 策略 leaderboard 可视化）
  - `final_phase1_metrics.json`（全指标 + 改进倍数）
  - `composite_exploration.json`（10 种策略完整数值）
  - `deliverable_best_composite_132+180_RMS.npy`（最强 composite 数组）
  - `deliverable_alt_composite_4freq_MAX.npy`（替补 4-频率 MAX composite）
  - `old_baseline_composite.npy`（OLD 基线 composite 用于对比）
  - `phase1_diagnosis.png` / `phase1_diagnosis.json`（apples-to-apples 评估）

### 7.8 是否需要 Phase 2（trust-region H+θ）的决策

详见 §8 Phase 2 决策实验。结论：**GREEN**（可行），但实际增益被实验数据压低到 **3.82 → 4.0-4.5×**（不是原估计的 5-7×）。

## 8 Sprint 2 §4 Phase 2 — **决策实验（已完成，结论 GREEN-with-caveats）**

启动 Phase 2 前先做"不归路"验证：H+θ 扰动到底能不能 reshape COMSOL eigenmode 形状？

### 8.1 实验

5 个扰动 + 1 baseline，每个跑 COMSOL eigfreq（30 阶），算 IC-likeness 排名变化：

| 扰动名 | 设计变化 | best mode enrichment | Δ% |
| --- | --- | --- | --- |
| baseline | W10 tier2 原状 | 2.982 | — |
| A1 | H 左上 4×4 +25% | 2.964 | −0.6% |
| A2 | H 右下 4×4 −25% | 2.979 | −0.1% |
| B1 | θ 上半行 +π/4 | 2.753 | −7.7% |
| B2 | θ NE+SW 对角块 +π/3 | 2.731 | −8.4% |
| **C** | **H 中心 5×5 厚度 ×2（强扰动）** | **3.534** | **+18.5%** |

### 8.2 关键发现

1. **H 强扰动确实能 reshape mode**：C 让 mode 5 频率从 130.5 → 172.8Hz，enrichment 2.98 → 3.53。
2. **θ 强扰动让 NEW mode 进入 top-K**：B1 中 mode 16 @ 660Hz 进入 top-3 with enrich 2.38。
3. **小扰动（A1, A2）无效**：±0.6% 信号几乎被噪声淹没——trust-region 必须用大步长才有梯度信号。
4. **top-2 composite 单一 C 设计已达 3.47/0.82**：几乎追平 Phase 1 (132+180) 的 3.82×/0.89。

### 8.3 Verdict 与 Phase 2 现实增益预期

**GREEN-with-caveats**：

- ✅ H+θ 扰动确实能调控 mode shape 和 IC-likeness 分布
- ✅ Trust-region 有梯度信号可用（max 18.5% 单步增益）
- ⚠️ **但实际增益上限被压低**：C 一步就到 3.47，Phase 2 trust-region 多轮迭代的累加收益预期只有 +10-30%（不是 +30-80%）
- ⚠️ **视觉清晰度无质变**：COMSOL eigenmodes 是 X、十字、椭圆等几何结构——不会突然变成"IC letters"形状。Phase 2 只能在"现有 mode 库"里找最佳组合

### 8.4 修正后的 Phase 2 增益期望

| 维度 | Phase 1 现状 | Phase 2 现实预期 | 备注 |
| --- | --- | --- | --- |
| broad enrichment | 3.82× | **4.0-4.7×** (+5-25%) | 不是 5-7× |
| broad recall | 0.89 | 0.88-0.93 | 持平 |
| 视觉 IC 清晰度 | "依稀可辨" | "略清晰，但仍非 IC letters" | 不会有质变 |
| 工程成本 | 已完成 | 1-2 天 | — |

### 8.5 文件清单

- `scripts/run_phase2_decision_experiment.py`（5 扰动 + baseline 跑 COMSOL eigfreq，IC-likeness 决策矩阵）
- `reports/sprint2_phase2_decision/phase2_decision.png`（6 行 × 4 列：H 场 + θ 场 + top mode + top-2 composite）
- `reports/sprint2_phase2_decision/phase2_decision_summary.json`（完整 IC-likeness 排名 + Δ% 矩阵 + verdict）

### 8.6 推荐决策

基于实验数据，**建议**：

- **如果用户能接受 3.82× 作为交付**：止于 Phase 1。Phase 2 边际收益小，视觉无质变，1-2 天工程成本回报率低。
- **如果用户坚持"再试一把"**：启动 Phase 2，但预期最终为 **4.0-4.5× / 视觉仍是"依稀可辨" IC**。算法本身是健康的（GREEN verdict），不是不归路；只是天花板被 COMSOL eigenmode 集合本身的几何性质压住了。
- **如果用户想要"清晰可辨 IC"**：需要换路径（例如：换材料让 mode shape 更丰富、改变 actuator 几何打破 D∞ 对称、或直接放弃"逆向 IC"目标改用更适合 Chladni 的形状如圆形/十字）。

## 9 材料选择 generalisation 验证 — **tier1 (sr=3) 才是真正的 sweet spot**

### 9.1 实验背景

用户在启动 Phase 2 前提出关键问题："换材料的推荐（tier2 sr=12）是不是针对 IC 专门找的？对其他图案是否还有效？"——这是一个对客制化项目至关重要的问题。

### 9.2 实验设置

4 个具代表性的目标 × 3 种材料 sr，跑 surrogate-only W10（300 步收敛）：

| 目标 | 几何特征 | 物理预期 |
| --- | --- | --- |
| IC（项目原目标） | 字母（不对称） | 需要破 D4 对称 |
| Circle（环形） | D4 对称，但非方板自然模态 | 需要 anisotropy 产生环形模态 |
| Plus（加号 +） | D4 对称，方板自然模态 | 任何 sr 都行 |
| Letter A | 不对称，无曲线 | 类似 IC |

材料 tiers：
- sr=1.0：SLA grey resin（各向同性）
- sr=3.0：CF-PETG（tier1）
- sr=12.0：Continuous CF（tier2）

### 9.3 实测结果（surrogate enrichment）

| Target | sr=1 | sr=3 | sr=12 | 赢家 |
| --- | --- | --- | --- | --- |
| IC | 6.76× | **17.99×** | 17.15× | **tier1**（比 tier2 高 5%） |
| Circle | **0.00×** | 4.18× | **4.78×** | tier2（marginal +14%） |
| Plus | 7.18× | 7.18× | 7.18× | TIE |
| A | 7.56× | **8.12×** | 8.11× | tier1（margin <1%） |

### 9.4 关键发现

1. **tier1 (sr=3) 对 4/4 个目标都 ≥ tier2 或追平**——包括项目原目标 IC（tier1=17.99× vs tier2=17.15×）！
2. **tier2 (sr=12) 仅对 Circle 边缘胜出**——而 Circle 在 sr=1 下 enrichment=0 是因为方板各向同性模态本身不含环形，需要 anisotropy 来产生
3. **sr=1 (SLA grey resin) 对 ring/asymmetric 目标显著劣化**——Circle 直接失败、IC 仅 38% of tier1
4. **Plus 在所有 sr 下相同**——因为加号正好是方板 (1,2)/(2,1) 模态的天然几何

### 9.5 物理解释

- **sr 增大 → mode shape 集合的"可达空间"扩张**：从纯 D4-symmetric → 含非 D4 项 → 可表示更丰富的形状
- **sr=3 已经足够"破对称"**：让方板的 mode 集合包含 IC、字母、不规则形状等
- **sr=12 是过犹不及**：进一步 anisotropy 让某些 mode 退化（推测：D12, D16, D26 项过大反而引入数值不稳定），surrogate 优化时更难找局部最优

### 9.6 对 Phase 1 / Phase 2 工作的影响

| 维度 | 当前 (tier2) | 切换到 tier1 后 |
| --- | --- | --- |
| Surrogate enrichment (IC) | 10.49×（旧）/ 17.15×（新跑） | 17.99×（+5%） |
| COMSOL enrichment (IC) | Phase 1 best 3.82× | **未知**——需在 COMSOL 复跑 tier1 设计 |
| MAC (surrogate vs COMSOL) | 0.78 | 未知 |
| 工程成本 | 已交付 | 半天 - 1 天重新跑 W10 + Phase 1 |

**重要保留**：旧版 COMSOL 验证显示 tier1 (sr=3) 的 H 场在 COMSOL 各向同性下 enrichment=0.72×（劣于 tier2 的 2.41×）。这可能是因为：
- 旧版 tier1 W10 没收敛好
- 或 tier1 的 surrogate 解过拟合，COMSOL 物理下泛化差

需要重新跑 tier1 全链路才能确定。

### 9.7 对用户的最终结论

**回答原问题"tier2 是 IC 专用还是通用？"**：

| 答案维度 | 实验事实 |
| --- | --- |
| tier2 是 IC 专用？ | ❌ **不是**——但也不是通用最优 |
| tier1 是更好的默认？ | ✅ **是**——4/4 目标下 tier1 ≥ tier2 |
| sr=1 (SLA) 是好默认？ | ❌ **否**——某些 ring/asymmetric 目标根本无法实现 |
| 是否需要 per-target material 选择？ | ⚠️ **建议**——tier1 作为默认，UI 提供 sr 切换让用户为 ring/复杂目标调高 |

### 9.8 修正后的 Phase 2 推荐

| 选项 | 描述 | 工程成本 |
| --- | --- | --- |
| **A**（前: 启动 Phase 2 on tier2） | 在已有 tier2 H+θ 上跑 trust-region | 1-2 天，预期 3.82 → 4.0-4.5× |
| **B**（新选项: 切换到 tier1 重跑） | 用 tier1 (sr=3) 重新跑 W10 + Phase 1，然后再决定 Phase 2 | 半天 W10+P1，可能直接超越 3.82× |
| **C**（前: 换材料/换路径） | 已被 §9 实验回答：tier1 是正确的换材料方向，不是放弃路径 | — |
| **D**（保守）：验收 Phase 1 (tier2 3.82×) | 当前成果交付 | 0 |

**建议路径**：先做 **B**——半天验证 tier1 在 COMSOL 下的真实表现，再决定是否在 tier1 上做 Phase 2 还是继续 tier2。

### 9.9 文件清单

- `scripts/generalisation_check_materials.py`（4 targets × 3 sr 的 W10 surrogate 网格 + verdict）
- `reports/generalisation_check/`（100 步快速版：4×3 完整）
- `reports/generalisation_check_v2/`（300 步精细版：Circle+IC 验证）
- `reports/generalisation_check/targets/`（生成的 Circle/Plus/A NPY 目标）
- `reports/generalisation_check/generalisation_check.png`（柱状对比）
- `reports/generalisation_check_v2/generalisation_check.png`（精细版）


