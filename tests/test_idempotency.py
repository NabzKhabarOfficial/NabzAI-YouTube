import tempfile
import unittest
from pathlib import Path
from src.idempotency import claim, finish, fingerprint

class IdempotencyTests(unittest.TestCase):
    def test_claim_is_single_use_and_finish_is_durable(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "claims.json"
            key = fingerprint("youtube", "story-1", "sha256:video")
            self.assertTrue(claim(p, key, {"story_id": "story-1"}))
            self.assertFalse(claim(p, key))
            finish(p, key, "video-123")
            self.assertIn("video-123", p.read_text())

if __name__ == "__main__": unittest.main()
