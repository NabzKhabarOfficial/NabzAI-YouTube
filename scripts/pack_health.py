"""Fail the pack run when it built nothing and nothing is queued.

Nov 17 2026: a manual run finished green while `Build the weekly pack` returned in under a second
(the bank held 3 ready stories), the Buffer gate correctly found no work, and no reel was created —
so the day passed silently and only Buffer showed the gap. This check turns that state into a red
run with one sentence that says what is missing.

Healthy means either:
- at least one reel was built today (Tehran), or
- a reel is already scheduled/sent with a due time in the next 36 hours.

Exit: 0 healthy, 1 nothing built and nothing queued.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "content" / "ig_pack_state.json"
BUFFER = ROOT / "content" / "ig_buffer_state.json"
TEHRAN = timezone(timedelta(hours=3, minutes=30))
HORIZON_HOURS = 36


def read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def built_today(pack: dict, now: datetime) -> list[str]:
    today = now.astimezone(TEHRAN).date().isoformat()
    out = []
    for info in (pack.get("weeks") or {}).values():
        if not isinstance(info, dict):
            continue
        built = info.get("built") or {}
        for item in info.get("plan") or []:
            record = built.get(item.get("id"))
            if not isinstance(record, dict):
                continue
            at = str(record.get("at") or "")
            if at.startswith(today):
                out.append(str(item.get("id")))
    return out


def queued(buffer_state: dict, now: datetime) -> list[tuple[str, datetime]]:
    out = []
    for key, record in (buffer_state.get("sent") or {}).items():
        if not isinstance(record, dict) or record.get("status") not in ("scheduled", "sent"):
            continue
        try:
            due = datetime.fromisoformat(str(record.get("due")))
        except ValueError:
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=TEHRAN)
        if now - timedelta(hours=2) <= due <= now + timedelta(hours=HORIZON_HOURS):
            out.append((key, due))
    return sorted(out, key=lambda pair: pair[1])


def main() -> int:
    now = datetime.now(timezone.utc)
    pack = read(PACK)
    buffer_state = read(BUFFER)
    built = built_today(pack, now)
    waiting = queued(buffer_state, now)
    print(f"pack health: built today {len(built)}, queued in {HORIZON_HOURS}h {len(waiting)}")
    if built or waiting:
        for key, due in waiting[:3]:
            print(f"  queued: {key} at {due.astimezone(TEHRAN).isoformat(timespec='minutes')}")
        return 0
    print("::error title=No reel today and none queued::the pack built nothing and Buffer has no "
          "reel due in the next 36 hours. Check the pack log (bank too small, quota, voice) and the "
          "Buffer gate; this run must not pass silently.", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
