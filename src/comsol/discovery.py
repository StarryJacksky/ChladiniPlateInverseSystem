from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import glob  # 导入通配路径查找 / Import glob path search
import copy  # 导入配置拷贝工具 / Import configuration copy helper
import os  # 导入操作系统判断 / Import operating-system checks
import re  # 导入文本匹配工具 / Import text matching helpers
import shutil  # 导入命令查找工具 / Import command lookup helper
import subprocess  # 导入进程列表命令工具 / Import process-list command tools
from pathlib import Path  # 导入路径对象 / Import path object


INSTALL_PATTERNS = {  # 定义常见安装路径模式 / Define common install path patterns
    "comsol": [  # COMSOL 路径模式 / COMSOL path patterns
        "/Applications/COMSOL*/Multiphysics/bin/comsol",  # macOS COMSOL 路径 / macOS COMSOL path
        "/usr/local/comsol*/multiphysics/bin/comsol",  # Linux COMSOL 路径 / Linux COMSOL path
        "/opt/comsol*/multiphysics/bin/comsol",  # Linux opt COMSOL 路径 / Linux opt COMSOL path
        "C:/Program Files/COMSOL/COMSOL*/Multiphysics/bin/win64/comsol.exe",  # Windows COMSOL 路径 / Windows COMSOL path
        "C:/Program Files (x86)/COMSOL/COMSOL*/Multiphysics/bin/win64/comsol.exe",  # Windows x86 COMSOL 路径 / Windows x86 COMSOL path
    ],  # 结束 COMSOL 路径模式 / End COMSOL path patterns
    "matlab": [  # MATLAB 路径模式 / MATLAB path patterns
        "/Applications/MATLAB_R*.app/bin/matlab",  # macOS MATLAB 路径 / macOS MATLAB path
        "/usr/local/MATLAB/R*/bin/matlab",  # Linux MATLAB 路径 / Linux MATLAB path
        "/opt/MATLAB/R*/bin/matlab",  # Linux opt MATLAB 路径 / Linux opt MATLAB path
        "C:/Program Files/MATLAB/R*/bin/matlab.exe",  # Windows MATLAB 路径 / Windows MATLAB path
        "C:/Program Files (x86)/MATLAB/R*/bin/matlab.exe",  # Windows x86 MATLAB 路径 / Windows x86 MATLAB path
    ],  # 结束 MATLAB 路径模式 / End MATLAB path patterns
}  # 结束安装路径模式 / End install path patterns


def command_available(name: str) -> bool:  # 检查系统命令是否可用 / Check whether a system command is available
    return shutil.which(name) is not None  # 返回命令查找结果 / Return command lookup result


def process_list_commands() -> list[list[str]]:  # 构造跨平台进程列表命令 / Build cross-platform process-list commands
    if os.name == "nt":  # 判断是否 Windows / Check whether Windows
        return [  # 返回 Windows 命令候选 / Return Windows command candidates
            ["wmic", "process", "get", "ProcessId,Name,ExecutablePath,CommandLine", "/FORMAT:CSV"],  # Windows 详细进程命令 / Windows detailed process command
            ["tasklist", "/FO", "CSV", "/NH"],  # Windows 备用进程命令 / Windows fallback process command
        ]  # 结束 Windows 命令候选 / End Windows command candidates
    return [["ps", "-axo", "pid=,comm=,args="], ["pgrep", "-afil", "comsol|matlab|mphserver"]]  # 返回 POSIX 进程命令 / Return POSIX process commands


def decode_process_bytes(data: bytes) -> str:  # 容错解码进程命令输出 / Decode process-command output safely
    if not data:  # 检查空字节 / Check empty bytes
        return ""  # 返回空文本 / Return empty text
    if b"\x00" in data[:200]:  # 检查 Windows UTF-16 常见空字节 / Check common Windows UTF-16 null bytes
        try:  # 尝试 UTF-16 解码 / Try UTF-16 decoding
            return data.decode("utf-16", errors="replace")  # 返回 UTF-16 文本 / Return UTF-16 text
        except UnicodeError:  # 处理异常编码情况 / Handle unusual encoding cases
            pass  # 继续走 UTF-8 兜底 / Continue to UTF-8 fallback
    return data.decode("utf-8", errors="replace")  # 用替换策略避免非 UTF-8 字节崩溃 / Avoid crashes on non-UTF-8 bytes with replacement


def collect_process_lines() -> tuple[list[str], str, str]:  # 读取系统进程列表文本 / Read system process list text
    last_error = ""  # 记录最近错误 / Track latest error
    for command in process_list_commands():  # 遍历候选命令 / Iterate command candidates
        if not command_available(command[0]):  # 检查命令是否存在 / Check command availability
            last_error = f"{command[0]} is not available. / {command[0]} 不可用。"  # 记录命令缺失 / Record missing command
            continue  # 尝试下一个命令 / Try next command
        try:  # 捕获命令执行异常 / Catch command execution errors
            result = subprocess.run(command, capture_output=True, timeout=3.0)  # 执行只读进程列表命令 / Run read-only process-list command
        except (OSError, subprocess.SubprocessError) as exc:  # 处理命令失败 / Handle command failure
            last_error = str(exc)  # 记录异常文本 / Record exception text
            continue  # 尝试下一个命令 / Try next command
        stdout = decode_process_bytes(result.stdout)  # 解码标准输出 / Decode stdout
        stderr = decode_process_bytes(result.stderr)  # 解码错误输出 / Decode stderr
        if result.returncode == 0 and stdout.strip():  # 检查是否拿到输出 / Check whether output exists
            return stdout.splitlines(), command[0], ""  # 返回进程行和来源 / Return process lines and source
        if stderr.strip():  # 检查错误输出 / Check stderr output
            last_error = stderr.strip().splitlines()[0]  # 保存首行错误 / Store first error line
        elif result.returncode != 0:  # 检查非零返回码 / Check non-zero return code
            last_error = f"{command[0]} exited with {result.returncode}. / {command[0]} 返回码 {result.returncode}。"  # 记录返回码 / Record return code
    return [], "", last_error  # 返回空结果和错误 / Return empty result and error


def process_kinds(text: str) -> list[str]:  # 判断进程是否像 COMSOL/MATLAB / Decide whether process looks like COMSOL/MATLAB
    lowered = text.lower()  # 转为小写便于匹配 / Lowercase for matching
    if " rg -i " in lowered or "ps -axo" in lowered or "pgrep -afil" in lowered:  # 跳过检测命令自身 / Skip probe commands themselves
        return []  # 返回空类型 / Return empty kinds
    if "src.main discover-comsol" in lowered or "src.main diagnose-comsol" in lowered or "src.main apply-comsol-discovery" in lowered:  # 跳过本工具命令自身 / Skip this tool's own commands
        return []  # 返回空类型 / Return empty kinds
    if "matlabwebui" in lowered or "mathworksservicehost" in lowered or "mwdocsearch" in lowered:  # 跳过 MATLAB 辅助进程 / Skip MATLAB helper processes
        return []  # 返回空类型 / Return empty kinds
    kinds = []  # 创建类型列表 / Create kind list
    if "mphserver" in lowered:  # 检查 mphserver / Check mphserver
        kinds.append("mphserver")  # 记录 mphserver / Record mphserver
    if "comsol" in lowered:  # 检查 COMSOL / Check COMSOL
        kinds.append("comsol")  # 记录 COMSOL / Record COMSOL
    if re.search(r"\bmatlab\b|matlab_r\d{4}[ab]", lowered):  # 检查 MATLAB 名称 / Check MATLAB name
        kinds.append("matlab")  # 记录 MATLAB / Record MATLAB
    return kinds  # 返回匹配类型 / Return matched kinds


def extract_pid(text: str) -> str:  # 从进程文本中提取进程编号 / Extract process id from process text
    match = re.search(r"^\s*(\d+)\b", text)  # 匹配 POSIX 行首进程号 / Match POSIX leading pid
    if match:  # 检查是否匹配 / Check match
        return match.group(1)  # 返回 POSIX 进程号 / Return POSIX pid
    csv_match = re.search(r"^[^,\n]*,(\d+),", text)  # 匹配 WMIC CSV 进程号 / Match WMIC CSV pid
    if csv_match:  # 检查 CSV 是否匹配 / Check CSV match
        return csv_match.group(1)  # 返回 CSV 进程号 / Return CSV pid
    tasklist_match = re.search(r'^"[^"]+","(\d+)"', text)  # 匹配 tasklist CSV 进程号 / Match tasklist CSV pid
    if tasklist_match:  # 检查 tasklist 是否匹配 / Check tasklist match
        return tasklist_match.group(1)  # 返回 tasklist 进程号 / Return tasklist pid
    numbers = re.findall(r"\b\d+\b", text)  # 查找所有数字 / Find all numbers
    return numbers[0] if numbers else ""  # 返回首个数字作为保守兜底 / Return first number as conservative fallback


def extract_executable_hint(text: str) -> str:  # 从进程文本中提取可执行路径线索 / Extract executable path hint from process text
    quoted = re.findall(r'"([^"]*(?:comsol|matlab)[^"]*)"', text, flags=re.IGNORECASE)  # 查找带引号路径 / Find quoted paths
    candidates = quoted + re.findall(r"(/\S*(?:comsol|matlab)\S*)", text, flags=re.IGNORECASE)  # 加入 POSIX 路径线索 / Add POSIX path hints
    candidates += re.findall(r"([A-Za-z]:[/\\][^,\"]*(?:comsol|matlab)[^,\"]*)", text, flags=re.IGNORECASE)  # 加入 Windows 路径线索 / Add Windows path hints
    for candidate in candidates:  # 遍历候选路径 / Iterate path candidates
        cleaned = candidate.strip().strip(",")  # 清理尾部符号 / Clean trailing punctuation
        if Path(cleaned).exists():  # 检查路径是否存在 / Check path existence
            return str(Path(cleaned))  # 返回存在路径 / Return existing path
    return candidates[0].strip().strip(",") if candidates else ""  # 返回最佳文本线索 / Return best text hint


def shorten_command(text: str, limit: int = 260) -> str:  # 缩短命令文本 / Shorten command text
    compact = " ".join(text.split())  # 压缩空白 / Compact whitespace
    return compact[:limit] + "..." if len(compact) > limit else compact  # 返回截断文本 / Return truncated text


def parse_process_lines(lines: list[str], source: str, error: str = "") -> dict:  # 解析进程列表文本 / Parse process-list text
    processes = []  # 创建进程结果列表 / Create process result list
    seen = set()  # 创建去重集合 / Create de-duplication set
    for line in lines:  # 遍历进程文本行 / Iterate process lines
        kinds = process_kinds(line)  # 判断进程类型 / Detect process kinds
        if not kinds:  # 跳过无关进程 / Skip unrelated process
            continue  # 继续下一行 / Continue to next line
        pid = extract_pid(line)  # 提取进程编号 / Extract process id
        executable = extract_executable_hint(line)  # 提取可执行路径线索 / Extract executable path hint
        command = shorten_command(line)  # 缩短命令文本 / Shorten command text
        for kind in kinds:  # 遍历匹配类型 / Iterate matched kinds
            key = (kind, pid, executable, command)  # 构造去重键 / Build de-duplication key
            if key in seen:  # 检查是否重复 / Check duplicate
                continue  # 跳过重复项 / Skip duplicate
            seen.add(key)  # 记录去重键 / Store de-duplication key
            processes.append({"kind": kind, "pid": pid, "executable": executable, "command": command, "source": source})  # 添加进程结果 / Add process result
    status = "ok" if source else "unavailable"  # 计算探测状态 / Compute probe status
    return {"status": status, "source": source, "error": error, "processes": processes}  # 返回进程结果 / Return process results


def discover_running_processes() -> dict:  # 发现已运行的 COMSOL/MATLAB 进程 / Discover running COMSOL/MATLAB processes
    lines, source, error = collect_process_lines()  # 读取进程列表 / Read process list
    return parse_process_lines(lines, source, error)  # 解析并返回进程结果 / Parse and return process results


def unique_existing_paths(patterns: list[str]) -> list[str]:  # 按模式查找存在路径 / Find existing paths by patterns
    found = []  # 创建路径列表 / Create path list
    seen = set()  # 创建去重集合 / Create de-duplication set
    for pattern in patterns:  # 遍历路径模式 / Iterate path patterns
        for match in glob.glob(os.path.expanduser(pattern)):  # 展开通配路径 / Expand glob pattern
            path = Path(match)  # 转换为路径对象 / Convert to path object
            if not path.exists():  # 检查路径存在 / Check path existence
                continue  # 跳过不存在路径 / Skip missing path
            text = str(path)  # 转换为文本 / Convert to text
            if text in seen:  # 检查是否重复 / Check duplicate
                continue  # 跳过重复路径 / Skip duplicate path
            seen.add(text)  # 记录路径 / Store path
            found.append(text)  # 添加路径 / Add path
    return sorted(found)  # 返回排序路径 / Return sorted paths


def discover_install_candidates(patterns: dict[str, list[str]] | None = None) -> dict[str, list[str]]:  # 发现常见安装路径候选 / Discover common install path candidates
    search_patterns = patterns or INSTALL_PATTERNS  # 读取搜索模式 / Read search patterns
    return {kind: unique_existing_paths(kind_patterns) for kind, kind_patterns in search_patterns.items()}  # 返回各类候选路径 / Return candidates by kind


def first_process_executable(processes: list[dict], kind: str) -> str:  # 读取指定类型的首个进程路径 / Read first process path for a kind
    for process in processes:  # 遍历进程 / Iterate processes
        if process.get("kind") == kind and process.get("executable"):  # 检查类型和路径 / Check kind and path
            return canonical_executable_path(kind, str(process["executable"]))  # 返回规范路径 / Return canonical path
    return ""  # 返回空路径 / Return empty path


def canonical_executable_path(kind: str, executable: str) -> str:  # 规范化发现到的可执行路径 / Canonicalize discovered executable path
    path = Path(executable)  # 转换路径对象 / Convert to path object
    text = str(path)  # 转换路径文本 / Convert path to text
    if kind == "matlab" and ".app/Contents/MacOS/MATLAB" in text:  # 检查 MATLAB GUI 主程序 / Check MATLAB GUI binary
        app_root = text.split(".app/", 1)[0] + ".app"  # 还原 app 根路径 / Restore app root path
        cli_path = Path(app_root) / "bin" / "matlab"  # 构造命令行 MATLAB 路径 / Build CLI MATLAB path
        return str(cli_path) if cli_path.exists() else text  # 优先返回命令行路径 / Prefer CLI path
    if kind == "comsol" and "comsollauncher" in path.name.lower():  # 检查 COMSOL launcher / Check COMSOL launcher
        bin_dir = path.parents[1] if len(path.parents) > 1 else path.parent  # 还原 bin 目录 / Restore bin directory
        cli_path = bin_dir / "comsol"  # 构造 COMSOL 命令路径 / Build COMSOL command path
        return str(cli_path) if cli_path.exists() else text  # 优先返回命令路径 / Prefer command path
    return text  # 返回原始路径 / Return original path


def suggested_paths(processes: list[dict], installs: dict[str, list[str]]) -> dict:  # 生成路径建议 / Build path suggestions
    comsol_from_process = first_process_executable(processes, "comsol")  # 读取 COMSOL 进程路径 / Read COMSOL process path
    matlab_from_process = first_process_executable(processes, "matlab")  # 读取 MATLAB 进程路径 / Read MATLAB process path
    comsol_path = comsol_from_process or (installs.get("comsol") or [""])[0]  # 选择 COMSOL 路径 / Choose COMSOL path
    matlab_path = matlab_from_process or (installs.get("matlab") or [""])[0]  # 选择 MATLAB 路径 / Choose MATLAB path
    return {  # 返回建议字典 / Return suggestion dictionary
        "comsol_command_path": comsol_path,  # COMSOL 建议路径 / Suggested COMSOL path
        "comsol_source": "running_process" if comsol_from_process else ("install_scan" if comsol_path else ""),  # COMSOL 来源 / COMSOL source
        "matlab_path": matlab_path,  # MATLAB 建议路径 / Suggested MATLAB path
        "matlab_source": "running_process" if matlab_from_process else ("install_scan" if matlab_path else ""),  # MATLAB 来源 / MATLAB source
    }  # 结束建议字典 / End suggestion dictionary


def path_usable(value: str | None) -> bool:  # 判断配置路径是否可用 / Decide whether configured path is usable
    if not value:  # 检查空值 / Check empty value
        return False  # 空值不可用 / Empty value is unusable
    return Path(str(value)).expanduser().exists()  # 返回路径存在性 / Return path existence


def config_with_runtime_discovery(config: dict, discovery: dict | None = None) -> tuple[dict, dict, dict]:  # 用发现结果补全运行时配置 / Fill runtime config with discovery results
    runtime_config = copy.deepcopy(config)  # 深拷贝配置避免改写原对象 / Deep-copy config to avoid mutating original
    runtime_discovery = discovery or discover_runtime_environment()  # 读取或执行发现 / Read or run discovery
    suggestions = runtime_discovery.get("suggestions", {})  # 读取路径建议 / Read path suggestions
    comsol_config = runtime_config.setdefault("comsol", {})  # 获取 COMSOL 分区 / Get COMSOL section
    applied = {}  # 记录运行时应用项 / Track runtime applied items
    if not path_usable(comsol_config.get("comsol_command_path")) and suggestions.get("comsol_command_path"):  # 检查是否补全 COMSOL 路径 / Check whether to fill COMSOL path
        comsol_config["comsol_command_path"] = suggestions["comsol_command_path"]  # 应用 COMSOL 建议 / Apply COMSOL suggestion
        applied["comsol_command_path"] = suggestions["comsol_source"]  # 记录 COMSOL 来源 / Record COMSOL source
    if not path_usable(comsol_config.get("matlab_path")) and suggestions.get("matlab_path"):  # 检查是否补全 MATLAB 路径 / Check whether to fill MATLAB path
        comsol_config["matlab_path"] = suggestions["matlab_path"]  # 应用 MATLAB 建议 / Apply MATLAB suggestion
        applied["matlab_path"] = suggestions["matlab_source"]  # 记录 MATLAB 来源 / Record MATLAB source
    return runtime_config, applied, runtime_discovery  # 返回运行时配置和发现信息 / Return runtime config and discovery info


def yaml_string(value: str) -> str:  # 构造 YAML 字符串值 / Build YAML string value
    normalized = str(value).replace("\\", "/")  # 归一化 Windows 反斜杠 / Normalize Windows backslashes
    return '"' + normalized.replace('"', '\\"') + '"'  # 返回双引号字符串 / Return double-quoted string


def write_discovered_paths_to_config(config_path: str | Path = "config.yaml", discovery: dict | None = None) -> dict:  # 写入发现到的路径 / Write discovered paths
    runtime_discovery = discovery or discover_runtime_environment()  # 读取或执行发现 / Read or run discovery
    suggestions = runtime_discovery.get("suggestions", {})  # 读取路径建议 / Read path suggestions
    replacements = {}  # 创建替换字典 / Create replacement dictionary
    if suggestions.get("comsol_command_path"):  # 检查 COMSOL 建议 / Check COMSOL suggestion
        replacements["comsol_command_path"] = suggestions["comsol_command_path"]  # 保存 COMSOL 替换 / Store COMSOL replacement
    if suggestions.get("matlab_path"):  # 检查 MATLAB 建议 / Check MATLAB suggestion
        replacements["matlab_path"] = suggestions["matlab_path"]  # 保存 MATLAB 替换 / Store MATLAB replacement
    if not replacements:  # 检查是否没有可写内容 / Check no writable values
        raise ValueError("No discovered COMSOL/MATLAB paths to write. / 没有可写入的 COMSOL/MATLAB 发现路径。")  # 抛出发现缺失错误 / Raise missing discovery error
    result = write_comsol_paths_to_config(config_path, replacements)  # 写入配置路径 / Write config paths
    result["discovery"] = runtime_discovery  # 附加发现结果 / Attach discovery result
    return result  # 返回写入结果 / Return write result


def write_comsol_paths_to_config(config_path: str | Path, replacements: dict[str, str]) -> dict:  # 写入 COMSOL/MATLAB 路径 / Write COMSOL/MATLAB paths
    allowed = {"comsol_command_path", "matlab_path"}  # 定义允许写入字段 / Define writable fields
    clean_replacements = {key: str(value).strip() for key, value in replacements.items() if key in allowed and str(value).strip()}  # 清理替换字典 / Clean replacement dictionary
    if not clean_replacements:  # 检查是否没有路径 / Check no paths
        raise ValueError("No COMSOL/MATLAB path values to write. / 没有可写入的 COMSOL/MATLAB 路径值。")  # 抛出缺失错误 / Raise missing value error
    target = Path(config_path)  # 转换配置路径 / Convert config path
    lines = target.read_text(encoding="utf-8").splitlines()  # 读取配置行 / Read config lines
    output = []  # 创建输出行 / Create output lines
    current_section = ""  # 记录当前分区 / Track current section
    written = set()  # 记录已写字段 / Track written keys
    for line in lines:  # 遍历配置行 / Iterate config lines
        stripped = line.strip()  # 去掉空白 / Strip whitespace
        if stripped.endswith(":") and not line.startswith(" "):  # 检查顶层分区 / Check top-level section
            if current_section == "comsol":  # 检查是否离开 COMSOL 分区 / Check leaving COMSOL section
                for key, value in clean_replacements.items():  # 遍历未写字段 / Iterate unwritten fields
                    if key not in written:  # 检查字段是否未写 / Check field not written
                        output.append(f"  {key}: {yaml_string(value)} # 自动发现或手动确认路径 / Auto-discovered or manually accepted path")  # 追加字段 / Append field
            current_section = stripped.rstrip(":")  # 更新当前分区 / Update current section
            output.append(line)  # 保留分区标题 / Keep section heading
            continue  # 继续下一行 / Continue to next line
        if current_section == "comsol" and ":" in stripped:  # 检查 COMSOL 分区字段 / Check COMSOL section field
            key = stripped.split(":", 1)[0]  # 读取字段名 / Read field name
            if key in clean_replacements:  # 检查是否要替换 / Check whether to replace
                output.append(f"  {key}: {yaml_string(clean_replacements[key])} # 自动发现或手动确认路径 / Auto-discovered or manually accepted path")  # 写入替换行 / Write replacement line
                written.add(key)  # 标记已写 / Mark written
                continue  # 继续下一行 / Continue to next line
        output.append(line)  # 保留原始行 / Keep original line
    if current_section == "comsol":  # 检查文件是否结束于 COMSOL 分区 / Check file ended in COMSOL section
        for key, value in clean_replacements.items():  # 遍历未写字段 / Iterate unwritten fields
            if key not in written:  # 检查字段是否未写 / Check field not written
                output.append(f"  {key}: {yaml_string(value)} # 自动发现或手动确认路径 / Auto-discovered or manually accepted path")  # 追加字段 / Append field
    target.write_text("\n".join(output) + "\n", encoding="utf-8")  # 写回配置文件 / Write config file
    return {"config_path": str(target), "written": clean_replacements}  # 返回写入结果 / Return write result


def discover_runtime_environment() -> dict:  # 发现本机 COMSOL/MATLAB 环境 / Discover local COMSOL/MATLAB environment
    process_probe = discover_running_processes()  # 发现运行进程 / Discover running processes
    processes = process_probe.get("processes", [])  # 读取进程结果 / Read process results
    installs = discover_install_candidates()  # 发现安装候选 / Discover install candidates
    suggestions = suggested_paths(processes, installs)  # 生成路径建议 / Build path suggestions
    summary = {  # 创建摘要 / Create summary
        "process_count": len(processes),  # 运行进程数量 / Running process count
        "process_probe_status": process_probe.get("status", ""),  # 进程探测状态 / Process probe status
        "process_probe_error": process_probe.get("error", ""),  # 进程探测错误 / Process probe error
        "comsol_install_count": len(installs.get("comsol", [])),  # COMSOL 候选数量 / COMSOL candidate count
        "matlab_install_count": len(installs.get("matlab", [])),  # MATLAB 候选数量 / MATLAB candidate count
        "has_comsol_hint": bool(suggestions.get("comsol_command_path")),  # 是否有 COMSOL 线索 / Whether COMSOL hint exists
        "has_matlab_hint": bool(suggestions.get("matlab_path")),  # 是否有 MATLAB 线索 / Whether MATLAB hint exists
    }  # 结束摘要 / End summary
    return {"processes": processes, "process_probe": process_probe, "install_candidates": installs, "suggestions": suggestions, "summary": summary}  # 返回发现结果 / Return discovery result
