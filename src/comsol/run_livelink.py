from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from src.comsol.credentials import ensure_comsol_credentials
from src.comsol.credentials import is_credential_failure
from src.comsol.discovery import config_with_runtime_discovery
from src.comsol.export_parameters import export_candidate_for_comsol
from src.comsol.server import ensure_comsol_server


DEFAULT_MATLAB_PATH = "/Applications/MATLAB_R2024a.app/bin/matlab"
DEFAULT_RUNNER_PATH = "comsol_templates/run_chladni_candidate.m"


def matlab_quote(value: str | Path) -> str:
    text = str(value)
    return "'" + text.replace("'", "''") + "'"


def resolve_candidate_dir(config: dict, candidate_id: str) -> Path:
    candidates_dir = Path(config["paths"]["candidates_dir"])
    candidate_dir = candidates_dir / candidate_id
    if not candidate_dir.exists():
        raise FileNotFoundError(f"Candidate not found: {candidate_dir}")
    if not (candidate_dir / "H.csv").exists():
        raise FileNotFoundError(f"Candidate H.csv not found: {candidate_dir / 'H.csv'}")
    return candidate_dir


def ensure_comsol_parameters(candidate_dir: Path, material: dict | None = None) -> Path:
    parameter_path = candidate_dir / "comsol_parameters.csv"
    material_path = candidate_dir / "material_parameters.csv"
    if not parameter_path.exists() or not material_path.exists() or material is not None:
        parameter_path = export_candidate_for_comsol(candidate_dir, material)
    return parameter_path


def matlab_path_from_comsol_command(command_path: str | Path) -> Path | None:
    path = Path(command_path)
    candidates: list[Path] = []
    env_mli_path = os.environ.get("COMSOL_MLI_PATH")
    if env_mli_path:
        candidates.append(Path(env_mli_path))
    for parent in path.parents:
        if parent.name.lower() == "multiphysics":
            candidates.append(parent / "mli")
    candidates.extend([
        Path("D:/comsol/COMSOL64/Multiphysics/mli"),
        Path("D:/COMSOL/COMSOL64/Multiphysics/mli"),
        Path("/Applications/COMSOL64/Multiphysics/mli"),
        Path("/usr/local/comsol64/multiphysics/mli"),
        Path("/opt/comsol64/multiphysics/mli"),
    ])
    for root, pattern in [
        (Path("/Applications"), "COMSOL*/Multiphysics/mli"),
        (Path("/usr/local"), "comsol*/multiphysics/mli"),
        (Path("/usr/local"), "COMSOL*/Multiphysics/mli"),
        (Path("/opt"), "comsol*/multiphysics/mli"),
        (Path("/opt"), "COMSOL*/Multiphysics/mli"),
        (Path("C:/Program Files/COMSOL"), "COMSOL*/Multiphysics/mli"),
        (Path("C:/Program Files (x86)/COMSOL"), "COMSOL*/Multiphysics/mli"),
    ]:
        if root.exists():
            candidates.extend(root.glob(pattern))
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold() if os.name == "nt" else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate
    return None


def build_matlab_batch(model_path: Path, candidate_dir: Path, export_dir: Path, runner_path: Path, num_modes: int, mli_path: Path | None = None) -> str:
    runner_dir = runner_path.parent.resolve()
    parts = []
    if mli_path is not None:
        parts.append(f"setenv('COMSOL_MLI_PATH',{matlab_quote(mli_path)})")
        parts.append(f"addpath({matlab_quote(mli_path)})")
    parts.extend([
        f"addpath({matlab_quote(runner_dir)})",
        f"run_chladni_candidate({matlab_quote(model_path.resolve())},{matlab_quote(candidate_dir.resolve())},{matlab_quote(export_dir.resolve())},{num_modes})",
    ])
    return "; ".join(parts)


def write_livelink_log(log_path: Path, command: list[str], output: str, returncode: int) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as file_obj:
        file_obj.write(f"started_at={datetime.now().isoformat(timespec='seconds')}\n")
        file_obj.write(f"returncode={returncode}\n")
        file_obj.write("command=" + " ".join(command) + "\n\n")
        file_obj.write(output or "")


def command_environment(command: list[str], log_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    executable_name = Path(command[0]).name.lower() if command else ""
    if executable_name.startswith("matlab"):
        runtime_root = (log_path.parent / ".matlab_runtime").resolve()
        prefs_dir = runtime_root / "prefs"
        tmp_dir = runtime_root / "tmp"
        home_dir = runtime_root / "home"
        appdata_dir = runtime_root / "appdata"
        local_appdata_dir = runtime_root / "local_appdata"
        for path in [prefs_dir, tmp_dir, home_dir, appdata_dir, local_appdata_dir]:
            path.mkdir(parents=True, exist_ok=True)
        env.update({
            "MATLAB_PREFDIR": str(prefs_dir),
            "TEMP": str(tmp_dir),
            "TMP": str(tmp_dir),
            "HOME": str(home_dir),
            "USERPROFILE": str(home_dir),
            "APPDATA": str(appdata_dir),
            "LOCALAPPDATA": str(local_appdata_dir),
            "COMSOL_SERVER_USER": os.environ.get("COMSOL_SERVER_USER") or os.environ.get("USERNAME") or os.environ.get("USER") or "",
            "COMSOL_SERVER_PASSWORD": os.environ.get("COMSOL_SERVER_PASSWORD", ""),
            "COMSOL_SERVER_HOST": os.environ.get("COMSOL_SERVER_HOST", "127.0.0.1"),
            "COMSOL_SERVER_PORT": os.environ.get("COMSOL_SERVER_PORT", "2036"),
        })
    return env


def apply_comsol_server_environment(config: dict) -> None:
    comsol_config = config.get("comsol", {})
    os.environ["COMSOL_SERVER_HOST"] = str(comsol_config.get("server_host", "127.0.0.1"))
    os.environ["COMSOL_SERVER_PORT"] = str(int(comsol_config.get("server_port", 2036)))


def run_command_streamed(command: list[str], log_path: Path, progress=None, event_base: dict | None = None, timeout_s: float | None = None, append: bool = False) -> tuple[int, str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    output_lines = []
    base = event_base or {}
    mode = "a" if append else "w"
    with log_path.open(mode, encoding="utf-8") as file_obj:
        if append:
            file_obj.write("\n--- retry / 重试 ---\n")
        file_obj.write(f"started_at={datetime.now().isoformat(timespec='seconds')}\n")
        file_obj.write(f"timeout_s={timeout_s or ''}\n")
        file_obj.write("command=" + " ".join(command) + "\n\n")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            env=command_environment(command, log_path),
        )
        assert process.stdout is not None

        def read_output() -> None:
            for line in process.stdout:
                text = line.rstrip("\n")
                output_lines.append(line)
                file_obj.write(line)
                file_obj.flush()
                if progress is not None and text.strip():
                    progress({**base, "stage": "log", "message": text.strip(), "log_path": str(log_path)})

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            returncode = process.wait(timeout=timeout_s) if timeout_s else process.wait()
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = process.wait()
            timeout_message = f"Command timed out after {timeout_s} seconds. / 命令超过 {timeout_s} 秒未完成。"
            file_obj.write(timeout_message + "\n")
            if progress is not None:
                progress({**base, "stage": "error", "message": timeout_message, "log_path": str(log_path)})
        reader.join(timeout=2.0)
        file_obj.write(f"\nreturncode={returncode}\n")
    return returncode, "".join(output_lines)


def is_livelink_connection_failure(output: str) -> bool:
    lowered = output.lower()
    tokens = ["mphstart", "connection refused", "failed to connect to server", "could not be established"]
    return any(token in lowered for token in tokens)


def run_livelink_candidate(config: dict, candidate_id: str, num_modes: int | None = None, model_path: str | Path | None = None, matlab_path: str | Path | None = None, runner_path: str | Path | None = None, progress=None) -> dict:
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)
    ensure_comsol_credentials(runtime_config)
    apply_comsol_server_environment(runtime_config)
    if not ensure_comsol_server(runtime_config):
        raise RuntimeError("COMSOL server is not reachable. / COMSOL server 无法连接。")
    candidate_dir = resolve_candidate_dir(runtime_config, candidate_id)
    ensure_comsol_parameters(candidate_dir, runtime_config.get("material"))
    modes = int(num_modes or runtime_config["simulation"]["num_modes"])
    model = Path(model_path or runtime_config.get("comsol", {}).get("model_path", "comsol_templates/Chladni_15x15_bound.mph"))
    matlab = str(matlab_path or runtime_config.get("comsol", {}).get("matlab_path", DEFAULT_MATLAB_PATH))
    runner = Path(runner_path or runtime_config.get("comsol", {}).get("runner_path", DEFAULT_RUNNER_PATH))
    export_root = Path(runtime_config["paths"]["comsol_exports_dir"])
    export_dir = export_root / candidate_id
    export_dir.mkdir(parents=True, exist_ok=True)
    mli_path = matlab_path_from_comsol_command(runtime_config.get("comsol", {}).get("comsol_command_path", ""))
    batch = build_matlab_batch(model, candidate_dir, export_dir, runner, modes, mli_path)
    command = [matlab, "-nosplash", "-noFigureWindows", "-sd", str(Path.cwd()), "-batch", batch]
    log_path = export_dir / "livelink.log"
    timeout_s = float(runtime_config.get("comsol", {}).get("livelink_timeout_s", 7200))
    returncode, output = run_command_streamed(command, log_path, progress, {"current_candidate": candidate_id}, timeout_s)
    if returncode != 0 and is_credential_failure(output):
        raise RuntimeError("COMSOL_CREDENTIALS_REQUIRED: COMSOL Server username or password is missing or incorrect. / COMSOL Server 用户名或密码缺失或错误。")
    if returncode != 0 and is_livelink_connection_failure(output):
        if progress is not None:
            progress({"current_candidate": candidate_id, "stage": "retry", "message": "LiveLink connection failed once; restarting COMSOL server and retrying. / LiveLink 首次连接失败，正在重启 COMSOL server 并重试。", "log_path": str(log_path)})
        ensure_comsol_server(runtime_config, wait_s=float(runtime_config.get("comsol", {}).get("server_start_timeout_s", 30.0)))
        returncode, output = run_command_streamed(command, log_path, progress, {"current_candidate": candidate_id}, timeout_s, append=True)
    if returncode != 0 and is_credential_failure(output):
        raise RuntimeError("COMSOL_CREDENTIALS_REQUIRED: COMSOL Server username or password is missing or incorrect. / COMSOL Server 用户名或密码缺失或错误。")
    if returncode != 0:
        raise RuntimeError(f"LiveLink simulation failed for {candidate_id}. See {log_path}. / {candidate_id} 的 LiveLink 仿真失败，见 {log_path}。")
    return {"candidate_id": candidate_id, "export_dir": str(export_dir), "num_modes": modes, "returncode": returncode, "log_path": str(log_path)}


def list_candidate_ids(config: dict, generation: int | None = None, limit: int | None = None) -> list[str]:
    candidates_dir = Path(config["paths"]["candidates_dir"])
    pattern = f"candidate_{generation:03d}_*" if generation is not None else "candidate_*"
    candidate_paths = sorted(path for path in candidates_dir.glob(pattern) if (path / "H.csv").exists())
    candidate_ids = [path.name for path in candidate_paths]
    return candidate_ids[:limit] if limit else candidate_ids


def run_livelink_batch(config: dict, candidate_ids: list[str] | None = None, generation: int | None = None, limit: int | None = None, num_modes: int | None = None, model_path: str | Path | None = None) -> list[dict]:
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)
    ensure_comsol_credentials(runtime_config)
    apply_comsol_server_environment(runtime_config)
    if not ensure_comsol_server(runtime_config):
        raise RuntimeError("COMSOL server is not reachable. / COMSOL server 无法连接。")
    selected_ids = candidate_ids or list_candidate_ids(runtime_config, generation, limit)
    if not selected_ids:
        return []
    modes = int(num_modes or runtime_config["simulation"]["num_modes"])
    model = Path(model_path or runtime_config.get("comsol", {}).get("model_path", "comsol_templates/Chladni_15x15_bound.mph"))
    matlab = str(runtime_config.get("comsol", {}).get("matlab_path", DEFAULT_MATLAB_PATH))
    runner = Path(runtime_config.get("comsol", {}).get("runner_path", DEFAULT_RUNNER_PATH))
    export_root = Path(runtime_config["paths"]["comsol_exports_dir"])
    runner_dir = runner.parent.resolve()
    mli_path = matlab_path_from_comsol_command(runtime_config.get("comsol", {}).get("comsol_command_path", ""))
    batch_parts = []
    if mli_path is not None:
        batch_parts.append(f"setenv('COMSOL_MLI_PATH',{matlab_quote(mli_path)})")
        batch_parts.append(f"addpath({matlab_quote(mli_path)})")
    batch_parts.append(f"addpath({matlab_quote(runner_dir)})")
    results = []
    for candidate_id in selected_ids:
        candidate_dir = resolve_candidate_dir(runtime_config, candidate_id)
        ensure_comsol_parameters(candidate_dir, runtime_config.get("material"))
        export_dir = export_root / candidate_id
        export_dir.mkdir(parents=True, exist_ok=True)
        batch_parts.append(f"run_chladni_candidate({matlab_quote(model.resolve())},{matlab_quote(candidate_dir.resolve())},{matlab_quote(export_dir.resolve())},{modes})")
        results.append({"candidate_id": candidate_id, "export_dir": str(export_dir), "num_modes": modes})
    command = [matlab, "-nosplash", "-noFigureWindows", "-sd", str(Path.cwd()), "-batch", "; ".join(batch_parts)]
    log_path = export_root / "livelink_batch.log"
    timeout_s = float(runtime_config.get("comsol", {}).get("livelink_timeout_s", 7200))
    returncode, output = run_command_streamed(command, log_path, timeout_s=timeout_s)
    if returncode != 0 and is_credential_failure(output):
        raise RuntimeError("COMSOL_CREDENTIALS_REQUIRED: COMSOL Server username or password is missing or incorrect. / COMSOL Server 用户名或密码缺失或错误。")
    if returncode != 0:
        raise RuntimeError(f"LiveLink batch simulation failed. See {log_path}. / LiveLink 批量仿真失败，见 {log_path}。")
    for result in results:
        result["returncode"] = returncode
        result["log_path"] = str(log_path)
    return results
