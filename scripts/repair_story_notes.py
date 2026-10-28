"""Repair only truncated outer story-notes JSON objects."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "content" / "story_notes_fa.json"


def _load_valid(raw: str):
    data = json.loads(raw)
    stories = data.get("stories")
    if not isinstance(stories, dict) or not stories:
        raise ValueError("story notes must contain a non-empty stories object")
    return data


def _repair_truncated_outer_object(raw: str) -> str:
    text = raw.rstrip()
    for count in range(1, 4):
        candidate = text + ("\n" + "}" * count) + "\n"
        try:
            _load_valid(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            continue
    raise json.JSONDecodeError(
        "story notes JSON is malformed and is not a truncated outer object",
        text,
        len(text),
    )


def main() -> int:
    raw = PATH.read_text(encoding="utf-8")
    try:
        data = _load_valid(raw)
    except json.JSONDecodeError:
        repaired = _repair_truncated_outer_object(raw)
        data = _load_valid(repaired)
        PATH.write_text(repaired, encoding="utf-8")
    print(f"story notes valid: {len(data['stories'])} stories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
