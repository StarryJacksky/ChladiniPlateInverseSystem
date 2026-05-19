# Chladni Plate Inverse Design

这是一个 Chladni 板逆向设计软件项目的工程骨架。  
This is the engineering scaffold for a Chladni plate inverse-design software project.

## Goal

用户绘制目标节点线图案后，系统会将图案转换为标准化目标图，再生成离散厚度矩阵，交给 COMSOL 做特征频率仿真，最后用 Python 对仿真节点线和目标图案进行相似度评分。  
After a user draws a desired nodal-line pattern, the system normalises it, generates discrete thickness matrices, sends them to COMSOL for eigenfrequency simulation, and scores simulated nodal lines against the target pattern in Python.

## First Milestone

第一阶段不追求一键式 AI 自动设计，而是建立稳定的半自动闭环：  
The first milestone is not a one-click AI designer, but a stable semi-automatic loop:

```text
target image -> target_binary.npy -> H.csv -> COMSOL exports -> nodal extraction -> scoring -> ranking
```

## Recommended Early Settings

```text
drawing canvas: 512 x 512
algorithm image size: 256 x 256
target line width: 8-16 px
thickness grid: 6 x 6
thickness levels: 2.0, 2.5, 3.0, 3.5 mm
COMSOL modes: 20
```

## Project Structure

```text
src/
  target/          target image processing
  candidate/       thickness matrix generation and constraints
  comsol/          file-based COMSOL interface
  nodal/           nodal-region extraction from mode shapes
  scoring/         IoU, Dice, and objective scoring
  optimisation/    random-search candidate generation and ranking
data/
  target_patterns/
  processed_targets/
  comsol_exports/
candidates/
comsol_templates/
reports/
```

## Usage

Install dependencies:

```powershell
pip install -r requirements.txt
```

Generate candidate matrices:

```powershell
python -m src.main generate-candidates
```

After COMSOL exports `mode_01.csv ... mode_20.csv` and `frequencies.csv`, score candidates:

```powershell
python -m src.main score-candidates
```

## Coding Rule

源码中的每一行 Python 代码都带有中英文双语注释，方便非编程背景成员理解。  
Every Python code line includes a bilingual Chinese-English comment so non-programmers can follow the logic.
