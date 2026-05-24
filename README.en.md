# Chladni Plate Inverse Design System

[Language](./README.md): [Bilingual](./README.md) | [中文](./README.zh-CN.md) | English

This project is a Chladni plate inverse-design software system. The goal is to let a user provide a target pattern, then let the software prepare the target, generate thickness matrices, run COMSOL/MATLAB LiveLink simulation, extract nodal lines, score candidates, rank results, and package outputs.

## Current Goal

The first milestone is a stable semi-automatic to automatic loop:

```text
target image -> target_binary.npy -> H.csv -> COMSOL exports -> nodal extraction -> scoring -> ranking
```

The current bridge contract uses the real `150 mm x 150 mm` plate with an odd `15 x 15` thickness grid, about `10 mm` per cell, and one fixed centre cell. Material parameters, scoring weights, target patterns, and run presets can be edited from the local Studio UI.

## Recommended Early Settings

```text
drawing canvas: 512 x 512
algorithm image size: 256 x 256
target line width: 8-16 px
thickness grid: 15 x 15
thickness levels: 0.6, 0.8, 0.9, 1.0, 1.3, 1.4, 1.8, 2.0 mm
COMSOL modes: 20
```

## Quick Start

Install dependencies:

```powershell
pip install -r requirements.txt
```

Launch the local Studio:

```powershell
python scripts/launch_chladni_studio.py
```

Or start the target-design UI directly:

```powershell
python -m src.main target-ui --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

## Main Features

- Users can draw a target pattern or drag photos/images into the canvas.
- The frontend saves the target, shows processed previews, foreground area, connected component count, and suitability hints.
- Material parameters can be edited in the frontend, including Young's modulus, Poisson's ratio, density, and heat-transfer-related values.
- The Run panel provides Smoke, Review, and Full presets, with preflight checks for target state, parameter ranges, and COMSOL diagnostics.
- The ranking panel shows candidate designs, best modes, scores, frequencies, comparison images, reports, and ZIP packages.
- The backend exposes a command-line workflow so deployed installations can automate COMSOL/MATLAB from the software.

## Common Commands

Generate candidate thickness matrices:

```powershell
python -m src.main generate-candidates
```

Simulate one candidate through COMSOL LiveLink:

```powershell
python -m src.main simulate-candidate --candidate-id candidate_011_0000
```

Run the automatic workflow:

```powershell
python -m src.main run-workflow --limit 2 --num-modes 20
```

Check local COMSOL/MATLAB readiness:

```powershell
python -m src.main diagnose-comsol
```

Run the Python-side self-test:

```powershell
python -m src.main self-test
```

## Documentation

- [Windows/macOS/Linux Bilingual Deployment Guide](./docs/deployment_guide.md)
- [Software User Manual](./docs/user_manual.md)
- [Documentation Index](./docs/README.md)
- [Ordered Remaining Work Plan](./reports/remaining_work_plan.md)

These documents are still development versions. Before release, they should be completed with final screenshots, measured material parameters, and lab-specific COMSOL/MATLAB paths and licensing notes.

## Coding Rule

Hand-written source code should keep bilingual Chinese/English comments for non-programmers. Check coverage with:

```powershell
python scripts/check_bilingual_comments.py
```
