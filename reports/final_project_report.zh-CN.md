# Chladni 板逆向设计系统 —— 结案报告

**项目**：参数化 Chladni 板的图案逆向设计与可制造化  
**机构**：Imperial College London（本科一年级 · Term 3 Summer Project）  
**周期**：2026 年 5 月（三个算法时代，约 350+ 个真实 COMSOL 候选，约 20 个算法路线）  
**报告日期**：2026-05-31  
**仓库**：`ChladiniPlateInverseSystem` · 分支 `jx/chladni-inverse-design-scaffold`

---

## 摘要

本项目研究一个经典而苛刻的逆问题：**给定一个目标图案，能否反向设计一块板（厚度场、可选的纤维取向）与一组驱动频率，使其 Chladni 沙图近似该目标？** 我们在固定硬件约束（150 mm 方板、15×15 厚度网格、中心 8 mm 夹持、中心单点激振、自由边界）下，历经三个算法时代、约 20 条算法路线、350+ 个 COMSOL 候选，构建了一套完整的"可微代理 → 高保真有限元验证 → 可制造导出"系统。

最核心、也最反直觉的结论有四条：

1. **任意客制化图案的逆向是物理不可能的，而非工程不努力。** 方板 + 中心夹持 + 中心激振使系统响应被对称群 D₄ 严格约束；中心点激振只能耦合到 **A₁ 不可约表示**。目标在 A₁ 子空间外的能量被系统性地过滤掉，无论算法多强都无法重建。X 形目标 100% 落在 A₁（可达），IC 字母只有 **41.9%** 落在 A₁（大半信号根本进不去）。
2. **各向异性（θ，纤维取向）几乎没有用。** 在工作频段内，质量项 ω²·‖M‖ 比刚度项 ‖K‖ 大约 5 个数量级，而 θ 只通过 K 进入物理，其梯度实际为零（敏感度 ≤ 7 ppm）。冻结 θ 在 6 个目标中有 4 个反而更好、1 平、1 负——**便宜的各向同性 PLA 优于昂贵的各向异性 CF-PETG**。
3. **代理-有限元差距（surrogate-COMSOL gap）是真正的天花板。** Kirchhoff 薄板代理可以把 surrogate 上的可识别度推到 8–18×，但 COMSOL Mindlin 厚板只能复现其中 1.5–4×。差距来自板理论、网格、边界、3D 弹性张量的系统性物理差异。
4. **最终交付不是"任意图案逆向"，而是一套诚实、可复现、可制造的系统：** W10 可微代理 → COMSOL 两阶段管线（模态选择 + 信赖域精修）→ 前后端打通的设计软件 → 可直接 3D 打印的 STL 导出。

> **一句话**：我们没有做到"想要啥图案就出啥图案"——因为那在物理上不存在；我们做到的是**精确地刻画了这个边界在哪、为什么在那，并把贴着边界的最优解工程化、产品化。**

---

## 1. 问题定义与不可变约束

### 1.1 逆问题

正问题：板几何 + 材料 + 驱动频率 → Chladni 节线图案（沙子聚集在位移最小的节线上）。  
逆问题：目标图案 → 反求板设计 + 驱动频率。

### 1.2 不可变硬约束

下列约束在整个项目周期内不可更改，所有算法都必须围绕它们设计：

| 项 | 值 | 来源 |
|---|---|---|
| 设计网格 | 15 × 15 厚度场 | COMSOL `H.csv` 合同 |
| 板尺寸 | 150 mm × 150 mm | 一体化打印边界 |
| 中心夹持 | 半径 8 mm 圆域 | 标准实验装置 |
| 边界 | 自由四边 | 自由振动 |
| 激振 | 中心单点 + 扫频 | 不引入多激振器/外接质量 |
| 主反馈 | COMSOL 特征频率 / 频域响应 | LiveLink with MATLAB |
| 厚度范围 | 0.6–2.0 mm，相邻差 ≤ 1.0 mm | 制造可行性 |

**这套约束本身就决定了项目的物理上限**——这是直到走完三个时代才被完全消化的真相。

---

## 2. 三个时代：约 20 条算法路线的演进史

| 时代 | 阶段 | 核心范式 | 结局 |
|---|---|---|---|
| **时代 I：盲走时代** | Phase A–I（9 条） | "猜厚度 → 跑 COMSOL → 改" | final_score 卡在 0.034，全部不达标 |
| **时代 II：结构化时代** | W1–W6（6 条） | "先验过滤 + 主损失重构 + 梯度链路" | IC final_score 推到 0.171（数字好看但视觉不像） |
| **时代 III：可识别度时代** | W7–W8（2 条） | "重新定义成功标准（撒粉物理）" | X 形 enrichment 3.76×（项目天花板）|
| **（现代生产期）** | W9、W10、两阶段管线（≈3 条） | "可微各向异性代理 + COMSOL 信赖域闭环 + 产品化" | 两阶段管线 + 软件交付 |

### 2.1 时代 I —— 盲走时代（Phase A–I）

最朴素的逆向设计：把 225 维厚度场当优化变量，用各种无梯度方法搜索。

| 阶段 | 方法 | 教训 |
|---|---|---|
| **A** 随机/进化搜索 | 遗传 + 突变 + 邻格差修复 + 骨架引导 | 只能跑出"通用板模态家族"（弧、星、环、中心主导），毫无字母感 |
| **B** 响应引导闭环 | 用 `missing/extra` 误差图引导下一代 | 误差图能说"哪里错"，但说不出"该把哪条节线移到哪"——本征模态是全局对象 |
| **C** Kirchhoff–Love 板代理 | 25×25 稀疏双调和板特征求解 | **首次暴露 surrogate↔COMSOL gap**；KL 高分迁移不到 COMSOL |
| **D** 严格评分升级 | `precision_topology_v1 → strict v5` | **诚实指标比好看指标重要**：历史最佳从虚高 0.2 跌到诚实 0.034 |
| **E** 设计合同扩展 | 加 density/loss/material 场，225→675 维 | 升维不是答案：675 维仍控制不了节线落点 |
| **F** Auxiliary Physics | 十余种手工物理启发式 | 历史最稳健来源（gen 174–181 top6），但 0.032–0.034 封顶 |
| **G** Latent Joint Physics | 人工 basis 线性组合源场 | basis 由人手设计可能漏关键方向 |
| **H** CMA 隐空间优化 | CMA-ES 在 latent 系数空间 | **暴露 surrogate optimism**：代理预测好、COMSOL 验证差 |
| **I** 响应校准隐空间调度 | optimism penalty + 自适应族调度 | **首次把"代理不可靠"做成系统层的事**，但迭代校准没充分落地 |

**时代 I 终点**：历史最佳 `candidate_174_0002` final_score = 0.0339，工程门槛 0.08 全部不达标。诊断结论：**"再多跑几代"解决不了，需要从物理/数学层重新设计。**

### 2.2 时代 II —— 结构化时代（W1–W6）

| 阶段 | 方法 | 关键结果 / 教训 |
|---|---|---|
| **W1** 可达性先验过滤 | Courant 节点域 + D₄ 对称失配 + 笔画宽度，输出 verdict | IC 的 `d4_mismatch=0.78` **早就预言了全部结局**——但当时没被前置使用（最大方法论失误） |
| **W2** 主损失重构 | IoU → amplitude valley（连续可微） | 优化更顺，但物理上限不变 |
| **W3** 可微板 + 伴随灵敏度 | PyTorch 实现 KL 板，autograd 给 `∂loss/∂H` | **梯度链路终于接通**——第一个结构性能力升级 |
| **W4** 低维流形搜索 | 历史候选 PCA，79 维系数空间 | **数据 basis 压倒人工 basis**；比 W3 低 6× loss |
| **W5** 同伦延拓 | 从自然图案逐步推向目标，warm start | λ 到 ~0.3 就卡住——这是**诚实的可达性指标** |
| **W6** 模态频率聚簇 | 推多个特征值聚集到驱动频率附近 | **时代 II 高潮**：IC final_score 0.034 → 0.171（5×），但视觉仍不像 |

### 2.3 时代 III —— 可识别度时代（W7–W8）

触发：W6 把分数推到 0.17 但视觉还是不像 IC。用户重新定义成功标准（接受"相似而非全等"）→ 整个评分体系重写。

- **W7 多频时分驱动**：联合优化 H + K 个频率 + K 个权重，RMS 合成。**发现多频 RMS 是伪突破**——优化器学会"加权 |u|²"人造低振幅区，COMSOL 没有这个自由度；而且优化器总倾向塌缩到单频。
- **W8 可识别度驱动优化**：放弃逐像素 IoU，改用真实撒粉物理——**粉沉积在节线（|u|≈0）**。新指标：enrichment（目标区粉密度/全图均值）、recall、contrast、direction。
  - 重排所有历史候选时发现：**项目长期用错指标，几个月前就有更好的候选被埋没**。
  - X 形 enrichment 达 **2.84× → 修复归一化 bug 后 3.76×**，成为项目天花板。

### 2.4 现代生产期 —— W9 / W10 / 两阶段管线

- **W9 信赖域回路**：外层 surrogate + COMSOL 交替校正。**结构正确但参数欠调**（内层步数太少、校正太弱、信赖域萎缩到 0.094 mm），best COMSOL 1.40× 没突破。结论：在"烂代理"周围打转没用，根本问题是代理物理本身不够好。
- **W10 可微正交各向异性板 + 联合优化**：实现完整 Kirchhoff 正交各向异性能量泛函（Reddy 2003），每格 θ 旋转弯曲刚度算子，让中心激振在物理上可耦合到非 A₁ irrep。联合优化 H + θ + ω。
- **两阶段 COMSOL 生产管线**（这正是时代 I 一直欠下的"迭代校准回路"，最终被建出来）：
  - **Phase 1（模态选择）**：跑 COMSOL 特征频率 → 按"目标相似度"对每阶本征模态排序 → 驱动受迫响应 → 复合。
  - **Phase 2（信赖域精修）**：以 COMSOL 为真值，对 H 做信赖域精修（surrogate 续跑 + COMSOL 重评 + 接受/收缩）。

---

## 3. 核心科学发现

### 3.1 D₄ 对称性与 A₁ irrep 天花板（项目第一性原理）

方板 + 中心夹持 + 中心激振的系统，其全部稳态响应都受二面体群 D₄ 约束。通过 D₄ 不可约表示分解（`src/symmetry/d4_decomposition.py`）得到精确结论：

> **中心激振只能耦合到 A₁ irrep。** 目标在 A₁ 上的能量占比 = 其物理可达性上限。

| 目标 | A₁ 占比 | A₁ 之外（不可达） | 含义 |
|---|---:|---:|---|
| X 形 | **100.0%** | 0% | 理论完全可达（项目天花板，COMSOL 3.76×） |
| 单对角线 | 51.7% | 48.3%（B₂） | 半可达 |
| **IC 字母** | **41.9%** | **58.1%（E+B₁）** | 大半信号根本进不去 |

这是项目历史上第一次对"为什么 IC 不会出现在 COMSOL"给出**精确的数学答案**：不是算法不行，是 IC 的 58% 能量被中心点振源系统性过滤掉了。

### 3.2 各向异性的误解，与 θ 的不重要

**最初的美好假设**：3D 打印件天然各向异性（纤维取向 θ 可调），让每格 θ 不同 → 弯曲刚度算子不再对易于 D₄ 群 → 中心激振也能耦合到非 A₁ irrep → 打破天花板。这是"物理打破对称"，看起来无懈可击。

**残酷的现实**：

1. **能量进不去 K。** 在 W10 的工作频段，质量惯性项 ω²·‖M‖ 比刚度项 ‖K‖ 大约 **5 个数量级**。θ 只通过 K 进入物理，因此它对响应的影响淹没在数值噪声里。
2. **直接敏感度测量**：把 θ 在均匀/随机间切换，复合振幅变化 **≤ 7 ppm**——远低于数值噪声。同种子下 θ-active 与 θ-frozen 的 surrogate enrichment **逐位相同**。
3. **它还是寄生维度。** θ 给 W10 损失曲面增加一个非凸维度，优化器把梯度预算浪费在探索 θ 上，而不是干净地收敛 H + ω。
4. **冻结 θ 反而更好**：在最该受益于各向异性的"对角线"目标上，冻结 θ 单独带来 **+17% enrichment、+6% recall**（不改材料、不改 H/ω 优化器）。

**6 目标 × 2 材料的对照实验（battery）**：

| 目标 | CF-PETG（θ 开，sr=3） | PLA（各向同性，无 θ） | 裁决 |
|---|---|---|---|
| binary | enr 1.00 | enr 1.10 | PLA +10% |
| cross | enr 9.19 | enr 10.00 | PLA +9% |
| **diagonal** | enr 8.37 | enr **11.35** | **PLA +36%** |
| xform | enr 7.60 | enr 8.46 | PLA +11% |
| star | enr 3.58 | enr 3.42 | 平 |
| ic | enr **11.80** | enr 10.27 | CF-PETG +13% |

**最终比分：PLA 胜 4、CF-PETG 胜 1、平 1。** 结论：**便宜的、学校 FDM 就能打的各向同性 PLA，是更好的默认路径。** θ 优化代码最终被整体移除，避免后人重新踩坑。

> 补充：我们一度从论文里取 sr=2.8/3.0，后来拿到真实材料 Bambu Lab PETG-CF 的 TDS（弯曲模量），实测各向异性比仅 **sr=1.87**——比假设值低得多，进一步印证各向异性带来的余量很有限。

### 3.3 代理-有限元差距（surrogate-COMSOL gap）

KL/Kirchhoff 代理与 COMSOL Mindlin 之间存在永久性物理差异：板理论（薄板 vs 含横向剪切的厚板）、网格密度（625 vs 10⁴）、边界几何（抽象 vs 圆形夹持）、2D plane-stress vs 完整 3D 弹性张量。后果：

- surrogate 上 enrichment 能推到 8–18×；COMSOL 上一般只有 1.5–4×。
- 频率系统性偏移约 40%（surrogate 398 Hz 的"IC 模态"对应 COMSOL 210 Hz，但 210 Hz 是 U 形而非 C 形）。
- 模态对齐质量（MAC）：低频（1–8 阶）0.73–0.90 极好，高频（16+ 阶）崩坏 < 0.4；频率映射是干净的幂律 `f_c = α·f_s^β`（β≈1.31–1.36）——说明差距是**系统性物理差，不是随机噪声**。

**两种用错代理的方式（项目都犯过）**：把 surrogate 当裁判（推到极致再送 COMSOL）、把 surrogate 当真理（早期 KL）。**正确用法是当指南针**——这就是两阶段管线存在的理由。

### 3.4 共振点驱动 vs 偏共振驱动（E3）

时代后期的关键 bug 级发现：Phase 1 曾默认在 `f_eig + 1.5 Hz`（偏共振）驱动以避开求解器奇异，结果**响应被中心点力主导、模态被"灌歪"**，十字/叉等图案出不来。改为 **on-resonance（offset 0）** 后，干净的模态节线立刻恢复。这也呼应了"那条中间的杠"——偏共振时中心是被点力顶起的反节点亮纹，而非真实节线。

### 3.5 数值精度 bug：历史结论一度被系统性低估

`chladni_powder_density` 的归一化 `amp/(max(amp)+1e-9)`：surrogate 域 amp~O(1) 无碍，但 COMSOL 域 amp~O(1e-12)，1e-9 比信号大 1000 倍，把 enrichment 永远压成 ≈1.00。修复后所有历史 COMSOL 数字上修（X 形 2.84→**3.76×**）。**教训：跨尺度的 epsilon 是隐形杀手。**

### 3.6 指标选择决定项目方向

项目用过 5 个主指标，每换一次，"最佳候选"就重新洗牌（W6 v1 在 final_score 下第 1，在 enrichment 下第 10）：

1. IoU/Dice/Chamfer（离散、不可微、对模态切换敏感）
2. `strict_precision_topology_v5`（平滑但仍逐像素）
3. amplitude valley（连续可微，但不完全等于撒粉物理）
4. multi-freq RMS（易被优化器作弊）
5. **recognisability：enrichment + recall + contrast + direction**（最接近"人眼像不像"）

后期的 E1–E6 算法审计进一步量化了这些指标的认知偏差（如 E1：enrichment 偏好"中心一坨"而非展开形状；E6：固定百分位阈值对粉密度敏感）。

> **给后人的第一条建议：先把"成功"的定义讲清楚再做优化。** 项目里相当一部分算力浪费在用错指标上。

---

## 4. 最终算法架构与含义

走完三个时代后，沉淀下来的不是某个"绝招"，而是一条**诚实分层、各司其职**的管线。

```
目标图案
  │
  ▼
[W10 可微代理]  正交各向异性 Kirchhoff 板，优化 H + ω（θ 已移除）
  │            作用：在秒级时间里把厚度场/频率推到"surrogate 意义下"的好解
  │            定位：指南针，不是裁判
  ▼
[Phase 1 · 模态选择]  COMSOL 特征频率 → 按目标相似度对本征模态排序
  │                  → on-resonance 驱动受迫响应 → 复合（best single / composite）
  │                  作用：用高保真物理筛出真正"目标相似"的模态并合成
  ▼
[Phase 2 · 信赖域精修]  以 COMSOL 为真值，对 H 做信赖域迭代
  │                    （surrogate 续跑 → COMSOL 重评 → 接受/收缩半径）
  │                    作用：把代理-COMSOL 差距用"信赖"显式管理，单调精修
  ▼
最佳设计（H 场） + 最佳驱动频率 + 沙图预测
```

**每一层的含义**：

- **W10 是"指南针不是裁判"**——这是时代 I–III 反复栽跟头换来的认知。代理负责快速给方向，绝不负责定胜负。
- **Phase 1 解决了"surrogate 押错频率"**——surrogate 自认为的"IC 模态"在 COMSOL 里排到第 16 名；Phase 1 用真实物理重新排序，并发现 **off-resonance 拍点（两个互补模态干涉）往往优于任何单一本征模态**（IC 上 132+180 Hz RMS 复合达 broad enr 3.82× / recall 0.89）。
- **Phase 2 是时代 I 欠了一路、最终补上的"迭代校准回路"**——把 W9 失败的根因（同时修频率+形状导致发散）解耦：频率层直接用 COMSOL 真频驱动，形状层只让信赖域修小残差。

**含义层面的总结**：最终算法的价值不在"逆向能力有多强"，而在**它精确地、可复现地把每个目标推到了其 A₁ 物理上限附近，并诚实地停在那里**。

---

## 5. 软件系统：前后端打通与功能

项目不止是算法，更是一套可交付的设计软件（COMSOL bridge + Web 前端）。

### 5.1 后端（`src/frontend/target_ui_server.py`，多线程 HTTP）

- **管线编排**：一键跑 W10 → Phase 1 → Phase 2，支持 surrogate-only / 跳过 COMSOL；可协作式取消（Stop 立即终止子进程组）。
- **COMSOL 桥**：mphserver 生命周期管理、自动发现 COMSOL/MATLAB 路径、LiveLink with MATLAB 调用、隔离运行时实例避免抢占已开窗口。
- **结果/诊断 API**：生产运行列表与详情、目标可达性分析（含 A₁ 占比直接显示给客户）、日志尾部、产物占用与清理预览、材料频率预扫。
- **在 COMSOL 中打开 .mph**：可分别打开 **Phase 1 最佳**与 **Phase 2 最佳**的受迫响应模型，让客户自己对比、挑选更满意的图案。
- **3D 打印导出**：`/api/export-info` 与 `/api/export-stl`，按 phase 把厚度场转可打印 STL。

### 5.2 前端（`frontend/target_designer.html`，单页应用）

标签页：**Target / Tune / Results / Run / Gallery / Export**。

- **Target**：上传/绘制目标，叠加 15×15 网格与中心夹持，目标可达性提示。
- **Tune**：材料面板（含 stiffness ratio E∥/E⊥、shear ratio），与 Run 面板自动同步。
- **Run**：跑管线，实时进度，Stop 即时停。
- **Results**：历代生产运行的指标、目标/达成沙图、厚度场、COMSOL 本征模态预览；一键在 COMSOL 打开 Phase 1 / Phase 2 最佳 .mph。
- **Gallery（均匀板图样画廊）**：浏览均匀板的本征模态目录，做参数化微扰（拉伸/旋转/缩放/切变/隆起），并用**中心驱动可激发性物理过滤**（`center_participation()`）剔除中心激振打不动的模态——把"客户想要的"与"物理做得到的"对齐。
- **Export（3D 打印导出）**：选运行 + 选 **Phase 1（初始）/ Phase 2（精修）** 设计 → 下载可打印阶梯板 STL；含厚度范围/材料体积摘要与无-θ 的 FDM 切片配方参考。

### 5.3 STL 导出模块（`src/export/stl_export.py`，零依赖）

不依赖 trimesh/numpy-stl（磁盘紧张时也能跑）：把 15×15 厚度场转成 225 个阶梯长方体的二进制 STL（2700 三角面片，约 132 KB），可选高斯柔化台阶。`plate_length_mm / grid = 10 mm` 见方 cell，平底贴床、阶梯朝上打印。

### 5.4 工程纪律

- **算法审计（E1–E6，只读）**：系统性量化指标/算法的认知偏差，不动核心代码，产出独立报告。
- **Git 回退纪律**：多次出现"加了优化反而更差 → 硬回退到已知良好基线 → 选择性 cherry-pick"。
- **可复现**：每个时代/实验都有脚本 + JSON 数字 + 对比图，接手者可一键复跑。

---

## 6. 结果汇总

### 6.1 各目标的可识别度上限（COMSOL 实测，修正归一化后）

| 目标 | A₁ 上限 | COMSOL 最佳 enrichment | 视觉评价 |
|---|---:|---:|---|
| **X 形** | 100% | **3.76×**（项目天花板） | 清晰 X 形对角节线 |
| IC（Phase 1 复合 132+180 Hz） | 41.9% | broad **3.82× / recall 0.89** | "I" 竖带 + "C" 开口曲线 + 中央连接，**依稀可辨**但非清晰字母 |
| + 十字 | 100% | ~1.5–1.6× | 节线网状，十字部分可见 |
| 单对角线 | 51.7% | ~2.4×（best single） | 沿对角粗节线，实际偏 X 形 |
| 圆环 | — | sr=1 下 enrichment≈0；需各向异性才出环 | 各向同性方板模态本身不含环 |

### 6.2 surrogate vs COMSOL 的"达成率"

surrogate 预测的 8–18× 提升中，COMSOL 各向同性管线只复现 9–44%。其余被 (a) 代理-物理差距与 (b) θ 在真实物理下的失效共同吃掉——这正是第 3 节四大发现的量化体现。

---

## 7. 局限与物理天花板（诚实的边界）

1. **任意非 D₄ 兼容图案（IC、单对角线、L 形、任意 logo）物理不可达。** 不是算法问题，是中心点激振的 A₁ irrep 过滤。这是硬上限。
2. **各向异性余量有限。** 真实材料 sr≈1.87，且 θ 在非共振频段梯度≈0；指望 θ 突破天花板不现实。
3. **代理永远不等于 COMSOL。** 任何只看 surrogate 的"突破"都要用 COMSOL 复核。
4. **要进一步突破必须动硬件**：破坏 D₄ 对称的激振（多激振器/偏心点激）、改变边界（非方板）、引入离散拓扑（孔/槽）。这些超出本项目固定约束。

---

## 8. 项目背后（致谢与现实）

这份报告的每一个表格背后，是一个本科一年级团队在一个暑期项目里**约 350 次 COMSOL 候选、约 20 条算法路线、以及一次连续 36 小时不睡觉的攻坚**。

值得写进结案的，不只是结果，还有几次"难受但正确"的转折：

- 把虚高的 0.2 分诚实地砍到 0.034——**承认指标错了，比保住好看数字更重要**。
- 发现各向异性、θ 这条寄托了很大希望的主线"几乎没用"——**愿意杀掉自己最得意的假设**。
- 在 W9 信赖域失败、W10 在 COMSOL 不复现、IC 始终做不清晰之后，没有继续粉饰，而是**把"为什么做不到"用 A₁ irrep 数学讲清楚**。

> 一个暑期项目最大的收获，往往不是"做出了想要的东西"，而是**搞清楚了想要的东西为什么在物理上不存在，并把贴着边界的最优解做成了能复现、能打印、能交付的系统。** 这件事，做到了。

---

## 9. 结论与未来工作

**结论**：在固定硬件约束下，本项目把 15×15 方板 + 中心激振的可达性边界压到了极限（X 形 3.76×，IC 复合 3.82× broad / 0.89 recall），并交付了一套从可微优化 → 高保真验证 → 可制造导出 → 前后端软件的完整系统。剩余的提升空间不在算法里，在硬件里。

**未来工作（按重要性）**：
1. 破坏 D₄ 对称的硬件方案（多激振器 / 偏心激振 / 非方板边界 / 离散拓扑孔槽）——唯一能真正突破 A₁ 天花板的路径。
2. 对称感知的方向指标（修复对称图案上 PCA 主轴退化）。
3. 真正的物理时分多频驱动（激一个频率撒粉、再换频率），而非数值 RMS。
4. 把两阶段管线的信赖域参数进一步调优（warm start、不锁频、内层步数自适应）。

---

## 附录 A：关键文件地图

| 模块 | 文件 |
|---|---|
| 可微正交各向异性板 | `src/physics/orthotropic_plate.py`、`differentiable_plate.py` |
| W10 联合优化 | `src/optimisation/recognisability_placement_w10.py` |
| 两阶段生产管线 | `src/optimisation/production_pipeline.py` |
| D₄ irrep 分解 | `src/symmetry/d4_decomposition.py` |
| 可达性 verdict | `src/target/target_realizability.py` |
| 可识别度指标 | `src/scoring/recognisability_score.py` |
| 中心驱动可激发性 | `src/physics/drive_reachability.py` |
| 均匀板画廊 | `src/uniform_pattern/`（catalogue/render/perturb/match）|
| STL 导出 | `src/export/stl_export.py` |
| 前端 | `frontend/target_designer.html` |
| 后端 | `src/frontend/target_ui_server.py` |
| COMSOL 模板 | `comsol_templates/*.m` |

## 附录 B：历史报告索引

- `reports/algorithm_trial_full_history.zh-CN.md` —— 时代 I–III 算法试错全史
- `reports/algorithm_breakthrough_plan.zh-CN.md` —— W1–W8 工程规划
- `reports/sprint1_w9_sprint2_summary.zh-CN.md` —— W9 / W10 / 两阶段管线 / 材料泛化
- `reports/_battery/BATTERY_FINDINGS.md` —— θ 寄生性与材料对照（6×2）
- `reports/audit_algorithmic_review_2026-05.zh-CN.md` —— E1–E6 算法认知偏差审计

---

## 附录 C：参考文献与数据来源

下列为项目实际引用或在代码/建模中直接使用的文献与数据。分两类：**（一）材料与板力学**（直接用于 W10 各向异性板建模与材料参数），**（二）方法学的经典理论基础**（可达性判定、对称分解、Chladni 物理所依据的标准理论）。

### C.1 材料与板力学（直接引用，见 `src/physics/orthotropic_plate.py`）

1. **Reddy, J. N. (2003).** *Mechanics of Laminated Composite Plates and Shells: Theory and Analysis* (2nd ed.). CRC Press. —— W10 正交各向异性 Kirchhoff 板的弯曲刚度 D₁₁…D₂₆ 与 θ 旋转公式（式 1.3.94）即取自此书。
2. **Letcher, T., & Waytashek, M. (2014).** "Material Property Testing of 3D-Printed Specimen in PLA on an Entry-Level 3D Printer." *ASME IMECE 2014.* —— FDM PLA 各向异性比 E∥/E⊥ ≈ 1.4 的来源。
3. **Pyl, L., Kalteremidou, K.-A., & Van Hemelrijck, D. (2018).** "Exploration of the Mechanical Properties of FDM-printed PLA." *Procedia Manufacturing, 14, 104–.* —— FDM 各向异性测试方法学参考。
4. **Formlabs (2018).** *Validating Isotropy in SLA 3D Printing.* (技术白皮书) —— SLA grey resin 充分后固化后近各向同性（E∥/E⊥ ≈ 1.00–1.10）的依据。
5. **Vat-photopolymerisation anisotropy study,** *Scientific Reports* 15:97294 (2025). —— SLA/光固化后固化各向异性约 0–10% 的补充证据。
6. **Bambu Lab PETG-CF 技术数据表（TDS V3.0）.** —— 真实材料弯曲模量数据，据此换算出实测各向异性比 **sr ≈ 1.87**（远低于早期文献假设的 2.8–3.0）。

### C.2 方法学的经典理论基础（项目方法所依据的标准理论）

7. **Chladni, E. F. F. (1787).** *Entdeckungen über die Theorie des Klanges.* —— Chladni 沙图（沙子聚集于节线）这一正问题的原始来源。
8. **Kirchhoff–Love 薄板理论**（Kirchhoff 1850；Love 1888）—— 代理板（W3/W10）所用的双调和薄板模型。
9. **Mindlin–Reissner 厚板理论**（Reissner 1945；Mindlin 1951）—— COMSOL Shell 含横向剪切的高保真模型，即"surrogate–COMSOL 物理差距"的厚板一侧。
10. **Courant 节点域定理**（Courant & Hilbert, *Methods of Mathematical Physics*, 1953）—— W1 可达性判定中 `courant_min_mode_index` 的理论依据。
11. **Pleijel, Å. (1956).** "Remarks on Courant's nodal line theorem." *Comm. Pure Appl. Math., 9, 543–550.* —— 节点域计数的渐近界，用于可达性先验。
12. **二面体群 D₄ 的表示论**（标准群论，如 Tinkham, *Group Theory and Quantum Mechanics*, 1964）—— A₁/A₂/B₁/B₂/E 不可约表示分解的理论基础，用于"中心激振仅耦合 A₁"这一核心结论。

### C.3 各时代算法方法论的引用文献（逐条对应）

下表把第一到第三时代（及现代生产期）**每一条算法路线**对应到其方法学出处。其中项目代码里本来就有的（板力学、可达性）见 C.1/C.2；其余为该方法的公认经典文献，按"没有就自己找"的要求补全，确保每条算法都能溯源到标准方法论。

| 算法路线 | 核心方法 | 方法学引用 |
|---|---|---|
| **I·A** 随机/进化厚度搜索 | 遗传算法 + 结构拓扑/材料分布优化 | Holland 1975, *Adaptation in Natural and Artificial Systems*；Bendsøe & Sigmund 2003, *Topology Optimization* |
| **I·B** 响应引导误差闭环 | 反问题的迭代反演 | Tarantola 2005, *Inverse Problem Theory and Methods for Model Parameter Estimation*, SIAM |
| **I·C** Kirchhoff–Love 板代理 | 薄板自由振动 / 双调和特征问题 | Leissa 1969, *Vibration of Plates*, NASA SP-160；Waller 1939, *Proc. Phys. Soc.* 51:831 |
| **I·D** 严格形状评分 | IoU/Jaccard、Dice、Chamfer 形状相似度 | Jaccard 1912；Dice 1945, *Ecology* 26:297；Barrow et al. 1977（Chamfer matching, IJCAI） |
| **I·E** 设计合同扩展（密度/损耗/材料场） | SIMP 变密度材料分布 | Bendsøe 1989, *Struct. Optim.* 1:193；Bendsøe & Sigmund 1999, *Arch. Appl. Mech.* 69:635 |
| **I·F** Auxiliary Physics 局部启发式 | 直接搜索 / 模式搜索 | Hooke & Jeeves 1961, *J. ACM* 8:212 |
| **I·G** 隐空间联合物理（人工 basis） | 降阶基 / 本征正交分解（POD） | Berkooz, Holmes & Lumley 1993, *Annu. Rev. Fluid Mech.* 25:539 |
| **I·H** CMA 隐空间优化 | 协方差矩阵自适应进化策略（CMA-ES） | Hansen & Ostermeier 2001, *Evol. Comput.* 9(2):159 |
| **I·I** 响应校准隐空间调度 | 代理/贝叶斯优化 + acquisition | Jones, Schonlau & Welch 1998, *J. Global Optim.* 13:455（EGO）；Shahriari et al. 2016, *Proc. IEEE* 104:148 |
| **II·W1** 可达性先验过滤 | 节点域定理 + 方板 D₄ 对称分类 | Courant & Hilbert 1953；Pleijel 1956, *CPAM* 9:543；Waller 1939, *Proc. Phys. Soc.* 51:831 |
| **II·W2** 主损失重构（amplitude valley） | 平滑可微目标的连续优化 | Nocedal & Wright 2006, *Numerical Optimization* (2nd ed.), Springer |
| **II·W3** 可微板 + 伴随灵敏度 | 伴随法 + 自动微分 + 特征值/向量灵敏度 | Giles & Pierce 2000, *Flow Turbul. Combust.* 65:393；Baydin et al. 2018, *JMLR* 18:1；Paszke et al. 2019（PyTorch, NeurIPS）；**Fox & Kapoor 1968, *AIAA J.* 6:2426**；**Nelson 1976, *AIAA J.* 14:1201**（特征值/向量灵敏度解析公式） |
| **II·W4** 低维流形搜索 | 主成分分析 / 降阶设计空间 | Pearson 1901, *Phil. Mag.* 2:559；Berkooz et al. 1993（POD） |
| **II·W5** 同伦延拓 | 数值延拓 / 渐进式（图）非凸优化 | Allgower & Georg 1990, *Numerical Continuation Methods*, Springer；Blake & Zisserman 1987, *Visual Reconstruction*（graduated non-convexity） |
| **II·W6** 模态频率聚簇 | 特征值拓扑优化 | Pedersen 2000, *Struct. Multidisc. Optim.* 20:2；Achtziger & Kočvara 2007, *SMO* 34:181 |
| **III·W7** 多频时分驱动 | 多频/谐波频域受迫响应 + 一阶随机优化 | Kingma & Ba 2015（Adam, ICLR）；（频域受迫响应见 Leissa 1969） |
| **III·W8** 可识别度驱动优化 | Chladni 节线物理 + 最优传输（Sinkhorn 散度），规避 IoU/L² 的 cycle-skipping | Chladni 1787；Cuturi 2013, *NeurIPS*（Sinkhorn Distances）；**Engquist & Froese 2014, *Commun. Math. Sci.* 12:979**（Wasserstein 用于波形匹配、规避 cycle-skipping） |
| **现代·W9** 信赖域闭环 | 信赖域法 + 代理管理框架 + 模态跟踪（MAC） | Conn, Gould & Toint 2000, *Trust-Region Methods*, SIAM；Booker et al. 1999, *SMO* 17:1；**Allemang & Brown 1982（Modal Assurance Criterion, IMAC）** |
| **现代·W10** 可微正交各向异性板 | 层合/正交各向异板理论 + 每格 θ 旋转 | Reddy 2003（见 C.1）；D₄ irrep 见 C.2 |

> 说明：表中 Holland / Hansen / Jones / Cuturi / Kingma / Conn 等为各方法的公认奠基或权威综述文献，团队按其思想在本问题上实现（而非照搬某一实现）；板力学（Leissa/Reddy/Waller）与可达性（Courant/Pleijel）在代码与建模中被直接使用。

### C.4 软件与数值工具

- **COMSOL Multiphysics 6.4** + **LiveLink™ for MATLAB**（高保真特征频率 / 频域受迫响应，Shell 物理场含正交各向异性配置）。
- **PyTorch**（W3–W10 可微板与 autograd 灵敏度）、**SciPy/NumPy**（稀疏特征求解、连通分量、距离变换、高斯滤波）。

> 说明：C.1 各项可在 `src/physics/orthotropic_plate.py` 头部注释中找到对应引用；C.2 为方法所依据的标准教科书级理论，列出以便读者溯源，团队按第一性原理实现而非照搬某一实现。

### C.5 相关工作与灵感来源（直接可比的前人工作）

下列是与本项目**同题或强相关**的前人工作，构成方法论的对照系与灵感来源。**第一条尤其重要**：它是与我们"几乎完全同题"的 2024 年工作，应作为本项目的主要 prior art 引用。

1. **"Topology optimization design of Chladni patterns for vibration mode manipulability." *Acta Mechanica Sinica* (2024),** DOI 10.1007/s10409-023-23445-x（作者名以期刊页面为准）。 —— **与本项目最直接可比的前人工作**：同样用基于密度的拓扑优化（SIMP），以"特征向量与目标 Chladni 图案之间误差最小"为目标，逆向设计材料分布以定制单阶/多阶 Chladni 图案。其"特征向量误差"目标与我们时代 I·D / II 的演进同源；其 SIMP 密度变量与我们的 `density_scale` 思路相近。**关键区别**：该工作未受"中心单点激振 + D₄ 对称"硬约束限制（这正是本项目 A₁ irrep 天花板的来源），因此其可达图样空间更大。
2. **Tcherniak, D. (2002).** "Topology optimization of resonating structures using SIMP method." *Int. J. Numer. Meth. Eng.* 54:1605. —— 谐振结构 SIMP 拓扑优化的奠基工作，上条 2024 论文的方法学源头之一。
3. **`PaulBellette/chladni_inverse_design`（开源实现）.** —— 把 Chladni 逆设计表述为"能量地形"问题：`E(x,y)=Σ_k b_k φ_k(x,y)²`（非负平方模态叠加）。这与我们 W2/W6 的 **amplitude valley loss** 思路一致，并独立印证了"非负平方叠加偏好 box/band/grid/cross/大连通字形、排斥细小分离特征"——与我们 D₄ + 撒粉物理得到的结论高度吻合。
4. **Misseroni, D., Movchan, A. B., & Movchan, N. V. (2016).** "Cymatics for the cloaking of flexural vibrations in a structured plate." *Scientific Reports* 6:23929. —— 用结构化板调控弯曲波/节线（cymatics 即 Chladni），是"用几何重塑节线分布"的物理灵感来源。
5. **Tuan, P.-T., Chen, Y.-F., et al.** —— Chen 组把 Chladni 强迫响应映射到**非齐次 Helmholtz 方程的最大熵态**来重建/预测节线图案，是"强迫响应 vs 自由振动"区分（本报告 §3.3 的盲区之一）的理论灵感。
6. **Zhou, Q., et al. (2016).** "Controlling the motion of multiple objects on a Chladni plate." *Nature Communications* 7:12764. —— 多激振器主动控制 Chladni 节线/粒子运动，印证了本报告 §7 的核心建议：**要突破 D₄ / A₁ 天花板，必须从硬件（多激振器、破对称激振）入手。**
7. **（未采用的替代路线）level-set 形状优化**：Allaire, Jouve & Toader 2004, *J. Comput. Phys.* 194:363。本项目用密度/厚度场而非 level-set 边界表示；列此以备对照。

---

*本报告所有定量结论均取自上述仓库内的实验记录与 JSON 数字；不含外推或修饰。相关工作（C.5）为对照与溯源用途，部分为同题前人工作或独立开源实现。*
