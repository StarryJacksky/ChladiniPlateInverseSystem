from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 检查工具 / Import CSV checking utilities
import os  # 导入系统权限检查 / Import OS permission checks
import re  # 导入版本解析工具 / Import version parsing tools
import tempfile  # 导入临时目录工具 / Import temporary directory utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.comsol.discovery import discover_runtime_environment  # 导入运行环境发现 / Import runtime environment discovery
from src.comsol.discovery import config_with_runtime_discovery  # 导入运行时配置补全 / Import runtime config completion
from src.comsol.export_parameters import export_candidate_for_comsol  # 导入参数导出函数 / Import parameter export helper
from src.comsol.run_livelink import build_matlab_batch  # 导入 MATLAB batch 构造函数 / Import MATLAB batch builder
from src.comsol.server import is_server_reachable  # 导入 server 端口检查 / Import server port check


def resolve_project_path(value: str | Path) -> Path:  # 解析项目相对路径 / Resolve project-relative path
    path = Path(value).expanduser()  # 展开用户目录 / Expand user directory
    return path if path.is_absolute() else Path.cwd() / path  # 返回绝对路径 / Return absolute path


def check_path(label: str, value: str | Path, required: bool = True, executable: bool = False) -> dict:  # 检查文件或目录路径 / Check a file or directory path
    path = resolve_project_path(value)  # 解析路径 / Resolve path
    exists = path.exists()  # 检查是否存在 / Check existence
    is_executable = os.access(path, os.X_OK) if exists else False  # 检查是否可执行 / Check executable permission
    ok = exists and (is_executable if executable else True)  # 计算检查结果 / Compute check result
    if not required and not exists:  # 检查可选路径缺失 / Check missing optional path
        status = "warn"  # 标记警告 / Mark warning
    elif ok:  # 检查通过 / Check passed
        status = "ok"  # 标记正常 / Mark ok
    else:  # 检查失败 / Check failed
        status = "fail" if required else "warn"  # 标记失败或警告 / Mark fail or warning
    message = "OK" if ok else ("Missing optional path" if not required and not exists else "Path check failed")  # 生成消息 / Build message
    return {"label": label, "path": str(path), "required": required, "exists": exists, "executable": is_executable, "status": status, "message": message}  # 返回检查详情 / Return check detail


def check_output_directory(label: str, value: str | Path) -> dict:  # 检查输出目录 / Check output directory
    path = resolve_project_path(value)  # 解析路径 / Resolve path
    path.mkdir(parents=True, exist_ok=True)  # 确保目录存在 / Ensure directory exists
    writable = os.access(path, os.W_OK)  # 检查是否可写 / Check writable permission
    status = "ok" if writable else "fail"  # 计算状态 / Compute status
    message = "OK" if writable else "Directory is not writable"  # 生成消息 / Build message
    return {"label": label, "path": str(path), "required": True, "exists": path.exists(), "writable": writable, "status": status, "message": message}  # 返回检查详情 / Return check detail


def self_test_item(label: str, ok: bool, message: str, path: str = "", required: bool = True) -> dict:  # 构造自检条目 / Build self-test item
    status = "ok" if ok else ("fail" if required else "warn")  # 计算条目状态 / Compute item status
    return {"label": label, "status": status, "message": message, "path": path, "required": required}  # 返回自检条目 / Return self-test item


def check_runner_contract(runner_path: Path) -> dict:  # 检查 LiveLink runner 合同 / Check LiveLink runner contract
    if not runner_path.exists():  # 检查 runner 是否存在 / Check whether runner exists
        return self_test_item("LiveLink runner contract", False, "Runner file is missing. / runner 文件不存在。", str(runner_path))  # 返回缺失结果 / Return missing result
    text = runner_path.read_text(encoding="utf-8", errors="ignore")  # 读取 runner 文本 / Read runner text
    required_tokens = ["function run_chladni_candidate", "mphload", "model.param.set", "frequencies.csv", "mode_%02d.csv"]  # 定义关键合同片段 / Define key contract tokens
    missing = [token for token in required_tokens if token not in text]  # 查找缺失片段 / Find missing tokens
    ok = not missing  # 判断是否通过 / Decide whether passed
    message = "Runner contract looks complete. / runner 合同看起来完整。" if ok else f"Missing tokens: {', '.join(missing)}"  # 生成检查消息 / Build check message
    return self_test_item("LiveLink runner contract", ok, message, str(runner_path))  # 返回检查结果 / Return check result


def check_export_directory_write(path: Path) -> dict:  # 检查导出目录写入 / Check export directory writing
    try:  # 捕获写入错误 / Catch write errors
        path.mkdir(parents=True, exist_ok=True)  # 确保目录存在 / Ensure directory exists
        probe = path / "self_test_write.tmp"  # 构造测试文件 / Build probe file
        probe.write_text("ok\n", encoding="utf-8")  # 写入测试内容 / Write probe content
        probe.unlink()  # 删除测试文件 / Remove probe file
        return self_test_item("Export directory write", True, "Write probe succeeded. / 写入探针成功。", str(path))  # 返回成功结果 / Return success result
    except OSError as exc:  # 处理系统写入错误 / Handle OS write error
        return self_test_item("Export directory write", False, str(exc), str(path))  # 返回失败结果 / Return failure result


def check_timeout_config(config: dict) -> dict:  # 检查超时配置 / Check timeout configuration
    comsol_config = config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    server_timeout = float(comsol_config.get("server_start_timeout_s", 30.0))  # 读取 server 超时 / Read server timeout
    livelink_timeout = float(comsol_config.get("livelink_timeout_s", 7200.0))  # 读取 LiveLink 超时 / Read LiveLink timeout
    ok = server_timeout > 0 and livelink_timeout > server_timeout  # 判断超时是否合理 / Decide whether timeouts are reasonable
    message = f"server_start_timeout_s={server_timeout:g}, livelink_timeout_s={livelink_timeout:g}. / server 启动超时={server_timeout:g}，LiveLink 超时={livelink_timeout:g}。"  # 生成超时消息 / Build timeout message
    return self_test_item("Timeout configuration", ok, message)  # 返回超时检查 / Return timeout check


def infer_comsol_version(command_path: str | Path) -> dict:  # 从路径推断 COMSOL 版本 / Infer COMSOL version from path
    path_text = str(command_path)  # 转换路径文本 / Convert path to text
    match = re.search(r"COMSOL(\d)(\d)", path_text, re.IGNORECASE)  # 匹配 macOS 安装目录 / Match macOS install folder
    version = f"{match.group(1)}.{match.group(2)}" if match else ""  # 构造版本字符串 / Build version string
    ok = bool(version)  # 判断是否识别版本 / Decide whether version was found
    message = f"Detected COMSOL {version} from path. / 从路径识别到 COMSOL {version}。" if ok else "COMSOL version was not inferred from the command path. / 未能从命令路径推断 COMSOL 版本。"  # 生成版本消息 / Build version message
    return self_test_item("COMSOL version hint", ok, message, path_text, False)  # 返回可选版本检查 / Return optional version check


def infer_matlab_version(command_path: str | Path) -> dict:  # 从路径推断 MATLAB 版本 / Infer MATLAB version from path
    path_text = str(command_path)  # 转换路径文本 / Convert path to text
    match = re.search(r"MATLAB_(R\d{4}[ab])", path_text, re.IGNORECASE)  # 匹配 MATLAB 应用目录 / Match MATLAB app folder
    version = match.group(1).upper() if match else ""  # 读取版本字符串 / Read version string
    ok = bool(version)  # 判断是否识别版本 / Decide whether version was found
    message = f"Detected MATLAB {version} from path. / 从路径识别到 MATLAB {version}。" if ok else "MATLAB version was not inferred from the command path. / 未能从命令路径推断 MATLAB 版本。"  # 生成版本消息 / Build version message
    return self_test_item("MATLAB version hint", ok, message, path_text, False)  # 返回可选版本检查 / Return optional version check


def check_license_environment() -> dict:  # 检查常见 license 环境变量 / Check common license environment variables
    keys = ["LM_LICENSE_FILE", "MLM_LICENSE_FILE", "COMSOL_LICENSE_FILE"]  # 定义常见 license 变量 / Define common license variables
    present = [key for key in keys if os.environ.get(key)]  # 查找已设置变量 / Find configured variables
    ok = bool(present)  # 判断是否有变量 / Decide whether any variable exists
    message = f"License variables set: {', '.join(present)}. / 已设置 license 变量：{', '.join(present)}。" if ok else "No common license environment variable detected; local login/license files may still work. / 未检测到常见 license 环境变量；本机登录或 license 文件仍可能可用。"  # 生成 license 消息 / Build license message
    return self_test_item("License environment hint", ok, message, "", False)  # 返回可选 license 检查 / Return optional license check


def discovery_check_items(discovery: dict) -> list[dict]:  # 构造自动发现诊断条目 / Build auto-discovery diagnostic items
    summary = discovery.get("summary", {})  # 读取发现摘要 / Read discovery summary
    suggestions = discovery.get("suggestions", {})  # 读取路径建议 / Read path suggestions
    process_count = int(summary.get("process_count", 0))  # 读取进程数量 / Read process count
    process_status = str(summary.get("process_probe_status", ""))  # 读取进程探测状态 / Read process probe status
    process_error = str(summary.get("process_probe_error", ""))  # 读取进程探测错误 / Read process probe error
    comsol_count = int(summary.get("comsol_install_count", 0))  # 读取 COMSOL 候选数 / Read COMSOL candidate count
    matlab_count = int(summary.get("matlab_install_count", 0))  # 读取 MATLAB 候选数 / Read MATLAB candidate count
    process_message = f"{process_count} matching process(es) found. / 找到 {process_count} 个相关运行进程。" if process_count else ("Process list unavailable: " + process_error + " / 进程列表不可用：" + process_error if process_status == "unavailable" else "No running COMSOL/MATLAB process detected. / 未检测到正在运行的 COMSOL/MATLAB 进程。")  # 构造进程消息 / Build process message
    install_message = f"COMSOL candidates={comsol_count}, MATLAB candidates={matlab_count}. / COMSOL 候选={comsol_count}，MATLAB 候选={matlab_count}。"  # 构造安装候选消息 / Build install-candidate message
    comsol_path = str(suggestions.get("comsol_command_path", ""))  # 读取 COMSOL 建议 / Read COMSOL suggestion
    matlab_path = str(suggestions.get("matlab_path", ""))  # 读取 MATLAB 建议 / Read MATLAB suggestion
    suggestion_ok = bool(comsol_path and matlab_path)  # 判断建议是否完整 / Decide whether suggestions are complete
    suggestion_message = "Suggested COMSOL and MATLAB paths are available. / 已找到 COMSOL 与 MATLAB 路径建议。" if suggestion_ok else "Path suggestions are incomplete; manual config may still be needed. / 路径建议不完整，可能仍需手动配置。"  # 构造建议消息 / Build suggestion message
    suggestion_path = f"COMSOL={comsol_path or '-'}; MATLAB={matlab_path or '-'}"  # 构造建议路径文本 / Build suggestion path text
    return [  # 返回诊断条目 / Return diagnostic items
        self_test_item("Running process discovery", process_count > 0 and process_status != "unavailable", process_message, "", False),  # 添加运行进程发现 / Add running-process discovery
        self_test_item("Install path discovery", bool(comsol_count or matlab_count), install_message, "", False),  # 添加安装路径发现 / Add install-path discovery
        self_test_item("Runtime path suggestion", suggestion_ok, suggestion_message, suggestion_path, False),  # 添加路径建议 / Add path suggestion
    ]  # 结束诊断条目 / End diagnostic items


def check_parameter_export(config: dict) -> dict:  # 检查候选参数导出 / Check candidate parameter export
    grid_size = int(config["project"]["grid_size"])  # 读取网格尺寸 / Read grid size
    default_mm = float(config["thickness"]["default_mm"])  # 读取默认厚度 / Read default thickness
    with tempfile.TemporaryDirectory(prefix="chladni_self_test_") as temporary_dir:  # 创建临时目录 / Create temporary directory
        candidate_dir = Path(temporary_dir) / "candidate_000_0000"  # 构造临时候选目录 / Build temporary candidate directory
        candidate_dir.mkdir(parents=True, exist_ok=True)  # 创建候选目录 / Create candidate directory
        np.savetxt(candidate_dir / "H.csv", np.full((grid_size, grid_size), default_mm), delimiter=",", fmt="%.3f")  # 写入临时厚度矩阵 / Write temporary thickness matrix
        export_candidate_for_comsol(candidate_dir, config.get("material"))  # 导出参数文件 / Export parameter files
        with (candidate_dir / "comsol_parameters.csv").open("r", encoding="utf-8", newline="") as file_obj:  # 打开厚度参数表 / Open thickness parameter table
            parameter_rows = list(csv.DictReader(file_obj))  # 读取厚度参数行 / Read thickness parameter rows
        with (candidate_dir / "material_parameters.csv").open("r", encoding="utf-8", newline="") as file_obj:  # 打开材料参数表 / Open material parameter table
            material_rows = list(csv.DictReader(file_obj))  # 读取材料参数行 / Read material parameter rows
    expected_count = grid_size * grid_size  # 计算预期参数数量 / Compute expected parameter count
    names_ok = parameter_rows[0]["name"] == "h0101" and parameter_rows[-1]["name"] == f"h{grid_size:02d}{grid_size:02d}" if parameter_rows else False  # 检查首尾参数名 / Check first and last parameter names
    material_ok = len(material_rows) >= 6  # 检查材料参数数量 / Check material parameter count
    ok = len(parameter_rows) == expected_count and names_ok and material_ok  # 汇总导出结果 / Combine export result
    message = f"{len(parameter_rows)}/{expected_count} thickness rows, {len(material_rows)} material rows. / 厚度行 {len(parameter_rows)}/{expected_count}，材料行 {len(material_rows)}。"  # 生成导出消息 / Build export message
    return self_test_item("Parameter export dry run", ok, message)  # 返回检查结果 / Return check result


def check_matlab_batch(config: dict) -> dict:  # 检查 MATLAB batch 表达式 / Check MATLAB batch expression
    comsol_config = config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    model = resolve_project_path(comsol_config.get("model_path", ""))  # 解析模型路径 / Resolve model path
    runner = resolve_project_path(comsol_config.get("runner_path", ""))  # 解析 runner 路径 / Resolve runner path
    batch = build_matlab_batch(model, Path("candidate_000_0000"), Path("data/comsol_exports/candidate_000_0000"), runner, 1)  # 构造测试 batch / Build test batch
    ok = "run_chladni_candidate" in batch and str(model.resolve()) in batch  # 检查表达式关键内容 / Check expression key content
    message = "MATLAB batch expression can be built. / MATLAB batch 表达式可构造。" if ok else "MATLAB batch expression is incomplete. / MATLAB batch 表达式不完整。"  # 生成检查消息 / Build check message
    return self_test_item("MATLAB batch dry run", ok, message)  # 返回检查结果 / Return check result


def run_deployment_self_test(config: dict) -> dict:  # 运行部署自检 / Run deployment self-test
    diagnostics = diagnose_comsol_environment(config)  # 运行基础诊断 / Run base diagnostics
    comsol_config = config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    paths_config = config.get("paths", {})  # 读取路径配置 / Read path config
    runner_path = resolve_project_path(comsol_config.get("runner_path", ""))  # 解析 runner 路径 / Resolve runner path
    export_dir = resolve_project_path(paths_config.get("comsol_exports_dir", "data/comsol_exports"))  # 解析导出目录 / Resolve export directory
    grid_size = int(config["project"]["grid_size"])  # 读取网格尺寸 / Read grid size
    checks = [  # 创建自检列表 / Create self-test list
        self_test_item("Diagnostics readiness", bool(diagnostics["ready_for_auto_run"]), "Base diagnostics are ready. / 基础诊断已就绪。" if diagnostics["ready_for_auto_run"] else "Base diagnostics are not ready. / 基础诊断尚未就绪。"),  # 添加基础诊断结果 / Add base diagnostics result
        self_test_item("Grid calibration", grid_size == 15 and grid_size % 2 == 1, f"grid_size={grid_size}. / 网格尺寸={grid_size}。"),  # 添加网格校准检查 / Add grid calibration check
        check_runner_contract(runner_path),  # 添加 runner 合同检查 / Add runner contract check
        check_export_directory_write(export_dir),  # 添加导出目录写入检查 / Add export directory write check
        check_timeout_config(config),  # 添加超时配置检查 / Add timeout configuration check
        check_parameter_export(config),  # 添加参数导出检查 / Add parameter export check
        check_matlab_batch(config),  # 添加 MATLAB batch 检查 / Add MATLAB batch check
    ]  # 结束自检列表 / End self-test list
    ready = all(item["status"] == "ok" for item in checks if item.get("required", True))  # 计算自检是否通过 / Compute self-test readiness
    return {"ready": ready, "checks": checks, "diagnostics": diagnostics}  # 返回自检结果 / Return self-test result


def diagnose_comsol_environment(config: dict) -> dict:  # 诊断 COMSOL/MATLAB 环境 / Diagnose COMSOL/MATLAB environment
    discovery = discover_runtime_environment()  # 发现运行进程和安装路径 / Discover running processes and install paths
    runtime_config, applied_paths, discovery = config_with_runtime_discovery(config, discovery)  # 应用运行时发现结果 / Apply runtime discovery result
    comsol_config = runtime_config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    paths_config = runtime_config.get("paths", {})  # 读取路径配置 / Read paths config
    checks = [  # 创建路径检查列表 / Create path check list
        check_path("COMSOL command", comsol_config.get("comsol_command_path", ""), True, True),  # 检查 COMSOL 命令 / Check COMSOL command
        infer_comsol_version(comsol_config.get("comsol_command_path", "")),  # 添加 COMSOL 版本提示 / Add COMSOL version hint
        check_path("MATLAB command", comsol_config.get("matlab_path", ""), True, True),  # 检查 MATLAB 命令 / Check MATLAB command
        infer_matlab_version(comsol_config.get("matlab_path", "")),  # 添加 MATLAB 版本提示 / Add MATLAB version hint
        check_license_environment(),  # 添加 license 环境提示 / Add license environment hint
        check_path("Bound MPH model", comsol_config.get("model_path", ""), True, False),  # 检查绑定模型 / Check bound model
        check_path("LiveLink runner", comsol_config.get("runner_path", ""), True, False),  # 检查 LiveLink 脚本 / Check LiveLink runner
        check_path("Source MPH model", comsol_config.get("source_model_path", ""), False, False),  # 检查原始模型 / Check source model
        check_output_directory("COMSOL exports", paths_config.get("comsol_exports_dir", "data/comsol_exports")),  # 检查导出目录 / Check export directory
        check_timeout_config(config),  # 检查超时配置 / Check timeout configuration
    ]  # 结束路径检查列表 / End path check list
    checks.extend(discovery_check_items(discovery))  # 加入自动发现提示 / Add auto-discovery hints
    if applied_paths:  # 检查是否应用运行时补全 / Check whether runtime completion was applied
        applied_text = ", ".join(f"{key} from {source}" for key, source in applied_paths.items())  # 构造应用说明 / Build applied-path description
        checks.append(self_test_item("Runtime path auto-fill", True, f"Applied {applied_text}. / 已应用 {applied_text}。", "", False))  # 添加补全提示 / Add completion hint
    host = str(comsol_config.get("server_host", "127.0.0.1"))  # 读取 server 主机 / Read server host
    port = int(comsol_config.get("server_port", 2036))  # 读取 server 端口 / Read server port
    auto_start = bool(comsol_config.get("auto_start_server", True))  # 读取自动启动设置 / Read auto-start setting
    reachable = is_server_reachable(host, port)  # 检查 server 端口 / Check server port
    server_status = "ok" if reachable else ("warn" if auto_start else "fail")  # 计算 server 状态 / Compute server status
    server_message = "mphserver is already listening" if reachable else ("Will be started automatically when needed" if auto_start else "mphserver is not reachable and auto-start is disabled")  # 生成 server 消息 / Build server message
    server = {"host": host, "port": port, "auto_start": auto_start, "reachable": reachable, "status": server_status, "message": server_message}  # 构造 server 详情 / Build server detail
    required_ok = all(item["status"] == "ok" for item in checks if item.get("required"))  # 检查必需项 / Check required items
    ready_for_auto_run = required_ok and (reachable or auto_start)  # 判断是否可自动运行 / Decide automatic-run readiness
    return {"ready_for_auto_run": ready_for_auto_run, "checks": checks, "server": server, "discovery": discovery, "applied_runtime_paths": applied_paths}  # 返回诊断结果 / Return diagnostics
