"""Merge Instagram-only English story additions for one CI run."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "content" / "mysteries.json"
ADD = ROOT / "content" / "mysteries_add.json"


def read_stories(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    stories = data.get("stories")
    if not isinstance(stories, list):
        raise ValueError(f"{path}: stories must be a list")
    return data, stories


def validate(story: dict, source: Path) -> None:
    sid = story.get("id")
    if not isinstance(sid, str) or not sid.strip():
        raise ValueError(f"{source}: story is missing an id")
    beats = story.get("beats")
    if not isinstance(beats, list) or len(beats) != 6:
        raise ValueError(f"{source}: {sid} must have exactly six beats")
    for number, beat in enumerate(beats, 1):
        if not isinstance(beat, dict) or not str(beat.get("text", "")).strip() or not str(beat.get("visual", "")).strip():
            raise ValueError(f"{source}: {sid} beat {number} needs text and visual")


def main() -> None:
    bank_data, bank = read_stories(BANK)
    sources = [ADD] + sorted(ROOT.glob("content/mysteries_add_batch*.json"))
    by_id: dict[str, dict] = {}
    for story in bank:
        validate(story, BANK)
        sid = story["id"]
        if sid in by_id:
            raise ValueError(f"duplicate story id in {BANK}: {sid}")
        by_id[sid] = story
    added = 0
    for source in sources:
        if not source.exists():
            continue
        _, additions = read_stories(source)
        for story in additions:
            validate(story, source)
            sid = story["id"]
            if sid not in by_id:
                bank.append(story)
                by_id[sid] = story
                added += 1
    bank_data["stories"] = bank
    BANK.write_text(json.dumps(bank_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Instagram English bank: {len(by_id)} stories ({added} staged additions visible to planner)")


if __name__ == "__main__":
    main()
