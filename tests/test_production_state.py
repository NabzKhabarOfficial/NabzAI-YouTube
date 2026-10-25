import tempfile
import unittest
from pathlib import Path
from src.production_state import (
    begin_claim, mark_ambiguous, mark_failed, mark_succeeded, retry_allowed,
    save_json_state, save_text_state,
)


class ProductionStateTests(unittest.TestCase):
    def test_atomic_json_and_text_writes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_json_state(root / "state.json", {"fa": "نبض"})
            save_text_state(root / "report.txt", "safe\n")
            self.assertIn("نبض", (root / "state.json").read_text())
            self.assertEqual((root / "report.txt").read_text(), "safe\n")
            self.assertFalse(list(root.glob("*.tmp")))

    def test_ambiguous_is_manual_review_and_not_retryable(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "claims.json"
            key, created = begin_claim(p, "buffer.create", "story-1", "media-sha")
            self.assertTrue(created)
            mark_ambiguous(p, key, "response lost")
            self.assertFalse(retry_allowed(p, key))
            self.assertIn(key, str(p.read_text()))

    def test_success_and_failure_are_terminal(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "claims.json"
            key, _ = begin_claim(p, "youtube.upload", "story-1", "video-sha")
            mark_succeeded(p, key, "video-1")
            self.assertFalse(retry_allowed(p, key))
            key2, _ = begin_claim(p, "meta.publish", "story-2", "image-sha")
            mark_failed(p, key2, "definitive 400")
            self.assertFalse(retry_allowed(p, key2))


if __name__ == "__main__":
    unittest.main()
