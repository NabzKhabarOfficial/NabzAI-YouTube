"""Dependency-free gate for the Buffer part of ig-pack.yml.

The Buffer job runs only when there is work for it. Work means:
- built reels not present in the local Buffer sent-state (new posts);
- built carousels inside CAR_AHEAD_DAYS that are not sent yet;
- evening stories whose source reel is scheduled/sent and whose story is not recorded yet;
- upkeep: a scheduled reel whose video was rebuilt after it was queued (audio_v newer);
- upkeep: a post recorded as 'error' (Buffer could not publish it);
- upkeep: today's stats have not been collected yet (ig_stats.json 'collected');
- upkeep: the Monday weekly report for this week has not been sent (report_week).

Not covered by the gate (they run on any job that does run): caption refresh of waiting posts,
replacement of rebuilt videos, and stories remade in a newer design. Those need the caption
bank, so the gate does not try to reproduce them.

On an unreadable state file the script exits non-zero without writing run=false, and the
workflow step uses continue-on-error, so downstream steps fail open.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "content" / "ig_pack_state.json"
BUFFER = ROOT / "content" / "ig_buffer_state.json"
STATS = ROOT / "content" / "ig_stats.json"
TEHRAN = timezone(timedelta(hours=3, minutes=30))
LEAD_MIN = 30
STORY_AFTER_MIN = 15
STORY_FROM_HOUR = 17
STORY_MAX_AGE_HOURS = 2
CAR_AHEAD_DAYS = int(os.getenv("NABZ_CAROUSEL_AHEAD_DAYS", "4"))
STORIES = os.getenv("NABZ_STORIES", "1") != "0"


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def reel_stem(item: dict) -> str:
    if item.get("file"):
        return str(item["file"])
    return f"{int(item['n']):02d}_{item['date']}_{str(item['time']).replace(':', '')}_{item['id']}"


def built_reels(pack: dict) -> dict[str, dict]:
    result = {}
    for week, info in sorted((pack.get("weeks") or {}).items()):
        if not isinstance(info, dict):
            continue
        built = info.get("built") or {}
        for item in info.get("plan") or []:
            if item.get("id") in built:
                stem = reel_stem(item)
                result[stem] = {
                    **item,
                    "stem": stem,
                    "week": week,
                    "audio_v": int((built[item["id"]] or {}).get("audio_v", 1)),
                }
    return result


def due_at(item: dict) -> datetime:
    return datetime.fromisoformat(f"{item['date']}T{item['time']}:00").replace(tzinfo=TEHRAN)


def upkeep(pack: dict, buffer_state: dict, stats: dict, now: datetime, reels: dict) -> tuple[bool, str]:
    sent = buffer_state.get("sent") or {}
    for key, rec in sent.items():
        if not isinstance(rec, dict):
            continue
        if rec.get("status") == "error":
            return True, f"Buffer reported an error for {key}"
        if rec.get("status") == "scheduled" and key in reels:
            if int(reels[key].get("audio_v", 1)) > int(rec.get("audio_v", 1)):
                return True, f"video rebuilt after queueing: {key}"
    if stats.get("collected") != now.astimezone(TEHRAN).date().isoformat():
        return True, "today's stats not collected yet"
    local = now.astimezone(TEHRAN)
    if local.weekday() == 0:
        monday = (local.date()).isoformat()
        if buffer_state.get("report_week") != monday:
            return True, "Monday report not sent yet"
    return False, ""


def has_eligible_item(pack: dict, buffer_state: dict, now: datetime, stats: dict | None = None) -> tuple[bool, str]:
    sent = buffer_state.get("sent") or {}
    if not isinstance(sent, dict):
        raise ValueError("content/ig_buffer_state.json: sent must be an object")

    reels = built_reels(pack)

    # Same rule as ig_buffer.waiting_list(): any built reel not yet in sent-state.
    for stem in reels:
        if stem not in sent:
            return True, f"unsent built reel: {stem}"

    # Match built_carousels() and the four-day queue horizon in ig_buffer.py.
    ahead = now + timedelta(days=CAR_AHEAD_DAYS)
    carousels = ((pack.get("carousels") or {}).get("plan") or [])
    for item in carousels:
        if not item.get("slides"):
            continue
        stem = f"car_{item['id']}"
        if stem not in sent and due_at(item) <= ahead:
            return True, f"unsent built carousel: {stem}"

    # Match story_items() plus waiting_list()'s 30-minute lead-time filter.
    if STORIES:
        lead = now + timedelta(minutes=LEAD_MIN)
        oldest = now - timedelta(hours=STORY_MAX_AGE_HOURS)
        for key, rec in sent.items():
            if (
                rec.get("kind", "reel") != "reel"
                or rec.get("status") not in ("scheduled", "sent")
                or key not in reels
            ):
                continue
            story_stem = f"{key}_story"
            if story_stem in sent:
                continue
            story_due = datetime.fromisoformat(rec["due"]) + timedelta(minutes=STORY_AFTER_MIN)
            if story_due.astimezone(TEHRAN).hour < STORY_FROM_HOUR:
                continue
            if story_due < oldest or story_due < lead:
                continue
            return True, f"unsent story: {story_stem}"

    ok, why = upkeep(pack, buffer_state, stats or {}, now, reels)
    if ok:
        return True, why

    return False, "no eligible built reels, carousels, stories, or upkeep"


def main() -> int:
    pack = read_json(PACK)
    buffer_state = read_json(BUFFER)
    stats = read_json(STATS)
    now = datetime.now(timezone.utc)
    should_run, reason = has_eligible_item(pack, buffer_state, now, stats)
    print(f"Buffer gate: {'run' if should_run else 'skip'} - {reason}")
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"run={'true' if should_run else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
