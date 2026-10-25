import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src import guarded_youtube_upload


class PublicationOutcomeFixtures(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_fixture_is_complete(self):
        data = json.loads((self.ROOT / "tests/fixtures/publication_outcomes.json").read_text())
        self.assertEqual(data["youtube"]["unknown_timeout_after_acceptance"]["allowed_followup_inserts"], 0)
        self.assertEqual(data["youtube"]["deterministic_publish_at_rejection"]["allowed_followup_inserts"], 1)
        self.assertEqual(data["buffer"]["delete_timeout"]["expected_claim_status"], "ambiguous")

    def test_unknown_youtube_outcome_blocks_second_insert(self):
        calls = []
        original = guarded_youtube_upload.youtube_uploader._insert
        def fake_insert(*args, **kwargs):
            calls.append(1)
            raise TimeoutError("response lost after acceptance")
        guarded_youtube_upload.youtube_uploader._insert = fake_insert
        try:
            original, state = guarded_youtube_upload._single_insert_only()
            with self.assertRaises(TimeoutError):
                guarded_youtube_upload.youtube_uploader._insert("yt", {}, "video")
            with self.assertRaises(RuntimeError):
                guarded_youtube_upload.youtube_uploader._insert("yt", {}, "video")
            self.assertEqual(len(calls), 1)
            self.assertEqual(state["count"], 2)
        finally:
            guarded_youtube_upload.youtube_uploader._insert = original

    def test_deterministic_publish_at_rejection_allows_one_safe_fallback(self):
        original = guarded_youtube_upload.youtube_uploader._insert
        calls = []
        class FakeHttpError(Exception):
            def __init__(self):
                self.resp = SimpleNamespace(status=400)
            def __str__(self):
                return "publishAt rejected by API"
        def fake_insert(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise FakeHttpError()
            return {"id": "video-1"}
        guarded_youtube_upload.youtube_uploader._insert = fake_insert
        try:
            original, state = guarded_youtube_upload._single_insert_only()
            with self.assertRaises(FakeHttpError):
                guarded_youtube_upload.youtube_uploader._insert("yt", {}, "video")
            result = guarded_youtube_upload.youtube_uploader._insert("yt", {}, "video")
            self.assertEqual(result["id"], "video-1")
            self.assertEqual(state["count"], 2)
        finally:
            guarded_youtube_upload.youtube_uploader._insert = original


if __name__ == "__main__":
    unittest.main()
