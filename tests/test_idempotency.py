import tempfile
import unittest
from pathlib import Path

from src.idempotency import claim, finish, fingerprint, get, reconcile


class IdempotencyTests(unittest.TestCase):
    def test_claim_is_single_use_and_finish_is_durable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claims.json"
            key = fingerprint("youtube", "story-1", "sha256:video")
            self.assertTrue(claim(path, key, {"story_id": "story-1"}))
            self.assertFalse(claim(path, key))
            self.assertEqual(get(path, key).status, "pending")
            finish(path, key, "video-123")
            self.assertEqual(get(path, key).external_id, "video-123")
            self.assertEqual(get(path, key).status, "succeeded")

    def test_ambiguous_claim_requires_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claims.json"
            key = fingerprint("buffer", "reel-1", "sha256:video")
            self.assertTrue(claim(path, key))
            finish(path, key, "", status="ambiguous")
            current = get(path, key)
            self.assertEqual(current.status, "ambiguous")
            self.assertFalse(claim(path, key))
            reconcile(path, key, "buffer-post-42")
            self.assertEqual(get(path, key).external_id, "buffer-post-42")
            self.assertEqual(get(path, key).status, "succeeded")

    def test_invalid_status_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claims.json"
            key = fingerprint("meta", "story-1", "sha256:image")
            claim(path, key)
            with self.assertRaises(ValueError):
                finish(path, key, "", status="retry")


if __name__ == "__main__":
    unittest.main()
