"""Probe COMSOL Orthotropic propertyGroup + Shell physics emm1 API.

Output goes to data/comsol_logs/orthotropic_api_probe.log
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))

from src.comsol.credentials import ensure_comsol_credentials
from src.comsol.discovery import config_with_runtime_discovery
from src.comsol.run_livelink import (
    DEFAULT_MATLAB_PATH,
    apply_comsol_server_environment,
    matlab_path_from_comsol_command,
    matlab_quote,
    run_command_streamed,
)
from src.comsol.server import ensure_comsol_server
from src.config import load_config


def main() -> None:
    config = load_config("config.yaml")
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)
    ensure_comsol_credentials(runtime_config)
    apply_comsol_server_environment(runtime_config)
    if not ensure_comsol_server(runtime_config, wait_s=60.0):
        raise RuntimeError("COMSOL server is not reachable.")
    time.sleep(2.0)

    comsol_config = runtime_config.get("comsol", {})
    matlab = str(comsol_config.get("matlab_path", DEFAULT_MATLAB_PATH))
    model = Path(
        comsol_config.get("model_path", "comsol_templates/Chladni_15x15_bound.mph")
    )
    runner_dir = Path("comsol_templates").resolve()
    output_log = Path("data/comsol_logs/orthotropic_api_probe.log").resolve()
    output_log.parent.mkdir(parents=True, exist_ok=True)
    mli_path = matlab_path_from_comsol_command(comsol_config.get("comsol_command_path", ""))

    parts: list[str] = []
    if mli_path is not None:
        parts.append(f"setenv('COMSOL_MLI_PATH',{matlab_quote(mli_path)})")
        parts.append(f"addpath({matlab_quote(mli_path)})")
    parts.append(f"addpath({matlab_quote(runner_dir)})")
    parts.append(
        f"probe_orthotropic_api({matlab_quote(model.resolve())},{matlab_quote(output_log)})"
    )
    batch = "; ".join(parts)
    command = [matlab, "-nosplash", "-noFigureWindows", "-sd", str(Path.cwd()), "-batch", batch]
    log_path = Path("data/comsol_logs/probe_orthotropic_api_run.log")
    rc, _ = run_command_streamed(command, log_path, timeout_s=1800.0)
    print(f"returncode={rc}; probe_log={output_log}")
    if rc != 0:
        sys.exit(rc)


if __name__ == "__main__":
    main()
