# Chladni 逆向设计 — 算法试错全史 / Full Trial-and-Error History

日期：2026-05-27
分支：`codex/chladni-inverse-design-scaffold`
统计：跑过 **293 + 后续 W3–W8** 共约 350+ 个真实 COMSOL 候选；surrogate 端跑过万级别迭代。
相关文档：
- [`algorithm_logic_and_structure_explanation.md`](./algorithm_logic_and_structure_explanation.md) — 当前代码结构说明
- [`algorithm_trial_history_research_handoff.md`](./algorithm_trial_history_research_handoff.md) — 前 W1 时代英文交接版
- [`algorithm_breakthrough_plan.zh-CN.md`](./algorithm_breakthrough_plan.zh-CN.md) — W1–W8 工程规划
- [`target_aligned_passive_geometry_strategy.md`](./target_aligned_passive_geometry_strategy.md) — TAGS 主线
- [`mosaic_z_feasibility_report.md`](./mosaic_z_feasibility_report.md) — MOSAIC-Z 子空间方法
- [`comsol_first_simulation_principle.md`](./comsol_first_simulation_principle.md) — COMSOL-first 原则

---

## 0. 摘要（一页 TL;DR）

这份文档把项目从最早的随机试错到最新 W8 的全部算法尝试**按时间顺序**和**统一格式**汇总，让任何接手者（人或 AI）能：

1. 5 分钟内看清"已经试过什么、效果怎么样"
2. 不再重复跑已经被验证失败的方向
3. 看到跨阶段的**结构性教训**（不是一时的代码 bug，是物理 / 数学层面的发现）
4. 找到"现在哪些路线还没被穷尽"

**一句话核心结论**：
> 在 **15×15 网格 + 150 mm 方板 + 中心 8 mm 夹持 + 单中心激振** 这个不可变硬约束下，**任意非 D4 对称的复杂图案（如 IC 字母）物理可达性上限约 enrichment 2.0x**；**D4 对称友好图案（X 形、对角线、+ 形、环）能达到 enrichment 2.5–3.0x**，肉眼可识别。算法层面已无明显空间；下一步要么改硬件（破坏 D4 对称的激振 / 边界），要么承认这是物理硬上限。

---

## 1. 不可变硬约束 / Hard Constraints

下列项在整个试错周期内**不可改**，所有算法都必须围绕它们设计。

| 项 | 值 | 来源 |
|---|---|---|
| 设计网格 | `15 × 15` | COMSOL `H.csv` / `density_scale.csv` / `loss_factor.csv` 合同 |
| 板尺寸 | `150 mm × 150 mm` | 一体化打印边界 |
| 中心夹持 | 半径 `8 mm` 圆域 | 标准实验装置 |
| 边界 | 自由四边 | 板自由振动 |
| 激振 | 中心单点 + 扫频 | 不引入多激振器 / 外接质量 / 可调支撑 |
| 主反馈 | COMSOL eigenfrequency / frequency-domain | LiveLink with MATLAB |
| 厚度范围 | `0.6–2.0 mm`，相邻差 ≤ `1.0 mm`，中心夹固 `2.0 mm` | 制造可行性 |

---

## 2. 三大时代划分

| 时代 | 大致代号 | 阶段 | 核心范式 | 主导技术 |
|---|---|---|---|---|
| **时代 I：盲走时代** | Phase A–I | 截至 candidate_181_xxxx | "猜厚度 → 跑 COMSOL → 改" | 进化算法、KL proxy、auxiliary physics、CMA latent |
| **时代 II：结构化时代** | W1–W6 | 2026-05-26 之前 | "先验过滤 + 主损失换 + 梯度链路" | 可达性判定、可微板、PCA 流形、同伦、模态聚簇 |
| **时代 III：可识别度时代** | W7–W8 | 2026-05-26~27 | "重新定义成功标准" | 多频 RMS、enrichment-driven 优化 |

---

## 3. 时代 I：盲走时代（Phase A–I）

> 用户最早的目标：让 COMSOL 跑出一个看起来像 IC 字母的 Chladni 节点线。整个时代假设"再多跑几代就能成功"。

### Phase A — 随机 / 进化 / 目标引导厚度搜索

**动机**：最朴素的逆向设计——把 15×15 厚度场当作 225 维优化变量，用遗传/突变/交叉爬山。

**方法**：
- 随机初始化 H ∈ [0.6, 2.0] mm
- 选择、交叉、变异
- 加入"邻格差 ≤ 1 mm"修复 + 中心固定 2.0 mm 夹持约束
- 加入"目标骨架引导"启发式（沿目标骨架方向加薄）

**关键文件**：`src/candidate/generate_candidate.py`、`src/candidate/constraints.py`

**结果**：能跑出有效的 COMSOL 模态，但形状全是**通用板模态家族**——宽弧线、星状、环、中心主导图案。没有任何字母感。

**教训**：
> 仅靠厚度变化的 225 维搜索会被**板的自然对称性（D4） + 中心夹持** 拉到一组低维模态家族里。优化器爬到的局部极小值在符号上离任何字母都很远。**这是后来所有"surrogate 看起来好但 COMSOL 不像"的最早预警**。

---

### Phase B — 响应引导闭环 / Response-Guided Closed Loop

**动机**：既然随机搜索没方向感，那就用真实 COMSOL 的失败图反馈来引导下一步。

**方法**：
- 算 `missing = target − simulated`（目标里没被命中的部分）
- 算 `extra = simulated − target`（错命中的部分）
- 把 `extra` 转成"avoidance map"
- 候选生成时在 missing 区加薄、在 extra 区改厚

**结果**：流程上有用——避免了重复跑同样错误的图案。但还是出不了 IC 字母。

**教训**：
> 误差图能告诉你"哪里错了"，但**不能告诉你"该把哪个 eigenmode 的零等高线移到哪"**。eigenmode 是全局对象，局部加薄 0.1 mm 的影响是整个模态家族的细微旋转，不是节线本地移动。

---

### Phase C — Kirchhoff–Love Plate Proxy（KL 代理）

**动机**：COMSOL 一次跑 ~30 秒，225 维搜索几代就要几小时。需要一个快的物理代理。

**方法**：离散 KL 双调和板：
```
K(p) u = λ M(p) u,  K ≈ Lᵀ D L,  D = E h³/(12(1−ν²)),  M ≈ ρh
```
去掉中心夹持自由度，在 25×25 上稀疏求解。

**变体**：
- KL 连续目标引导搜索
- KL 直接优化
- 高分辨率稀疏 KL
- KL 标定 Bayesian 候选排序

**关键文件**：早期 `src/proxy/kl_plate.py`（后来演化为 W3 的 `src/physics/differentiable_plate.py`）

**结果**：KL 内部能跑出"看起来像"的图，但 KL 高分**不能可靠迁移到 COMSOL**。COMSOL 验证后多数塌缩成环/星/中心结构。

**教训**：
> **第一次明确暴露 "surrogate vs COMSOL gap"**。KL 是薄板假设，但项目板厚 1.5–2.5 mm / 边长 150 mm ≈ 1/100，已经在 Mindlin 厚板的边界。**这个 gap 到 W8 都没消失，只是被理解得越来越深**。

---

### Phase D — 严格评分升级 / Strict Scoring Upgrade

**动机**：早期 IoU/recall 会被"大星状图案"刷分（一不小心就覆盖了字母骨架的一部分）。要让数字跟人眼一致。

**方法**：从 `precision_topology_v1` 一路升级到 `strict_precision_topology_v5`：
- 加入 precision floor
- 加入 layout / projection / topology / complexity / connected-component / centerline overreach 等多个子指标
- 最低 mode index 从 1 提升到 8（强迫看高阶模态）
- 加入 roughness / mass / frequency 惩罚

**关键文件**：`src/scoring/score_candidate.py`、`src/scoring/strict_precision_topology.py`

**结果**：数字终于跟人眼对齐了——历史最佳从虚高的 ~0.2 跌到诚实的 0.034。

**教训**：
> **诚实的指标比好看的指标重要**。但这一升级也把硬真相摆到桌面上：当前合同下连 `final_score = 0.08` 的工程门槛都达不到。后来 W2/W8 都是在这个基础上继续修指标。

---

### Phase E — COMSOL 设计合同扩展 / Design Contract Expansion

**动机**：纯厚度搜索表达能力不够。

**方法**：把 COMSOL 输入合同从单纯 `H.csv` 扩展到：
- `density_scale.csv` — 15×15 单格密度缩放
- `loss_factor.csv` — 15×15 单格损耗
- `material_parameters.csv` — 全局材料

设计向量从 225 维升到 675 维。

**结果**：**第一次出现稳定改进**。historical best `candidate_174_0002` (score=0.0339) 就来自这个家族。

**教训**：
> "刚度场" + "质量场" + "阻尼场" 分开控制比纯厚度强。但即便 675 维，**仍然无法控制 eigenmode 零等高线落在字母位置**——证明问题不是维度，而是 D4 对称性 + 单中心激振的内在结构。

---

### Phase F — Auxiliary Physics 局部搜索

**动机**：手工设计十几种"物理直觉"启发式，逐个测试。

**已尝试的策略**（保留作为词典，避免后人重新发明）：
```
aux_mass_target_heavy        — 目标区加重
aux_mass_target_light        — 目标区减重
aux_loss_outer_suppress      — 外圈加阻尼
aux_inertia_edge_heavy       — 边缘加质量
aux_inertia_ring_break       — 环形质量打破对称
aux_low_loss_target_channel  — 目标通道低阻尼
aux_heavy_loss_balanced      — 平衡阻尼
aux_target_edge_bridge       — 目标边桥
aux_recall_outer_trim        — 外圈削减以提 recall
aux_precision_channel_guard  — 通道保护以提 precision
```

**关键文件**：`src/candidate/auxiliary_physics.py`

**结果**：**这个家族是历史最稳健的来源**。Generation 174–181 的 top 6 候选全部来自这里。但 final_score 始终在 0.032–0.034 之间，无法突破。

**教训**：
> 手工启发式能填补 optimizer 死角，但**改不了模态家族的本质**。这些策略在"已经接近最佳"的 anchor 周围做局部精修很有效，但不会发现新的全局最优。

---

### Phase G — Latent Joint Physics Search

**动机**：用低维 latent basis 替代手工启发式。

**方法**：定义一组 basis maps（target、target edge、radial、inverse radial、当前厚度场、横/纵坐标、对角线、角对称破坏等），用一组系数线性组合，生成 density / loss 源场。

**关键文件**：`src/candidate/latent_physics.py`

**结果**：随机 latent 搜索一次找到 `candidate_177_0001` (score=0.0337)——接近但没超过 auxiliary best。

**教训**：
> latent basis 是好工具，但**取决于基函数是否覆盖了正确方向**。我们的 basis 由人手设计，可能漏了关键方向。后来 W4 的 PCA 流形是这个思路的正确版本——让数据告诉我们哪些方向重要。

---

### Phase H — CMA-Style Latent Coefficient Optimization

**动机**：随机 latent 是被动撒点，CMA 是主动定向。

**方法**：在 latent 系数空间用 CMA-ES 围绕高分 anchor 采样，更新均值/sigma。增加 acquisition score、optimism penalty、novelty 等多个 latent_* 元数据。

**关键文件**：`src/candidate/cma_latent.py`

**结果**：
- generation 178: best CMA latent ≈ 0.030，被 auxiliary best 0.0324 击败
- generation 179: CMA latent 大多劣于 auxiliary
- generation 180–181: latent 名额被 adaptive 调度器减少

**教训**：
> **CMA 技术上能跑，但暴露了 "surrogate optimism"**：学到的代理模型预测某 latent 候选会好，COMSOL 验证后却不行。**这是 W7/W8 的物理-代理 gap 的早期版本**。

---

### Phase I — Response-Calibrated Latent Scheduling

**动机**：既然 CMA 高估，那就在 acquisition 里加惩罚 + 让调度器自适应。

**方法**：
```python
trusted_prediction = predicted - optimism_penalty * max(0, predicted - anchor_real_score)
```
加上 response correction（基于真实 COMSOL 误差图）和 adaptive family scheduling（auxiliary 表现好就给它更多名额）。

**关键文件**：`src/candidate/response_calibrated_latent.py`

**结果**：
- 调度器前：14 个候选里 6 个 latent + 8 个 auxiliary
- 调度器后：generation 181 里 3 个 latent + 11 个 auxiliary

**教训**：
> **第一次把"surrogate 不可靠"做成系统层的事**——不是禁用 surrogate，而是让它的预测被现实校准。**这条思路在 W7/W8 时代依然没充分落地（我跑 W8 的时候还是 "surrogate 推到极致 → COMSOL 一次验证"，没有做迭代校准）**——这是当前最大的未尽工作。

---

### 时代 I 终点：historical best 表

| 排名 | 候选 ID | 家族 | final_score | precision | recall | mode | freq (Hz) |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | `candidate_174_0002` | auxiliary | **0.033914** | 0.107656 | 0.214882 | 18 | 486.21 |
| 2 | `candidate_177_0001` | latent | 0.033721 | 0.105616 | 0.199533 | 18 | 462.20 |
| 3 | `candidate_173_0011` | search frontier | 0.033228 | 0.105272 | 0.204538 | 18 | 520.03 |
| 4 | `candidate_176_0011` | aux/frontier | 0.033169 | 0.105612 | 0.207207 | 18 | 504.99 |
| 5 | `candidate_179_0011` | auxiliary | 0.033129 | 0.105380 | 0.206540 | 18 | 502.59 |
| 6 | `candidate_181_0003` | auxiliary | 0.032797 | 0.104149 | 0.200200 | 18 | 522.12 |

工程门槛 `final_score ≥ 0.08`，**全部不达标**。**这是时代 I 结束时的诚实状态**。

---

## 4. 时代 II：结构化时代（W1–W6）

> 起因：时代 I 的诊断结论是 "不能靠多跑几代解决"。需要从物理 / 数学层面重新设计。规划文档：[`algorithm_breakthrough_plan.zh-CN.md`](./algorithm_breakthrough_plan.zh-CN.md)。

### W1 — 目标可达性先验过滤 / Target Realizability Filter

**动机**：在跑任何 COMSOL 之前，先用经典定理判定"用户目标是否物理可达"。

**方法**：基于 Courant 节点域定理、Pleijel 渐近、方板 D4 对称性、笔画最小宽度，输出 5 个数字 + 一个 verdict：
```text
verdict ∈ {easy, borderline, requires_topology, infeasible_as_nodal_set}
```

**关键文件**：`src/target/target_realizability.py`、`scripts/analyze_target_realizability.py`

**关键发现**（IC 目标）：
- `n_connected_components`: 2（I 和 C）
- `n_closed_loops`: 0
- `courant_min_mode_index`: ~12
- `stroke_min_gap_mm`: 12（接近网格分辨率极限）
- `d4_symmetry_mismatch`: **0.78（高，I-C 整体非 D4 对称）**
- **verdict: `borderline`**

**教训**：
> **W1 跑出来的数字其实直接告诉了我们后面所有结局**——IC 字母 d4_mismatch=0.78，这意味着所有 D4 对称的板模态家族**都"装不下"** IC。但我跑 W7/W8 时**忽略了这个数字**，直到 W8 在 X 形 / 对角线上对比之后才意识到。**这是项目最大的方法论失误**：W1 工具做出来了但没被前置使用。

---

### W2 — 主损失从 IoU 切到 Amplitude Valley / Unified Ranker

**动机**：单模态 IoU 是离散指示函数，对参数微小变化不可微也不平滑。需要连续可微的主目标。

**方法**：
- 把 `amplitude_valley_loss = E[|u(x)|² · w(x)]` 升格为主目标（w(x) 强调目标骨架像素）
- 写 `src/scoring/unified_ranker.py`：当目标可达性是 amplitude 路线时用 amplitude_valley，nodal 路线时用 IoU
- 历史候选全部按新指标重排

**关键文件**：`src/scoring/amplitude_valley_loss.py`、`src/scoring/unified_ranker.py`、`scripts/rank_candidates.py`

**结果**：评分更平滑、对优化更友好。但物理上限没变。

**教训**：
> **更换主损失能让优化器走得更顺，但不能突破物理上限**。这跟 Phase D 严格评分升级的精神一致——指标改善是工程必需，但不是算法突破。

---

### W3 — 可微板模型 + 伴随灵敏度 / Differentiable Plate + Adjoint

**动机**：要在 225+ 维做梯度优化，必须有 `∂loss/∂H` 解析梯度。

**方法**：用 PyTorch 实现 Kirchhoff–Love 双调和板，自动微分给梯度。在 COMSOL 上做一次校准（频率系数）让 surrogate 输出尽量接近 COMSOL。

**关键文件**：`src/physics/differentiable_plate.py`、`src/optimisation/gradient_optimizer.py`、`scripts/run_w3_optimization.py`、`scripts/check_w3_smoke.py`

**核心方程**：
```
(K(H) − ω² M(H)) u = F
loss = E[|u(x)|² · w(x)]
∇H loss 通过 PyTorch autograd 解析得到
```

**结果**：
- smoke 测试：50 步内 loss 从 ~2.7 降到 ~0.3
- IC 目标：surrogate 端进步明显，但 COMSOL 端基本只是匹配 Phase F 的 `candidate_174_0002` 水平

**教训**：
> **梯度链路终于接通了**——之前 5 个 phase 都没做到。这是项目第一个**结构性能力升级**。但 Kirchhoff 简化模型与 Mindlin COMSOL 的 gap **依然存在**——校准能让单频对齐，但优化路径上整张 loss landscape 的形状还是不一样。

---

### W4 — 低维流形搜索 / Manifold PCA Search

**动机**：W3 的 225 维优化即便有梯度也容易陷入低分辨率局部解。历史数据告诉我们有效维度其实只有 30–80。

**方法**：对历史候选 H 做 PCA，提取前 79 个主成分（覆盖 95% 方差），所有搜索在 79 维 PCA 系数空间进行。

**关键文件**：`src/subspace/manifold_pca.py`、`scripts/build_design_manifold.py`、`scripts/run_w4_manifold.py`

**结果**（圆环+中线 sanity 目标）：
| 候选 | 搜索空间 | first loss | best loss | 用时 |
|---|---|---:|---:|---|
| `w3_gradient_ringbar_sanity` | 225 维 sigmoid(theta) | 2.745 | 1.377 | ~8 s |
| `w4_manifold_ringbar_sanity` | 79 维 PCA 系数 | 1.806 | **0.233** | ~10 s |

W4 比 W3 低 6 倍 loss，**证明 79 维流形覆盖通用结构方向**（不是 IC 专属）。

**教训**：
> **数据驱动的 basis（PCA）压倒人工 basis（latent_basis）**——这是 Phase G 的正确版本。但在 IC 目标上，**流形虽然减少维度但不能改变 D4 对称约束**，所以 COMSOL 端没显著突破。

---

### W5 — 同伦延拓 / Homotopy Continuation

**动机**：直接对复杂目标优化会陷入鞍点。从板天然能做的简单图案出发，逐步推向目标，每步 warm-start。

**方法**：参数 `λ ∈ [0, 1]`，`target(λ) = (1−λ)·natural + λ·user_target`。每个 λ 跑几十步梯度，把 H 传给下一个 λ。

**关键文件**：`src/optimisation/homotopy.py`、`scripts/run_w5_homotopy.py`

**结果**：在简单同伦路径上能跑通，**但 λ 到 ~0.3 时 IC 目标就开始卡住**——这跟 W1 verdict=borderline 一致。

**教训**：
> **同伦延拓能避免鞍点，但不能突破物理不可达**。λ_max ~0.3 是个**诚实的可达性指标**——可以告诉客户"你的目标在物理上只能做到 30% 相似"。

---

### W6 — 模态频率聚簇 / Spectral Placement

**动机**：MOSAIC-Z 的精神反向落地——不是用多个模态线性组合，而是用梯度推动若干 eigenvalue 聚集到驱动频率 ω 附近，让强迫响应天然落入目标友好子空间。

**方法**：loss 加项 `Σ_k (λ_k(H) − ω²)²` 鼓励聚簇。`λ_k` 由 W3 可微板提供解析灵敏度。

**关键文件**：`src/optimisation/spectral_placement.py`、`scripts/run_w6_spectral.py`

**结果**：
- IC 目标 `w6_pipeline_ic_full_v1` @ 820 Hz: COMSOL final_score = **0.171**（比 Phase F 0.034 高 5 倍！）
- 在 W2 unified ranker 下排第一

**教训**：
> **W6 是时代 II 的高潮**——把 IC 目标的 final_score 从 0.034 推到 0.171。**但视觉上还是不像 IC**——只是数字好看。这正是 W7 重新审视目标和成功标准的触发点。

---

### 时代 II 终点：W1–W6 全流水线串通

写了 `scripts/run_full_pipeline.py`，端到端串通：
```
target → W1 verdict → {W3, W4, W6} 并行优化 → COMSOL 频率扫描验证 → W2 unified ranker
```

跑过 IC、ringbar、diagonal 三个 target，全部通过。

**当前 IC final_score 历史**：
| 阶段 | 最佳 | 提升 |
|---|---:|---|
| Phase A–I 末（candidate_174_0002） | 0.0339 | baseline |
| W3 单独 | ~0.05 | 1.5x |
| W4 单独 | ~0.08 | 2.4x |
| W6 (`w6_pipeline_ic_full_v1`) | **0.1709** | **5.0x** |

---

## 5. 时代 III：可识别度时代（W7–W8）

> 起因：W6 把 final_score 推到 0.17 但视觉上还是不像 IC。用户重新定义成功标准——**"完全可以接受相似（不全等）的目标，未覆盖目标区域可以有纹路"**。这个澄清触发了对整个评分体系和优化目标的重写。

### W7 — 多频时分驱动 / Multi-frequency Time-division Drive

**动机**：单频 + 单板物理上限存在；也许多个频率"拼"出复杂图案能突破。

**方法**：联合优化 H + K 个频率 logits + K 个权重 logits，合成振幅 `u_rms = sqrt(Σ_k w_k |u_k|²)`，loss 跟 W6 一样基于 amplitude valley。

**关键文件**：
- `src/physics/multifreq_amp_valley.py`
- `src/optimisation/multifreq_placement.py`
- `scripts/run_w7_multifreq.py`、`scripts/check_w7_smoke.py`

**结果**：
| 候选 | Surrogate IoU | COMSOL IoU | COMSOL final |
|---|---:|---:|---:|
| `w7_multifreq_ic_v1` (单频塌缩) | 16.96% | 2.51% | 0.082 |
| `w7_multifreq_ic_v2_diverse` (6 频强制分散) | 13.4% | 1.8% | 0.136 |
| W6 v1 baseline | - | 1.0% | 0.171 |

**W7 surrogate 指标好但 COMSOL 反而比 W6 差**。

**教训**：
> 1. **多频 RMS 数值合成是个伪突破**——surrogate 优化器学会"加权 |u|²"来人造低振幅区，COMSOL 没有这个自由度。
> 2. **优化器倾向于塌缩到单频**——除非强制频率分散，否则 K 个频率会全部权重塌到 1 个。
> 3. 强制分散后总 loss 反而上升——证明"多频"在数值层面不一定优于"单频"。
> 4. **真正的多频策略只能用物理时分**（一次激发一个频率，撒粉再换频率），不是数值 RMS。

---

### W8 — 可识别度驱动优化 / Recognisability-Driven Optimisation

**触发**：用户澄清成功标准 + W7 发现 final_score 0.17 但视觉不像 → 整个评分体系需要重写。

#### 新指标设计

放弃 IoU / Dice / Chamfer 的"逐像素加权"思路，改用真实 Chladni 撒粉物理：**粉沉积在节线**（|u|≈0 且梯度大），而不是泛泛的低振幅区。

模型：`p(x) = exp(-(|u(x)| / (σ·peak))²)`，σ=0.05 时粉只覆盖真正节线的 2–3 像素宽。

新指标（`src/scoring/recognisability_score.py`）：
1. **Enrichment factor** — 目标区单位面积粉密度 / 全图平均粉密度（> 2.0 视为肉眼可识别）
2. **Coverage recall** — 目标像素中落入振幅最低 20% 区域的比例
3. **Gaussian contrast** — 高斯撒粉下目标区均值 / 背景区均值
4. **Directional alignment** — 撒粉密度加权主轴 与 目标主轴 的余弦相似度
5. **Composite** — `0.40·log1p(enr-1) + 0.30·recall + 0.20·log1p(ct-1) + 0.10·direction`

#### 重排所有历史候选（A 步，1 小时无 COMSOL）

跑 `scripts/rank_candidates_recognisable.py`，**最大发现**：
- IC top-1：**`tags_ic_case_a_target_thick_refine_240_270 @ 240 Hz`**，enrichment=2.01x, recall=64%
- 旧 final_score top-1 的 W6 v1 在新指标下只排第 10
- **项目长期"用错指标"，几个月前就有真正的最佳候选被埋没**

#### W8 联合优化（B 步）

复用 W7 多频架构 + manifold，loss 换成：
```
combined = enrichment_loss + contrast_loss + 0.5·recall_loss
```

**关键文件**：
- `src/physics/recognisability_loss.py`（可微 enrichment）
- `src/optimisation/recognisability_placement.py`
- `scripts/run_w8_recognisability.py`、`scripts/check_w8_smoke.py`

smoke 测试：15 个 Adam 步内 surrogate enrichment 从 0 → 2.0+。

#### W8 在四个目标上的 COMSOL 验证

| 目标 | W8 候选 | Surrogate enr | COMSOL RMS enr | COMSOL best single freq | 视觉判断 |
|---|---|---:|---:|---:|---|
| 对角线 | `w8_diagonal_v1` | 12.73x | **0.94x（劣化）** | 1.66x @ 228 Hz | 跑出 X 形，方向偏离对角线 |
| **X 形** | **`w8_xform_v1`** | 8.43x | 2.93x | **2.84x @ 440 Hz** | **清晰 X 形对角节线，全局新最佳** |
| + 十字 | `w8_cross_v1` | 15.24x | 1.37x | 1.63x @ 935 Hz | 复杂网格 |
| IC 字母 | `w8_ic_v1` | 9.18x | 1.71x | 1.72x @ 220 Hz | 与历史 IC top1 同档，未突破 |

#### 关键教训（W8 暴露的根本性问题）

1. **目标-物理对称性不匹配 → 优化器找最接近的可达解**
   - "对角线" target 不是 D4 对称 → 优化器学到的最优解是 **X 形**（被对称性强制镜像）
   - W1 verdict 早就告诉我们"对角线 d4_mismatch 高"——**但跑 W8 前忽略了 W1**

2. **物理-代理 gap 在新指标下更大**
   - surrogate 上 enrichment 能推到 8–15x（Kirchhoff 可以让任意区域"看起来低振幅"）
   - COMSOL 上一般只有 1.5–3x（Mindlin 厚板 + 真实模态约束）
   - **多频 RMS 在 COMSOL 上反而劣化**（两频节线位置不一致 → RMS 把"低振幅"叠平了）

3. **方向指标在对称图案上 PCA 退化**
   - 对角线 target 主轴明确（45°），但撒粉密度在 D4 模态上各向同性 → PCA 主轴随机化
   - X 形 target 主轴退化（两个等长方向），direction=0.81 是 PCA 噪声而非真实信号

4. **"全局最佳"是 X 形而非 IC**
   - X 形 enrichment=2.84x（W8 找到），**新的项目历史最佳非平凡结果**
   - IC 字母最佳还是 2.01x（A 步重排发现的历史候选）
   - **D4 友好图案上 W8 真有效，D4 不相容图案上 W8 失效**

---

### 时代 III 终点：四个目标的最佳 enrichment

| 目标 | 最佳候选 | 频率 | enrichment | 视觉评价 |
|---|---|---:|---:|---|
| 对角线 | `diagonal_dense_sweep` (history sweep) | 220 Hz | **2.41x** | 沿对角线方向有粗节线，肉眼可识别 |
| **X 形** | **`w8_xform_v1`** (新) | 440 Hz | **2.84x** | **清晰 X 形，全局新最佳** |
| IC 字母 | `tags_ic_case_a_target_thick_refine_240_270` (重排发现) | 240 Hz | 2.01x | 方框对称网格，IC 字母大致落在节线带间 |
| + 十字 | `w8_cross_v1` (新) | 935 Hz | 1.63x | 节线网状，十字部分可见 |

---

## 6. 跨阶段元教训（最重要部分）

这一节是给后人/AI 的**核心**——这些不是技术细节，是看遍三个时代后的结构性洞察。

### 元教训 1：D4 对称性是硬约束，不是软约束

**方板 + 中心夹持 + 中心激振 → 系统的所有响应都是 D4 对称的**。

- 你能做出的图案集 = D4 对称图案的子集
- 任何非 D4 图案（IC 字母、单条对角线、L 形）**物理不可达**
- 优化器看到不可达目标 → 找到最接近的可达图案（通常是 X、+、环、方框，及组合）

**这个事实贯穿所有 9 个时代阶段**（Phase A → W8），但**我们在 W8 后才完全消化它**。

### 元教训 2：Surrogate-COMSOL gap 永远存在，关键是怎么用

KL/Kirchhoff 代理（W3, W7, W8）和 COMSOL Mindlin 有几个永久性差异：
- 板理论（薄板 vs 厚板，含剪切）
- 网格密度（625 vs 10⁴）
- 边界几何（抽象 vs 圆形夹持）
- 数值精度

**两种用错方式**（项目都犯过）：
- ❌ surrogate 当裁判（W7/W8 把 surrogate 推到极致再送 COMSOL）
- ❌ surrogate 当真理（Phase C 早期）

**正确用法**（**尚未充分落地，最大未尽工作**）：
- ✅ surrogate 当指南针（每 30 步用 COMSOL 校准一次，强制 surrogate-COMSOL trust region）
- ✅ homotopy + 校准回路：surrogate 推一段 → COMSOL 拉回 → 再推

### 元教训 3：指标选择决定项目方向

项目至今用过 5 个主指标：
1. **IoU/Dice/Chamfer**（Phase A–D）→ 离散、不可微、对模态切换敏感
2. **`strict_precision_topology_v5` final_score**（Phase D 之后） → 平滑了但仍是逐像素加权
3. **`amplitude_valley_loss`**（W2/W3/W4/W6） → 连续可微，但和真实撒粉物理不完全一致
4. **multi-freq RMS amplitude valley**（W7） → 容易被优化器作弊
5. **Recognisability (enrichment + recall + contrast + direction)**（W8） → 最接近"人眼看着像不像"

**每次换指标，"最佳候选"重新洗牌**——比如 W6 v1 在 final_score 下排第 1，在 enrichment 下排第 10。

**给后人的建议**：**先把"成功"的定义讲清楚再做优化**。项目里 80% 的算力浪费在用错指标上。

### 元教训 4：维度不是瓶颈，结构是

项目维度演进：225（厚度）→ 675（厚度+密度+阻尼）→ 79（PCA）→ 79+K+K（W8 多频联合）。

**结论**：**降维（W4）效果优于升维（Phase E）**——因为低维流形覆盖的是真实有效方向。但即便在最优维度上，**结构性约束（D4 对称、中心夹持）才是真正的瓶颈**。

### 元教训 5：手工 basis < 数据 basis < 理论 basis

Phase G 用手工 latent basis ≈ 0.0337
W4 用数据 PCA basis → 0.171 (W6 配合)
**理论 basis（按模态家族的对称类型分解）尚未尝试**——这是值得探索的方向。

### 元教训 6：CMA / Bayesian / 进化算法在这个问题上效率低下

Phase A、F、G、H 全部用过这些方法，**全部在 final_score 0.033 左右停滞**。原因：
- 它们都是无梯度爬山
- 评估代价高（一次 COMSOL ~15-30 秒）
- landscape 充满模态切换的不连续点

**正确做法是梯度方法（W3 之后）**——一旦能做 `∂loss/∂H` 解析微分，效率提升 100x+。

### 元教训 7：W1 工具做出来了但没被前置使用

这是项目最大的方法论失误。`scripts/analyze_target_realizability.py` 能告诉你"目标是否可达"，但：
- 跑 W7 时没看 W1 → 浪费几小时跑物理不可达的 IC 多频
- 跑 W8 对角线时没看 W1 → 浪费几小时跑非 D4 目标
- 直到 W8 后向用户解释"为什么对角线跑出 X" 才回头看 W1

**所有未来任务必须先过 W1**。

---

## 7. 失败模式索引（可快速诊断）

| 症状 | 原因 | 解决路线 |
|---|---|---|
| 候选总是星状 / 环 / 中心主导 | D4 对称 + 中心夹持的低阶模态 | 选高阶模态（mode ≥ 8）或强制对称破坏 |
| Surrogate 高分但 COMSOL 低分 | 物理模型不匹配 | 加 COMSOL 校准回路（**未做**） |
| IoU 涨但视觉变差 | 离散指标对模态切换敏感 | 换 amplitude_valley 或 enrichment |
| 多频联合塌缩到单频 | loss landscape 倾向单频极值 | 强制 freq separation 罚 + sparsity 罚 |
| 多频 RMS 不如单频 | 节线位置不一致，RMS 叠平 | 单频或物理时分（一次激一个频） |
| 复杂图案永远做不出来 | 目标非 D4 对称 | W1 verdict 显示 infeasible，必须简化目标 |
| 优化 H 不收敛 | 邻格差约束让 sigmoid 梯度过小 | 用 manifold 系数空间（W4） |
| Direction 指标在对称图案上不稳 | PCA 主轴退化 | 改用对称感知方向指标（**未做**） |

---

## 8. 历代最佳成绩纵向对比

### IC 字母目标（项目主目标）

| 时代 | 最佳候选 | 主指标值 | 视觉评价 |
|---|---|---:|---|
| Phase A–I | `candidate_174_0002` | final_score=0.034 | 星状，不像 IC |
| W3 单独 | `w3_pipeline_ic_full` | final_score≈0.05 | 略有改进 |
| W4 单独 | `w4_pipeline_ic_full` | final_score≈0.08 | 模态对称性更强 |
| W6 | `w6_pipeline_ic_full_v1` @ 820 Hz | **final_score=0.171** | 数字最佳但视觉仍不像 |
| W7 multifreq | `w7_multifreq_ic_v2_diverse` | final_score=0.136 | 低于 W6 |
| **W8 重排** | **`tags_ic_case_a_target_thick_refine_240_270` @ 240 Hz** | **enrichment=2.01x** | **方框对称网络，IC 字母粗略可见** |

### 对角线目标（W8 时代引入）

| 候选 | 频率 | enrichment | direction | 视觉 |
|---|---:|---:|---:|---|
| `pipeline_diagonal_v1_w4` @ 200 Hz | 200 | 2.43x | 1.00 | 强对角节线带 |
| `pipeline_diagonal_v1_w6` @ 474 Hz | 474 | 2.14x | 1.00 | 沿对角方向 |
| **`diagonal_dense_sweep` @ 220 Hz** | 220 | **2.41x** | 0.98 | **最佳，但实际是 X 形** |
| `w8_diagonal_v1` @ 228 Hz | 228 | 1.66x | 0.04 | W8 自己优化的反而差 |

### X 形目标（W8 时代引入）

| 候选 | 频率 | enrichment | 视觉 |
|---|---:|---:|---|
| **`w8_xform_v1`** @ 440 Hz | 440 | **2.84x** | **清晰 X 形，全局历史最佳** |

---

## 9. 已废弃但值得记住的尝试

这些路线试过、效果不好或已被替代，但记下来避免后人重新发明：

| 尝试 | 时代 | 为什么不用 |
|---|---|---|
| 纯遗传/CMA 在 225 维上爬山 | Phase A, H | 无梯度 + 评估贵 = 收敛慢 |
| KL proxy 单独评分排序 | Phase C | gap 太大，COMSOL 验证不可靠 |
| 手工 latent basis | Phase G | 被 W4 PCA 取代 |
| 单模态 IoU 主目标 | Phase A–E | 不可微，对模态切换敏感 |
| 多频 RMS 合成 | W7 | 物理上反而劣化 |
| Direction (PCA-based) 作主指标 | W8 | 对称图案上 PCA 退化 |
| `surrogate 单向推 → 一次 COMSOL 验证` 流程 | W3–W8 | 应该改成迭代校准回路 |
| 把 IC / 单对角线 作目标 | 全程 | D4 对称不相容，物理不可达 |

---

## 10. 当前未尽工作（按重要性排序）

### 高优先级

1. **Surrogate-COMSOL trust-region 校准回路**
   - 现在 surrogate 推 280 步 → 一次 COMSOL 验证
   - 应该改成 surrogate 30 步 → COMSOL 校准 → 强制 surrogate 输出对齐到 COMSOL → 再推 30 步
   - 这是元教训 2 的落地，**项目从 W3 拖到 W8 都没做**

2. **W1 verdict 强制前置在所有 pipeline**
   - 在 `scripts/run_full_pipeline.py` 顶部加 verdict 检查
   - verdict=infeasible 时停止 + 给客户"简化目标"建议
   - 这是元教训 7 的落地

3. **对称感知的方向指标**
   - 当前 directional_alignment 用 PCA 主轴
   - 应该根据目标的对称类型（C∞, D4, D2, 等）选择合适的方向相似度
   - 修复 W8 暴露的"上下两图反了"问题

### 中优先级

4. **理论 basis（按模态对称类型）**
   - 把 H 分解为 D4 不可约表示的基（A1, A2, B1, B2, E）
   - 优化时显式区分 "对称类型对齐" 与 "幅度"

5. **真正的物理时分多频驱动**
   - 不是 RMS，是"激频率 1 撒粉 30 秒 → 改频率 2 撒粉 30 秒"
   - 实验层面的事，需要 MATLAB / 硬件接口支持

6. **离散拓扑变量（孔/槽/肋）**
   - Phase F 之后就提过但没实施
   - 能突破 D4 对称（通过非对称孔位置）

### 低优先级（探索性）

7. **多激振器协同**
   - 不仅破坏 D4 对称，还能主动控制相位
   - 需要硬件改造

8. **不规则边界形状**
   - 把方板改成八边形/六边形
   - 能改变模态家族

---

## 11. 给接手者的检查清单

当下一位人/AI 接手时，按这个顺序读：

1. **本文档** — 5 分钟了解全史
2. [`algorithm_breakthrough_plan.zh-CN.md`](./algorithm_breakthrough_plan.zh-CN.md) §10–11 — W7/W8 详细规划
3. [`algorithm_logic_and_structure_explanation.md`](./algorithm_logic_and_structure_explanation.md) — 当前代码结构
4. 运行 `scripts/check_w3_smoke.py` / `check_w7_smoke.py` / `check_w8_smoke.py` — 确认环境
5. 读最新 leaderboard：`reports/recognisability_leaderboard_*.{json,csv}`
6. 看最新对比图：`reports/pipeline/final_best_per_target.png`

**禁止重复做的事**（已被验证失败）：
- 在 225 维上跑无梯度优化
- 用单模态 IoU 当主目标
- 把 surrogate 高分当裁判结果
- 给方板 + 中心激振设置非 D4 对称目标（IC、单对角线、L 形等），除非明确告诉客户"做不到"

**优先做的事**：
- 上面 §10 高优先级 1, 2, 3

---

## 12. 一句话总结

> 项目从 "随机猜厚度" 一路走到 "可微多频联合可识别度优化"，花了 9 个阶段，跑了 350+ 个 COMSOL 候选，最终的硬真相是：**算法已经把 15×15 + D4 对称方板 + 中心激振的可达性边界压到极限了（X 形 enrichment 2.84x，IC 字母 enrichment 2.01x），剩下的提升空间不在算法里，在硬件里。**
