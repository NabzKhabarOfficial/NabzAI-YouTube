"""Merge the new story batches into the banks that src.ig_pack reads.

Why: ig_pack only reads content/story_notes_fa.json (approval notes) and content/mysteries_fa.json
(Persian text). The batch files written after Oct 26 (story_notes_fa_add*.json and
mysteries_fa_add_batch2.json, mysteries_fa_batch2.json) were never merged, so the pack saw zero
ready stories for the week of Nov 2 2026.

Usage (from the repo root):
    python scripts/merge_story_batches.py          # dry run: prints what would change
    python scripts/merge_story_batches.py --apply  # writes the merged banks

Rules: an existing entry is never overwritten; a new entry with an empty or 'placeholder' title is
skipped; a note list must have at least 3 items. The script prints how many approved stories now
have both Persian text and an English bank entry, which is what the pack needs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

NOTES = CONTENT / "story_notes_fa.json"
NOTES_ADDS = [CONTENT / "story_notes_fa_add.json", CONTENT / "story_notes_fa_add_batch2.json"]
FA = CONTENT / "mysteries_fa.json"
FA_ADDS = [CONTENT / "mysteries_fa_add_batch2.json", CONTENT / "mysteries_fa_batch2.json"]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def stories_of(data: dict) -> dict:
    value = data.get("stories")
    return value if isinstance(value, dict) else {}


def good_note(value) -> bool:
    return isinstance(value, list) and len([x for x in value if str(x).strip()]) >= 3


def good_fa(value) -> bool:
    return isinstance(value, dict) and str(value.get("title", "")).strip() not in ("", "placeholder")


def english_ids() -> set:
    ids: set = set()
    for path in sorted(CONTENT.glob("mysteries*.json")):
        if path.name.endswith("_fa.json") or "_fa_" in path.name or "_fa" in path.stem:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = data if isinstance(data, list) else (data.get("stories") or data.get("items") or [])
        if isinstance(items, dict):
            ids.update(str(k) for k in items)
        elif isinstance(items, list):
            ids.update(str(x.get("id")) for x in items if isinstance(x, dict) and x.get("id"))
    return ids


def main() -> int:
    apply = "--apply" in sys.argv
    notes = load(NOTES)
    note_stories = stories_of(notes)
    added_notes, skipped_notes = 0, 0
    for path in NOTES_ADDS:
        if not path.exists():
            continue
        for sid, value in stories_of(load(path)).items():
            if sid in note_stories:
                continue
            if good_note(value):
                note_stories[sid] = value
                added_notes += 1
            else:
                skipped_notes += 1

    fa = load(FA)
    fa_stories = stories_of(fa)
    added_fa, skipped_fa = 0, 0
    for path in FA_ADDS:
        if not path.exists():
            continue
        for sid, value in stories_of(load(path)).items():
            if sid in fa_stories:
                continue
            if good_fa(value):
                fa_stories[sid] = value
                added_fa += 1
            else:
                skipped_fa += 1

    en = english_ids()
    ready = [sid for sid in note_stories if sid in fa_stories and sid in en]
    print(f"notes: +{added_notes} (skipped {skipped_notes}) -> {len(note_stories)} stories")
    print(f"persian text: +{added_fa} (skipped {skipped_fa}) -> {len(fa_stories)} stories")
    print(f"approved with Persian text and English entry: {len(ready)}")

    if not apply:
        print("dry run: nothing written. Run with --apply to write.")
        return 0

    notes["stories"] = note_stories
    fa["stories"] = fa_stories
    NOTES.write_text(json.dumps(notes, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    FA.write_text(json.dumps(fa, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
