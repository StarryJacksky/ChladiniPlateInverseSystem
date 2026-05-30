"""One-shot back-fill: add centre_participation to every existing tier.
后端代码已更新但还没重启时，旧服务器在 Generate 时会写出不带 centre_participation 的 catalogue.json。
这个脚本把所有 data/uniform_catalogue/<tier_id>/catalogue.json 用最新规则补齐字段。
"""
from __future__ import annotations
import sys
sys.path.insert(0, ".")
from pathlib import Path
from src.config import load_config
from src.uniform_pattern.catalogue import backfill_centre_participation, catalogue_default_dir

cfg = load_config("config.yaml")
base = Path(catalogue_default_dir(cfg))
tiers = [d for d in base.iterdir() if d.is_dir()]
print(f"scanning {len(tiers)} tier(s) under {base}")
for tdir in tiers:
    changed = backfill_centre_participation(tdir)
    print(f"  {tdir.name:<14} {'BACK-FILLED' if changed else 'already populated / no entries'}")
print("done")
