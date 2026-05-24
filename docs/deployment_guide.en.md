# Deployment Guide

[Language](./deployment_guide.md): [Bilingual](./deployment_guide.md) | [中文](./deployment_guide.zh-CN.md) | English

This is the development-version deployment guide for Chladni Studio. The goal is simple: after setup, a user should open the app, provide a target image, and let the local COMSOL/MATLAB bridge produce candidate results automatically.

## 1. What You Need

Required for the Python-only UI and dry run:

- Windows 10/11, macOS, or Linux.
- Python 3.9 or newer.
- Git, or a downloaded ZIP copy of this repository.

Required for automatic simulation:

- COMSOL Multiphysics installed locally.
- MATLAB installed locally.
- COMSOL LiveLink for MATLAB licensed and working.
- A bound Chladni MPH model matching the project contract.

## 2. Get the Project

Using Git:

```bash
git clone <repository-url>
cd ChladiniPlateProject
```

Using a ZIP download:

```text
1. Download the repository ZIP from GitHub.
2. Extract it to a simple path without special characters.
3. Open a terminal in the extracted folder.
```

Recommended paths:

```text
Windows: C:\Users\<you>\Documents\ChladiniPlateProject
macOS:   /Users/<you>/Documents/ChladiniPlateProject
Linux:   /home/<you>/ChladiniPlateProject
```

## 3. Install Python Dependencies

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Activate it on macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

If `python` points to an old Python on macOS/Linux, use `python3` instead.

## 4. First Python-Only Check

Run the self-test:

```bash
python -m src.main self-test
```

Expected result:

```text
"ready": true
```

Warnings about license environment variables can be acceptable if your COMSOL/MATLAB login or local license files work.

## 5. Launch the App

Cross-platform terminal launch:

```bash
python scripts/launch_chladni_studio.py
```

macOS double-click launch:

```text
scripts/launch_chladni_studio.command
```

Windows double-click launch:

```text
scripts\launch_chladni_studio.bat
```

Linux terminal launch:

```bash
./scripts/launch_chladni_studio.sh
```

If the Linux script is not executable:

```bash
chmod +x scripts/launch_chladni_studio.sh
./scripts/launch_chladni_studio.sh
```

The launcher runs a Python-only self-test, finds an available local port, starts the UI, and opens the browser.

## 6. Configure COMSOL and MATLAB

The current development version uses configured executable paths. Running-process detection and automatic discovery of COMSOL/MATLAB installations are planned, but users should still verify or edit `config.yaml` for now.

Open `config.yaml` and check these fields:

```yaml
comsol:
  comsol_command_path: "/Applications/COMSOL64/Multiphysics/bin/comsol"
  matlab_path: "/Applications/MATLAB_R2024a.app/bin/matlab"
  model_path: "comsol_templates/Chladni_15x15_bound.mph"
  runner_path: "comsol_templates/run_chladni_candidate.m"
  server_host: "127.0.0.1"
  server_port: 2036
  auto_start_server: true
```

Windows examples:

```yaml
comsol_command_path: "C:/Program Files/COMSOL/COMSOL64/Multiphysics/bin/win64/comsol.exe"
matlab_path: "C:/Program Files/MATLAB/R2024a/bin/matlab.exe"
```

macOS examples:

```yaml
comsol_command_path: "/Applications/COMSOL64/Multiphysics/bin/comsol"
matlab_path: "/Applications/MATLAB_R2024a.app/bin/matlab"
```

Linux examples:

```yaml
comsol_command_path: "/usr/local/comsol64/multiphysics/bin/comsol"
matlab_path: "/usr/local/MATLAB/R2024a/bin/matlab"
```

Then run diagnostics:

```bash
python -m src.main diagnose-comsol
```

The important required checks are COMSOL command, MATLAB command, bound MPH model, LiveLink runner, exports directory, and timeout configuration.

## 7. First UI Smoke Run

1. Launch Chladni Studio.
2. Open the `Target` tab and draw or import a simple high-contrast image.
3. Click `Save`.
4. Confirm `Target Quality` shows a processed preview and suitability metrics.
5. Open the `Run` tab.
6. Choose `Smoke`.
7. Keep `Run COMSOL` enabled only if COMSOL/MATLAB are configured.
8. Click `Run`.

For Python-only testing, turn off `Run COMSOL`.

## 8. Common Problems

`PermissionError` when starting the UI:

```text
Use another port, or launch through scripts/launch_chladni_studio.py so it can find a free port.
```

COMSOL command missing:

```text
Open config.yaml and set comsol_command_path to the real COMSOL executable.
```

MATLAB command missing:

```text
Open config.yaml and set matlab_path to the real MATLAB executable.
```

License warning:

```text
Open COMSOL and MATLAB manually once, confirm login/license status, then rerun diagnostics.
```

No ranking appears:

```text
Check whether COMSOL mode CSV files and frequencies.csv exist in data/comsol_exports/<candidate_id>.
```

## 9. What Is Still Lab-Specific

These items should be finalized after real project data are available:

- Final material presets from measured density, Young's modulus, Poisson ratio, and thermal parameters.
- Final COMSOL model file, boundary naming, hole/spacer assumptions, and fixed constraints.
- Physical plate frequency and nodal pattern validation.
- Final screenshots for this deployment guide.
