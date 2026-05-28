from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from src.comsol.credentials import ensure_comsol_credentials
from src.comsol.credentials import is_credential_failure
from src.comsol.discovery import config_with_runtime_discovery
from src.comsol.export_parameters import export_candidate_for_comsol
from src.comsol.server import ensure_comsol_server


DEFAULT_MATLAB_PATH = "/Applications/MATLAB_R2024a.app/bin/matlab"
DEFAULT_RUNNER_PATH = "comsol_templates/run_chladni_candidate.m"
DEFAULT_FORCED_RUNNER_PATH = "comsol_templates/run_chladni_forced_response.m"  # 默认强迫响应 runner 路径 / Default forced-response runner path


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


def build_forced_matlab_batch(model_path: Path, candidate_dir: Path, export_dir: Path, runner_path: Path, mli_path: Path | None = None) -> str:  # 构造强迫响应 MATLAB batch / Build forced-response MATLAB batch
    runner_dir = runner_path.parent.resolve()  # 解析 runner 目录 / Resolve runner directory
    parts = []  # 创建 batch 片段列表 / Create batch part list
    if mli_path is not None:  # 检查是否找到 COMSOL-MATLAB 接口 / Check whether COMSOL-MATLAB interface was found
        parts.append(f"setenv('COMSOL_MLI_PATH',{matlab_quote(mli_path)})")  # 写入接口环境变量 / Write interface environment variable
        parts.append(f"addpath({matlab_quote(mli_path)})")  # 添加接口路径 / Add interface path
    parts.extend([  # 添加 runner 与调用语句 / Add runner path and invocation
        f"addpath({matlab_quote(runner_dir)})",  # 添加 runner 目录 / Add runner directory
        f"run_chladni_forced_response({matlab_quote(model_path.resolve())},{matlab_quote(candidate_dir.resolve())},{matlab_quote(export_dir.resolve())})",  # 调用强迫响应 runner / Call forced-response runner
    ])  # 结束 batch 片段 / End batch parts
    return "; ".join(parts)  # 返回 MATLAB batch 字符串 / Return MATLAB batch string


def write_livelink_log(log_path: Path, command: list[str], output: str, returncode: int) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as file_obj:
        file_obj.write(f"started_at={datetime.now().isoformat(timespec='seconds')}\n")
        file_obj.write(f"returncode={returncode}\n")
        file_obj.write("command=" + " ".join(command) + "\n\n")
        file_obj.write(output or "")


def _cleanup_stale_windows_matlab_runtime(log_path: Path) -> None:
    runtime_root = log_path.parent / ".matlab_runtime"
    try:
        if runtime_root.exists():
            shutil.rmtree(runtime_root)
    except OSError:
        pass


def command_environment(command: list[str], log_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    # Use plain string ops so this works no matter what os.name pathlib
    # initialised against (matters for unit-testing the Windows branch on
    # POSIX, where Path('foo.exe') would try to construct WindowsPath). /
    # 用纯字符串切分，便于在 POSIX 单测里 mock os.name='nt' 时不挂掉 pathlib
    exe_str = (command[0] if command else "")
    exe_tail = exe_str.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if exe_tail.startswith("matlab"):
        # COMSOL Server credentials always need to be present so MATLAB can
        # connect via LiveLink. / COMSOL Server 凭据始终要有，否则 LiveLink 连不上
        env.update({
            "COMSOL_SERVER_USER": os.environ.get("COMSOL_SERVER_USER") or os.environ.get("USERNAME") or os.environ.get("USER") or "",
            "COMSOL_SERVER_PASSWORD": os.environ.get("COMSOL_SERVER_PASSWORD", ""),
            "COMSOL_SERVER_HOST": os.environ.get("COMSOL_SERVER_HOST", "127.0.0.1"),
            "COMSOL_SERVER_PORT": os.environ.get("COMSOL_SERVER_PORT", "2036"),
        })

        if os.name == "nt":
            # On Windows we deliberately keep MATLAB's environment as vanilla
            # as the user's shell. Overriding MATLAB_PREFDIR / TEMP / TMP /
            # USERPROFILE / APPDATA / LOCALAPPDATA to anything other than the
            # OS defaults has been observed to cause
            #     Fatal Startup Error:
            #     Dynamic exception type: class std::runtime_error
            #     std::exception::what: System Error: File system inconsistency
            #     ERROR: MATLAB error Exit Status: 0x00000001
            # *before* MATLAB even parses ``-batch``. MATLAB's Windows
            # startup expects to find license, prefs, and cache layout in
            # the OS-default locations; pointing them at a project-local
            # ``.matlab_runtime`` folder confuses MATLAB's own consistency
            # checks. Just pass COMSOL_SERVER_* through and let MATLAB
            # behave exactly as it does when you double-click matlab.exe. /
            # Windows 上保持 MATLAB 看到的环境与用户双击 matlab.exe 时一致：
            # 任何对 MATLAB_PREFDIR/TEMP/USERPROFILE/APPDATA 的重定向都会触发
            # "Fatal Startup Error: File system inconsistency" 启动崩溃
            _cleanup_stale_windows_matlab_runtime(log_path)
            env.pop("MATLAB_PREFDIR", None)
            env.pop("MATLAB_LOG_DIR", None)
            for env_name in ("TEMP", "TMP", "HOME"):
                value = env.get(env_name, "")
                if ".matlab_runtime" in value.replace("\\", "/").lower():
                    env.pop(env_name, None)
            return env

        # POSIX (Mac/Linux): isolate MATLAB's per-run state under the log
        # directory so concurrent runs don't fight over ~/.matlab and tmp
        # files don't pollute the user's real $HOME. This has been safe on
        # POSIX for months. / Mac/Linux 保持老行为：把 prefs/temp/home 隔离到
        # log 目录下，避免并发 MATLAB 互相踩
        runtime_root = (log_path.parent / ".matlab_runtime").resolve()
        prefs_dir = runtime_root / "prefs"
        tmp_dir = runtime_root / "tmp"
        home_dir = runtime_root / "home"
        for path in [prefs_dir, tmp_dir, home_dir]:
            path.mkdir(parents=True, exist_ok=True)
        env["MATLAB_PREFDIR"] = str(prefs_dir)
        env["TEMP"] = str(tmp_dir)
        env["TMP"] = str(tmp_dir)
        env["HOME"] = str(home_dir)
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
    lowered = (output or "").lower()
    tokens = [
        # COMSOL LiveLink connect entry points
        "mphstart", "mphsave", "mphload", "mphquit", "mphtag",
        # COMSOL Server Java side (these names appear in MATLAB stack traces
        # when the connection drops mid-call)
        "modelutil.connectserver", "modelutil.disconnect", "modelutil",
        "comsolserver", "comsolmphserver", "mphremoteconnector",
        # Plain English connection errors
        "connection refused", "connection reset",
        "failed to connect to server", "could not be established",
        "could not connect to comsol", "unable to connect",
    ]
    return any(token in lowered for token in tokens)


def is_likely_mphserver_problem(output: str, returncode: int) -> bool:
    """Heuristic: does this MATLAB failure look like a transient mphserver /
    LiveLink / license issue worth retrying after a server reset?

    Returns True for any of:
    * Explicit LiveLink connection-failure tokens (covered by ``is_livelink_connection_failure``).
    * Broader transient patterns (license server, MATLAB engine, broken pipe,
      Java exceptions, socket errors, timeouts during connect).
    * Non-zero return code with essentially no useful log output — typically a
      startup-time failure (server died before MATLAB could print anything).
    """
    lowered = (output or "").lower()
    if is_livelink_connection_failure(lowered):
        return True
    if is_likely_matlab_startup_runtime_failure(lowered):
        return True
    transient_patterns = (
        # Connection / socket
        "no connection could be made",
        "broken pipe",
        "socket closed",
        "socket exception",
        "socketexception",
        "timed out connecting",
        "connect timed out",
        "address already in use",
        # COMSOL / LiveLink internals
        "com.comsol.util.exceptions",
        "flexnetlicensingexception",
        "license manager",
        "license error",
        "license token",
        "license check-out failed",
        "lmgrd",
        # MATLAB engine on the Python/COMSOL boundary
        "matlab engine",
        "java.lang.runtimeexception",
        "java.io.ioexception",
        # Server lifecycle
        "server stopped responding",
        "server has gone away",
        "rmi exception",
    )
    if any(pat in lowered for pat in transient_patterns):
        return True
    # Hard-error patterns: only genuine MATLAB / model bugs go here. MUST NOT
    # include the bare ``"error using "`` prefix because MATLAB prints it for
    # **every** error including mphserver/LiveLink connection failures (e.g.
    # ``Error using mphstart`` or ``Error using ModelUtil/connectServer``)
    # which we want to retry. Connection-side ``Error using ...`` lines are
    # already caught above by ``is_livelink_connection_failure`` (mphstart /
    # modelutil / etc. are in its token list). /
    # 硬错误黑名单：不要包含光秃秃的 "error using " — MATLAB 给所有错误（包括 mphserver
    # 抽风）都加这个前缀，会误杀。LiveLink 连接相关的 "Error using ..." 上面就被
    # is_livelink_connection_failure 捕获了
    hard_error_patterns = (
        # Undefined / unrecognised — strong signal of a setup or model bug,
        # not a transient server issue (would have shown a connection-side
        # token above)
        "undefined function",
        "undefined variable",
        "unrecognized function or variable",
        "unrecognized variable",
        # Field / index issues — pure MATLAB / data bugs
        "reference to non-existent field",
        "index exceeds the number",
        "subscript indices",
        "incorrect dimensions",
        # Resource / model
        "out of memory",
        "comsol:domain",
        "no boundary condition",
        "geometry contains no",
        "physics interface",
        # Bad MATLAB input
        "not enough input arguments",
        "too many input arguments",
        "invalid expression",
    )
    if any(pat in lowered for pat in hard_error_patterns):
        return False
    # If MATLAB returned non-zero with nearly empty output the server almost
    # certainly died before MATLAB could write anything useful — retry. /
    # 失败但日志几乎为空：mphserver 通常在 MATLAB 输出任何信息前就挂了，值得重试
    if returncode != 0:
        meaningful = [
            line for line in lowered.splitlines()
            if line.strip() and not line.startswith((
                "command=", "started_at=", "timeout_s=", "returncode=",
                "--- retry", "started_at"))
        ]
        if len(meaningful) < 5:
            return True
    return False


def is_likely_matlab_startup_runtime_failure(output: str) -> bool:
    lowered = (output or "").lower()
    if "fatal startup error" not in lowered and "matlab error exit status" not in lowered:
        return False
    runtime_tokens = (
        "createfile failed",
        "system:5",
        "access is denied",
        "access denied",
        "permission denied",
        "file system inconsistency",
        "matlab_prefdir",
        ".matlab_runtime",
        "temp",
        "tmp",
    )
    return "fatal startup error" in lowered or any(token in lowered for token in runtime_tokens)


CREDENTIALS_REQUIRED_MESSAGE = (
    "COMSOL_CREDENTIALS_REQUIRED: COMSOL Server username or password is missing or incorrect. "
    "/ COMSOL Server 用户名或密码缺失或错误。"
)


def _emit_retry(progress, event_base: dict | None, message: str, log_path: Path) -> None:
    if progress is None:
        return
    progress({**(event_base or {}), "stage": "retry", "message": message, "log_path": str(log_path)})


def run_matlab_with_mphserver_retry(
    command: list[str],
    log_path: Path,
    runtime_config: dict,
    label: str,
    timeout_s: float | None = None,
    progress=None,
    event_base: dict | None = None,
    max_attempts: int | None = None,
) -> tuple[int, str]:
    """Run a MATLAB ``-batch`` command and self-heal transient COMSOL
    mphserver failures, borrowing all the safety nets the legacy
    ``run_livelink_candidate`` path already had:

    * **Refresh COMSOL credentials and server env vars before every attempt**
      so a stale ``os.environ`` (or a worker forked before
      ``ensure_comsol_credentials`` ran) can't silently break MATLAB's
      login.
    * **Fail fast on credential errors** — re-raise with the
      ``COMSOL_CREDENTIALS_REQUIRED:`` token prefix the frontend matches in
      ``frontend/comsol_credentials.js`` to pop the username/password
      prompt. Retrying with bad creds would just burn another 7200-second
      timeout for nothing.
    * **Escalating retry policy**: the first retry only re-runs
      ``ensure_comsol_server`` (cheap — just starts a server if the port
      is unreachable). Only if a *second* retry is needed do we hard-reset
      via ``reset_mphserver`` (kill the stale ``comsolmphserver`` on the
      configured port, then start a fresh one). This avoids tearing down
      a healthy server when the failure was a one-off LiveLink hiccup.
    * **Skip retries on hard MATLAB / model errors** (``Error using``,
      ``Undefined function``, ``Index exceeds``, ...) — they're not going
      to fix themselves and a retry just doubles the wall-clock cost.

    Each attempt streams output to ``log_path``; retries append a
    ``--- retry ---`` section to the same log so users can read one file
    to see the full history. Returns ``(returncode, accumulated_output)``.
    """
    from src.comsol.server import reset_mphserver  # 延迟导入避免循环 / Lazy import avoids a cycle

    comsol_config = (runtime_config or {}).get("comsol", {})
    if max_attempts is None:
        max_attempts = int(comsol_config.get("retry_max_attempts", 2))
    max_attempts = max(1, int(max_attempts))
    server_wait_s = float(comsol_config.get("server_start_timeout_s", 30.0))

    accumulated_output = ""
    rc = 0
    last_output = ""
    attempts_used = 0
    retry_log: list[str] = []  # 简短重试记录，最后写入 log 末尾便于 postmortem / Short retry trace appended to log footer for postmortems

    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt
        # Defensive refresh: a previous attempt may have killed the server,
        # forks may have lost the env vars, etc. Both helpers are idempotent. /
        # 每次发车前补一遍凭据 + server env vars，避免 fork/重启把环境弄丢
        try:
            ensure_comsol_credentials(runtime_config)
            apply_comsol_server_environment(runtime_config)
        except Exception:
            pass

        rc, output = run_command_streamed(
            command,
            log_path,
            progress,
            event_base,
            timeout_s,
            append=(attempt > 1),
        )
        accumulated_output = (accumulated_output + "\n" + (output or "")) if accumulated_output else (output or "")
        last_output = output or ""

        if rc == 0:
            retry_log.append(f"attempt {attempt}/{max_attempts}: rc=0 (success)")
            _write_wrapper_footer(log_path, retry_log, attempts_used, rc, classification="success")
            return 0, accumulated_output

        # Credential failure → fail fast with the token-prefixed message so the
        # UI's credential prompt fires (``frontend/comsol_credentials.js``
        # matches the lowercased token). / 凭据错误 → 立刻抛出带 token 的异常让前端弹凭据界面
        if is_credential_failure(last_output):
            retry_log.append(f"attempt {attempt}/{max_attempts}: rc={rc}, classification=credential_failure (fail-fast, will not retry)")
            _write_wrapper_footer(log_path, retry_log, attempts_used, rc, classification="credential_failure")
            raise RuntimeError(CREDENTIALS_REQUIRED_MESSAGE)

        if attempt >= max_attempts:
            retry_log.append(f"attempt {attempt}/{max_attempts}: rc={rc} (max attempts reached)")
            break

        is_transient = is_likely_mphserver_problem(last_output, rc)
        if not is_transient:
            # Hard MATLAB / model error — retry won't help. /
            # 模型/语法等硬错误，重试无效
            retry_log.append(f"attempt {attempt}/{max_attempts}: rc={rc}, classification=hard_error (will not retry)")
            break

        startup_runtime_failure = is_likely_matlab_startup_runtime_failure(last_output)
        retry_log.append(f"attempt {attempt}/{max_attempts}: rc={rc}, classification=transient (retrying)")

        try:
            if startup_runtime_failure:
                _cleanup_stale_windows_matlab_runtime(log_path)
                _emit_retry(
                    progress, event_base,
                    f"{label}: attempt {attempt}/{max_attempts} failed during MATLAB startup (rc={rc}); "
                    f"cleaning MATLAB runtime environment and retrying. "
                    f"/ 第 {attempt}/{max_attempts} 次在 MATLAB 启动阶段失败 (rc={rc})，清理 MATLAB runtime 环境后重试。",
                    log_path,
                )
                retry_log.append("  recovery=clean_windows_matlab_runtime_env")
            elif attempt == 1 and max_attempts > 2:
                # Cheap recovery: just make sure the server is up. /
                # 先做便宜的恢复：确保 server 还活着
                _emit_retry(
                    progress, event_base,
                    f"{label}: attempt {attempt}/{max_attempts} failed (rc={rc}); ensuring mphserver and retrying. "
                    f"/ 第 {attempt}/{max_attempts} 次失败 (rc={rc})，确保 mphserver 在并重试。",
                    log_path,
                )
                ensure_comsol_server(runtime_config, wait_s=server_wait_s)
                retry_log.append("  recovery=ensure_comsol_server")
            else:
                # Stronger recovery: kill any stale listener and start fresh. /
                # 更狠的恢复：杀掉端口上的旧 mphserver 再起新的
                _emit_retry(
                    progress, event_base,
                    f"{label}: attempt {attempt}/{max_attempts} failed (rc={rc}); hard-resetting mphserver and retrying. "
                    f"/ 第 {attempt}/{max_attempts} 次失败 (rc={rc})，硬重置 mphserver 并重试。",
                    log_path,
                )
                reset_mphserver(runtime_config, wait_s=server_wait_s)
                retry_log.append("  recovery=reset_mphserver (kill + restart)")
        except Exception as exc:
            # Recovery itself failed — surface the original MATLAB error to the caller. /
            # 连恢复都挂了就不再重试，让外层把原始 MATLAB 错误抛上去
            _emit_retry(progress, event_base, f"server recovery raised: {exc}", log_path)
            retry_log.append(f"  recovery RAISED: {exc} (will not retry)")
            break

        time.sleep(2.0)  # 给 mphserver 一点缓冲再发下一发 / Give mphserver a brief warm-up before re-firing

    # Final guard: if a credential failure only showed up after a retry, still surface it cleanly. /
    # 兜底：某次重试后才露出凭据错误也照样抛 token 异常
    if rc != 0 and is_credential_failure(last_output):
        _write_wrapper_footer(log_path, retry_log, attempts_used, rc, classification="credential_failure")
        raise RuntimeError(CREDENTIALS_REQUIRED_MESSAGE)

    _write_wrapper_footer(log_path, retry_log, attempts_used, rc, classification="exhausted" if rc != 0 else "success")
    return rc, accumulated_output


def _write_wrapper_footer(log_path: Path, retry_log: list[str], attempts: int, final_rc: int, classification: str) -> None:
    """Append a clearly labeled summary block to the MATLAB log so a user
    inspecting ``livelink_*.log`` can immediately see how many attempts the
    wrapper made and what the final classification was."""
    try:
        with log_path.open("a", encoding="utf-8") as file_obj:
            file_obj.write("\n=== mphserver-retry wrapper summary / 重试封装总结 ===\n")
            file_obj.write(f"attempts_used={attempts}\n")
            file_obj.write(f"final_returncode={final_rc}\n")
            file_obj.write(f"classification={classification}\n")
            for line in retry_log:
                file_obj.write(line + "\n")
            file_obj.write("======================================================\n")
    except OSError:
        pass


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
    # 统一走带 mphserver 重置 + 凭据 fail-fast 的 retry wrapper / Route through the unified wrapper (mphserver reset + credential fail-fast)
    returncode, _output = run_matlab_with_mphserver_retry(
        command, log_path, runtime_config,
        label=f"LiveLink eigenfreq ({candidate_id})",
        timeout_s=timeout_s,
        progress=progress,
        event_base={"current_candidate": candidate_id},
    )
    if returncode != 0:
        raise RuntimeError(f"LiveLink simulation failed for {candidate_id}. See {log_path}. / {candidate_id} 的 LiveLink 仿真失败，见 {log_path}。")
    return {"candidate_id": candidate_id, "export_dir": str(export_dir), "num_modes": modes, "returncode": returncode, "log_path": str(log_path)}


def run_livelink_forced_response(config: dict, candidate_id: str, model_path: str | Path | None = None, matlab_path: str | Path | None = None, runner_path: str | Path | None = None, progress=None) -> dict:  # 运行强迫响应 LiveLink 验证 / Run forced-response LiveLink validation
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)  # 应用运行时发现路径 / Apply runtime-discovered paths
    ensure_comsol_credentials(runtime_config)  # 确保 COMSOL 凭据可用 / Ensure COMSOL credentials are available
    apply_comsol_server_environment(runtime_config)  # 设置 COMSOL server 环境变量 / Set COMSOL server environment variables
    if not ensure_comsol_server(runtime_config):  # 检查 COMSOL server 可连接 / Check COMSOL server reachability
        raise RuntimeError("COMSOL server is not reachable. / COMSOL server 无法连接。")  # 抛出 server 错误 / Raise server error
    candidate_dir = resolve_candidate_dir(runtime_config, candidate_id)  # 解析候选目录 / Resolve candidate directory
    ensure_comsol_parameters(candidate_dir, runtime_config.get("material"))  # 确保参数合同已导出 / Ensure parameter contracts are exported
    comsol_config = runtime_config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL configuration
    model = Path(model_path or comsol_config.get("model_path", "comsol_templates/Chladni_15x15_bound.mph"))  # 解析模型路径 / Resolve model path
    matlab = str(matlab_path or comsol_config.get("matlab_path", DEFAULT_MATLAB_PATH))  # 解析 MATLAB 路径 / Resolve MATLAB path
    runner = Path(runner_path or comsol_config.get("forced_response_runner_path", DEFAULT_FORCED_RUNNER_PATH))  # 解析强迫响应 runner / Resolve forced-response runner
    export_root = Path(runtime_config["paths"]["comsol_exports_dir"])  # 读取导出根目录 / Read export root directory
    export_dir = export_root / candidate_id / "forced_response"  # 构造强迫响应导出目录 / Build forced-response export directory
    export_dir.mkdir(parents=True, exist_ok=True)  # 创建导出目录 / Create export directory
    mli_path = matlab_path_from_comsol_command(comsol_config.get("comsol_command_path", ""))  # 查找 COMSOL MLI 路径 / Find COMSOL MLI path
    batch = build_forced_matlab_batch(model, candidate_dir, export_dir, runner, mli_path)  # 构造 MATLAB batch / Build MATLAB batch
    command = [matlab, "-nosplash", "-noFigureWindows", "-sd", str(Path.cwd()), "-batch", batch]  # 构造 MATLAB 命令 / Build MATLAB command
    log_path = export_dir / "livelink_forced_response.log"  # 构造日志路径 / Build log path
    timeout_s = float(comsol_config.get("livelink_timeout_s", 7200))  # 读取 LiveLink 超时 / Read LiveLink timeout
    event_base = {"current_candidate": candidate_id, "simulation_type": "forced_response"}  # 构造进度基础字段 / Build progress base fields
    # 统一走带 mphserver 重置 + 凭据 fail-fast 的 retry wrapper / Route through the unified wrapper (mphserver reset + credential fail-fast)
    returncode, _output = run_matlab_with_mphserver_retry(
        command, log_path, runtime_config,
        label=f"LiveLink forced-response ({candidate_id})",
        timeout_s=timeout_s,
        progress=progress,
        event_base=event_base,
    )
    if returncode != 0:
        raise RuntimeError(f"Forced-response LiveLink simulation failed for {candidate_id}. See {log_path}. / {candidate_id} 的强迫响应 LiveLink 仿真失败，见 {log_path}。")
    response_path = export_dir / "forced_response.csv"  # 构造响应文件路径 / Build response file path
    return {"candidate_id": candidate_id, "export_dir": str(export_dir), "response_path": str(response_path), "returncode": returncode, "log_path": str(log_path)}


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
    # 统一走带 mphserver 重置 + 凭据 fail-fast 的 retry wrapper / Route through the unified wrapper
    returncode, _output = run_matlab_with_mphserver_retry(
        command, log_path, runtime_config,
        label=f"LiveLink batch ({len(selected_ids)} candidates)",
        timeout_s=timeout_s,
    )
    if returncode != 0:
        raise RuntimeError(f"LiveLink batch simulation failed. See {log_path}. / LiveLink 批量仿真失败，见 {log_path}。")
    for result in results:
        result["returncode"] = returncode
        result["log_path"] = str(log_path)
    return results
