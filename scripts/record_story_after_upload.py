"""Record a story only after a confirmed successful upload.

This script is executable both ways:
  python scripts/record_story_after_upload.py output/mystery-short
  python -m scripts.record_story_after_upload output/mystery-short
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Running a file under scripts/ makes scripts/ the first sys.path entry.
# Add the repository root before importing the src package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mystery_short import record_story


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "output/mystery-short")
    if not root.is_absolute():
        root = ROOT / root

    story_path = root / "story.json"
    if not story_path.exists():
        raise SystemExit(f"story.json not found: {story_path}")

    try:
        story = json.loads(story_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"could not read story.json: {type(exc).__name__}: {exc}") from None

    story_id = str(story.get("id") or story.get("story_id") or "").strip()
    if not story_id:
        raise SystemExit("story.json has no story id")

    record_story(story_id)
    print(f"Recorded uploaded story: {story_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
