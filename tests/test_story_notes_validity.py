import json
import tempfile
import unittest
from pathlib import Path

from scripts.repair_story_notes import main as repair_main


class StoryNotesValidityTests(unittest.TestCase):
    def test_repair_closes_only_truncated_outer_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "story_notes_fa.json"
            path.write_text('{"stories":{"x":["ثابت"]}\n', encoding="utf-8")
            old = __import__("scripts.repair_story_notes", fromlist=["PATH"]).PATH
            module = __import__("scripts.repair_story_notes", fromlist=["PATH"])
            module.PATH = path
            try:
                self.assertEqual(repair_main(), 0)
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("x", data["stories"])
            finally:
                module.PATH = old


if __name__ == "__main__":
    unittest.main()
