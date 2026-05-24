# Remaining Work Plan / 剩余工作顺序表

[Language / 语言](./remaining_work_plan.md): Bilingual | [中文](./remaining_work_plan.zh-CN.md) | [English](./remaining_work_plan.en.md)

This document separates tasks Codex can continue now from tasks blocked by real material, COMSOL, or physical-test data.
本文把 Codex 现在还能继续做的任务，与需要真实材料、COMSOL 或实体测试数据后才能做的任务分开。

## A. Can Continue Now / 现在可以继续做

### 1. Frontend Design Polish / 前端设计打磨

Goal: make the app feel like a serious engineering design console, not a temporary debug page.
目标：让软件像正式工程设计控制台，而不是临时调试页。

Tasks:
任务：

1. Unify visual hierarchy across Target, Tune, Results, and Run tabs.
   统一 Target、Tune、Results、Run 页签的视觉层级。
2. Tighten spacing, typography, and empty states in Results and Run.
   收紧 Results 和 Run 页的间距、文字层级和空状态。
3. Keep the first screen as the usable workspace, not a marketing page.
   保持首屏是可用工作区，而不是营销页面。
4. Verify desktop and narrow layouts in the browser after each visible change.
   每次可见改动后，用浏览器检查桌面和窄屏布局。

### 2. Frontend Function Completion / 前端功能补齐

Goal: let users draw/import, run, inspect, and compare without opening files manually.
目标：让用户不用手动打开文件，也能完成绘制/导入、运行、查看和比较。

Tasks:
任务：

1. Add stronger candidate-to-candidate comparison views.
   增强候选之间的横向比较视图。
2. Add clearer best-candidate summary and ranking explanation.
   增加更清楚的最佳候选摘要和排名解释。
3. Extend report-style export from selected candidates to full run summaries.
   将报告式导出从单个候选扩展到整次运行摘要。
4. Improve target-quality recommendations for imported photos and logos.
   改进导入照片和 Logo 的目标质量建议。

### 3. Automation Robustness / 自动化稳健性

Goal: make the Run tab predictable before asking users to trust one-click automation.
目标：在让用户信任一键自动化前，让 Run 页行为足够可预测。

Tasks:
任务：

1. Validate COMSOL/MATLAB running-process detection and install-path discovery on clean Windows, macOS, and Linux machines.
   在干净的 Windows、macOS、Linux 机器上验证 COMSOL/MATLAB 运行进程检测与安装路径发现。
2. Add deeper model-specific preflight checks after the final COMSOL model is frozen.
   最终 COMSOL 模型冻结后，增加更深入的模型专属运行前检查。
3. Improve failed-run recovery messages using diagnostics and logs.
   结合诊断和日志改进失败恢复提示。
4. Keep Python-only self-test independent from COMSOL/MATLAB execution.
   保持 Python-only 自检不依赖 COMSOL/MATLAB 实际启动。

Recently completed:
最近完成：

- Frontend setup assistant for COMSOL/MATLAB discovery, path confirmation, and diagnostics verification.
  已完成 COMSOL/MATLAB 自动发现、路径确认与诊断验证的前端安装向导。
- Safe local Stop pathway with persisted cancelling/cancelled workflow state.
  已完成本地安全停止入口，并持久化 cancelling/cancelled 工作流状态。

### 4. Backend Checks and Contracts / 后端检查与合同

Goal: catch configuration problems before expensive COMSOL/MATLAB runs.
目标：在昂贵的 COMSOL/MATLAB 运行前发现配置问题。

Tasks:
任务：

1. Harden config validation for paths, model files, export directories, and numeric limits.
   加强路径、模型文件、导出目录和数值范围的配置校验。
2. Add non-invasive COMSOL/MATLAB version probes where safe.
   在安全的前提下增加非侵入式 COMSOL/MATLAB 版本探测。
3. Expand discovery tests with simulated missing config paths and known install-path fixtures.
   增加发现逻辑测试，覆盖配置路径缺失和已知安装路径样例。
4. Prefer already-running processes, then known install folders, then manual override in the setup flow.
   安装流程优先使用已运行进程，其次查找常见安装目录，最后才进入手动覆盖。
5. Add manual override fields to the setup wizard when discovery fails.
   当自动发现失败时，在安装向导中提供手动覆盖字段。
7. Add clearer authentication/license guidance when diagnostics detect risk.
   当诊断发现风险时，提供更清楚的认证/license 指引。
8. Keep generated artifacts recoverable and cleanup conservative.
   保持生成产物可恢复，清理逻辑保守。

### 5. Documentation Drafts / 文档开发版

Goal: make GitHub understandable before final screenshots and lab-specific values exist.
目标：即使最终截图和实验室参数还没定，也让 GitHub 当前可读。

Tasks:
任务：

1. Keep README as a short entry page.
   保持 README 是简洁入口页。
2. Maintain Windows/macOS/Linux deployment guide in `docs/deployment_guide.md`.
   维护 `docs/deployment_guide.md` 中的 Windows/macOS/Linux 部署指南。
3. Maintain software user manual in `docs/user_manual.md`.
   维护 `docs/user_manual.md` 中的软件说明书。
4. Add final screenshots later after UI stops moving.
   等 UI 稳定后再补最终截图。

### 6. Python-Only Smoke Test Path / 无 COMSOL 烟测路径

Goal: let new users verify the app without COMSOL first.
目标：让新用户先在没有 COMSOL 的情况下验证软件。

Tasks:
任务：

1. Confirm clone/install/self-test/launch workflow on a clean environment.
   在干净环境确认 clone、安装、自检、启动流程。
2. Confirm target import, preprocessing, candidate generation, and UI refresh.
   确认目标导入、预处理、候选生成和 UI 刷新。
3. Document expected files after a smoke test.
   记录烟测后应出现的文件。

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

### 5. Final Release Guide / 最终发布指南

Needs stable UI screenshots, final install paths, final lab-specific COMSOL/MATLAB notes, and confirmed troubleshooting cases.
需要稳定 UI 截图、最终安装路径、实验室专属 COMSOL/MATLAB 注意事项和确认过的故障排查案例。

## C. Current Waiting Boundary / 当前等待边界

Codex is not yet blocked.
Codex 目前还没有进入等待阶段。

Continue with: COMSOL/MATLAB running-process detection and auto-discovery, frontend polish, comparison/report features, run validation/cancel behavior, backend config hardening, and documentation refinement.
下一步继续做：COMSOL/MATLAB 运行进程检测与自动发现、前端打磨、比较/报告功能、运行校验/取消行为、后端配置加固和文档细化。

Only after those are complete should the project wait mainly for real material data, final COMSOL model acceptance, and physical validation data.
只有这些完成后，项目才主要进入等待真实材料数据、最终 COMSOL 模型验收和实体验证数据的阶段。
