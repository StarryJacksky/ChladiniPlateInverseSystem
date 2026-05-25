# Chladni Plate 逆向设计系统

[语言](./README.md): [双语](./README.md) | 中文 | [English](./README.en.md)

这是一个 Chladni 板逆向设计软件项目。目标是让用户给定目标图案后，系统自动完成目标预处理、厚度矩阵生成、COMSOL/MATLAB LiveLink 仿真、节点线提取、评分排序和结果打包。

## 当前目标

第一阶段先建立稳定的半自动到自动化闭环：

```text
target image -> target_binary.npy -> H.csv -> COMSOL exports -> nodal extraction -> scoring -> ranking
```

当前桥接约定使用真实 `150 mm x 150 mm` 板，厚度网格为奇数 `15 x 15`，每格约 `10 mm`，中心格固定。材料参数、评分权重、目标图案和运行预设都可以从本地 Studio 界面调整。

## 推荐起步设置

```text
drawing canvas: 512 x 512
algorithm image size: 256 x 256
target line width: 8-16 px
thickness grid: 15 x 15
thickness levels: 0.6, 0.8, 0.9, 1.0, 1.3, 1.4, 1.8, 2.0 mm
COMSOL modes: 20
```

## 快速开始

安装依赖：

```powershell
pip install -r requirements.txt
```

启动本地 Studio：

```powershell
python scripts/launch_chladni_studio.py
```

或者直接启动目标设计界面：

```powershell
python -m src.main target-ui --port 8765
```

然后打开：

```text
http://127.0.0.1:8765
```

## 主要功能

- 用户可以手绘图案，也可以拖入照片或图片作为目标。
- 前端会保存目标图、显示预处理预览、目标面积、连通区域数量和适用性提醒。
- 材料参数支持在前端编辑，包括杨氏模量、泊松比、密度和传热相关参数。
- Run 面板提供 Smoke、Review、Full 三种运行预设，并在启动前做目标、参数和 COMSOL 诊断预检。
- 排名面板可以查看候选设计、最佳模态、评分、频率、对比图、报告和 ZIP 打包文件。
- 后端支持命令行自动工作流，便于部署后由软件自动驱动 COMSOL/MATLAB。

## 常用命令

生成候选厚度矩阵：

```powershell
python -m src.main generate-candidates
```

运行一名候选的 COMSOL LiveLink 仿真：

```powershell
python -m src.main simulate-candidate --candidate-id candidate_011_0000
```

运行自动工作流：

```powershell
python -m src.main run-workflow --limit 2 --num-modes 20
```

检查本地 COMSOL/MATLAB 部署：

```powershell
python -m src.main diagnose-comsol
```

单独查看 COMSOL/MATLAB 自动发现结果：

```powershell
python -m src.main discover-comsol
```

把确认后的发现结果写入 `config.yaml`：

```powershell
python -m src.main apply-comsol-discovery
```

运行 Python 侧自检：

```powershell
python -m src.main self-test
```

## 文档

- [Windows/macOS/Linux 部署教程](./docs/deployment_guide.zh-CN.md) ([双语](./docs/deployment_guide.md) | [English](./docs/deployment_guide.en.md))
- [软件使用说明书](./docs/user_manual.zh-CN.md) ([双语](./docs/user_manual.md) | [English](./docs/user_manual.en.md))
- [项目代码结构与逻辑说明](./docs/code_structure.zh-CN.md) ([双语](./docs/code_structure.md) | [English](./docs/code_structure.en.md))
- [文档索引](./docs/README.zh-CN.md) ([双语](./docs/README.md) | [English](./docs/README.en.md))
- [后续任务规划](./reports/remaining_work_plan.zh-CN.md) ([双语](./reports/remaining_work_plan.md) | [English](./reports/remaining_work_plan.en.md))

这些文档目前是开发版。正式发布前还需要加入最终界面截图、真实实验材料参数、实验室 COMSOL/MATLAB 安装路径和授权注意事项。

## 代码规则

手写源码需要保持中英文双语注释，方便零基础成员理解。检查命令：

```powershell
python scripts/check_bilingual_comments.py
```

修改 README 或文档后检查链接：

```powershell
python scripts/check_docs_links.py
```

检查保守的产物清理行为：

```powershell
python scripts/check_artifact_cleanup.py
```
