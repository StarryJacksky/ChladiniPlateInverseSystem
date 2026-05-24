# Chladni Studio

[Language / 语言](./README.md): Bilingual | [中文](./README.zh-CN.md) | [English](./README.en.md)

Chladni Studio is a local inverse-design tool for Chladni plates. Users draw or import a target pattern, adjust physical material parameters, run the COMSOL/MATLAB simulation bridge, and inspect ranked candidate plate designs with scoring data.

Chladni Studio 是一个用于 Chladni 板的本地逆向设计工具。用户可以绘制或导入目标图案，调整真实材料参数，运行 COMSOL/MATLAB 仿真桥接，并查看带评分数据的候选板设计排序结果。

## Start Here / 从这里开始

- [Deployment Guide / 三系统部署教程](./docs/deployment_guide.md) ([中文](./docs/deployment_guide.zh-CN.md) | [English](./docs/deployment_guide.en.md))
- [User Manual / 软件使用说明书](./docs/user_manual.md) ([中文](./docs/user_manual.zh-CN.md) | [English](./docs/user_manual.en.md))
- [Code Structure and Logic / 项目代码结构与逻辑说明](./docs/code_structure.md) ([中文](./docs/code_structure.zh-CN.md) | [English](./docs/code_structure.en.md))
- [Documentation Index / 文档索引](./docs/README.md) ([中文](./docs/README.zh-CN.md) | [English](./docs/README.en.md))
- [Remaining Work Plan / 后续任务规划](./reports/remaining_work_plan.md) ([中文](./reports/remaining_work_plan.zh-CN.md) | [English](./reports/remaining_work_plan.en.md))

## What It Does / 它能做什么

- Accepts hand-drawn patterns, uploaded images, or dragged-in photos as target patterns.
  支持手绘图案、上传图片或拖入照片作为目标图案。
- Converts the target into processed nodal-line data for scoring.
  将目标图案转换为可评分的节点线数据。
- Generates `15 x 15` discrete thickness matrices for a real `150 mm x 150 mm` plate.
  为真实 `150 mm x 150 mm` 板生成 `15 x 15` 离散厚度矩阵。
- Exposes editable material parameters including Young's modulus, Poisson's ratio, density, and heat-transfer-related values.
  支持编辑杨氏模量、泊松比、密度和传热相关材料参数。
- Bridges Python candidate generation with COMSOL/MATLAB LiveLink simulation.
  将 Python 候选生成流程与 COMSOL/MATLAB LiveLink 仿真桥接。
- Shows candidate rankings, scores, mode previews, reports, and ZIP result packages.
  展示候选排序、评分、模态预览、报告和 ZIP 结果包。

## Quick Launch / 快速启动

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Launch the local Studio:

```powershell
python scripts/launch_chladni_studio.py
```

Or start the UI directly:

```powershell
python -m src.main target-ui --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

## COMSOL Automation / COMSOL 自动化

For full automatic simulation, the deployed machine needs working local COMSOL and MATLAB installations with LiveLink available. After configuration, the software can prepare the target, generate candidates, connect to `mphserver`, run COMSOL simulation, score results, and refresh the frontend ranking view without requiring the user to operate COMSOL manually.

完整自动仿真需要部署机器本地安装并配置好 COMSOL、MATLAB 和 LiveLink。配置完成后，软件可以自动完成目标预处理、候选生成、连接 `mphserver`、运行 COMSOL 仿真、评分排序和前端刷新，用户不需要手动操作 COMSOL。

Check readiness:

```powershell
python -m src.main diagnose-comsol
```

Inspect automatic COMSOL/MATLAB discovery:

```powershell
python -m src.main discover-comsol
```

Write accepted discovery results into `config.yaml`:

```powershell
python -m src.main apply-comsol-discovery
```

Run the automatic workflow:

```powershell
python -m src.main run-workflow --limit 2 --num-modes 20
```

## Current Development Status / 当前开发状态

The project currently has a working local Studio UI, candidate generation, target preprocessing, scoring, artifact management, COMSOL diagnostics, LiveLink runner scaffolding, parameterized baseline MPH models, and draft user/deployment documentation. The next major work is deeper COMSOL-model-specific validation and real-lab calibration after the physical baseline model and measured material data are frozen.

项目目前已经具备本地 Studio 界面、候选生成、目标预处理、评分、产物管理、COMSOL 诊断、LiveLink 运行骨架、参数化基准 MPH 模型和开发版用户/部署文档。下一阶段重点是在物理基准模型和实测材料数据冻结后，继续补充更深的 COMSOL 模型级校验与真实实验校准。

## Coding Rule / 代码规则

Hand-written source code should keep bilingual Chinese/English comments for non-programmers.
手写源码需要保持中英文双语注释，方便零基础成员理解。

```powershell
python scripts/check_bilingual_comments.py
```
