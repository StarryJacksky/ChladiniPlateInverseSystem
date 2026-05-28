from __future__ import annotations

import os
import subprocess
import socket
import sys
import time
from pathlib import Path

from src.comsol.credentials import ensure_comsol_credentials
from src.comsol.discovery import config_with_runtime_discovery


DEFAULT_COMSOL_COMMAND = "/Applications/COMSOL64/Multiphysics/bin/comsol"
STARTED_SERVERS = []


def build_runtime_options(config: dict) -> list[str]:
    runtime_root = Path(config.get("paths", {}).get("comsol_exports_dir", "data/comsol_exports")) / ".comsol_runtime"
    prefs_dir = runtime_root / "prefs"
    configuration_dir = runtime_root / "configuration"
    tmp_dir = runtime_root / "tmp"
    recovery_dir = runtime_root / "recovery"
    for path in [prefs_dir, configuration_dir, tmp_dir, recovery_dir]:
        path.mkdir(parents=True, exist_ok=True)
    return [
        "-prefsdir",
        str(prefs_dir),
        "-configuration",
        str(configuration_dir),
        "-tmpdir",
        str(tmp_dir),
        "-recoverydir",
        str(recovery_dir),
    ]


def build_server_options(config: dict) -> list[str]:
    credentials = ensure_comsol_credentials(config)
    user_name = credentials.username
    options = ["-multi", "on", "-silent"]
    if user_name:
        options.extend(["-user", user_name, "-passwd", "nostore"])
    return options


def build_mphserver_command(command_path: str, port: int, runtime_options: list[str] | None = None) -> list[str]:
    executable = Path(command_path)
    executable_name = executable.name.lower()
    options = list(runtime_options or [])
    if executable_name in {"comsolmphserver", "comsolmphserver.exe"}:
        return [str(executable), "-port", str(port), *options]
    if executable_name in {"comsol.exe", "comsolui.exe"}:
        dedicated_server = executable.with_name("comsolmphserver.exe")
        if dedicated_server.exists():
            return [str(dedicated_server), "-port", str(port), *options]
    return [command_path, "mphserver", "-port", str(port), *options]


def is_server_reachable(host: str, port: int, timeout_s: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def comsol_server_log_path(config: dict) -> Path:
    log_dir = Path(config.get("paths", {}).get("comsol_exports_dir", "data/comsol_exports"))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "mphserver.log"


def stop_started_servers() -> None:
    while STARTED_SERVERS:
        process = STARTED_SERVERS.pop()
        if process.poll() is not None:
            continue
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)


def start_mphserver(config: dict) -> subprocess.Popen:
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)
    comsol_config = runtime_config.get("comsol", {})
    command_path = str(comsol_config.get("comsol_command_path", DEFAULT_COMSOL_COMMAND))
    port = int(comsol_config.get("server_port", 2036))
    log_path = comsol_server_log_path(config)
    log_file = log_path.open("a", encoding="utf-8")
    runtime_options = build_runtime_options(runtime_config) + build_server_options(runtime_config)
    command = build_mphserver_command(command_path, port, runtime_options)
    log_file.write("command=" + " ".join(command) + "\n")
    log_file.flush()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    credentials = ensure_comsol_credentials(runtime_config)
    if credentials.password and process.stdin is not None:
        process.stdin.write((credentials.password + "\n" + credentials.password + "\n").encode("utf-8"))
        process.stdin.flush()
    STARTED_SERVERS.append(process)
    return process


def ensure_comsol_server(config: dict, wait_s: float | None = None) -> bool:
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)
    comsol_config = runtime_config.get("comsol", {})
    host = str(comsol_config.get("server_host", "127.0.0.1"))
    port = int(comsol_config.get("server_port", 2036))
    wait_seconds = float(wait_s if wait_s is not None else comsol_config.get("server_start_timeout_s", 30.0))
    if is_server_reachable(host, port):
        return True
    if not bool(comsol_config.get("auto_start_server", True)):
        return False
    process = start_mphserver(runtime_config)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if is_server_reachable(host, port):
            return True
        if process.poll() is not None:
            return False
        time.sleep(1.0)
    return is_server_reachable(host, port)


def kill_mphserver_on_port(port: int) -> int:
    """Kill any process listening on the given COMSOL server port.

    Cross-platform best-effort: uses ``netstat -ano`` + ``taskkill`` on
    Windows and ``lsof -ti`` + ``kill -9`` elsewhere. Also drains any
    ``subprocess.Popen`` handles we started in this Python process so
    they don't linger as zombies.

    Returns the number of PIDs killed.
    """
    killed_pids: set[str] = set()
    try:
        if sys.platform == "win32":
            # netstat -ano returns lines like "TCP   127.0.0.1:2036   0.0.0.0:0   LISTENING   12345"
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10.0,
            )
            for line in result.stdout.splitlines():
                upper = line.upper()
                if f":{port}" in line and "LISTENING" in upper:
                    parts = line.split()
                    if parts and parts[-1].isdigit():
                        killed_pids.add(parts[-1])
            for pid in killed_pids:
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True,
                    check=False,
                    timeout=10.0,
                )
        else:
            # ``lsof -ti :PORT`` matches ANY socket touching the port, including
            # outgoing connections from unrelated processes. Restrict to actual
            # TCP LISTEN sockets so we never accidentally kill a remote-side
            # client. / 限定 LISTEN，避免误杀任何端口 2036 的远端连接进程
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5.0,
            )
            for pid in result.stdout.split():
                if pid.isdigit():
                    killed_pids.add(pid)
                    subprocess.run(
                        ["kill", "-9", pid],
                        capture_output=True,
                        check=False,
                        timeout=5.0,
                    )
    except Exception:
        # netstat / lsof may not exist or may be blocked by AV;
        # we still need to drain our owned subprocess handles below.
        pass

    # Reap any Popen handles we still own so they don't linger as zombies
    # even if the OS-level kill above missed them. / 顺手回收 Python 自己拉起来的 server 进程
    for process in list(STARTED_SERVERS):
        try:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5.0)
        except Exception:
            pass
        try:
            STARTED_SERVERS.remove(process)
        except ValueError:
            pass

    return len(killed_pids)


def reset_mphserver(config: dict, wait_s: float | None = None, settle_s: float = 2.0) -> bool:
    """Hard-reset the COMSOL mphserver: kill whatever is on the port, then
    start a fresh server and wait until it's reachable.

    Returns True if the new server became reachable within the timeout.
    """
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)
    comsol_config = runtime_config.get("comsol", {})
    port = int(comsol_config.get("server_port", 2036))
    kill_mphserver_on_port(port)
    # Give the kernel a moment to release the TCP socket before re-binding. /
    # 给内核一点时间释放 TCP socket，避免 bind 时被 "Address already in use" 卡住
    time.sleep(max(0.0, float(settle_s)))
    return ensure_comsol_server(runtime_config, wait_s=wait_s)
