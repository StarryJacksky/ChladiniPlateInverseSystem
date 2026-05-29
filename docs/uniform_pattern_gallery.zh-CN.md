# 均匀板图样画廊（Uniform Pattern Gallery）

[Language / 语言](./README.md): [双语](./code_structure.md) · 中文 · _English（待补）_

## 1. 这是什么？

主项目（Chladni Studio）让用户绘制 _任意_ 目标节点线图案，然后通过 W10 surrogate + COMSOL eigenfreq + Phase 1 IC-likeness + Phase 2 trust-region 流水线，反推出非均匀厚度板设计——这是"硬模式"，因为搜索空间非常大、目标图案与板物理本征模态可能差得很远。

**Gallery（画廊）分支项目**给用户一条更容易的路：

1. **看：** 软件直接展示一块 _均匀 2 mm 厚度_ 板能"天然"震出的全部低阶节点线图案（默认 30 个本征模态）；
2. **选：** 用户在缩略图网格里挑一个看起来接近想要图案的；
3. **微扰：** 在右侧滑块里对它做轻量参数化变形（X/Y 拉伸把圆变成椭圆、平面旋转、整体缩放、切变、平移、Gaussian 隆起 / 凹陷）；
4. **应用：** 点 _Use as target_，软件会把微扰后的节点线图自动保存为 `data/target_patterns/target.png`，并立刻跑预处理；
5. **逆向：** 切回 Target / Run 页签，按主流水线一键反推。

这样做的好处是：**初始猜测已经在"几乎可达"的邻域**，主流水线的 Phase 1 IC-likeness 损失从一开始就低，Phase 2 trust-region 只需要做"局部修正"，收敛性与可制造性都会比从任意手绘图案出发好得多。

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
        catalogue.json       # 元信息：板尺寸、材料、N 阶频率、家族分类
        mode_NNN_field.npy   # 代理网格上的位移场（float32）
        mode_NNN_nodal.npy   # 代理网格上的节点线掩膜（uint8）
        mode_NNN_preview.png # 512x512 黑底白线渲染
        mode_NNN_thumb.png   # 160x160 缩略图
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
| `src/frontend/target_ui_server.py` | 新增 4 个 API：`uniform-catalogue` / `uniform-catalogue/<i>/{thumb,preview,field}` / `uniform-perturb` / `uniform-apply` |
| `frontend/target_designer.html` | 新增 Gallery 标签页 + JS 逻辑 |
| `src/main.py` | 新增 CLI：`python -m src.main build-uniform-catalogue` |

## 4. 命令行

```powershell
# 重建目录（30 个模态、代理网格 51×51） / Rebuild the catalogue with 30 modes
python -m src.main build-uniform-catalogue

# 自定义模态数 + 代理网格 / Custom mode count + proxy grid
python -m src.main build-uniform-catalogue --num-modes 60 --proxy-grid 71
```

修改 `config.yaml` 的 `thickness.default_mm` 或 `material.*` 后，启动 UI 时会自动检测元信息不一致并重建。也可以手动删除 `data/uniform_catalogue/` 强制重建。

## 5. UI 使用

1. 启动：`python scripts/launch_chladni_studio.py`
2. 浏览器进入 `http://127.0.0.1:8765`
3. 顶部右侧标签栏点 **Gallery**
4. 网格里有 30 张缩略图，每张标注：模态编号 / 本征频率 / 形状家族（ring / cross / diagonal）
5. 点一张缩略图 → 右侧 _Perturb & Preview_ 面板出现 → 滑动任意滑块时实时预览
6. 满意后点 **Use as target** → 软件落盘 + 跑预处理 + 自动切回 Target 页签
7. 切到 **Run** 页签 → 跑主流水线（surrogate-only ≈ 30 s，全流程含 COMSOL ≈ 2 h）

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
- **缓存失效**：`uniform_catalogue_summary()` 会比对 `plate_length_mm`、`thickness_mm`、`material` 三个 key，发现配置变化时自动重建。
- **API 性能**：单次 `/api/uniform-perturb` ≈ 30 ms（51×51 网格上的反向 bilinear + Gaussian + 512×512 渲染）。前端用 160 ms 的去抖确保滑动滑块时不打爆服务端。

## 8. 与主项目的关系

这是一个 **可选 UX 通道**，不替换主流水线。所有真正的逆向计算（W10 / COMSOL / Phase 1+2）依旧在 `src/optimisation/` 里。Gallery 只负责把"任意手绘"的高自由度目标，替换成"已知物理可达起点 + 已知小扰动"的低自由度目标——也就是把搜索的"难度"从主流水线之外切掉一部分。

## 9. 后续可改进

- **D₄ 规范化**：把简并对的两个基线性组合成 A₁/A₂/B₁/B₂/E 不可约表示，让每个模态在镜像/旋转下看起来"标准"。
- **可达性预估**：在画廊缩略图上加一个小标签，提示"此模态做 X 微扰后大致需要 ±0.4 mm 的厚度修正"，让用户提前判断难度。
- **图样收藏**：让用户把常用的微扰组合保存为 preset。
- **画廊也支持 D₄ 仅画唯一代表**：现在 30 个模态里有简并对（如 mode 1/2 都是 353 Hz），可以折叠成同一个槽。
