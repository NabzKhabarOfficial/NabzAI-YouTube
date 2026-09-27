from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORIES_PATH = ROOT / "config" / "story_templates.json"


def _slot() -> int:
    raw = os.getenv("NABZ_STORY_SLOT", "")
    if raw.isdigit():
        return int(raw) % 10
    day = datetime.now(timezone.utc).timetuple().tm_yday
    hour = datetime.now(timezone.utc).hour
    return ((day * 12) + (hour // 2)) % 10


def load_story(slot: int | None = None) -> dict:
    templates = json.loads(STORIES_PATH.read_text(encoding="utf-8"))
    index = _slot() if slot is None else slot % len(templates)
    story = templates[index]
    story["slot"] = index
    return story


if __name__ == "__main__":
    print(json.dumps(load_story(), ensure_ascii=False, indent=2))
