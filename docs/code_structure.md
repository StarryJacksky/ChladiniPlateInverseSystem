# Project Code Structure and Logic / 项目代码结构与逻辑说明

[Language / 语言](./code_structure.md): Bilingual | [中文](./code_structure.zh-CN.md) | [English](./code_structure.en.md)

This document explains what each main folder does and how data moves through the project.
本文说明每个主要目录的用途，以及数据如何在项目中流动。

It is written for beginners who may not know Python, COMSOL, MATLAB, or web development yet.
它面向还不熟悉 Python、COMSOL、MATLAB 或网页开发的零基础读者。

## 1. Big Picture / 整体逻辑

The software turns a user target pattern into candidate Chladni plate designs.
软件会把用户给定的目标图案转换为 Chladni 板候选设计。

```text
user image or drawing
用户图片或手绘图案
        |
        v
target preprocessing
目标预处理
        |
        v
15 x 15 thickness candidates
15 x 15 厚度候选矩阵
        |
        v
COMSOL/MATLAB simulation
COMSOL/MATLAB 仿真
        |
        v
nodal-line extraction and scoring
节点线提取与评分
        |
        v
ranked results, reports, packages
排序结果、报告、结果包
```

The current physical contract is a real `150 mm x 150 mm` plate with a `15 x 15` thickness grid.
当前物理约定是真实 `150 mm x 150 mm` 板和 `15 x 15` 厚度网格。

## 2. Root Files / 根目录文件

- `README.md`: the GitHub front page and first entry point.
  `README.md`：GitHub 首页和第一入口。
- `config.yaml`: the main project configuration, including geometry, material values, scoring weights, paths, and COMSOL/MATLAB settings.
  `config.yaml`：主配置文件，包含几何、材料、评分权重、路径和 COMSOL/MATLAB 设置。
- `requirements.txt`: Python package dependencies.
  `requirements.txt`：Python 依赖包列表。
- `.gitignore`: files Git should ignore, such as generated cache or temporary outputs.
  `.gitignore`：Git 应忽略的文件，例如缓存和临时产物。

Beginners usually start with `README.md`, then read the deployment guide, user manual, and this code-structure guide.
零基础读者通常先看 `README.md`，再看部署指南、使用说明书和本文档。

## 3. `frontend/` / 前端目录

`frontend/target_designer.html` is the main local Studio interface.
`frontend/target_designer.html` 是本地 Studio 的主界面。

It contains:
它包含：

- the drawing canvas and image import controls.
  绘图画布和图片导入控件。
- the Target, Tune, Results, and Run tabs.
  Target、Tune、Results 和 Run 页签。
- JavaScript code that calls local backend APIs.
  调用本地后端 API 的 JavaScript 代码。
- visual layout and styling for the engineering console.
  工程控制台的视觉布局和样式。

The frontend does not run COMSOL directly.
前端不会直接运行 COMSOL。

Instead, it sends requests to the local Python server in `src/frontend/target_ui_server.py`.
它会把请求发送给 `src/frontend/target_ui_server.py` 中的本地 Python 服务。

## 4. `src/main.py` / 命令入口

`src/main.py` is the command-line entry point.
`src/main.py` 是命令行入口。

Common commands include:
常见命令包括：

- `target-ui`: starts the local web interface.
  `target-ui`：启动本地网页界面。
- `prepare-target`: preprocesses the target image.
  `prepare-target`：预处理目标图。
- `generate-candidates`: generates thickness matrices.
  `generate-candidates`：生成厚度矩阵。
- `run-workflow`: runs the automated design workflow.
  `run-workflow`：运行自动设计流程。
- `diagnose-comsol`: checks COMSOL/MATLAB readiness.
  `diagnose-comsol`：检查 COMSOL/MATLAB 是否准备好。
- `self-test`: runs deployment checks.
  `self-test`：运行部署自检。

If a beginner wants to understand how commands enter the project, start here.
如果零基础读者想理解命令如何进入项目，可以从这里开始。

## 5. `src/config.py` / 配置读取

`src/config.py` loads `config.yaml` and creates required folders.
`src/config.py` 负责读取 `config.yaml` 并创建必要目录。

Most modules receive a `config` dictionary from this file.
大多数模块都会从这里拿到一个 `config` 字典。

That dictionary tells the code:
这个字典告诉代码：

- where target images live.
  目标图在哪里。
- where candidates should be saved.
  候选结果保存在哪里。
- what plate size and grid size are used.
  板尺寸和网格尺寸是什么。
- what material and scoring values should be used.
  材料参数和评分参数是什么。
- where COMSOL and MATLAB are located.
  COMSOL 和 MATLAB 在哪里。

## 6. `src/target/` / 目标图处理

This folder prepares user drawings or imported images for scoring.
这个目录负责把用户手绘或导入图片处理成可评分目标。

- `preprocess_target.py`: converts the input image into a clean binary target.
  `preprocess_target.py`：把输入图转换成干净的二值目标。
- `analyse_target.py`: measures target quality, such as foreground area, connected parts, and complexity warnings.
  `analyse_target.py`：分析目标质量，例如前景面积、连通区域数量和复杂度警告。

Important outputs:
重要输出：

- `target_binary.npy`: the numerical target array used by scoring code.
  `target_binary.npy`：评分代码使用的数值目标数组。
- `target_preview.png`: preview image shown in the UI.
  `target_preview.png`：UI 中显示的预览图。
- `target_analysis.json`: target-quality data shown in the UI.
  `target_analysis.json`：UI 中显示的目标质量数据。

## 7. `src/candidate/` / 候选厚度生成

This folder creates one stepped-thickness plate candidate.
这个目录负责生成一个阶梯厚度板候选。

- `generate_candidate.py`: creates a `15 x 15` thickness matrix.
  `generate_candidate.py`：生成 `15 x 15` 厚度矩阵。
- `constraints.py`: keeps generated values inside physical and design limits.
  `constraints.py`：保证生成值符合物理和设计约束。

Important outputs:
重要输出：

- `H.csv`: the candidate thickness matrix.
  `H.csv`：候选厚度矩阵。
- `metadata.json`: generation settings and candidate metadata.
  `metadata.json`：生成设置和候选元数据。
- `comsol_parameters.csv`: parameter values that can be passed toward COMSOL.
  `comsol_parameters.csv`：可传给 COMSOL 的参数值。

## 8. `src/optimisation/` / 搜索与自动流程

This folder controls candidate batches and workflow order.
这个目录控制候选批次和工作流顺序。

- `random_search.py`: generates many candidate thickness matrices and previews.
  `random_search.py`：生成多个候选厚度矩阵和预览图。
- `workflow.py`: connects target preprocessing, candidate generation, optional COMSOL simulation, and scoring.
  `workflow.py`：串联目标预处理、候选生成、可选 COMSOL 仿真和评分。

The current search method is intentionally simple and robust.
当前搜索方法刻意保持简单稳健。

Later, after real COMSOL and physical validation data are stable, this folder can grow into stronger optimization methods.
之后等真实 COMSOL 和实体验证数据稳定后，这个目录可以扩展为更强的优化方法。

## 9. `src/comsol/` / COMSOL 与 MATLAB 桥接

This folder handles the connection between Python and COMSOL/MATLAB.
这个目录负责 Python 与 COMSOL/MATLAB 之间的连接。

- `discovery.py`: finds already-running COMSOL/MATLAB processes and common install paths.
  `discovery.py`：查找正在运行的 COMSOL/MATLAB 进程和常见安装路径。
- `diagnostics.py`: checks whether the local machine is ready for automated simulation.
  `diagnostics.py`：检查本机是否准备好自动仿真。
- `server.py`: starts or connects to COMSOL `mphserver`.
  `server.py`：启动或连接 COMSOL `mphserver`。
- `run_livelink.py`: runs MATLAB LiveLink commands for one or more candidates.
  `run_livelink.py`：为一个或多个候选运行 MATLAB LiveLink 命令。
- `export_parameters.py`: writes candidate parameters in a COMSOL-friendly format.
  `export_parameters.py`：以 COMSOL 友好的格式写出候选参数。
- `import_results.py`: reads COMSOL-exported frequencies and mode shapes.
  `import_results.py`：读取 COMSOL 导出的频率和模态结果。
- `validate_exports.py`: checks exported COMSOL result folders.
  `validate_exports.py`：检查 COMSOL 导出结果目录。
- `model_audit.py`: records basic information about the bound COMSOL model.
  `model_audit.py`：记录绑定 COMSOL 模型的基础信息。

This folder is the most deployment-sensitive part of the project.
这个目录是整个项目里最依赖部署环境的部分。

It depends on local COMSOL, local MATLAB, LiveLink, licenses, and the final `.mph` model.
它依赖本地 COMSOL、本地 MATLAB、LiveLink、授权和最终 `.mph` 模型。

## 10. `comsol_templates/` / COMSOL 模型与 LiveLink 模板

This folder stores COMSOL model files and MATLAB scripts used by LiveLink.
这个目录保存 COMSOL 模型文件和 LiveLink 使用的 MATLAB 脚本。

- `Chladni_15x15_parameterized.mph`: parameterized baseline model for the `15 x 15` grid.
  `Chladni_15x15_parameterized.mph`：`15 x 15` 网格的参数化基准模型。
- `Chladni_15x15_bound.mph`: bound model variant used by the current bridge.
  `Chladni_15x15_bound.mph`：当前桥接使用的绑定模型版本。
- `run_chladni_candidate.m`: MATLAB script that receives candidate parameters, runs COMSOL, and exports results.
  `run_chladni_candidate.m`：接收候选参数、运行 COMSOL 并导出结果的 MATLAB 脚本。
- `export_specification.md`: explains expected COMSOL export files.
  `export_specification.md`：说明预期 COMSOL 导出文件。

This folder becomes final only after the baseline COMSOL model is accepted.
这个目录要等基准 COMSOL 模型验收后才会最终冻结。

## 11. `src/nodal/` and `src/scoring/` / 节点线与评分

`src/nodal/` converts simulated mode fields into nodal-line masks.
`src/nodal/` 把仿真模态场转换成节点线掩膜。

- `extract_nodal.py`: extracts nodal regions from simulation arrays.
  `extract_nodal.py`：从仿真数组中提取节点线区域。

`src/scoring/` compares simulated nodal masks with the user target.
`src/scoring/` 把仿真节点线掩膜与用户目标进行比较。

- `metrics.py`: computes similarity metrics such as IoU and Dice.
  `metrics.py`：计算 IoU 和 Dice 等相似度指标。
- `score_candidate.py`: combines similarity with penalties and writes ranking data.
  `score_candidate.py`：结合相似度和惩罚项，并写出排序数据。

Important outputs:
重要输出：

- `score.json`: detailed score for one candidate.
  `score.json`：单个候选的详细评分。
- `ranked_candidates.csv`: sorted candidate ranking.
  `ranked_candidates.csv`：候选排序表。

## 12. `src/visualisation/` / 可视化

This folder creates images for humans to inspect.
这个目录负责生成便于人查看的图片。

- `plot_thickness.py`: draws thickness-field previews from `H.csv`.
  `plot_thickness.py`：根据 `H.csv` 绘制厚度场预览。
- `plot_modes.py`: draws COMSOL mode previews and comparison images.
  `plot_modes.py`：绘制 COMSOL 模态预览和对比图。

The UI uses these images in the Results tab.
UI 会在 Results 页使用这些图片。

## 13. `src/frontend/` / 本地后端服务

`src/frontend/target_ui_server.py` is the Python server behind the local Studio.
`src/frontend/target_ui_server.py` 是本地 Studio 背后的 Python 服务。

It provides APIs for:
它提供 API 来完成：

- loading and saving the target canvas.
  读取和保存目标画布。
- updating material, scoring, COMSOL, and artifact-retention settings.
  更新材料、评分、COMSOL 和产物保留设置。
- running target preprocessing and workflow jobs.
  运行目标预处理和工作流任务。
- reading rankings, candidate details, reports, logs, and diagnostics.
  读取排行、候选详情、报告、日志和诊断。
- safely cancelling a running workflow.
  安全取消正在运行的工作流。

Think of this file as the bridge between the HTML interface and the Python algorithm code.
可以把这个文件理解为 HTML 界面和 Python 算法代码之间的桥。

## 14. `scripts/` / 辅助脚本

This folder contains scripts that help developers, deployers, and COMSOL model builders.
这个目录包含辅助开发者、部署者和 COMSOL 建模者的脚本。

Important Python scripts:
重要 Python 脚本：

- `launch_chladni_studio.py`: starts the UI and finds an available local port.
  `launch_chladni_studio.py`：启动 UI 并寻找可用本地端口。
- `check_bilingual_comments.py`: checks bilingual source-code comments.
  `check_bilingual_comments.py`：检查源码双语注释。
- `check_config_contract.py`: checks core configuration contracts.
  `check_config_contract.py`：检查核心配置约定。
- `check_discovery_fixtures.py`: checks COMSOL/MATLAB discovery examples.
  `check_discovery_fixtures.py`：检查 COMSOL/MATLAB 自动发现样例。
- `check_python_smoke.py`: verifies Python-only target preprocessing and candidate generation.
  `check_python_smoke.py`：验证无 COMSOL 的目标预处理和候选生成。

Important MATLAB scripts:
重要 MATLAB 脚本：

- `parameterize_chladni_15x15.m`: helps create a parameterized `15 x 15` COMSOL model.
  `parameterize_chladni_15x15.m`：帮助创建参数化 `15 x 15` COMSOL 模型。
- `bind_chladni_15x15_model.m`: binds model parameters to the LiveLink workflow.
  `bind_chladni_15x15_model.m`：把模型参数绑定到 LiveLink 流程。
- `probe_chladni_faces.m` and related probe scripts: inspect COMSOL geometry selections.
  `probe_chladni_faces.m` 等探测脚本：检查 COMSOL 几何选择。

The `.bat`, `.sh`, and `.command` launchers are convenience wrappers for Windows, Linux, and macOS users.
`.bat`、`.sh` 和 `.command` 启动器是给 Windows、Linux 和 macOS 用户使用的便捷包装。

## 15. Data Folders / 数据目录

- `data/target_patterns/`: user target images.
  `data/target_patterns/`：用户目标图。
- `data/processed_targets/`: processed target arrays, previews, and analysis.
  `data/processed_targets/`：处理后的目标数组、预览和分析。
- `candidates/`: generated thickness candidates.
  `candidates/`：生成的厚度候选。
- `data/comsol_exports/`: COMSOL output files, mode CSV files, logs, reports, and workflow state.
  `data/comsol_exports/`：COMSOL 输出文件、模态 CSV、日志、报告和工作流状态。
- `reports/`: planning notes, audits, calibration notes, and remaining-work plans.
  `reports/`：规划、审计、校准说明和后续任务表。

Most generated data can be recreated, but large COMSOL outputs and useful validation records should be handled carefully.
多数生成数据可以重新创建，但大型 COMSOL 输出和有用的验证记录应谨慎处理。

## 16. Normal Developer Reading Order / 推荐阅读顺序

For a beginner who wants to understand the code, read in this order:
零基础读者想理解代码时，建议按这个顺序读：

1. `README.md`
   先看项目目标。
2. `docs/user_manual.md`
   了解用户如何使用软件。
3. `docs/code_structure.md`
   理解代码地图。
4. `src/main.py`
   理解命令如何进入系统。
5. `src/optimisation/workflow.py`
   理解自动流程如何串起来。
6. `src/frontend/target_ui_server.py`
   理解前端如何调用后端。
7. `src/target/`, `src/candidate/`, `src/scoring/`
   理解算法核心。
8. `src/comsol/` and `comsol_templates/`
   最后再看 COMSOL/MATLAB 桥接。

## 17. What Is Still Waiting for Real Data / 仍需真实数据的部分

Some parts should not be treated as final until lab data are frozen:
有些部分要等实验数据冻结后才能视为最终版：

- final material values.
  最终材料参数。
- final COMSOL boundary names and model selections.
  最终 COMSOL 边界名称和模型选择。
- final physical validation frequencies and photographed nodal patterns.
  最终实测频率和实体节点线图案。
- final optimization weights.
  最终优化权重。
- final release screenshots.
  最终发布截图。

Until then, this project is already usable for Python-side smoke testing, UI workflow testing, COMSOL/MATLAB discovery, and bridge planning.
在此之前，本项目已经可以用于 Python 侧烟测、UI 流程测试、COMSOL/MATLAB 自动发现和桥接规划。
