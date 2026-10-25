"""Record a story only after a successful upload step."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.mystery_short import record_story


def main() -> int:
    root = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else "output/mystery-short"
    )

    story_path = root / "story.json"

    story = json.loads(
        story_path.read_text(encoding="utf-8")
    )

    story_id = str(
        story.get("id")
        or story.get("story_id")
        or ""
    ).strip()

    if not story_id:
        raise SystemExit(
            "story.json has no story id"
        )

    record_story(story_id)
    print(f"Recorded uploaded story: {story_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
