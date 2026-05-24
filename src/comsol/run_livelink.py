from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import subprocess  # 导入子进程工具 / Import subprocess utilities
import threading  # 导入线程工具 / Import threading utilities
from datetime import datetime  # 导入时间戳工具 / Import timestamp helper
from pathlib import Path  # 导入路径工具 / Import path utilities

from src.comsol.discovery import config_with_runtime_discovery  # 导入运行时路径发现 / Import runtime path discovery
from src.comsol.export_parameters import export_candidate_for_comsol  # 导入参数导出函数 / Import parameter export helper
from src.comsol.server import ensure_comsol_server  # 导入 COMSOL server 检查函数 / Import COMSOL server check helper


DEFAULT_MATLAB_PATH = "/Applications/MATLAB_R2024a.app/bin/matlab"  # 默认 MATLAB 路径 / Default MATLAB path
DEFAULT_RUNNER_PATH = "comsol_templates/run_chladni_candidate.m"  # 默认 LiveLink runner 路径 / Default LiveLink runner path


def matlab_quote(value: str | Path) -> str:  # 转义 MATLAB 字符串 / Escape MATLAB string
    text = str(value)  # 转为字符串 / Convert to string
    return "'" + text.replace("'", "''") + "'"  # 返回 MATLAB 单引号字符串 / Return MATLAB single-quoted string


def resolve_candidate_dir(config: dict, candidate_id: str) -> Path:  # 解析候选目录 / Resolve candidate directory
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选根目录 / Read candidate root directory
    candidate_dir = candidates_dir / candidate_id  # 构造候选目录 / Build candidate directory
    if not candidate_dir.exists():  # 检查候选是否存在 / Check candidate existence
        raise FileNotFoundError(f"Candidate not found: {candidate_dir}")  # 抛出缺失错误 / Raise missing error
    if not (candidate_dir / "H.csv").exists():  # 检查厚度矩阵 / Check thickness matrix
        raise FileNotFoundError(f"Candidate H.csv not found: {candidate_dir / 'H.csv'}")  # 抛出缺失错误 / Raise missing error
    return candidate_dir  # 返回候选目录 / Return candidate directory


def ensure_comsol_parameters(candidate_dir: Path, material: dict | None = None) -> Path:  # 确保候选参数表存在 / Ensure parameter table exists
    parameter_path = candidate_dir / "comsol_parameters.csv"  # 构造参数表路径 / Build parameter path
    material_path = candidate_dir / "material_parameters.csv"  # 构造材料参数表路径 / Build material parameter path
    if not parameter_path.exists() or not material_path.exists() or material is not None:  # 检查参数表是否缺失或材料已更新 / Check whether parameter tables are missing or material updated
        parameter_path = export_candidate_for_comsol(candidate_dir, material)  # 从 H.csv 导出参数表 / Export parameters from H.csv
    return parameter_path  # 返回参数表路径 / Return parameter path


def build_matlab_batch(model_path: Path, candidate_dir: Path, export_dir: Path, runner_path: Path, num_modes: int) -> str:  # 构造 MATLAB batch 表达式 / Build MATLAB batch expression
    runner_dir = runner_path.parent.resolve()  # 获取 runner 目录 / Get runner directory
    parts = [  # 创建 MATLAB 命令片段 / Create MATLAB command parts
        f"addpath({matlab_quote(runner_dir)})",  # 添加 runner 目录 / Add runner directory
        f"run_chladni_candidate({matlab_quote(model_path.resolve())},{matlab_quote(candidate_dir.resolve())},{matlab_quote(export_dir.resolve())},{num_modes})",  # 调用 runner / Call runner
    ]  # 结束命令片段 / End command parts
    return "; ".join(parts)  # 拼接 batch 表达式 / Join batch expression


def write_livelink_log(log_path: Path, command: list[str], output: str, returncode: int) -> None:  # 写入 LiveLink 日志 / Write LiveLink log
    log_path.parent.mkdir(parents=True, exist_ok=True)  # 确保日志目录存在 / Ensure log directory exists
    with log_path.open("w", encoding="utf-8") as file_obj:  # 打开日志文件 / Open log file
        file_obj.write(f"started_at={datetime.now().isoformat(timespec='seconds')}\n")  # 写入开始时间 / Write start time
        file_obj.write(f"returncode={returncode}\n")  # 写入返回码 / Write return code
        file_obj.write("command=" + " ".join(command) + "\n\n")  # 写入命令 / Write command
        file_obj.write(output or "")  # 写入 MATLAB 输出 / Write MATLAB output


def run_command_streamed(command: list[str], log_path: Path, progress=None, event_base: dict | None = None, timeout_s: float | None = None) -> tuple[int, str]:  # 流式运行命令并写日志 / Run command with streamed logging
    log_path.parent.mkdir(parents=True, exist_ok=True)  # 确保日志目录存在 / Ensure log directory exists
    output_lines = []  # 创建输出缓存 / Create output cache
    base = event_base or {}  # 读取事件基础字段 / Read base event fields
    with log_path.open("w", encoding="utf-8") as file_obj:  # 打开日志文件 / Open log file
        file_obj.write(f"started_at={datetime.now().isoformat(timespec='seconds')}\n")  # 写入开始时间 / Write start time
        file_obj.write(f"timeout_s={timeout_s or ''}\n")  # 写入超时设置 / Write timeout setting
        file_obj.write("command=" + " ".join(command) + "\n\n")  # 写入命令 / Write command
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)  # 启动子进程并合并输出 / Start subprocess with merged output
        assert process.stdout is not None  # 帮助类型检查确认输出存在 / Help type checking confirm stdout exists
        def read_output() -> None:  # 定义输出读取线程 / Define output-reader thread
            for line in process.stdout:  # 逐行读取输出 / Read output line by line
                text = line.rstrip("\n")  # 去掉换行符 / Strip newline
                output_lines.append(line)  # 保存原始输出行 / Store raw output line
                file_obj.write(line)  # 写入日志文件 / Write log file
                file_obj.flush()  # 立即刷新日志 / Flush log immediately
                if progress is not None and text.strip():  # 检查是否发送非空日志事件 / Check whether to emit non-empty log event
                    progress({**base, "stage": "log", "message": text.strip(), "log_path": str(log_path)})  # 发送日志事件 / Emit log event
        reader = threading.Thread(target=read_output, daemon=True)  # 创建输出读取线程 / Create output-reader thread
        reader.start()  # 启动输出读取线程 / Start output-reader thread
        try:  # 捕获超时 / Catch timeout
            returncode = process.wait(timeout=timeout_s) if timeout_s else process.wait()  # 等待进程结束或超时 / Wait for process exit or timeout
        except subprocess.TimeoutExpired:  # 处理命令超时 / Handle command timeout
            process.kill()  # 杀掉超时进程 / Kill timed-out process
            returncode = process.wait()  # 等待杀进程完成 / Wait for killed process
            timeout_message = f"Command timed out after {timeout_s} seconds. / 命令超过 {timeout_s} 秒未完成。"  # 构造超时消息 / Build timeout message
            file_obj.write(timeout_message + "\n")  # 写入超时日志 / Write timeout log
            if progress is not None:  # 检查是否发送超时事件 / Check whether to emit timeout event
                progress({**base, "stage": "error", "message": timeout_message, "log_path": str(log_path)})  # 发送超时事件 / Emit timeout event
        reader.join(timeout=2.0)  # 等待读取线程收尾 / Wait for reader cleanup
        file_obj.write(f"\nreturncode={returncode}\n")  # 写入返回码 / Write return code
    return returncode, "".join(output_lines)  # 返回返回码和输出 / Return return code and output


def run_livelink_candidate(config: dict, candidate_id: str, num_modes: int | None = None, model_path: str | Path | None = None, matlab_path: str | Path | None = None, runner_path: str | Path | None = None, progress=None) -> dict:  # 运行单个候选 / Run one candidate
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)  # 应用运行时路径发现 / Apply runtime path discovery
    if not ensure_comsol_server(runtime_config):  # 确保 COMSOL server 可用 / Ensure COMSOL server availability
        raise RuntimeError("COMSOL server is not reachable. / COMSOL server 无法连接。")  # 抛出 server 错误 / Raise server error
    candidate_dir = resolve_candidate_dir(runtime_config, candidate_id)  # 解析候选目录 / Resolve candidate directory
    ensure_comsol_parameters(candidate_dir, runtime_config.get("material"))  # 确保参数表存在 / Ensure parameter table exists
    modes = int(num_modes or runtime_config["simulation"]["num_modes"])  # 读取模态数量 / Read mode count
    model = Path(model_path or runtime_config.get("comsol", {}).get("model_path", "comsol_templates/Chladni_15x15_bound.mph"))  # 解析模型路径 / Resolve model path
    matlab = str(matlab_path or runtime_config.get("comsol", {}).get("matlab_path", DEFAULT_MATLAB_PATH))  # 解析 MATLAB 路径 / Resolve MATLAB path
    runner = Path(runner_path or runtime_config.get("comsol", {}).get("runner_path", DEFAULT_RUNNER_PATH))  # 解析 runner 路径 / Resolve runner path
    export_root = Path(runtime_config["paths"]["comsol_exports_dir"])  # 读取导出根目录 / Read export root
    export_dir = export_root / candidate_id  # 构造导出目录 / Build export directory
    export_dir.mkdir(parents=True, exist_ok=True)  # 创建导出目录 / Create export directory
    batch = build_matlab_batch(model, candidate_dir, export_dir, runner, modes)  # 构造 MATLAB batch / Build MATLAB batch
    command = [matlab, "-batch", batch]  # 构造命令列表 / Build command list
    log_path = export_dir / "livelink.log"  # 构造候选日志路径 / Build candidate log path
    timeout_s = float(runtime_config.get("comsol", {}).get("livelink_timeout_s", 7200))  # 读取 LiveLink 超时 / Read LiveLink timeout
    returncode, _output = run_command_streamed(command, log_path, progress, {"current_candidate": candidate_id}, timeout_s)  # 流式运行并记录日志 / Run with streamed logging
    if returncode != 0:  # 检查 MATLAB 返回码 / Check MATLAB return code
        raise RuntimeError(f"LiveLink simulation failed for {candidate_id}. See {log_path}. / {candidate_id} 的 LiveLink 仿真失败，见 {log_path}。")  # 抛出日志指向错误 / Raise log-pointing error
    return {"candidate_id": candidate_id, "export_dir": str(export_dir), "num_modes": modes, "returncode": returncode, "log_path": str(log_path)}  # 返回运行结果 / Return run result


def list_candidate_ids(config: dict, generation: int | None = None, limit: int | None = None) -> list[str]:  # 列出候选编号 / List candidate ids
    candidates_dir = Path(config["paths"]["candidates_dir"])  # 读取候选根目录 / Read candidate root directory
    pattern = f"candidate_{generation:03d}_*" if generation is not None else "candidate_*"  # 构造候选匹配模式 / Build candidate glob pattern
    candidate_paths = sorted(path for path in candidates_dir.glob(pattern) if (path / "H.csv").exists())  # 查找有效候选目录 / Find valid candidate directories
    candidate_ids = [path.name for path in candidate_paths]  # 提取候选编号 / Extract candidate ids
    return candidate_ids[:limit] if limit else candidate_ids  # 返回限制后的编号 / Return limited ids


def run_livelink_batch(config: dict, candidate_ids: list[str] | None = None, generation: int | None = None, limit: int | None = None, num_modes: int | None = None, model_path: str | Path | None = None) -> list[dict]:  # 批量运行候选 / Run candidate batch
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)  # 应用运行时路径发现 / Apply runtime path discovery
    if not ensure_comsol_server(runtime_config):  # 确保 COMSOL server 可用 / Ensure COMSOL server availability
        raise RuntimeError("COMSOL server is not reachable. / COMSOL server 无法连接。")  # 抛出 server 错误 / Raise server error
    selected_ids = candidate_ids or list_candidate_ids(runtime_config, generation, limit)  # 选择候选编号 / Select candidate ids
    if not selected_ids:  # 检查是否无候选 / Check whether candidate list is empty
        return []  # 返回空结果 / Return empty result
    modes = int(num_modes or runtime_config["simulation"]["num_modes"])  # 读取模态数量 / Read mode count
    model = Path(model_path or runtime_config.get("comsol", {}).get("model_path", "comsol_templates/Chladni_15x15_bound.mph"))  # 解析模型路径 / Resolve model path
    matlab = str(runtime_config.get("comsol", {}).get("matlab_path", DEFAULT_MATLAB_PATH))  # 解析 MATLAB 路径 / Resolve MATLAB path
    runner = Path(runtime_config.get("comsol", {}).get("runner_path", DEFAULT_RUNNER_PATH))  # 解析 runner 路径 / Resolve runner path
    export_root = Path(runtime_config["paths"]["comsol_exports_dir"])  # 读取导出根目录 / Read export root
    runner_dir = runner.parent.resolve()  # 获取 runner 目录 / Get runner directory
    batch_parts = [f"addpath({matlab_quote(runner_dir)})"]  # 初始化 MATLAB batch 片段 / Initialise MATLAB batch parts
    results = []  # 创建结果列表 / Create result list
    for candidate_id in selected_ids:  # 遍历候选编号 / Iterate candidate ids
        candidate_dir = resolve_candidate_dir(runtime_config, candidate_id)  # 解析候选目录 / Resolve candidate directory
        ensure_comsol_parameters(candidate_dir, runtime_config.get("material"))  # 确保参数表存在 / Ensure parameter table exists
        export_dir = export_root / candidate_id  # 构造导出目录 / Build export directory
        export_dir.mkdir(parents=True, exist_ok=True)  # 创建导出目录 / Create export directory
        batch_parts.append(f"run_chladni_candidate({matlab_quote(model.resolve())},{matlab_quote(candidate_dir.resolve())},{matlab_quote(export_dir.resolve())},{modes})")  # 添加候选仿真命令 / Add candidate simulation command
        results.append({"candidate_id": candidate_id, "export_dir": str(export_dir), "num_modes": modes})  # 记录预期结果 / Record expected result
    command = [matlab, "-batch", "; ".join(batch_parts)]  # 构造单 MATLAB 批量命令 / Build one MATLAB batch command
    log_path = export_root / "livelink_batch.log"  # 构造批量日志路径 / Build batch log path
    timeout_s = float(runtime_config.get("comsol", {}).get("livelink_timeout_s", 7200))  # 读取 LiveLink 超时 / Read LiveLink timeout
    returncode, _output = run_command_streamed(command, log_path, timeout_s=timeout_s)  # 流式运行批量命令 / Run batch command with streamed logging
    if returncode != 0:  # 检查 MATLAB 返回码 / Check MATLAB return code
        raise RuntimeError(f"LiveLink batch simulation failed. See {log_path}. / LiveLink 批量仿真失败，见 {log_path}。")  # 抛出日志指向错误 / Raise log-pointing error
    for result in results:  # 遍历结果行 / Iterate result rows
        result["returncode"] = returncode  # 写入返回码 / Store return code
        result["log_path"] = str(log_path)  # 写入日志路径 / Store log path
    return results  # 返回批量结果 / Return batch results
