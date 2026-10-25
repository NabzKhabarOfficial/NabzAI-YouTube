import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import ig_pack, voice_check, yt_comment


class AtomicProductionWriterTests(unittest.TestCase):
    def test_voice_learning_report_are_atomic_and_report_counters_reset(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learned = root / "pron_learned.json"
            report = root / "voice_check.json"
            with patch.object(voice_check, "LEARNED", learned), patch.object(voice_check, "REPORT", report):
                voice_check._save_learned("en", "Worcester", "WUSS-ter")
                self.assertEqual(voice_check.learned("en")["Worcester"], "WUSS-ter")
                old_beats, old_reason, old_events = voice_check._BEATS, voice_check._REASON, list(voice_check.EVENTS)
                try:
                    voice_check._BEATS = 3
                    voice_check._REASON = "offline test"
                    voice_check.EVENTS[:] = [{"event": "offline"}]
                    voice_check.write_report("story-offline", "en")
                    self.assertEqual(voice_check._BEATS, 0)
                    self.assertEqual(voice_check._REASON, "")
                    self.assertEqual(voice_check.EVENTS, [])
                    self.assertEqual(json.loads(report.read_text(encoding="utf-8"))[-1]["beats_checked"], 3)
                finally:
                    voice_check._BEATS, voice_check._REASON = old_beats, old_reason
                    voice_check.EVENTS[:] = old_events
                self.assertFalse(any(p.suffix == ".tmp" for p in root.iterdir()))

    def test_youtube_comment_state_atomic_write(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "comments.json"
            yt_comment.save_state({"commented": ["story-offline"]}, path)
            self.assertEqual(yt_comment.load_state(path)["commented"], ["story-offline"])
            self.assertFalse(any(p.suffix == ".tmp" for p in path.parent.iterdir()))

    def test_instagram_pack_state_atomic_write(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ig-pack.json"
            old_path = ig_pack.STATE_FILE
            ig_pack.STATE_FILE = path
            try:
                ig_pack.save_state({"weeks": {"week-offline": {"built": {}}}})
                self.assertEqual(ig_pack.load_json(path, {})["weeks"]["week-offline"]["built"], {})
                self.assertFalse(any(p.suffix == ".tmp" for p in path.parent.iterdir()))
            finally:
                ig_pack.STATE_FILE = old_path


if __name__ == "__main__":
    unittest.main()
