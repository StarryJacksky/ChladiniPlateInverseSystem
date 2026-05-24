# 部署指南

[语言](./deployment_guide.md): [双语](./deployment_guide.md) | 中文 | [English](./deployment_guide.en.md)

这是 Chladni Studio 的开发版部署指南。目标很简单：部署完成后，用户打开软件、给定目标图案，本机 COMSOL/MATLAB 桥接流程自动生成候选结果。

## 1. 你需要准备什么

仅运行 Python UI 与无 COMSOL 自检需要：

- Windows 10/11、macOS 或 Linux。
- Python 3.9 或更新版本。
- Git，或者本仓库 ZIP 压缩包。

自动仿真额外需要：

- 本机已安装 COMSOL Multiphysics。
- 本机已安装 MATLAB。
- COMSOL LiveLink for MATLAB 授权可用。
- 与项目参数合同匹配的 Chladni MPH 模型。

## 2. 获取项目

使用 Git：

```bash
git clone <repository-url>
cd ChladiniPlateProject
```

使用 ZIP 下载：

```text
1. 从 GitHub 下载仓库 ZIP。
2. 解压到没有特殊字符的简单路径。
3. 在解压后的项目文件夹中打开终端。
```

推荐路径：

```text
Windows: C:\Users\<you>\Documents\ChladiniPlateProject
macOS:   /Users/<you>/Documents/ChladiniPlateProject
Linux:   /home/<you>/ChladiniPlateProject
```

## 3. 安装 Python 依赖

创建虚拟环境：

```bash
python -m venv .venv
```

在 Windows PowerShell 中启用：

```powershell
.\.venv\Scripts\Activate.ps1
```

在 macOS/Linux 中启用：

```bash
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

如果 macOS/Linux 上 `python` 指向旧版本，请改用 `python3`。

## 4. 第一次无 COMSOL 检查

运行自检：

```bash
python -m src.main self-test
```

预期结果：

```text
"ready": true
```

如果你的 COMSOL/MATLAB 登录或本地 license 文件可用，license 环境变量警告可以暂时接受。

## 5. 启动软件

跨平台终端启动：

```bash
python scripts/launch_chladni_studio.py
```

macOS 双击启动：

```text
scripts/launch_chladni_studio.command
```

Windows 双击启动：

```text
scripts\launch_chladni_studio.bat
```

Linux 终端启动：

```bash
./scripts/launch_chladni_studio.sh
```

如果 Linux 脚本没有执行权限：

```bash
chmod +x scripts/launch_chladni_studio.sh
./scripts/launch_chladni_studio.sh
```

启动器会运行 Python-only 自检、寻找可用本地端口、启动 UI 并打开浏览器。

## 6. 配置 COMSOL 与 MATLAB

当前开发版会报告运行进程检测与常见安装路径发现。如果配置里的可执行文件路径缺失，运行时诊断和 LiveLink 运行可以临时使用发现到的路径；但在持久化安装向导完成前，用户仍应检查或编辑 `config.yaml`。

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

Windows 示例：

```yaml
comsol_command_path: "C:/Program Files/COMSOL/COMSOL64/Multiphysics/bin/win64/comsol.exe"
matlab_path: "C:/Program Files/MATLAB/R2024a/bin/matlab.exe"
```

macOS 示例：

```yaml
comsol_command_path: "/Applications/COMSOL64/Multiphysics/bin/comsol"
matlab_path: "/Applications/MATLAB_R2024a.app/bin/matlab"
```

Linux 示例：

```yaml
comsol_command_path: "/usr/local/comsol64/multiphysics/bin/comsol"
matlab_path: "/usr/local/MATLAB/R2024a/bin/matlab"
```

然后运行诊断：

```bash
python -m src.main diagnose-comsol
```

如果只想查看运行进程检测与安装路径发现：

```bash
python -m src.main discover-comsol
```

查看发现结果后，可以把确认的路径写入 `config.yaml`：

```bash
python -m src.main apply-comsol-discovery
```

关键必需检查包括 COMSOL 命令、MATLAB 命令、绑定 MPH 模型、LiveLink runner、导出目录和超时配置。

## 7. 第一次 UI 烟测

1. 启动 Chladni Studio。
2. 打开 `Target` 页，绘制或导入简单高对比度图案。
3. 点击 `Save`。
4. 确认 `Target Quality` 显示预处理预览与适配度指标。
5. 打开 `Run` 页。
6. 选择 `Smoke`。
7. 只有 COMSOL/MATLAB 已配置时才保持 `Run COMSOL` 开启。
8. 点击 `Run`。

只测试 Python 流程时，请关闭 `Run COMSOL`。

命令行无 COMSOL 烟测：

```bash
python scripts/check_python_smoke.py
```

该检查会在临时目录运行，并应创建 `target_binary.npy`、`target_preview.png`、`target_analysis.json`、`H.csv` 和 `metadata.json`。

## 8. 常见问题

启动 UI 出现 `PermissionError`：

```text
换一个端口，或使用 scripts/launch_chladni_studio.py，让启动器自动寻找空闲端口。
```

找不到 COMSOL 命令：

```text
打开 config.yaml，将 comsol_command_path 设置为真实 COMSOL 可执行文件。
```

找不到 MATLAB 命令：

```text
打开 config.yaml，将 matlab_path 设置为真实 MATLAB 可执行文件。
```

license 警告：

```text
先手动打开 COMSOL 和 MATLAB，确认登录/授权状态，再重新运行诊断。
```

没有排行结果：

```text
检查 data/comsol_exports/<candidate_id> 中是否存在 COMSOL mode CSV 和 frequencies.csv。
```

## 9. 仍需实验室确认的内容

以下内容应在真实项目数据可用后定稿：

- 基于实测密度、杨氏模量、泊松比和热参数的最终材料预设。
- 最终 COMSOL 模型文件、边界命名、孔/垫片假设和固定约束。
- 实体板频率和节点线图案验证。
- 本部署指南的最终截图。
