"""Cheap first step of ig-pack.yml: is next week's Instagram pack already complete?

Writes skip=true|false to $GITHUB_OUTPUT so a finished week costs no install time.
Loads src/ig_pack.py straight from its file (standard library only, no package import).
"""
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ig_pack_light", ROOT / "src" / "ig_pack.py")
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)

week = pack.target_week(forced=os.getenv("NABZ_PACK_WEEK", "").strip())
state = pack.load_json(pack.STATE_FILE, {})
info = (state.get("weeks") or {}).get(week.isoformat()) or {}
skip = bool(info.get("done"))
print(f"week-{week.isoformat()}: {'complete, skipping' if skip else 'to build'} "
      f"({len(info.get('built', {}))}/{len(info.get('plan', []))} reels ready)")
out = os.getenv("GITHUB_OUTPUT")
if out:
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(f"skip={'true' if skip else 'false'}\n")
