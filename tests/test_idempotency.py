import multiprocessing
import tempfile
import unittest
from pathlib import Path

from src.idempotency import claim, finish, fingerprint, get


def _claim_worker(path_text, key, result):
    result.put(claim(Path(path_text), key, {"story_id": "story-race"}))


class IdempotencyTests(unittest.TestCase):
    def test_claim_is_single_use_and_finish_is_durable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claims.json"
            key = fingerprint("youtube", "story-1", "sha256:video")
            self.assertTrue(claim(path, key, {"story_id": "story-1"}))
            self.assertFalse(claim(path, key))
            finish(path, key, "video-123")
            self.assertEqual(get(path, key).status, "succeeded")
            self.assertEqual(get(path, key).external_id, "video-123")

    def test_concurrent_claims_allow_exactly_one_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claims.json"
            key = fingerprint("buffer", "race")
            result = multiprocessing.Queue()
            workers = [multiprocessing.Process(target=_claim_worker, args=(str(path), key, result)) for _ in range(2)]
            for worker in workers: worker.start()
            for worker in workers: worker.join(10)
            self.assertEqual([result.get(timeout=2) for _ in workers].count(True), 1)
            self.assertEqual([result.get_nowait() for _ in []], [])

    def test_explicit_failure_can_be_retried_but_success_cannot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claims.json"
            key = fingerprint("youtube", "retryable")
            self.assertTrue(claim(path, key))
            finish(path, key, "", status="failed")
            self.assertTrue(claim(path, key))
            finish(path, key, "video-1", status="succeeded")
            self.assertFalse(claim(path, key))


if __name__ == "__main__":
    unittest.main()
