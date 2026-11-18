import json
import tempfile
import unittest
from pathlib import Path

from src.ig_inventory import available_story_ids, inventory_status


class InstagramInventoryTests(unittest.TestCase):
    def test_inventory_requires_persian_approval_english_script_and_unused_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = root / "content"
            content.mkdir()
            (content / "mysteries.json").write_text(json.dumps([
                {"id": "posted"}, {"id": "planned"}, {"id": "fresh"}
            ]), encoding="utf-8")
            (content / "mysteries_batch01.json").write_text(json.dumps([
                {"id": "retired"}, {"id": "not-approved"}
            ]), encoding="utf-8")
            (content / "mysteries_fa.json").write_text(json.dumps({
                "stories": {sid: {"title": sid} for sid in
                           ("posted", "planned", "fresh", "retired", "not-approved", "no-english")}
            }), encoding="utf-8")
            (content / "story_notes_fa.json").write_text(json.dumps({
                "stories": {sid: ["proven", "probable", "unknown"] for sid in
                           ("posted", "planned", "fresh", "retired")}
            }), encoding="utf-8")
            (content / "ig_state.json").write_text(json.dumps({"posted": ["posted"]}), encoding="utf-8")
            (content / "ig_pack_state.json").write_text(json.dumps({
                "retired": ["retired"],
                "weeks": {"2026-11-23": {"plan": [{"id": "planned"}]}}
            }), encoding="utf-8")

            self.assertEqual(available_story_ids(root), ["fresh"])
            status = inventory_status(root, reserve=3)
            self.assertEqual(status["available"], 1)
            self.assertTrue(status["low"])

    def test_duplicate_english_ids_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = root / "content"
            content.mkdir()
            row = json.dumps([{"id": "same"}])
            (content / "mysteries.json").write_text(row, encoding="utf-8")
            (content / "mysteries_batch01.json").write_text(row, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "duplicate English story id"):
                available_story_ids(root)


if __name__ == "__main__":
    unittest.main()
