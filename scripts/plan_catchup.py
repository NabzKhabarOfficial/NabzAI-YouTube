"""Top up the Persian reel banks from the story batches, then plan the nights still ahead.

Nov 18 2026, two holes made the daily Reel stop without a single red run:

1. A story batch carries its Persian text and fact notes inline (``mysteries_batchNN.json`` has
   ``fa`` and ``notes`` in every row), but nothing copied them into ``mysteries_fa.json`` and
   ``story_notes_fa.json``. ``ig_pack`` plans only stories that exist in BOTH files, so four days
   of runs planned nothing: the bank held 112 stories and every one of the 39 unused ones had no
   English entry, i.e. "only 0 unused Persian stories" and a green run in 0.3 seconds.
2. A week that never got a plan stayed empty for ever: ``pick_week`` only ever returns the next
   Monday, so after a short bank the current week is never filled and its nights pass silently.

This script is idempotent and cheap (no quota, no network):
- it copies inline batch text into the banks only where a story is missing;
- it plans the current week when that week has no plan yet, keeping only the nights that are
  still ahead, so the pack builds tonight's reel instead of one with a due date in the past.

Once the pack itself catches up an unplanned week (src/ig_pack.choose_week), step two is a no-op.
Exit 0 when the banks are complete and the current week has a plan, 1 when the bank is too small.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
sys.path.insert(0, str(ROOT))

from src import ig_pack as pack  # noqa: E402

NOTES = CONTENT / "story_notes_fa.json"
FA = CONTENT / "mysteries_fa.json"
NOTE_LABELS = ("ثابت", "محتمل", "نامعلوم")


def read(path: Path, default: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return value if isinstance(value, dict) else default


def good_fa(value) -> bool:
    """A Persian story that can be spoken: a title and at least one beat."""
    return (isinstance(value, dict)
            and str(value.get("title", "")).strip() not in ("", "placeholder")
            and bool(value.get("beats")))


def notes_from_row(row: dict) -> list[str] | None:
    """A batch row's proven/probable/unknown notes as the bank's three Persian lines."""
    notes = row.get("notes")
    if not isinstance(notes, dict) or not {"proven", "probable", "unknown"} <= set(notes):
        return None
    lines = [f"{label}: {str(notes[key]).strip()}"
             for label, key in zip(NOTE_LABELS, ("proven", "probable", "unknown"))]
    return lines if all(line.split(":", 1)[-1].strip() for line in lines) else None


def merge_inline_batch_text() -> int:
    """Copy every batch story's inline Persian text and notes into the banks. Returns how many."""
    fa = read(FA, {}).setdefault("stories", {})
    notes = read(NOTES, {}).setdefault("stories", {})
    added = 0

    for path in sorted(CONTENT.glob("mysteries_batch*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        for row in rows if isinstance(rows, list) else []:
            sid = str(row.get("id") or "").strip()
            if not sid:
                continue
            if sid not in fa and good_fa(row.get("fa")):
                fa[sid] = row["fa"]
                added += 1
            row_notes = notes_from_row(row)
            if sid not in notes and row_notes:
                notes[sid] = row_notes

    # Older batches were split into separate add files; the same "only where missing" rule keeps
    # the bank byte-identical when there is nothing new.
    for path in sorted(CONTENT.glob("mysteries_fa_add*.json")) + sorted(CONTENT.glob("mysteries_fa_batch*.json")):
        for sid, value in (read(path, {}).get("stories") or {}).items():
            if str(sid) not in fa and good_fa(value):
                fa[str(sid)] = value
                added += 1
    for path in sorted(CONTENT.glob("story_notes_fa_add*.json")):
        for sid, value in (read(path, {}).get("stories") or {}).items():
            if str(sid) not in notes and isinstance(value, list) and len(value) == 3:
                notes[str(sid)] = value

    if not added:
        return 0

    # Same one-line-per-story layout ig_pack._fa_text writes, so a merge that adds nothing leaves
    # the file byte-identical and the two writers never fight over formatting.
    FA.write_text(pack._fa_text(fa), encoding="utf-8")
    NOTES.write_text(json.dumps({"stories": notes}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return added


def plan_remaining_nights() -> int:
    """Plan this week's nights that are still ahead, when the week was never planned at all."""
    state = pack.load_json(pack.STATE_FILE, {})
    today = pack.now_tehran().date()
    monday = today - timedelta(days=today.weekday())
    key = monday.isoformat()
    info = (state.get("weeks") or {}).get(key) or {}
    if info.get("done"):
        print(f"week {key} is complete; nothing to plan")
        return 0
    if info.get("plan"):
        print(f"week {key} already planned ({len(info['plan'])} reels); nothing to plan")
        return 0

    per_day = max(1, min(int(os.getenv("NABZ_PACK_PER_DAY", "1") or 1), 3))
    rf, _, _, _ = pack._modules()
    fa_bank = rf.load_fa()
    en = pack.load_english_bank()
    if pack.plan_week(state, monday, per_day, fa_bank, set(en), allow_partial=True) is None:
        print("::error title=No plan::the Persian bank has fewer than 7 ready stories, so week "
              f"{key} cannot be planned. Write the next story batch (content/mysteries_batchNN.json "
              "with fa + notes in every row).", flush=True)
        return 1

    # plan_week fills the whole Monday..Sunday grid; a catch-up may only use the nights ahead.
    state = pack.load_json(pack.STATE_FILE, {})
    week = state["weeks"][key]
    nights = [item for item in week["plan"] if date.fromisoformat(item["date"]) >= today]
    for n, item in enumerate(nights, 1):
        item["n"] = n
    keep = {item["id"] for item in nights}
    week["plan"] = nights
    week["built"] = {sid: value for sid, value in (week.get("built") or {}).items() if sid in keep}
    week.pop("done", None)
    pack.save_state(state)
    print(f"week {key}: planned {len(nights)} reels for the nights still ahead "
          f"({nights[0]['date']} .. {nights[-1]['date']})")
    return 0


def main() -> int:
    added = merge_inline_batch_text()
    if added:
        print(f"banks: +{added} batch stories with their Persian text")
    return plan_remaining_nights()


if __name__ == "__main__":
    raise SystemExit(main())
