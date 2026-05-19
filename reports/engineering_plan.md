# Chladni Inverse Design Engineering Plan

## 1. Product Definition

本项目的软件目标是帮助用户从手绘目标节点线图案出发，获得一个可制造的阶梯厚度 Chladni 板设计。  
The product goal is to help users start from a hand-drawn target nodal pattern and obtain a manufacturable stepped-thickness Chladni plate design.

## 2. First-Version Technical Boundary

第一版采用半自动工程闭环，不直接追求完全自动化 AI 设计。  
The first version uses a semi-automatic engineering loop rather than a fully automatic AI designer.

```text
target image
-> Python target preprocessing
-> candidate H.csv generation
-> COMSOL manual or semi-automatic simulation
-> COMSOL mode export
-> Python nodal extraction
-> Python scoring and ranking
```

## 3. Resolution Decision

第一版建议固定算法比较分辨率为 `256 x 256`。  
The first version should fix the algorithmic comparison resolution at `256 x 256`.

```text
UI drawing canvas: 512 x 512
internal target binary map: 256 x 256
COMSOL displacement grid after import: 256 x 256
thickness design grid: 6 x 6
```

这样可以让用户绘图足够顺滑，同时避免第一版评分和 COMSOL 数据处理过重。  
This keeps drawing smooth for users while avoiding excessive scoring and COMSOL-data cost in the first version.

## 4. Core Data Contract

Python 输出给 COMSOL：  
Python output to COMSOL:

```text
candidates/candidate_xxx_xxxx/H.csv
candidates/candidate_xxx_xxxx/comsol_parameters.csv
```

COMSOL 输出给 Python：  
COMSOL output to Python:

```text
data/comsol_exports/candidate_xxx_xxxx/frequencies.csv
data/comsol_exports/candidate_xxx_xxxx/mode_01.csv
data/comsol_exports/candidate_xxx_xxxx/mode_02.csv
...
```

## 5. First Milestone Acceptance Criteria

第一阶段完成标准：  
First-stage acceptance criteria:

```text
1. Python can generate valid 6 x 6 H.csv files.
2. Each H.csv respects the neighbour thickness difference constraint.
3. COMSOL has a documented input parameter format.
4. Python can read COMSOL x,y,w mode CSV files.
5. Python can extract nodal regions from mode shapes.
6. Python can compare nodal regions with target patterns.
7. Python can produce ranked_candidates.csv.
```

## 6. Next Engineering Steps

推荐下一步顺序：  
Recommended next steps:

```text
1. Put one simple target image into data/target_patterns/target.png.
2. Run python -m src.main prepare-target.
3. Import one generated comsol_parameters.csv into the COMSOL template model.
4. Export mode_01.csv ... mode_20.csv and frequencies.csv.
5. Run python -m src.main score-candidates.
6. Review candidates/ranked_candidates.csv.
```
