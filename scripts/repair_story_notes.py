"""Repair only the known truncated story-notes envelope, then validate it."""
from __future__ import annotations
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "content" / "story_notes_fa.json"


def main() -> int:
    raw = PATH.read_text(encoding="utf-8")
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        # The audited defect is a truncated object with exactly two missing closers.
        if exc.pos != len(raw.rstrip()) or raw.rstrip().endswith("}"):
            raise
        repaired = raw.rstrip() + "\n}\n}\n"
        json.loads(repaired)
        PATH.write_text(repaired, encoding="utf-8")
    data = json.loads(PATH.read_text(encoding="utf-8"))
    stories = data.get("stories")
    if not isinstance(stories, dict) or not stories:
        raise SystemExit("story notes must contain a non-empty stories object")
    print(f"story notes valid: {len(stories)} stories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
