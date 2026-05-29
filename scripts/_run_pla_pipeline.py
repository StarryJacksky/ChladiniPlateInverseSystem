"""Run the production pipeline with isotropic FDM PLA material params,
then restore config.yaml.  Side-by-side comparison vs the current CF-PETG
baseline at reports/production/production_design/.

Material override (school FDM PLA):
  density_kg_m3    : 1300 → 1240
  youngs_modulus_pa: 3.7e9 → 3.5e9
  poisson_ratio    : 0.38  → 0.36
  (production.stiffness_ratio / shear_ratio are passed via CLI flags below.)

Pipeline overrides:
  --stiffness-ratio 1.0   (isotropic)
  --shear-ratio 1.0
  --magic-off-resonance-hz ""   (165 Hz is tier1 empirical; meaningless for iso)
  --output-dir reports/production_pla
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PROJECT_ROOT / "config.yaml"
BACKUP = PROJECT_ROOT / "config.yaml.bak_pla_run"


def patch_material(text: str) -> str:
    text = re.sub(r"^(\s*density_kg_m3:\s*)\d+(\.\d+)?", r"\g<1>1240", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^(\s*youngs_modulus_pa:\s*)[\d.eE+\-]+", r"\g<1>3500000000", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^(\s*poisson_ratio:\s*)[\d.]+", r"\g<1>0.36", text, count=1, flags=re.MULTILINE)
    return text


def main() -> int:
    if BACKUP.exists():
        print(f"[abort] backup file already exists: {BACKUP} — refusing to overwrite. Inspect & remove first.")
        return 2

    shutil.copy(CONFIG, BACKUP)
    print(f"[backup] {CONFIG} → {BACKUP}")

    try:
        original = CONFIG.read_text()
        patched = patch_material(original)
        if patched == original:
            print("[abort] patch did not modify config.yaml material section; aborting.")
            return 3
        CONFIG.write_text(patched)
        print("[patched] material → PLA (ρ=1240, E=3.5 GPa, ν=0.36)")
        # echo diff for sanity
        for tag in ("density_kg_m3", "youngs_modulus_pa", "poisson_ratio"):
            for line in patched.splitlines():
                if tag + ":" in line and line.lstrip().startswith(tag):
                    print(f"    {line.strip()}")
                    break

        cmd = [
            ".venv/bin/python", "-u", "scripts/run_production_pipeline.py",
            "--candidate-id", "production_design",
            "--output-dir", "reports/production_pla",
            "--stiffness-ratio", "1.0",
            "--shear-ratio", "1.0",
            "--magic-off-resonance-hz", "",
        ]
        print(f"[run] {' '.join(cmd)}")
        t0 = time.time()
        rc = subprocess.call(cmd, cwd=str(PROJECT_ROOT))
        print(f"[done] pipeline rc={rc}, wall={time.time()-t0:.1f}s")
        return rc
    finally:
        shutil.copy(BACKUP, CONFIG)
        BACKUP.unlink()
        print(f"[restore] {CONFIG} restored from backup; backup removed.")


if __name__ == "__main__":
    raise SystemExit(main())
