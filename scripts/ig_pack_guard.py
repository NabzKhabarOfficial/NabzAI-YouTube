"""Cheap first step of ig-pack.yml: should the pack job run at all?

The pack job is skipped when:
- the target week is complete;
- today's YouTube Short is not built yet and no old-voice reel needs an urgent rebuild
  (the Short gets the free quotas first);
- every reel due from today to two days ahead (Tehran dates) is already built, in any planned
  week, so a run would only repeat work. There must be at least one such reel, otherwise the
  pack keeps running.

Writes skip=true|false to $GITHUB_OUTPUT. Loads src/ig_pack.py straight from its file
(standard library only, no package import).
"""
import importlib.util
import os
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ig_pack_light", ROOT / "src" / "ig_pack.py")
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)

LOOKAHEAD_DAYS = 2

state = pack.load_json(pack.STATE_FILE, {})
week = pack.pick_week(state, os.getenv("NABZ_PACK_WEEK", "").strip())
info = (state.get("weeks") or {}).get(week.isoformat()) or {}
urgent = pack.urgent_redo(state) if pack.youtube_first() else []

today = pack.now_tehran().date()
end = today + timedelta(days=LOOKAHEAD_DAYS)

covered_items = 0
covered = True
for wk_info in (state.get("weeks") or {}).values():
    built = wk_info.get("built") or {}
    for item in wk_info.get("plan") or []:
        d = pack.date.fromisoformat(item["date"])
        if today <= d <= end:
            covered_items += 1
            if item["id"] not in built:
                covered = False
if covered_items == 0:
    covered = False

skip_done = bool(info.get("done"))
skip_short = pack.youtube_first() and not urgent
skip_covered = covered
skip = skip_done or skip_short or skip_covered

if skip_done:
    reason = f"week-{week.isoformat()} is complete"
elif skip_short:
    print("today's YouTube Short is not built yet: it gets the free quotas first")
    reason = "waiting for the Short"
elif skip_covered:
    reason = f"all {covered_items} reels due {today.isoformat()}..{end.isoformat()} are built"
else:
    reason = f"reels still to build for {today.isoformat()}..{end.isoformat()}"

print(f"week-{week.isoformat()}: {'skipping' if skip else 'to build'} ({reason}; "
      f"{len(info.get('built', {}))}/{len(info.get('plan', []))} reels ready)")
out = os.getenv("GITHUB_OUTPUT")
if out:
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(f"skip={'true' if skip else 'false'}\n")
