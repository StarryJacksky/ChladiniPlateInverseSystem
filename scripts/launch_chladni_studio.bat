@echo off
rem Double-click launcher for Chladni Studio / 双击启动 Chladni Studio
setlocal

rem Resolve the project root directory / 解析项目根目录
set "PROJECT_DIR=%~dp0.."

rem Change into the project root directory / 切换到项目根目录
cd /d "%PROJECT_DIR%"

rem Launch the Python launcher / 启动 Python 启动器
py -3 scripts\launch_chladni_studio.py %*

rem Keep the console open after errors / 出错后保留控制台
if errorlevel 1 pause
