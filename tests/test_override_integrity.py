"""Every override must match a real base story with the same beat count.

mystery_short.apply_overrides() skips an override silently when the beat count
differs, so the video keeps the old script. This test makes that visible.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"


def _rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("stories", []) if isinstance(data, dict) else []
    return [r for r in rows if isinstance(r, dict)]


def _base_stories() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in [CONTENT / "mysteries.json", *sorted(CONTENT.glob("mysteries_batch*.json"))]:
        for row in _rows(path):
            sid = str(row.get("id") or "").strip()
            if sid:
                out.setdefault(sid, row)
    return out


class OverrideIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.base = _base_stories()
        self.override = json.loads((CONTENT / "mysteries_override.json").read_text(encoding="utf-8")).get("stories", {})

    def test_every_override_has_a_base_story(self):
        missing = sorted(sid for sid in self.override if sid not in self.base)
        self.assertEqual(missing, [], "override ids without a base story")

    def test_every_override_beat_count_matches_base(self):
        bad = []
        for sid, item in self.override.items():
            texts = item.get("beats") or []
            base = self.base.get(sid)
            if not base or not texts:
                continue
            if len(texts) != len(base.get("beats") or []):
                bad.append((sid, len(texts), len(base.get("beats") or [])))
        self.assertEqual(bad, [], "override beat count differs from base; the override would be skipped")

    def test_every_override_hook_is_short(self):
        bad = [(sid, len(str(item["beats"][0]).split())) for sid, item in self.override.items()
               if item.get("beats") and len(str(item["beats"][0]).split()) > 14]
        self.assertEqual(bad, [], "override hooks longer than 14 words")


if __name__ == "__main__":
    unittest.main()
