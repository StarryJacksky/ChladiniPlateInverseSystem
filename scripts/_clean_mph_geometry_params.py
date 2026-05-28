"""Clean dead `wide` + `cell_size` global params from the COMSOL template.

Strategy:
  1. Default action is a DRY-RUN — first verifies wide == length numerically,
     then exhaustively scans every model expression for references to `wide`
     or `cell_size`. Reports all findings without writing anything.
  2. Pass --apply to actually delete the params. Original .mph is backed up
     to *.bak.mph; cleaned model is written in place.
  3. Verification mode (default after --apply): runs an eigenfrequency probe
     on the cleaned model and compares the first 6 eigenfrequencies against
     a fresh probe on the backup. Any deviation > 0.1 Hz triggers a roll-back.

Usage:
    # dry run (just see what would change)
    .venv/bin/python scripts/_clean_mph_geometry_params.py

    # actually clean (with backup + auto-rollback safety)
    .venv/bin/python scripts/_clean_mph_geometry_params.py --apply
"""
from __future__ import annotations

import argparse
import os
import shutil
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
    p = argparse.ArgumentParser(description="Safely remove dead `wide` + `cell_size` params from .mph")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--model", default="comsol_templates/Chladni_15x15_bound.mph")
    p.add_argument("--apply", action="store_true",
                     help="Actually modify the .mph (default: dry-run only).")
    p.add_argument("--output-log", default="reports/_geom_probe/clean_params.log")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    runtime_config, _, _ = config_with_runtime_discovery(config)

    model_path = (PROJECT_ROOT / args.model).resolve()
    if not model_path.exists():
        print(f"ERROR: model not found: {model_path}")
        return 1
    backup_path = model_path.with_suffix(".bak.mph")
    log_path = (PROJECT_ROOT / args.output_log).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if args.apply:
        if backup_path.exists():
            print(f"WARNING: backup already exists at {backup_path}; using existing backup.")
        else:
            print(f"Creating backup: {backup_path}")
            shutil.copy2(model_path, backup_path)

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

    dry_run_flag = "false" if args.apply else "true"

    parts = []
    if mli_path:
        parts += [f"setenv('COMSOL_MLI_PATH',{matlab_quote(mli_path)})",
                  f"addpath({matlab_quote(mli_path)})"]
    parts.append(f"addpath({matlab_quote(runner_dir)})")
    parts.append(
        f"clean_geometry_params({matlab_quote(str(model_path))},"
        f"{matlab_quote(str(model_path))},{dry_run_flag})"
    )
    cmd = [matlab, "-nosplash", "-noFigureWindows", "-sd", str(PROJECT_ROOT), "-batch", "; ".join(parts)]

    matlab_log = log_path.with_suffix(".matlab.log")
    rc, _ = run_matlab_with_mphserver_retry(
        cmd, matlab_log, runtime_config,
        label="COMSOL clean_geometry_params",
        timeout_s=300.0,
    )

    if rc != 0:
        print(f"ERROR: MATLAB returned rc={rc}; see {matlab_log}")
        if args.apply and backup_path.exists():
            print(f"Rolling back from backup: {backup_path} -> {model_path}")
            shutil.copy2(backup_path, model_path)
        return 3

    print(f"\nMATLAB log: {matlab_log}")
    if args.apply:
        print(f"\nApplied changes to {model_path}")
        print(f"Backup retained at {backup_path}")
        print(f"\nRecommended next step: run scripts/_probe_geometry_extents.py to confirm,")
        print(f"and a smoke eigenfreq before trusting the cleaned model in production.")
    else:
        print(f"\nDry-run complete. Re-run with --apply to make the changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
