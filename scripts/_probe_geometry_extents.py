"""Probe .mph geometry primitives + workplane sketch sizes.

Diagnoses the "shell looks 15x15 but workplane / result display shows 10x10"
discrepancy by walking every geometry feature in the COMSOL template, dumping
its size / position parameters, and reporting the global bounding box for
each geometry node.

Usage:
    .venv/bin/python scripts/_probe_geometry_extents.py
    .venv/bin/python scripts/_probe_geometry_extents.py \
        --model comsol_templates/Chladni_15x15_bound.mph

The probe is read-only — it does not modify the .mph. /
只读探针：dump 几何尺寸，不修改模型
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))

from src.comsol.credentials import ensure_comsol_credentials
from src.comsol.discovery import config_with_runtime_discovery
from src.comsol.run_livelink import (
    DEFAULT_MATLAB_PATH,
    apply_comsol_server_environment,
    matlab_path_from_comsol_command,
    matlab_quote,
    run_matlab_with_mphserver_retry,
)
from src.comsol.server import ensure_comsol_server
from src.config import load_config


def parse_args():
    p = argparse.ArgumentParser(description="Probe COMSOL .mph geometry / workplane sizes.")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--model", default="comsol_templates/Chladni_15x15_bound.mph",
                     help="Path to the .mph template to probe (default: Chladni_15x15_bound).")
    p.add_argument("--output", default="reports/_geom_probe/geom_probe.log",
                     help="Where the probe writes its diagnostic log.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    runtime_config, _, _ = config_with_runtime_discovery(config)

    model_path = (PROJECT_ROOT / args.model).resolve()
    if not model_path.exists():
        print(f"ERROR: model not found: {model_path}")
        return 1
    output_path = (PROJECT_ROOT / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ensure_comsol_credentials(runtime_config)
    apply_comsol_server_environment(runtime_config)
    if not ensure_comsol_server(runtime_config, wait_s=60.0):
        print("ERROR: COMSOL server is not reachable.")
        return 2
    time.sleep(1.0)

    comsol_config = runtime_config.get("comsol", {})
    matlab = str(comsol_config.get("matlab_path", DEFAULT_MATLAB_PATH))
    runner_dir = (PROJECT_ROOT / "comsol_templates").resolve()
    mli_path = matlab_path_from_comsol_command(comsol_config.get("comsol_command_path", ""))

    parts = []
    if mli_path:
        parts += [f"setenv('COMSOL_MLI_PATH',{matlab_quote(mli_path)})",
                  f"addpath({matlab_quote(mli_path)})"]
    parts.append(f"addpath({matlab_quote(runner_dir)})")
    parts.append(f"probe_geometry_extents({matlab_quote(str(model_path))},{matlab_quote(str(output_path))})")
    cmd = [matlab, "-nosplash", "-noFigureWindows", "-sd", str(PROJECT_ROOT), "-batch", "; ".join(parts)]

    log_file = output_path.with_suffix(".matlab.log")
    rc, _ = run_matlab_with_mphserver_retry(
        cmd, log_file, runtime_config,
        label="COMSOL geometry probe",
        timeout_s=300.0,
    )
    if rc != 0:
        print(f"ERROR: MATLAB returned rc={rc}; see {log_file}")
        return 3

    print()
    print("=" * 80)
    print(f"Geometry probe log: {output_path}")
    print("=" * 80)
    if output_path.exists():
        print(output_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
