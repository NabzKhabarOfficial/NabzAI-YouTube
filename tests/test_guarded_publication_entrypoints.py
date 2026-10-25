import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import guarded_buffer, guarded_meta, guarded_youtube_upload


class GuardedPublicationEntryPointTests(unittest.TestCase):
    def test_youtube_claim_blocks_second_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "story.json").write_text(json.dumps({"id": "story-1"}), encoding="utf-8")
            (root / "final_short.mp4").write_bytes(b"offline-video")
            old = guarded_youtube_upload.CLAIMS
            guarded_youtube_upload.CLAIMS = root / "claims.json"
            try:
                with patch.object(guarded_youtube_upload.youtube_uploader, "upload_from_metadata", return_value="yt-1"):
                    self.assertEqual(guarded_youtube_upload.run(str(root)), "yt-1")
                    with self.assertRaisesRegex(RuntimeError, "claim already exists"):
                        guarded_youtube_upload.run(str(root))
            finally:
                guarded_youtube_upload.CLAIMS = old

    def test_buffer_uncertain_run_is_not_retried_but_success_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pack = root / "pack.json"
            pack.write_text('{"weeks": {"w": {"built": {}}}}', encoding="utf-8")
            old_claims, old_pack = guarded_buffer.CLAIMS, guarded_buffer.PACK
            guarded_buffer.CLAIMS, guarded_buffer.PACK = root / "claims.json", pack
            try:
                with patch.object(guarded_buffer.ig_buffer, "main", side_effect=TimeoutError("lost response")):
                    with self.assertRaises(TimeoutError):
                        guarded_buffer.run()
                with self.assertRaisesRegex(RuntimeError, "claim already exists"):
                    guarded_buffer.run()
            finally:
                guarded_buffer.CLAIMS, guarded_buffer.PACK = old_claims, old_pack

    def test_buffer_confirmed_snapshot_is_idempotent_noop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pack = root / "pack.json"
            pack.write_text('{"weeks": {"w": {"built": {}}}}', encoding="utf-8")
            old_claims, old_pack = guarded_buffer.CLAIMS, guarded_buffer.PACK
            guarded_buffer.CLAIMS, guarded_buffer.PACK = root / "claims.json", pack
            try:
                with patch.object(guarded_buffer.ig_buffer, "main", return_value=0) as call:
                    self.assertEqual(guarded_buffer.run(), 0)
                    self.assertEqual(guarded_buffer.run(), 0)
                    self.assertEqual(call.call_count, 1)
            finally:
                guarded_buffer.CLAIMS, guarded_buffer.PACK = old_claims, old_pack

    def test_meta_story_dry_run_claims_once_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            old = guarded_meta.CLAIMS
            guarded_meta.CLAIMS = Path(td) / "claims.json"
            try:
                result = guarded_meta.publish_story(video_url="https://example.test/story.mp4", dry_run=True)
                self.assertTrue(result["dry_run"])
                with self.assertRaisesRegex(RuntimeError, "claim already exists"):
                    guarded_meta.publish_story(video_url="https://example.test/story.mp4", dry_run=True)
            finally:
                guarded_meta.CLAIMS = old


if __name__ == "__main__":
    unittest.main()
