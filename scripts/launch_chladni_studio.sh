#!/bin/sh
# Linux 启动 Chladni Studio / Linux launcher for Chladni Studio
set -eu

# 解析脚本目录 / Resolve script directory
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# 解析项目根目录 / Resolve project root directory
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

# 切换到项目根目录 / Change into project root directory
cd "$PROJECT_DIR"

# 优先使用 python3 / Prefer python3
if command -v python3 >/dev/null 2>&1; then
  # 设置 Python 命令 / Set Python command
  PYTHON_BIN=python3
else
  # 回退到 python / Fall back to python
  PYTHON_BIN=python
fi

# 打印启动位置 / Print launch location
printf '%s\n' "Launching Chladni Studio from $PROJECT_DIR / 正在从 $PROJECT_DIR 启动 Chladni Studio"

# 启动 Python 启动器 / Run Python launcher
"$PYTHON_BIN" scripts/launch_chladni_studio.py "$@"
