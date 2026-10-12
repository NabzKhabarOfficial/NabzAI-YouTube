"""Hard checks for the approved six-beat mystery structure."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "content" / "mysteries.json"
OVERRIDE = ROOT / "content" / "mysteries_override.json"


def _words(text: str) -> int:
    return len(str(text).split())


def _effective_stories():
    data = json.loads(BANK.read_text(encoding="utf-8"))
    extra = json.loads(OVERRIDE.read_text(encoding="utf-8")).get("stories", {})
    for story in data["stories"]:
        item = extra.get(story["id"], {})
        beats = item.get("beats") or []
        if beats and len(beats) == len(story["beats"]):
            for beat, text in zip(story["beats"], beats):
                beat["text"] = str(text).strip()
    return data["stories"]


class StoryStructureTests(unittest.TestCase):
    def test_every_story_is_exactly_six_beats(self):
        for story in _effective_stories():
            self.assertEqual(len(story["beats"]), 6, story["id"])

    def test_every_story_has_a_short_hook_and_valid_length(self):
        for story in _effective_stories():
            beats = story["beats"]
            self.assertLessEqual(_words(beats[0]["text"]), 14, story["id"])
            total = sum(_words(beat["text"]) for beat in beats)
            self.assertTrue(50 <= total <= 95, (story["id"], total))

    def test_every_beat_has_text_and_visual(self):
        for story in _effective_stories():
            for number, beat in enumerate(story["beats"], 1):
                self.assertTrue(beat.get("text", "").strip(), (story["id"], number))
                self.assertTrue(beat.get("visual", "").strip(), (story["id"], number))


if __name__ == "__main__":
    unittest.main()
