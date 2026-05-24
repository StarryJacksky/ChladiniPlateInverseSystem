# Chladni Inverse Design Engineering Plan

## 1. Product Definition

本项目的软件目标是帮助用户从手绘目标节点线图案出发，获得一个可制造的阶梯厚度 Chladni 板设计。
The product goal is to help users start from a hand-drawn target nodal pattern and obtain a manufacturable stepped-thickness Chladni plate design.

## 2. First-Version Technical Boundary

第一版已经从半自动工程闭环推进到本地自动化闭环：用户给定图案后，Python 负责目标预处理、候选生成、COMSOL/MATLAB LiveLink 调度、评分和结果展示。
The first version has moved from a semi-automatic engineering loop toward a local automated loop: after the user provides a pattern, Python handles target preprocessing, candidate generation, COMSOL/MATLAB LiveLink orchestration, scoring, and result display.

```text
target image
-> Python target preprocessing
-> candidate H.csv generation
-> COMSOL/MATLAB LiveLink automated simulation
-> COMSOL mode export
-> Python nodal extraction
-> Python scoring and ranking
-> frontend result review
```

当前仍保留命令行入口，便于调试每个阶段；部署目标则是一键式用户流程，不要求用户手动操作 COMSOL。
Command-line entry points remain for debugging each stage; the deployment target is a one-action user workflow that does not require the user to operate COMSOL manually.

## 3. Resolution Decision

第一版建议固定算法比较分辨率为 `256 x 256`。
The first version should fix the algorithmic comparison resolution at `256 x 256`.

```text
UI drawing canvas: 512 x 512
internal target binary map: 256 x 256
COMSOL displacement grid after import: 256 x 256
thickness design grid: 15 x 15
```

这样可以让用户绘图足够顺滑，同时避免第一版评分和 COMSOL 数据处理过重。
This keeps drawing smooth for users while avoiding excessive scoring and COMSOL-data cost in the first version.

The `15 x 15` grid is the current calibrated choice. It keeps the design grid odd, gives one fixed centre cell, and maps the real `150 mm x 150 mm` plate to 10 mm design cells.

## 4. Frontend Target Drawing Module

规划书原始版本只隐含了 `UI drawing canvas: 512 x 512`，但没有把前端单独列成模块。当前项目需要一个客制化图案入口，让用户能直接画目标节点线，而不是只手动替换 `target.png`。

第一版前端目标：

```text
1. 512 x 512 drawing canvas.
2. Brush, eraser, clear, undo/redo.
3. Adjustable stroke width, default around 8-16 px.
4. Optional centre clamp preview/mask.
5. Import existing PNG target.
6. Export/save target.png into data/target_patterns/target.png.
7. Trigger or guide python -m src.main prepare-target.
```

This frontend should be a practical drawing tool, not a marketing landing page. The first screen should be the drawing workspace.

Current implementation:

```text
python -m src.main target-ui --port 8765
```

The local UI now loads or creates `data/target_patterns/target.png`, provides brush/eraser/undo/redo/import/drag-and-drop/save controls, overlays the calibrated `15 x 15` grid and centre clamp, then runs the existing target preprocessing pipeline after save. The Target tab now surfaces the processed preview, foreground area, connected component count, suitability recommendation, and warning flags from `target_analysis.json`, so imported photos or custom marks can be judged before a COMSOL run.

The deployment launcher is now:

```text
python scripts/launch_chladni_studio.py
```

It runs the Python-only self-test, selects an available UI port, starts the local studio, and opens the browser unless `--no-browser` is provided.

OS-level launch wrappers are also present: macOS can double-click `scripts/launch_chladni_studio.command`, and Windows can double-click `scripts\launch_chladni_studio.bat`. Both wrappers enter the project directory and call the same Python launcher, so deployment users do not need to remember terminal commands.

It also exposes first-pass material controls for density, Young's modulus, Poisson ratio, thermal conductivity, heat capacity, and thermal expansion. These values are saved back to `config.yaml`, exported as `material_parameters.csv` in candidate folders, and are ready to be bound to the COMSOL material contract. The material panel now includes editable presets for resin-like materials. The scoring controls expose roughness, mass, frequency weights, and preferred frequency range, also written back to `config.yaml`, with balanced, similarity-first, frequency-targeted, and smooth-light profiles.

The first automatic workflow control is now in place. The UI can launch a background job that prepares the target, generates candidates, optionally runs COMSOL LiveLink, scores available exports, and refreshes ranking data. The Run tab now includes Smoke, Review, and Full presets for common candidate/mode counts. The Python side also attempts to start COMSOL `mphserver` automatically when `auto_start_server` is enabled in `config.yaml`, and the workflow status now reports the active candidate index during simulation.

Workflow status is now persisted to `data/comsol_exports/workflow_state.json`. If the local UI/server restarts while a workflow was marked as running, the restored state is marked as interrupted instead of leaving the user with a stale running job. The persisted state now also keeps a bounded event timeline for queued, target preparation, candidate generation, simulation, scoring, completion, interruption, and error stages.

The deployment diagnostics layer has also started. The UI and command line can check the COMSOL command, MATLAB command, inferred COMSOL/MATLAB versions, common license environment variables, bound MPH model, LiveLink runner, export directory writability, optional source model, and mphserver reachability through a real TCP connection probe before the user starts an automated run. The Run tab now also exposes a Python-only self-test that verifies diagnostics readiness, 15 x 15 calibration, LiveLink runner contract tokens, export-directory writes, 225-row thickness parameter export, material-parameter export, and MATLAB batch construction without launching COMSOL or MATLAB.

LiveLink stdout/stderr is now streamed while the process is running and captured into log files. Single-candidate runs write `data/comsol_exports/<candidate_id>/livelink.log`, legacy batch runs write `data/comsol_exports/livelink_batch.log`, and candidate-level MATLAB/COMSOL output lines are forwarded into workflow timeline events. Stalled LiveLink commands are now guarded by `livelink_timeout_s`, and `server_start_timeout_s` controls how long Python waits for `mphserver` to become reachable.

The UI can now read recent log tails through `/api/logs`, including `mphserver.log`, batch LiveLink logs, and recent candidate LiveLink logs. It also shows the workflow event timeline in the Run tab, so users can see stage-level automation progress without opening files manually. Timeline log lines can be toggled when long MATLAB/COMSOL runs produce too much raw output, consecutive raw log events are grouped, and failed/interrupted runs now surface recovery hints for timeout, mphserver, license, MATLAB, and MPH-model issues.

The UI now includes an artifact summary panel backed by `/api/artifacts`. It reports candidate files, COMSOL exports, mode CSV files, preview images, logs, saved MPH models, processed targets, workflow state, deduplicated total size, and largest generated files. A cleanup preview backed by `/api/artifacts/cleanup-preview` estimates recoverable space from saved MPH copies, regenerated preview images, and temporary workflow files. Confirmed cleanup is backed by `/api/artifacts/cleanup`, refuses to run while a workflow is active, and only deletes regenerable or temporary artifact classes that match the configured retention policy. The current policy keeps the latest three generations and files newer than fourteen days, and the Run tab can edit that policy without hand-editing `config.yaml`.

The result-review panel now supports candidate detail inspection: ranked candidates can be searched, sorted, filtered by minimum IoU, and selected to show target/simulated/overlay comparison images, thickness preview images, best-mode score metrics, frequency data, and rendered COMSOL mode previews. It also includes a scored mode list so users can switch the comparison view across exported modes, plus a generation history panel that summarises candidate counts, simulated counts, scored counts, and the best scored candidate per generation. The generation history browser can now filter all, simulated, scored, or best-candidate generations, and it includes a compact trend view for recent scored-generation IoU and score movement. Candidate result images can be opened in a larger inspection viewer for target, simulated, overlay, thickness, and mode preview review. Candidate detail now includes a ZIP package download for the design matrix, COMSOL parameter tables, scoring files, modal exports, previews, comparison images, and manifest.

## 5. Core Data Contract

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

## 6. First Milestone Acceptance Criteria

第一阶段完成标准：
First-stage acceptance criteria:

```text
1. Python can generate valid 15 x 15 H.csv files.
2. Each H.csv respects the neighbour thickness difference constraint.
3. COMSOL has a documented input parameter format.
4. Python can read COMSOL x,y,w mode CSV files.
5. Python can extract nodal regions from mode shapes.
6. Python can compare nodal regions with target patterns.
7. Python can produce ranked_candidates.csv.
8. User can create or import a custom target pattern through a drawing UI.
```

## 7. Next Engineering Steps

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

After the 15 x 15 COMSOL bridge smoke test, step 3 and step 4 are now represented by:

```text
python -m src.main simulate-candidate --candidate-id candidate_xxx_xxxx
```

The first end-to-end 15 x 15 loop has also produced a 20-mode ranking entry:

```text
candidate: candidate_011_0000
best mode: 3
best IoU: 0.32011696912359167
best Dice: 0.48498273503159817
frequency: 43.2866986584 Hz
final score: -4.5089468360106455
```

The nodal interpolation bug from the first scoring pass has been fixed by replacing sparse zero-filled pixels with inverse-distance interpolation from COMSOL sample points. The current next optimisation work is to run multiple candidates through the bridge and compare their ranked scores.

Batch simulation is exposed as:

```text
python -m src.main simulate-batch --generation 12 --limit 2 --num-modes 3
```

The first batch smoke test for generation 12 simulated two candidates with 3 modes each and produced:

```text
rank 1: candidate_012_0000, mode 3, IoU 0.28276199804113616, Dice 0.44086432007329923, final score -4.145379074949048
rank 2: candidate_012_0001, mode 3, IoU 0.306640625, Dice 0.4693572496263079, final score -4.465402182206029
```

`candidate_012_0001` has better pattern similarity, but `candidate_012_0000` currently ranks higher because the roughness penalty is lower. This confirms that penalty weighting is already affecting optimisation choices.

Nodal postprocessing now removes small isolated components and masks the simulated centre clamp region before scoring, matching the target preprocessing path more closely.

## 8. Remaining Work

当前规划书里还没有完全完成的部分：

```text
Frontend remaining:
1. Add project-specific preset calibration once physical material measurements are available.

Backend remaining:
1. Harden COMSOL/MATLAB startup checks with active vendor version/license probes and authentication handling beyond the current path/version hints, license environment hints, and TCP mphserver probe.

Optimisation and physics remaining:
1. Run larger random-search batches with full 20-mode exports and review ranked_candidates.csv.
2. Tune roughness, mass, frequency, and similarity weights so final score matches design intent.
3. Continue nodal extraction QA by visually inspecting mode previews and adjusting epsilon/dilation settings.
4. Implement genetic algorithm selection, crossover, mutation, and repair after random search is stable.
5. Defer surrogate modelling until enough COMSOL simulation data exist, likely 100+ candidates.
6. Compare simulated frequencies/patterns with physical plate measurements when available.
```
