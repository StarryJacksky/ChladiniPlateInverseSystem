from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import subprocess  # 导入进程启动工具 / Import process-launch utilities
import socket  # 导入 TCP 连接探测工具 / Import TCP connection probe utilities
import time  # 导入等待工具 / Import waiting utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

from src.comsol.discovery import config_with_runtime_discovery  # 导入运行时路径发现 / Import runtime path discovery


DEFAULT_COMSOL_COMMAND = "/Applications/COMSOL64/Multiphysics/bin/comsol"  # 默认 COMSOL 命令路径 / Default COMSOL command path
STARTED_SERVERS = []  # 保留本进程启动的 server 句柄 / Keep server handles started by this process


def is_server_reachable(host: str, port: int, timeout_s: float = 1.0) -> bool:  # 检查 COMSOL server 是否可连接 / Check whether COMSOL server is reachable
    try:  # 捕获连接错误 / Catch connection errors
        with socket.create_connection((host, port), timeout=timeout_s):  # 尝试真实 TCP 连接 / Try a real TCP connection
            return True  # 连接成功 / Connection succeeded
    except OSError:  # 处理未监听或不可达 / Handle closed or unreachable port
        return False  # 连接失败 / Connection failed


def comsol_server_log_path(config: dict) -> Path:  # 获取 COMSOL server 日志路径 / Get COMSOL server log path
    log_dir = Path(config.get("paths", {}).get("comsol_exports_dir", "data/comsol_exports"))  # 读取日志目录 / Read log directory
    log_dir.mkdir(parents=True, exist_ok=True)  # 创建日志目录 / Create log directory
    return log_dir / "mphserver.log"  # 返回日志文件路径 / Return log file path


def start_mphserver(config: dict) -> subprocess.Popen:  # 启动 COMSOL mphserver / Start COMSOL mphserver
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)  # 应用运行时路径发现 / Apply runtime path discovery
    comsol_config = runtime_config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    command_path = str(comsol_config.get("comsol_command_path", DEFAULT_COMSOL_COMMAND))  # 读取 COMSOL 命令路径 / Read COMSOL command path
    port = int(comsol_config.get("server_port", 2036))  # 读取 server 端口 / Read server port
    log_path = comsol_server_log_path(config)  # 获取日志路径 / Get log path
    log_file = log_path.open("a", encoding="utf-8")  # 打开日志文件 / Open log file
    command = [command_path, "mphserver", "-port", str(port)]  # 构造启动命令 / Build start command
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log_file, stderr=subprocess.STDOUT)  # 启动后台 server 并保持 stdin / Start background server and keep stdin
    STARTED_SERVERS.append(process)  # 保存进程句柄避免被回收 / Store process handle to avoid cleanup
    return process  # 返回进程对象 / Return process object


def ensure_comsol_server(config: dict, wait_s: float | None = None) -> bool:  # 确保 COMSOL server 可用 / Ensure COMSOL server is available
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)  # 应用运行时路径发现 / Apply runtime path discovery
    comsol_config = runtime_config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    host = str(comsol_config.get("server_host", "127.0.0.1"))  # 读取 server 主机 / Read server host
    port = int(comsol_config.get("server_port", 2036))  # 读取 server 端口 / Read server port
    wait_seconds = float(wait_s if wait_s is not None else comsol_config.get("server_start_timeout_s", 30.0))  # 读取 server 启动等待时间 / Read server startup wait time
    if is_server_reachable(host, port):  # 检查现有 server / Check existing server
        return True  # 已经可用 / Already available
    if not bool(comsol_config.get("auto_start_server", True)):  # 检查是否允许自动启动 / Check whether auto-start is allowed
        return False  # 不自动启动 / Do not auto-start
    start_mphserver(runtime_config)  # 启动 server / Start server
    deadline = time.time() + wait_seconds  # 计算等待截止时间 / Compute wait deadline
    while time.time() < deadline:  # 等待 server 就绪 / Wait for server readiness
        if is_server_reachable(host, port):  # 检查连接 / Check connection
            return True  # server 已就绪 / Server is ready
        time.sleep(1.0)  # 短暂等待 / Wait briefly
    return is_server_reachable(host, port)  # 返回最终检查结果 / Return final check result
