from __future__ import annotations  # Enable modern type hints

import copy  # Import configuration copy helper
import glob  # Import glob path search
import os  # Import operating-system checks
import re  # Import text matching helpers
import shutil  # Import command lookup helper
import subprocess  # Import process-list command tools
from pathlib import Path  # Import path object


INSTALL_PATTERNS = {  # Define common install path patterns
    "comsol": [  # COMSOL path patterns
        "/Applications/COMSOL*/Multiphysics/bin/comsol",
        "/usr/local/comsol*/multiphysics/bin/comsol",
        "/opt/comsol*/multiphysics/bin/comsol",
        "C:/Program Files/COMSOL/COMSOL*/Multiphysics/bin/win64/comsol.exe",
        "C:/Program Files (x86)/COMSOL/COMSOL*/Multiphysics/bin/win64/comsol.exe",
        "D:/comsol/COMSOL*/Multiphysics/bin/win64/comsol.exe",
        "D:/COMSOL/COMSOL*/Multiphysics/bin/win64/comsol.exe",
    ],
    "matlab": [  # MATLAB path patterns
        "/Applications/MATLAB_R*.app/bin/matlab",
        "/usr/local/MATLAB/R*/bin/matlab",
        "/opt/MATLAB/R*/bin/matlab",
        "C:/Program Files/MATLAB/R*/bin/matlab.exe",
        "C:/Program Files (x86)/MATLAB/R*/bin/matlab.exe",
        "D:/MATLAB/bin/matlab.exe",
        "D:/matlab/bin/matlab.exe",
        "D:/MATLAB/R*/bin/matlab.exe",
        "D:/matlab/R*/bin/matlab.exe",
    ],
}


def command_available(name: str) -> bool:  # Check whether a system command is available
    return shutil.which(name) is not None


def process_list_commands() -> list[list[str]]:  # Build cross-platform process-list commands
    if os.name == "nt":
        return [
            ["wmic", "process", "get", "ProcessId,Name,ExecutablePath,CommandLine", "/FORMAT:CSV"],
            ["powershell", "-NoProfile", "-Command", "Get-Process | Select-Object Id,ProcessName,Path | ConvertTo-Csv -NoTypeInformation"],
            ["tasklist", "/FO", "CSV", "/NH"],
        ]
    return [["ps", "-axo", "pid=,comm=,args="], ["pgrep", "-afil", "comsol|matlab|mphserver"]]


def decode_process_bytes(data: bytes) -> str:  # Decode process-command output safely
    if not data:
        return ""
    if b"\x00" in data[:200]:
        try:
            return data.decode("utf-16", errors="replace")
        except UnicodeError:
            pass
    return data.decode("utf-8", errors="replace")


def collect_process_lines() -> tuple[list[str], str, str]:  # Read system process list text
    last_error = ""
    for command in process_list_commands():
        if not command_available(command[0]):
            last_error = f"{command[0]} is not available."
            continue
        try:
            result = subprocess.run(command, capture_output=True, timeout=3.0)
        except (OSError, subprocess.SubprocessError) as exc:
            last_error = str(exc)
            continue
        stdout = decode_process_bytes(result.stdout)
        stderr = decode_process_bytes(result.stderr)
        if result.returncode == 0 and stdout.strip():
            return stdout.splitlines(), command[0], ""
        if stderr.strip():
            last_error = stderr.strip().splitlines()[0]
        elif result.returncode != 0:
            last_error = f"{command[0]} exited with {result.returncode}."
    return [], "", last_error


def process_kinds(text: str) -> list[str]:  # Decide whether process looks like COMSOL/MATLAB
    lowered = text.lower()
    if " rg -i " in lowered or "ps -axo" in lowered or "pgrep -afil" in lowered:
        return []
    if "src.main discover-comsol" in lowered or "src.main diagnose-comsol" in lowered or "src.main apply-comsol-discovery" in lowered:
        return []
    if "matlabwebui" in lowered or "mathworksservicehost" in lowered or "mwdocsearch" in lowered:
        return []
    kinds = []
    if "mphserver" in lowered:
        kinds.append("mphserver")
    if "comsol" in lowered:
        kinds.append("comsol")
    if re.search(r"\bmatlab\b|matlab_r\d{4}[ab]", lowered):
        kinds.append("matlab")
    return kinds


def extract_pid(text: str) -> str:  # Extract process id from process text
    match = re.search(r"^\s*(\d+)\b", text)
    if match:
        return match.group(1)
    csv_match = re.search(r"^[^,\n]*,(\d+),", text)
    if csv_match:
        return csv_match.group(1)
    tasklist_match = re.search(r'^"[^"]+","(\d+)"', text)
    if tasklist_match:
        return tasklist_match.group(1)
    numbers = re.findall(r"\b\d+\b", text)
    return numbers[0] if numbers else ""


def extract_executable_hint(text: str) -> str:  # Extract executable path hint from process text
    quoted = re.findall(r'"([^"]*(?:comsol|matlab)[^"]*)"', text, flags=re.IGNORECASE)
    candidates = quoted + re.findall(r"(/\S*(?:comsol|matlab)\S*)", text, flags=re.IGNORECASE)
    candidates += re.findall(r"([A-Za-z]:[/\\][^,\"]*(?:comsol|matlab)[^,\"]*)", text, flags=re.IGNORECASE)
    for candidate in candidates:
        cleaned = candidate.strip().strip(",")
        if Path(cleaned).exists():
            return str(Path(cleaned))
    return candidates[0].strip().strip(",") if candidates else ""


def shorten_command(text: str, limit: int = 260) -> str:  # Shorten command text
    compact = " ".join(text.split())
    return compact[:limit] + "..." if len(compact) > limit else compact


def parse_process_lines(lines: list[str], source: str, error: str = "") -> dict:  # Parse process-list text
    processes = []
    seen = set()
    for line in lines:
        kinds = process_kinds(line)
        if not kinds:
            continue
        pid = extract_pid(line)
        executable = extract_executable_hint(line)
        command = shorten_command(line)
        for kind in kinds:
            key = (kind, pid, executable, command)
            if key in seen:
                continue
            seen.add(key)
            processes.append({"kind": kind, "pid": pid, "executable": executable, "command": command, "source": source})
    status = "ok" if source else "unavailable"
    return {"status": status, "source": source, "error": error, "processes": processes}


def discover_running_processes() -> dict:  # Discover running COMSOL/MATLAB processes
    lines, source, error = collect_process_lines()
    return parse_process_lines(lines, source, error)


def unique_existing_paths(patterns: list[str]) -> list[str]:  # Find existing paths by patterns
    found = []
    seen = set()
    for pattern in patterns:
        for match in glob.glob(os.path.expanduser(pattern)):
            path = Path(match)
            if not path.exists():
                continue
            text = str(path)
            key = text.casefold() if os.name == "nt" else text
            if key in seen:
                continue
            seen.add(key)
            found.append(text)
    return sorted(found)


def discover_install_candidates(patterns: dict[str, list[str]] | None = None) -> dict[str, list[str]]:  # Discover common install path candidates
    search_patterns = patterns or INSTALL_PATTERNS
    candidates = {kind: unique_existing_paths(kind_patterns) for kind, kind_patterns in search_patterns.items()}
    for kind, command_name in ({"comsol": "comsol", "matlab": "matlab"}.items() if patterns is None else []):
        command_path = shutil.which(command_name)
        existing = {path.casefold() if os.name == "nt" else path for path in candidates.get(kind, [])}
        key = command_path.casefold() if command_path and os.name == "nt" else command_path
        if command_path and key not in existing:
            candidates.setdefault(kind, []).append(command_path)
    return {kind: sorted(paths) for kind, paths in candidates.items()}


def first_process_executable(processes: list[dict], kind: str) -> str:  # Read first process path for a kind
    for process in processes:
        if process.get("kind") == kind and process.get("executable"):
            return canonical_executable_path(kind, str(process["executable"]))
    return ""


def canonical_executable_path(kind: str, executable: str) -> str:  # Canonicalize discovered executable path
    path = Path(executable)
    text = str(path)
    normalized = str(executable).replace("\\", "/")
    if kind == "matlab" and ".app/Contents/MacOS/MATLAB" in normalized:
        app_root = normalized.split(".app/", 1)[0] + ".app"
        cli_text = f"{app_root}/bin/matlab"
        cli_path = Path(cli_text)
        return str(cli_path) if cli_path.exists() else cli_text
    if kind == "comsol" and path.name.lower() in {"comsolmphserver", "comsolmphserver.exe"}:
        cli_name = "comsol.exe" if os.name == "nt" else "comsol"
        cli_path = path.with_name(cli_name)
        return str(cli_path) if cli_path.exists() else text
    if kind == "comsol" and path.name.lower() in {"comsollauncher", "comsollauncher.exe", "comsolui.exe"}:
        bin_dir = path.parents[1] if "comsollauncher" in path.name.lower() and len(path.parents) > 1 else path.parent
        cli_name = "comsol.exe" if os.name == "nt" else "comsol"
        cli_path = bin_dir / cli_name
        return str(cli_path) if cli_path.exists() else text
    return text


def suggested_paths(processes: list[dict], installs: dict[str, list[str]]) -> dict:  # Build path suggestions
    comsol_from_process = first_process_executable(processes, "comsol")
    matlab_from_process = first_process_executable(processes, "matlab")
    comsol_path = comsol_from_process or (installs.get("comsol") or [""])[0]
    matlab_path = matlab_from_process or (installs.get("matlab") or [""])[0]
    return {
        "comsol_command_path": comsol_path,
        "comsol_source": "running_process" if comsol_from_process else ("install_scan" if comsol_path else ""),
        "matlab_path": matlab_path,
        "matlab_source": "running_process" if matlab_from_process else ("install_scan" if matlab_path else ""),
    }


def path_usable(value: str | None) -> bool:  # Decide whether configured path is usable
    if not value:
        return False
    return Path(str(value)).expanduser().exists()


def config_with_runtime_discovery(config: dict, discovery: dict | None = None) -> tuple[dict, dict, dict]:  # Fill runtime config with discovery results
    runtime_config = copy.deepcopy(config)
    runtime_discovery = discovery or discover_runtime_environment()
    suggestions = runtime_discovery.get("suggestions", {})
    comsol_config = runtime_config.setdefault("comsol", {})
    applied = {}
    if not path_usable(comsol_config.get("comsol_command_path")) and suggestions.get("comsol_command_path"):
        comsol_config["comsol_command_path"] = suggestions["comsol_command_path"]
        applied["comsol_command_path"] = suggestions["comsol_source"]
    if not path_usable(comsol_config.get("matlab_path")) and suggestions.get("matlab_path"):
        comsol_config["matlab_path"] = suggestions["matlab_path"]
        applied["matlab_path"] = suggestions["matlab_source"]
    return runtime_config, applied, runtime_discovery


def yaml_string(value: str) -> str:  # Build YAML string value
    normalized = str(value).replace("\\", "/")
    return '"' + normalized.replace('"', '\\"') + '"'


def write_discovered_paths_to_config(config_path: str | Path = "config.yaml", discovery: dict | None = None) -> dict:  # Write discovered paths
    runtime_discovery = discovery or discover_runtime_environment()
    suggestions = runtime_discovery.get("suggestions", {})
    replacements = {}
    if suggestions.get("comsol_command_path"):
        replacements["comsol_command_path"] = suggestions["comsol_command_path"]
    if suggestions.get("matlab_path"):
        replacements["matlab_path"] = suggestions["matlab_path"]
    if not replacements:
        raise ValueError("No discovered COMSOL/MATLAB paths to write.")
    result = write_comsol_paths_to_config(config_path, replacements)
    result["discovery"] = runtime_discovery
    return result


def write_comsol_paths_to_config(config_path: str | Path, replacements: dict[str, str]) -> dict:  # Write COMSOL/MATLAB paths
    allowed = {"comsol_command_path", "matlab_path"}
    clean_replacements = {key: str(value).strip() for key, value in replacements.items() if key in allowed and str(value).strip()}
    if not clean_replacements:
        raise ValueError("No COMSOL/MATLAB path values to write.")
    target = Path(config_path)
    lines = target.read_text(encoding="utf-8").splitlines()
    output = []
    current_section = ""
    written = set()
    for line in lines:
        stripped = line.strip()
        if stripped.endswith(":") and not line.startswith(" "):
            if current_section == "comsol":
                for key, value in clean_replacements.items():
                    if key not in written:
                        output.append(f"  {key}: {yaml_string(value)} # Auto-discovered or manually accepted path")
            current_section = stripped.rstrip(":")
            output.append(line)
            continue
        if current_section == "comsol" and ":" in stripped:
            key = stripped.split(":", 1)[0]
            if key in clean_replacements:
                output.append(f"  {key}: {yaml_string(clean_replacements[key])} # Auto-discovered or manually accepted path")
                written.add(key)
                continue
        output.append(line)
    if current_section == "comsol":
        for key, value in clean_replacements.items():
            if key not in written:
                output.append(f"  {key}: {yaml_string(value)} # Auto-discovered or manually accepted path")
    target.write_text("\n".join(output) + "\n", encoding="utf-8")
    return {"config_path": str(target), "written": clean_replacements}


def discover_runtime_environment() -> dict:  # Discover local COMSOL/MATLAB environment
    process_probe = discover_running_processes()
    processes = process_probe.get("processes", [])
    installs = discover_install_candidates()
    suggestions = suggested_paths(processes, installs)
    summary = {
        "process_count": len(processes),
        "process_probe_status": process_probe.get("status", ""),
        "process_probe_error": process_probe.get("error", ""),
        "comsol_install_count": len(installs.get("comsol", [])),
        "matlab_install_count": len(installs.get("matlab", [])),
        "has_comsol_hint": bool(suggestions.get("comsol_command_path")),
        "has_matlab_hint": bool(suggestions.get("matlab_path")),
    }
    return {"processes": processes, "process_probe": process_probe, "install_candidates": installs, "suggestions": suggestions, "summary": summary}
