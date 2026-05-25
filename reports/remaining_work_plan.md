# Remaining Work Plan / 剩余工作顺序表

[Language / 语言](./remaining_work_plan.md): Bilingual | [中文](./remaining_work_plan.zh-CN.md) | [English](./remaining_work_plan.en.md)

This document separates tasks Codex can continue now from tasks blocked by real material, COMSOL, or physical-test data.
本文把 Codex 现在还能继续做的任务，与需要真实材料、COMSOL 或实体测试数据后才能做的任务分开。

## A. Can Continue Independently / 现在可以独立继续做

The independent development queue is now mostly quality maintenance rather than new feature construction.
当前可独立推进的队列已经主要是质量维护，而不是继续堆新功能。

### 1. Quality Gate Maintenance / 质量门维护

Tasks:
任务：

1. Run `python scripts/check_local_quality.py` after every meaningful code or documentation change.
   每次有实质代码或文档改动后，运行 `python scripts/check_local_quality.py`。
2. Keep the bilingual comment checker passing for hand-written `.py`, `.m`, and `.html` files.
   保持手写 `.py`、`.m`、`.html` 文件通过中英双语注释检查。
3. Extend the local quality bundle only when a new repeatable local check appears.
   只有出现新的可重复本地检查时，才扩展本地质量检查合集。

Completed foundation:
已完成基础：

- The quality bundle now covers documentation links, bilingual comments, config contracts, discovery fixtures, artifact cleanup, Python-only smoke tests, Python compilation, and optional frontend syntax checks.
  质量检查合集现在覆盖文档链接、双语注释、配置合同、自动发现样例、产物清理、无 COMSOL 烟测、Python 编译和可选前端语法检查。

### 2. Documentation Maintenance / 文档维护

Tasks:
任务：

1. Keep the root README as the short bilingual entry page that links into user-facing guides.
   保持根目录 README 是简洁双语入口页，并链接到用户文档。
2. Keep the deployment guide, user manual, code-structure guide, and planning reports synchronized with any later implementation changes.
   后续实现变化时，同步维护部署指南、软件说明书、代码结构说明和规划报告。
3. Add final screenshots and lab-specific notes only after the UI and COMSOL workflow are stable.
   只有在 UI 和 COMSOL 工作流稳定后，再补最终截图和实验室专属说明。

Completed foundation:
已完成基础：

- Beginner-facing bilingual docs now exist for setup, software use, project structure, local checks, run reports, and remaining work.
  面向零基础用户的双语文档已经覆盖安装、软件使用、项目结构、本地检查、运行报告和剩余工作。

### 3. Visual Verification When Available / 条件允许时的视觉验证

Tasks:
任务：

1. Re-open the local app in a browser once local server approval or another usable preview route is available.
   当本地 server 权限或其他可用预览方式恢复后，重新用浏览器打开本地应用。
2. Check desktop and narrow layouts for Target, Tune, Results, and Run.
   检查 Target、Tune、Results、Run 的桌面和窄屏布局。
3. Capture final screenshots for README and user manual only after the interface is no longer changing quickly.
   等界面不再快速变化后，再为 README 和软件说明书截最终图。

Current note:
当前说明：

- The recent local preview attempt was blocked by local server/file preview permissions, so this item is waiting on a usable preview path rather than more implementation code.
  最近一次本地预览被 server/file 预览权限挡住，所以这一项等待可用预览路径，而不是继续写更多功能代码。

## B. Needs Real Project Data Later / 需要真实项目数据后再做

### 1. Material Calibration / 材料校准

Needs measured or trusted values for density, Young's modulus, Poisson ratio, and thermal parameters.
需要实测或可信的密度、杨氏模量、泊松比和热参数。

### 2. COMSOL Baseline Freeze / COMSOL 基准模型冻结

Needs the final MPH model, final hole/spacer assumptions, final boundary naming, and final fixed constraints.
需要最终 MPH 模型、最终孔/垫片假设、最终边界命名和最终固定约束。

### 3. Physical Validation / 实体验证

Needs measured plate frequencies, excitation setup, and photographed or extracted physical nodal patterns.
需要实体板频率、激励设置，以及拍摄或提取的实体节点线图案。

### 4. Optimization Tuning / 优化调参

Needs enough COMSOL results to tune scoring weights, random search settings, and genetic algorithm operators.
需要足够 COMSOL 结果来调整评分权重、随机搜索设置和遗传算法算子。

### 5. Clean Machine Validation / 干净机器验证

Needs real Windows, macOS, and Linux machines, or equivalent clean virtual machines, with actual COMSOL/MATLAB installations to confirm discovery behavior.
需要真实 Windows、macOS、Linux 机器，或等价干净虚拟机，并安装实际 COMSOL/MATLAB 来确认发现逻辑。

### 6. Final Release Guide / 最终发布指南

Needs stable UI screenshots, final install paths, final lab-specific COMSOL/MATLAB notes, and confirmed troubleshooting cases.
需要稳定 UI 截图、最终安装路径、实验室专属 COMSOL/MATLAB 注意事项和确认过的故障排查案例。

## C. Current Waiting Boundary / 当前等待边界

Codex is now close to the planned waiting boundary.
Codex 现在已经接近计划中的等待边界。

Most meaningful new work now needs one of these inputs: the accepted final MPH model, real material values, real COMSOL output images/CSV data, physical validation measurements, clean OS validation machines, or a working local browser preview route.
现在大多数有意义的新工作需要以下输入之一：验收后的最终 MPH 模型、真实材料参数、真实 COMSOL 输出图片/CSV、实体测量数据、干净系统验证机器，或可用的本地浏览器预览路径。

Until then, the safe independent work is maintenance: keep docs synchronized, keep checks passing, and avoid inventing model-specific assumptions that could fight the real COMSOL baseline.
在这些输入到位前，安全的独立工作主要是维护：同步文档、保持检查通过，并避免编造会和真实 COMSOL 基准模型冲突的模型专属假设。
