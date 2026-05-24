# Deployment Guide / 部署指南

[Language / 语言](./deployment_guide.md): Bilingual | [中文](./deployment_guide.zh-CN.md) | [English](./deployment_guide.en.md)

This is the development-version deployment guide for Chladni Studio.
这是 Chladni Studio 的开发版部署指南。

The goal is simple: after setup, a user should open the app, provide a target image, and let the local COMSOL/MATLAB bridge produce candidate results automatically.
目标很简单：部署完成后，用户打开软件、给定目标图案，本机 COMSOL/MATLAB 桥接流程自动生成候选结果。

## 1. What You Need / 你需要准备什么

Required for the Python-only UI and dry run:
仅运行 Python UI 与无 COMSOL 自检需要：

- Windows 10/11, macOS, or Linux.
  Windows 10/11、macOS 或 Linux。
- Python 3.9 or newer.
  Python 3.9 或更新版本。
- Git, or a downloaded ZIP copy of this repository.
  Git，或者本仓库 ZIP 压缩包。

Required for automatic simulation:
自动仿真额外需要：

- COMSOL Multiphysics installed locally.
  本机已安装 COMSOL Multiphysics。
- MATLAB installed locally.
  本机已安装 MATLAB。
- COMSOL LiveLink for MATLAB licensed and working.
  COMSOL LiveLink for MATLAB 授权可用。
- A bound Chladni MPH model matching the project contract.
  与项目参数合同匹配的 Chladni MPH 模型。

## 2. Get the Project / 获取项目

Using Git:
使用 Git：

```bash
git clone <repository-url>
cd ChladiniPlateProject
```

Using a ZIP download:
使用 ZIP 下载：

```text
1. Download the repository ZIP from GitHub.
2. Extract it to a simple path without special characters.
3. Open a terminal in the extracted folder.

1. 从 GitHub 下载仓库 ZIP。
2. 解压到没有特殊字符的简单路径。
3. 在解压后的项目文件夹中打开终端。
```

Recommended paths:
推荐路径：

```text
Windows: C:\Users\<you>\Documents\ChladiniPlateProject
macOS:   /Users/<you>/Documents/ChladiniPlateProject
Linux:   /home/<you>/ChladiniPlateProject
```

## 3. Install Python Dependencies / 安装 Python 依赖

Create a virtual environment:
创建虚拟环境：

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:
在 Windows PowerShell 中启用：

```powershell
.\.venv\Scripts\Activate.ps1
```

Activate it on macOS/Linux:
在 macOS/Linux 中启用：

```bash
source .venv/bin/activate
```

Install dependencies:
安装依赖：

```bash
pip install -r requirements.txt
```

If `python` points to an old Python on macOS/Linux, use `python3` instead.
如果 macOS/Linux 上 `python` 指向旧版本，请改用 `python3`。

## 4. First Python-Only Check / 第一次无 COMSOL 检查

Run the self-test:
运行自检：

```bash
python -m src.main self-test
```

Expected result:
预期结果：

```text
"ready": true
```

Warnings about license environment variables can be acceptable if your COMSOL/MATLAB login or local license files work.
如果你的 COMSOL/MATLAB 登录或本地 license 文件可用，license 环境变量警告可以暂时接受。

## 5. Launch the App / 启动软件

Cross-platform terminal launch:
跨平台终端启动：

```bash
python scripts/launch_chladni_studio.py
```

macOS double-click launch:
macOS 双击启动：

```text
scripts/launch_chladni_studio.command
```

Windows double-click launch:
Windows 双击启动：

```text
scripts\launch_chladni_studio.bat
```

Linux terminal launch:
Linux 终端启动：

```bash
./scripts/launch_chladni_studio.sh
```

If the Linux script is not executable:
如果 Linux 脚本没有执行权限：

```bash
chmod +x scripts/launch_chladni_studio.sh
./scripts/launch_chladni_studio.sh
```

The launcher runs a Python-only self-test, finds an available local port, starts the UI, and opens the browser.
启动器会运行 Python-only 自检、寻找可用本地端口、启动 UI 并打开浏览器。

## 6. Configure COMSOL and MATLAB / 配置 COMSOL 与 MATLAB

The current development version reports running-process detection and common install-path discovery. If configured executable paths are missing, runtime diagnostics and LiveLink runs can temporarily use discovered paths, but users should still verify or edit `config.yaml` until the persistent setup wizard is finished.
当前开发版会报告运行进程检测与常见安装路径发现。如果配置里的可执行文件路径缺失，运行时诊断和 LiveLink 运行可以临时使用发现到的路径；但在持久化安装向导完成前，用户仍应检查或编辑 `config.yaml`。

Open `config.yaml` and check these fields:
打开 `config.yaml` 并检查这些字段：

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
Windows 示例：

```yaml
comsol_command_path: "C:/Program Files/COMSOL/COMSOL64/Multiphysics/bin/win64/comsol.exe"
matlab_path: "C:/Program Files/MATLAB/R2024a/bin/matlab.exe"
```

macOS examples:
macOS 示例：

```yaml
comsol_command_path: "/Applications/COMSOL64/Multiphysics/bin/comsol"
matlab_path: "/Applications/MATLAB_R2024a.app/bin/matlab"
```

Linux examples:
Linux 示例：

```yaml
comsol_command_path: "/usr/local/comsol64/multiphysics/bin/comsol"
matlab_path: "/usr/local/MATLAB/R2024a/bin/matlab"
```

Then run diagnostics:
然后运行诊断：

```bash
python -m src.main diagnose-comsol
```

To inspect only running-process detection and install-path discovery:
如果只想查看运行进程检测与安装路径发现：

```bash
python -m src.main discover-comsol
```

After reviewing the discovery output, write accepted paths into `config.yaml`:
查看发现结果后，可以把确认的路径写入 `config.yaml`：

```bash
python -m src.main apply-comsol-discovery
```

The important required checks are COMSOL command, MATLAB command, bound MPH model, LiveLink runner, exports directory, and timeout configuration.
关键必需检查包括 COMSOL 命令、MATLAB 命令、绑定 MPH 模型、LiveLink runner、导出目录和超时配置。

## 7. First UI Smoke Run / 第一次 UI 烟测

1. Launch Chladni Studio.
   启动 Chladni Studio。
2. Open the `Target` tab and draw or import a simple high-contrast image.
   打开 `Target` 页，绘制或导入简单高对比度图案。
3. Click `Save`.
   点击 `Save`。
4. Confirm `Target Quality` shows a processed preview and suitability metrics.
   确认 `Target Quality` 显示预处理预览与适配度指标。
5. Open the `Run` tab.
   打开 `Run` 页。
6. Choose `Smoke`.
   选择 `Smoke`。
7. Keep `Run COMSOL` enabled only if COMSOL/MATLAB are configured.
   只有 COMSOL/MATLAB 已配置时才保持 `Run COMSOL` 开启。
8. Click `Run`.
   点击 `Run`。

For Python-only testing, turn off `Run COMSOL`.
只测试 Python 流程时，请关闭 `Run COMSOL`。

## 8. Common Problems / 常见问题

`PermissionError` when starting the UI:
启动 UI 出现 `PermissionError`：

```text
Use another port, or launch through scripts/launch_chladni_studio.py so it can find a free port.
换一个端口，或使用 scripts/launch_chladni_studio.py，让启动器自动寻找空闲端口。
```

COMSOL command missing:
找不到 COMSOL 命令：

```text
Open config.yaml and set comsol_command_path to the real COMSOL executable.
打开 config.yaml，将 comsol_command_path 设置为真实 COMSOL 可执行文件。
```

MATLAB command missing:
找不到 MATLAB 命令：

```text
Open config.yaml and set matlab_path to the real MATLAB executable.
打开 config.yaml，将 matlab_path 设置为真实 MATLAB 可执行文件。
```

License warning:
license 警告：

```text
Open COMSOL and MATLAB manually once, confirm login/license status, then rerun diagnostics.
先手动打开 COMSOL 和 MATLAB，确认登录/授权状态，再重新运行诊断。
```

No ranking appears:
没有排行结果：

```text
Check whether COMSOL mode CSV files and frequencies.csv exist in data/comsol_exports/<candidate_id>.
检查 data/comsol_exports/<candidate_id> 中是否存在 COMSOL mode CSV 和 frequencies.csv。
```

## 9. What Is Still Lab-Specific / 仍需实验室确认的内容

These items should be finalized after real project data are available:
以下内容应在真实项目数据可用后定稿：

- Final material presets from measured density, Young's modulus, Poisson ratio, and thermal parameters.
  基于实测密度、杨氏模量、泊松比和热参数的最终材料预设。
- Final COMSOL model file, boundary naming, hole/spacer assumptions, and fixed constraints.
  最终 COMSOL 模型文件、边界命名、孔/垫片假设和固定约束。
- Physical plate frequency and nodal pattern validation.
  实体板频率和节点线图案验证。
- Final screenshots for this deployment guide.
  本部署指南的最终截图。
