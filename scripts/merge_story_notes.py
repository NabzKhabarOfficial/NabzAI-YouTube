"""Merge approved story notes into the canonical story lock before planning."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "content" / "story_notes_fa.json"
ADD = ROOT / "content" / "story_notes_fa_add.json"

def main() -> int:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    add = json.loads(ADD.read_text(encoding="utf-8")) if ADD.exists() else {"stories": {}}
    stories = base.setdefault("stories", {})
    before = len(stories)
    for sid, notes in (add.get("stories") or {}).items():
        if sid not in stories:
            stories[sid] = notes
    if len(stories) != before:
        BASE.write_text(json.dumps(base, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"story notes ready: {len(stories)} total, {len(stories) - before} added")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
