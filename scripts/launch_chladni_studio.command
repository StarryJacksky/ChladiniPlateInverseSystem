#!/bin/zsh
# 双击启动 Chladni Studio / Double-click launcher for Chladni Studio
set -e

# 出错时暂停终端窗口 / Keep the terminal window open on errors
trap 'STATUS=$?; if [ "$STATUS" -ne 0 ]; then echo "Launcher failed with exit code $STATUS / 启动器退出码 $STATUS"; read -k 1 "?Press any key to close / 按任意键关闭"; fi' EXIT

# 解析脚本所在目录 / Resolve the script directory
SCRIPT_DIR="${0:A:h}"

# 解析项目根目录 / Resolve the project root directory
PROJECT_DIR="${SCRIPT_DIR:h}"

# 切换到项目根目录 / Change into the project root directory
cd "$PROJECT_DIR"

# 优先使用 python3 / Prefer python3
if command -v python3 >/dev/null 2>&1; then
  # 设置 Python 命令 / Set Python command
  PYTHON_BIN="python3"
else
  # 回退到 python / Fall back to python
  PYTHON_BIN="python"
fi

# 打印启动位置 / Print launch location
echo "Launching Chladni Studio from $PROJECT_DIR / 正在从 $PROJECT_DIR 启动 Chladni Studio"

# 启动 Python 启动器 / Run the Python launcher
"$PYTHON_BIN" scripts/launch_chladni_studio.py "$@"
