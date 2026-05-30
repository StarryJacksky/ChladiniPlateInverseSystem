# 均匀板图样画廊（Uniform Pattern Gallery）

[Language / 语言](./README.md): [双语](./code_structure.md) · 中文 · _English（待补）_

## 1. 这是什么？

主项目（Chladni Studio）让用户绘制 _任意_ 目标节点线图案，然后通过 W10 surrogate + COMSOL eigenfreq + Phase 1 IC-likeness + Phase 2 trust-region 流水线，反推出非均匀厚度板设计——这是"硬模式"，因为搜索空间非常大、目标图案与板物理本征模态可能差得很远。

**Gallery（画廊）分支项目**给用户一条更容易的路：

1. **生成：** 用户在 Tune 标签里选定材料（PLA / CF-PETG / 自定义），切回 Gallery 标签，从 _Modes_ 下拉里挑模态数（20/30/40/50/80/100/150/200，默认 50），点 _Generate for current material_，软件求解出该 _(材料, 模态数)_ 组合对应的均匀板低阶节点线图案，并落盘到 `data/uniform_catalogue/<tier_id>/`；
2. **看：** 缩略图网格展示当前档位下全部图案；下拉 _Catalogue tier_ 可以在已生成的任意档位间切换查看，无需重算；
3. **选 / 自动匹配：** 在缩略图网格里挑一个；或者，如果你已经有了一张 target.png（手绘 / 上传 / 上次 Gallery 输出的），可以直接点 **Find closest to target / 自动匹配当前目标**——后端会用 Chamfer 距离把目标和当前档位每张图样比对一遍，再在每张图样上小范围搜旋转/拉伸，自动选最接近的并把推荐的 `rotate_deg / stretch_x / stretch_y` 写进滑块；
4. **微扰：** 在右侧滑块里对它做轻量参数化变形（X/Y 拉伸把圆变成椭圆、平面旋转、整体缩放、切变、平移、Gaussian 隆起 / 凹陷）。自动匹配后也可以继续手动微调；
5. **应用：** 点 _Use as target_，软件会把微扰后的节点线图自动保存为 `data/target_patterns/target.png`，并立刻跑预处理；
6. **逆向：** 切回 Target / Run 页签，按主流水线一键反推。

这样做的好处是：**初始猜测已经在"几乎可达"的邻域**，主流水线的 Phase 1 IC-likeness 损失从一开始就低，Phase 2 trust-region 只需要做"局部修正"，收敛性与可制造性都会比从任意手绘图案出发好得多。

> **关于"档位 (tier)"：** 一个 tier = `(板长×宽, 厚度, 材料指纹, 模态数 N)` 的组合，对应 `data/uniform_catalogue/<tier_id>/` 一个独立的子目录。`tier_id` 是上述签名的 SHA1 前 10 位。同一材料的 30/50/80 模态算三个不同 tier，互不覆盖；切换材料后再点 Generate 会得到新 tier，旧 tier 还能继续切回查看。

## 2. 算法链路

```text
config.yaml  (plate_length_mm / center_clamp_radius_mm / material)
        |
        v
src/uniform_pattern/catalogue.py
        |    solve_uniform_plate_modes
        |    -> 把 H_mm 设为 default_mm（默认 2.0）的常数矩阵
        |    -> 复用 src/physics/kirchhoff_love.py 的稀疏 Laplacian / KL 双调和刚度 / SciPy eigh
        |    -> 输出 (eigenvalues, mode fields N×N, frequencies Hz)
        v
src/uniform_pattern/render.py
        |    bilinearly upsample 模态场到 512×512
        |    sign-change + zero-band 抽节点线 → 二值掩膜
        |    膨胀 line_width_px / 清除中心夹持区 → 输出 PNG
        v
data/uniform_catalogue/
        index.json                # 已生成档位索引：tier_id → label / signature / num_modes / updated_at
        <tier_id>/                # tier_id = sha1(板尺寸+厚度+材料+模态数)[:10]
            catalogue.json        # 元信息：板尺寸、材料、N 阶频率、家族分类
            mode_NNN_field.npy    # 代理网格上的位移场（float32）
            mode_NNN_nodal.npy    # 代理网格上的节点线掩膜（uint8）
            mode_NNN_preview.png  # 512x512 黑底白线渲染
            mode_NNN_thumb.png    # 160x160 缩略图
        |
        v
src/uniform_pattern/perturb.py
        |    apply_perturbation(field, PerturbationParams):
        |        反向坐标变换（先平移，再 shear，再旋转，再 anisotropic 缩放）
        |        + Gaussian 隆起叠加在场上
        |    -> 返回扰动后的位移场
        v
后端 /api/uniform-perturb        → 微扰预览（data URL，不落盘）
后端 /api/uniform-apply          → 落盘成 target.png + 自动 prepare-target
        v
        | （用户切到 Target / Run 页签）
        v
主项目 src/optimisation/production_pipeline.py（W10 → COMSOL eig → P1 → P2）
```

## 3. 关键文件

| 文件 | 作用 |
| --- | --- |
| `src/uniform_pattern/__init__.py` | 包说明 |
| `src/uniform_pattern/catalogue.py` | 均匀板本征求解 + 目录构建（JSON + .npy） |
| `src/uniform_pattern/render.py` | 把位移场渲染成 512×512 黑底白线 PNG |
| `src/uniform_pattern/perturb.py` | 参数化微扰：拉伸 / 旋转 / 缩放 / 切变 / 平移 / 隆起 |
| `src/uniform_pattern/match.py` | 把 target.png 与档位内每张图样做 Chamfer 距离 + 旋转/拉伸网格搜索，找出 top-K 最接近的图样 + 推荐微扰参数 |
| `src/frontend/target_ui_server.py` | 新增 7 个 API：`uniform-catalogue` / `uniform-catalogue/tiers` / `uniform-catalogue/generate` / `uniform-catalogue/match-target` / `uniform-catalogue/<i>/{thumb,preview,field}` / `uniform-perturb` / `uniform-apply`（资源路由支持 `?tier_id=<id>` 查询参数） |
| `frontend/target_designer.html` | 新增 Gallery 标签页 + 档位切换 / Generate 按钮 + JS 逻辑 |
| `src/main.py` | 新增 CLI：`python -m src.main build-uniform-catalogue` |

## 4. 命令行

```powershell
# 用当前 config + 默认 50 模态生成档位 / Build a tier for current config with 50 modes (default)
python -m src.main build-uniform-catalogue

# 自定义模态数 + 代理网格（每个组合都是一个独立 tier） / Custom mode count + proxy grid (each combo is a distinct tier)
python -m src.main build-uniform-catalogue --num-modes 80 --proxy-grid 71
```

每次运行会把 _(板尺寸, 厚度, 材料指纹, 模态数)_ 的 sha1 前 10 位作为 `tier_id`，落盘到 `data/uniform_catalogue/<tier_id>/`，并把这条记录加进 `data/uniform_catalogue/index.json`。不同 _(材料, 模态数)_ 组合互不覆盖；用户随时可以切回旧档位查看。

## 5. UI 使用

1. 启动：`python scripts/launch_chladni_studio.py`
2. 浏览器进入 `http://127.0.0.1:8765`
3. 顶部右侧标签栏点 **Gallery**
4. （首次或换材料后）下拉 _Modes / 模态数_ 选 30/40/50/…，点 **Generate for current material** → 后端解算并写盘
5. _Catalogue tier_ 下拉里可以在已生成的任意档位间切换查看（带 ★ 标记的是当前 Tune 配置 + 默认模态数对应的"current"档位）
6. 网格里展示当前档位下全部 N 张缩略图，每张标注：模态编号 / 本征频率 / 形状家族（ring / cross / diagonal）
7. 点一张缩略图 → 右侧 _Perturb & Preview_ 面板出现 → 滑动任意滑块时实时预览
8. 满意后点 **Use as target** → 软件落盘 + 跑预处理 + 自动切回 Target 页签
9. 切到 **Run** 页签 → 跑主流水线（surrogate-only ≈ 30 s，全流程含 COMSOL ≈ 2 h）

## 6. 微扰参数说明

所有变换都作用在归一化坐标 `(nx, ny) ∈ [-1, 1]²` 下（中心为 0、板边为 1）：

| 参数 | 范围 | 物理含义 |
| --- | --- | --- |
| `stretch_x`, `stretch_y` | 0.30 ~ 3.0 | 各向异性缩放。把圆变椭圆的核心参数。`stretch_x > 1` 拉宽，`< 1` 压窄。 |
| `rotate_deg` | -180 ~ 180 | 平面旋转。 |
| `scale` | 0.5 ~ 2.0 | 整体等比缩放。 |
| `shear` | -0.5 ~ 0.5 | 切变（X 受 Y 影响）。 |
| `translate_x`, `translate_y` | -0.4 ~ 0.4 | 整体平移（保留中心夹持有效位置）。 |
| `bump_amplitude` | -1.0 ~ 1.0 | 在场上叠加一个高斯凸起 / 凹陷。**会改变节点线拓扑**，谨慎使用。 |
| `bump_x`, `bump_y` | -1.0 ~ 1.0 | 凸起中心位置。 |
| `bump_sigma` | 0.05 ~ 0.80 | 凸起范围。 |

> 几何变换（前 6 项）是 _准物理_ 的：它们不会改变节点线的拓扑结构，因此微扰后的图案 _仍然_ 是某个轻度非均匀板的可达本征模态附近的图案——这正是逆向流水线最容易解的情形。
>
> 隆起（最后 4 项）会改变拓扑，是为了让用户能在节点线上"加点东西"或"消掉点东西"，提供更大的设计自由度。

## 7. 实现细节

- **正方形板的简并模态**：由于 D₄ 对称，某些低阶模态会成对简并（例如 `f_n ≈ f_{n+1}`）。离散网格上数值求解时，每个简并对的两个基向量会被任意旋转，可能看起来不那么"对称"。可以通过把代理网格调高（`--proxy-grid 71`）减弱这个问题，或在后续版本里加 D₄ irrep 投影做规范化。
- **节点线渲染**：用 sign-change + |u| ≤ 2% peak 的复合判据抽节点线，避免在极小幅值的边界区出现假节点。
- **中心夹持**：渲染时按 `center_clamp_radius_mm` 把中心圆设为白色，主项目 `preprocess_target.py` 在二次预处理时也会再做一次中心清除。
- **档位 (tier) 缓存**：每个 _(板尺寸, 厚度, 材料指纹, 模态数)_ 组合 = 一个 tier，独立子目录、独立 catalogue.json，互不覆盖。前端切换 tier 不会重算，只是换文件读。点 **Generate** 才会触发求解。
- **物理可达性过滤（中心驱动参与度）**：实验上，正方板被中心激励器驱动时，**不是所有本征模态都能被激起来**——D₄ 不可约表示里只有"中心对称"那一支（A₁ 系列）会和均匀中心驱动强耦合，其它（A₂、B₁、B₂、E）几乎完全不响应。我们直接复用主项目 `src/physics/drive_reachability.py` 的 `center_participation()`：在中心 7% 半径的圆盘里取每个模态位移的 `|mean|`，再按全档最大值归一化到 0-1。这就是每个模态卡片右上角的 `p` 徽标：
  - `p ≥ 0.30` 绿色：在中心驱动下能被稳定激起来
  - `0.10 ≤ p < 0.30` 黄色：要靠夹持瑕疵或离轴驱动才能被激起来
  - `p < 0.10` 红色：实验上基本激不出来，默认隐藏
  顶部 _Hide modes unreachable by centre drive_ 复选框默认开启；自动匹配在后端硬过滤掉 `p < 0.10` 的模态，对 `0.10 ≤ p < 0.30` 的模态在 Chamfer 分数上加 `4.0 × (0.30 − p)` 的软惩罚——也就是 _即使_ 几何形状最像，物理上激不出来的模态也不会被推荐。
- **自动匹配的相似度度量**：用对称 Chamfer 距离（双向：A 上每个像素到 B 最近像素的平均欧氏距离 + 反向，再平均）。两阶段：先对当前档位所有图样在 192×192 上算未扰动 Chamfer 做粗排，再对前 8 名在 6 个旋转 × 5 组 (sx, sy) 拉伸的网格上精搜。30 模态档位约 0.7 s，50 模态约 1.3 s。SciPy 可用时走精确 EDT，否则走两遍曼哈顿距离扫描兜底。
- **API 性能**：单次 `/api/uniform-perturb` ≈ 30 ms（51×51 网格上的反向 bilinear + Gaussian + 512×512 渲染）。前端用 160 ms 的去抖确保滑动滑块时不打爆服务端。

## 8. 与主项目的关系

这是一个 **可选 UX 通道**，不替换主流水线。所有真正的逆向计算（W10 / COMSOL / Phase 1+2）依旧在 `src/optimisation/` 里。Gallery 只负责把"任意手绘"的高自由度目标，替换成"已知物理可达起点 + 已知小扰动"的低自由度目标——也就是把搜索的"难度"从主流水线之外切掉一部分。

## 9. 后续可改进

- **D₄ 规范化**：把简并对的两个基线性组合成 A₁/A₂/B₁/B₂/E 不可约表示，让每个模态在镜像/旋转下看起来"标准"。这同时也能把"参与度过滤"从经验阈值变成精确的群论判据（只保留 A₁ 系列）。
- **可达性预估**：在画廊缩略图上加一个小标签，提示"此模态做 X 微扰后大致需要 ±0.4 mm 的厚度修正"，让用户提前判断难度。
- **图样收藏**：让用户把常用的微扰组合保存为 preset。
- **画廊也支持 D₄ 仅画唯一代表**：现在 30 个模态里有简并对（如 mode 1/2 都是 353 Hz），可以折叠成同一个槽。
