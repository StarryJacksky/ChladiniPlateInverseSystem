# 项目代码结构与逻辑说明

[语言](./code_structure.md): [双语](./code_structure.md) | 中文 | [English](./code_structure.en.md)

本文面向零基础读者，说明本项目每个主要目录的用途，以及数据如何从用户图案流向最终结果。

## 1. 整体逻辑

软件会把用户给定的目标图案转换为 Chladni 板候选设计。

```text
用户图片或手绘图案
        |
        v
目标预处理
        |
        v
15 x 15 厚度候选矩阵
        |
        v
COMSOL/MATLAB 仿真
        |
        v
节点线提取与评分
        |
        v
排序结果、报告、结果包
```

当前物理约定是真实 `150 mm x 150 mm` 板和 `15 x 15` 厚度网格。

## 2. 根目录文件

- `README.md`：GitHub 首页和第一入口。
- `config.yaml`：主配置文件，包含几何、材料、评分权重、路径和 COMSOL/MATLAB 设置。
- `requirements.txt`：Python 依赖包列表。
- `.gitignore`：Git 应忽略的文件，例如缓存和临时产物。

零基础读者通常先看 `README.md`，再看部署指南、使用说明书和本文档。

## 3. `frontend/`

`frontend/target_designer.html` 是本地 Studio 的主界面。

它包含绘图画布、图片导入控件、Target/Tune/Results/Run 页签、调用本地后端 API 的 JavaScript，以及工程控制台的视觉样式。

前端不会直接运行 COMSOL，而是把请求发送给 `src/frontend/target_ui_server.py` 中的本地 Python 服务。

## 4. `src/main.py`

`src/main.py` 是命令行入口。

常见命令包括：

- `target-ui`：启动本地网页界面。
- `prepare-target`：预处理目标图。
- `generate-candidates`：生成厚度矩阵。
- `run-workflow`：运行自动设计流程。
- `diagnose-comsol`：检查 COMSOL/MATLAB 是否准备好。
- `self-test`：运行部署自检。

如果想理解命令如何进入项目，可以从这里开始。

## 5. `src/config.py`

`src/config.py` 负责读取 `config.yaml` 并创建必要目录。

大多数模块都会从这里拿到一个 `config` 字典。这个字典告诉代码：目标图在哪里、候选结果保存在哪里、板尺寸和网格尺寸是什么、材料参数和评分参数是什么，以及 COMSOL 和 MATLAB 在哪里。

## 6. `src/target/`

这个目录负责把用户手绘或导入图片处理成可评分目标。

- `preprocess_target.py`：把输入图转换成干净的二值目标。
- `analyse_target.py`：分析目标质量，例如前景面积、连通区域数量和复杂度警告。

重要输出：

- `target_binary.npy`：评分代码使用的数值目标数组。
- `target_preview.png`：UI 中显示的预览图。
- `target_analysis.json`：UI 中显示的目标质量数据。

## 7. `src/candidate/`

这个目录负责生成一个阶梯厚度板候选。

- `generate_candidate.py`：生成 `15 x 15` 厚度矩阵。
- `constraints.py`：保证生成值符合物理和设计约束。

重要输出：

- `H.csv`：候选厚度矩阵。
- `metadata.json`：生成设置和候选元数据。
- `comsol_parameters.csv`：可传给 COMSOL 的参数值。

## 8. `src/optimisation/`

这个目录控制候选批次和工作流顺序。

- `random_search.py`：生成多个候选厚度矩阵和预览图。
- `workflow.py`：串联目标预处理、候选生成、可选 COMSOL 仿真和评分。

当前搜索方法刻意保持简单稳健。等真实 COMSOL 和实体验证数据稳定后，这里可以扩展为更强的优化方法。

## 9. `src/comsol/`

这个目录负责 Python 与 COMSOL/MATLAB 之间的连接。

- `discovery.py`：查找正在运行的 COMSOL/MATLAB 进程和常见安装路径。
- `diagnostics.py`：检查本机是否准备好自动仿真。
- `server.py`：启动或连接 COMSOL `mphserver`。
- `run_livelink.py`：为一个或多个候选运行 MATLAB LiveLink 命令。
- `export_parameters.py`：以 COMSOL 友好的格式写出候选参数。
- `import_results.py`：读取 COMSOL 导出的频率和模态结果。
- `validate_exports.py`：检查 COMSOL 导出结果目录。
- `model_audit.py`：记录绑定 COMSOL 模型的基础信息。

这是整个项目里最依赖部署环境的部分，因为它依赖本地 COMSOL、本地 MATLAB、LiveLink、授权和最终 `.mph` 模型。

## 10. `comsol_templates/`

这个目录保存 COMSOL 模型文件和 LiveLink 使用的 MATLAB 脚本。

- `Chladni_15x15_parameterized.mph`：`15 x 15` 网格的参数化基准模型。
- `Chladni_15x15_bound.mph`：当前桥接使用的绑定模型版本。
- `run_chladni_candidate.m`：接收候选参数、运行 COMSOL 并导出结果的 MATLAB 脚本。
- `export_specification.md`：说明预期 COMSOL 导出文件。

这个目录要等基准 COMSOL 模型验收后才会最终冻结。

## 11. `src/nodal/` 与 `src/scoring/`

`src/nodal/` 把仿真模态场转换成节点线掩膜。

- `extract_nodal.py`：从仿真数组中提取节点线区域。

`src/scoring/` 把仿真节点线掩膜与用户目标进行比较。

- `metrics.py`：计算 IoU 和 Dice 等相似度指标。
- `score_candidate.py`：结合相似度和惩罚项，并写出排序数据。

重要输出：

- `score.json`：单个候选的详细评分。
- `ranked_candidates.csv`：候选排序表。

## 12. `src/visualisation/`

这个目录负责生成便于人查看的图片。

- `plot_thickness.py`：根据 `H.csv` 绘制厚度场预览。
- `plot_modes.py`：绘制 COMSOL 模态预览和对比图。

UI 会在 Results 页使用这些图片。

## 13. `src/frontend/`

`src/frontend/target_ui_server.py` 是本地 Studio 背后的 Python 服务。

它提供 API 来读取和保存目标画布、更新材料和评分设置、更新 COMSOL 设置、运行工作流、读取排行和候选详情、生成报告、查看日志和诊断，以及安全取消工作流。

可以把这个文件理解为 HTML 界面和 Python 算法代码之间的桥。

## 14. `scripts/`

这个目录包含辅助开发者、部署者和 COMSOL 建模者的脚本。

重要 Python 脚本：

- `launch_chladni_studio.py`：启动 UI 并寻找可用本地端口。
- `check_bilingual_comments.py`：检查源码双语注释。
- `check_config_contract.py`：检查核心配置约定。
- `check_discovery_fixtures.py`：检查 COMSOL/MATLAB 自动发现样例。
- `check_python_smoke.py`：验证无 COMSOL 的目标预处理和候选生成。

重要 MATLAB 脚本：

- `parameterize_chladni_15x15.m`：帮助创建参数化 `15 x 15` COMSOL 模型。
- `bind_chladni_15x15_model.m`：把模型参数绑定到 LiveLink 流程。
- `probe_chladni_faces.m` 等探测脚本：检查 COMSOL 几何选择。

`.bat`、`.sh` 和 `.command` 启动器是给 Windows、Linux 和 macOS 用户使用的便捷包装。

## 15. 数据目录

- `data/target_patterns/`：用户目标图。
- `data/processed_targets/`：处理后的目标数组、预览和分析。
- `candidates/`：生成的厚度候选。
- `data/comsol_exports/`：COMSOL 输出文件、模态 CSV、日志、报告和工作流状态。
- `reports/`：规划、审计、校准说明和后续任务表。

多数生成数据可以重新创建，但大型 COMSOL 输出和有用的验证记录应谨慎处理。

## 16. 推荐阅读顺序

零基础读者想理解代码时，建议按这个顺序读：

1. `README.md`：先看项目目标。
2. `docs/user_manual.md`：了解用户如何使用软件。
3. `docs/code_structure.md`：理解代码地图。
4. `src/main.py`：理解命令如何进入系统。
5. `src/optimisation/workflow.py`：理解自动流程如何串起来。
6. `src/frontend/target_ui_server.py`：理解前端如何调用后端。
7. `src/target/`、`src/candidate/`、`src/scoring/`：理解算法核心。
8. `src/comsol/` 和 `comsol_templates/`：最后再看 COMSOL/MATLAB 桥接。

## 17. 仍需真实数据的部分

有些部分要等实验数据冻结后才能视为最终版：

- 最终材料参数。
- 最终 COMSOL 边界名称和模型选择。
- 最终实测频率和实体节点线图案。
- 最终优化权重。
- 最终发布截图。

在此之前，本项目已经可以用于 Python 侧烟测、UI 流程测试、COMSOL/MATLAB 自动发现和桥接规划。
