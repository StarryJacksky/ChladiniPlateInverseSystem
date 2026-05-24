# User Manual / 软件使用说明书

[Language / 语言](./user_manual.md): Bilingual | [中文](./user_manual.zh-CN.md) | [English](./user_manual.en.md)

This manual explains the current Chladni Studio workflow.
本说明书解释当前 Chladni Studio 的使用流程。

## 1. What the Software Does / 软件做什么

Chladni Studio helps users turn a desired visual pattern into candidate stepped-thickness plate designs.
Chladni Studio 帮助用户把目标视觉图案转换为阶梯厚度板候选设计。

The workflow is:
流程是：

```text
target image -> preprocessing -> thickness candidates -> COMSOL/MATLAB simulation -> scoring -> ranked results
目标图案 -> 预处理 -> 厚度候选 -> COMSOL/MATLAB 仿真 -> 评分 -> 排行结果
```

## 2. Main Screen / 主界面

The main screen has a drawing canvas on the left and control tabs on the right.
主界面左侧是绘图画布，右侧是控制页签。

Top controls:
顶部控制：

- `Brush`: draw dark target strokes.
  `Brush`：绘制深色目标线。
- `Erase`: erase strokes.
  `Erase`：擦除笔迹。
- `Width`: change brush width.
  `Width`：调整画笔宽度。
- `Stroke`: use strokes as nodal-line targets.
  `Stroke`：把线条作为节点线目标。
- `Edge`: extract edges from filled logos or photos.
  `Edge`：从填充 Logo 或照片中提取边缘。
- `Filled`: use the filled region itself as the target.
  `Filled`：把填充区域本身作为目标。
- `Import`: load a PNG/JPEG/WebP image.
  `Import`：导入 PNG/JPEG/WebP 图片。
- `Save`: save and preprocess the target.
  `Save`：保存并预处理目标。

## 3. Target Tab / Target 页

Use this tab to prepare the user-defined pattern.
这个页签用于准备用户给定图案。

Recommended target images:
推荐目标图：

- High contrast.
  高对比度。
- Simple enough for a first search.
  第一轮搜索不要过于复杂。
- Not too tiny or too filled.
  不要太细小，也不要大面积填满。
- Avoid many isolated small pieces in the first loop.
  第一轮尽量避免很多孤立小碎片。

`Target Quality` shows:
`Target Quality` 会显示：

- Processed preview.
  预处理预览。
- Foreground area percentage.
  前景面积比例。
- Connected component count.
  连通部分数量。
- First-loop suitability recommendation.
  第一轮适配建议。
- Warnings for fine detail, complexity, and area balance.
  细节、复杂度和面积平衡警告。
- A short quality guidance note for imported photos, logos, and dense hand drawings.
  针对导入照片、Logo 和复杂手绘目标的简短质量建议。

If the recommendation is `Late-stage target`, use it later after the optimization loop is stable, or simplify the image first.
如果建议是 `Late-stage target`，可以等优化流程稳定后再用，或先简化图案。

## 4. Tune Tab / Tune 页

Use this tab to edit material and scoring parameters.
这个页签用于编辑材料和评分参数。

Material parameters:
材料参数：

- Density.
  密度。
- Young's modulus.
  杨氏模量。
- Poisson ratio.
  泊松比。
- Thermal conductivity.
  导热系数。
- Heat capacity.
  热容。
- Thermal expansion.
  热膨胀系数。

Scoring parameters:
评分参数：

- Roughness weight.
  粗糙度权重。
- Mass weight.
  质量权重。
- Frequency weight.
  频率权重。
- Frequency range.
  频率范围。

Press `Apply` after changing material or scoring values.
修改材料或评分参数后，请点击 `Apply`。

## 5. Run Tab / Run 页

Use this tab to run the automatic pipeline.
这个页签用于运行自动化流程。

Run presets:
运行预设：

- `Smoke`: 1 candidate, 3 modes. Use for quick checks.
  `Smoke`：1 个候选、3 个模态，用于快速检查。
- `Review`: 3 candidates, 10 modes. Use for short comparison runs.
  `Review`：3 个候选、10 个模态，用于短对比。
- `Full`: 12 candidates, 20 modes. Use for a fuller local search.
  `Full`：12 个候选、20 个模态，用于较完整本地搜索。

`Run COMSOL`:
`Run COMSOL`：

- On: run the COMSOL/MATLAB bridge.
  开启：运行 COMSOL/MATLAB 桥接。
- Off: run the Python-side workflow without COMSOL simulation.
  关闭：只运行 Python 侧流程，不跑 COMSOL 仿真。

Run control:
运行控制：

- `Run`: starts the queued local workflow after preflight checks.
  `Run`：通过运行前检查后，启动本地排队工作流。
- `Stop`: requests a safe cancellation; the current external COMSOL/MATLAB command is not force-killed, and the workflow stops at the next safe checkpoint.
  `Stop`：请求安全取消；当前外部 COMSOL/MATLAB 命令不会被强杀，工作流会在下一个安全检查点停止。

Preflight checks:
运行前检查：

- Candidate count must be from 1 to 100.
  候选数量必须是 1 到 100。
- Mode count must be from 1 to 60.
  模态数量必须是 1 到 60。
- The target should be saved once so preprocessing metrics exist.
  目标图应至少保存一次，以生成预处理指标。
- If `Run COMSOL` is enabled, diagnostics should be ready.
  如果开启 `Run COMSOL`，诊断状态应为 ready。

Diagnostics:
诊断：

- `Refresh`: checks config contracts, paths, model, runner, timeout settings, and mphserver reachability.
  `Refresh`：检查配置合同、路径、模型、runner、超时设置和 mphserver 可达性。
- `Self-test`: runs a safer Python-only deployment check.
  `Self-test`：运行更安全的 Python-only 部署检查。

Timeline and Logs:
时间线与日志：

- Timeline shows queued, target preparation, candidate generation, simulation, scoring, cancelling, cancelled, done, and error stages.
  Timeline 显示排队、目标预处理、候选生成、仿真、评分、正在取消、已取消、完成和错误阶段。
- Logs show recent COMSOL/MATLAB output tails.
  Logs 显示最近的 COMSOL/MATLAB 输出尾部。
- On failure, Recovery hints combine workflow state, diagnostics, and recent logs to suggest the next check.
  失败时，Recovery hints 会结合工作流状态、诊断和最近日志，提示下一步检查。

Artifacts:
产物：

- Shows generated file sizes.
  显示生成文件大小。
- Previews cleanup candidates.
  预览可清理文件。
- Cleans only regenerable or temporary files covered by the retention policy.
  只清理保留策略允许的可再生成或临时文件。

## 6. Results Tab / Results 页

Use this tab to inspect scored candidates.
这个页签用于查看已评分候选。

You can:
你可以：

- Search candidates by ID.
  按编号搜索候选。
- Sort by rank, score, IoU, Dice, or frequency.
  按排名、分数、IoU、Dice 或频率排序。
- Filter by minimum IoU.
  按最小 IoU 过滤。
- Open target/simulated/overlay images in a larger viewer.
  放大查看目标、仿真、叠加图片。
- Switch between scored modes.
  在已评分模态之间切换。
- Compare the top visible candidates in the overview block.
  在总览区横向比较当前可见的前几个候选。
- Open a full run report from the overview.
  从总览区打开整次运行报告。
- Open a readable candidate report.
  打开可读的候选报告。
- Download a candidate result package.
  下载候选结果包。

The best candidate is not always the highest IoU candidate, because the final score can include roughness, mass, and frequency penalties.
最佳候选不一定是 IoU 最高的候选，因为最终分数可能包含粗糙度、质量和频率惩罚。

## 7. Typical Beginner Workflow / 新手典型流程

1. Launch Chladni Studio.
   启动 Chladni Studio。
2. Draw or import a simple target.
   绘制或导入简单目标。
3. Choose `Edge` for filled logos/photos, or `Stroke` for hand-drawn lines.
   填充 Logo/照片选 `Edge`，手绘线条选 `Stroke`。
4. Click `Save`.
   点击 `Save`。
5. Check `Target Quality`.
   检查 `Target Quality`。
6. Open `Tune` and confirm material/scoring settings.
   打开 `Tune`，确认材料和评分设置。
7. Open `Run`, choose `Smoke`, and click `Run`.
   打开 `Run`，选择 `Smoke`，点击 `Run`。
8. If the smoke run works, try `Review` or `Full`.
   如果烟测成功，再尝试 `Review` 或 `Full`。
9. Open `Results` and inspect the best candidates.
   打开 `Results`，查看最佳候选。

## 8. Reading Results / 如何理解结果

Important metrics:
关键指标：

- IoU: overlap between simulated nodal region and target.
  IoU：仿真节点区域与目标区域的重叠程度。
- Dice: another similarity measure, often easier to compare visually.
  Dice：另一种相似度指标，常用于视觉比较。
- Frequency: exported modal frequency from COMSOL.
  Frequency：COMSOL 导出的模态频率。
- Final score: similarity minus penalties.
  Final score：相似度扣除惩罚项后的综合分数。

Use the overlay image first for quick visual judgment, then compare metrics.
快速判断时先看叠加图，再比较指标。

## 9. Current Limitations / 当前限制

These items depend on future real project data:
以下内容依赖后续真实项目数据：

- Final material presets.
  最终材料预设。
- Physical frequency validation.
  实体频率验证。
- Final COMSOL model acceptance.
  最终 COMSOL 模型验收。
- Official release screenshots.
  正式发布截图。

The current manual is therefore a development-version manual.
因此当前说明书是开发版说明书。
