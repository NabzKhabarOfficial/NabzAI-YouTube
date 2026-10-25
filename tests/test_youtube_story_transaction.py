import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import youtube_uploader


class YouTubeStoryTransactionTests(unittest.TestCase):
    def _fixture(self, root):
        (root / "final_short.mp4").write_bytes(b"offline-video-stub")
        (root / "story.json").write_text(json.dumps({"id": "story-1"}), encoding="utf-8")
        (root / "metadata.json").write_text(
            json.dumps({"title": "Test", "description": "Offline test", "tags": ["test"], "category_id": "27"}),
            encoding="utf-8",
        )

    def test_confirmed_upload_records_story(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._fixture(root)
            with patch.object(youtube_uploader, "upload_video", return_value="youtube-video-123"), patch(
                "src.mystery_short.record_story"
            ) as record:
                result = youtube_uploader.upload_from_metadata(root)
            self.assertEqual(result, "youtube-video-123")
            record.assert_called_once_with("story-1")

    def test_upload_failure_does_not_record_story(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._fixture(root)
            with patch.object(youtube_uploader, "upload_video", side_effect=TimeoutError("offline simulated timeout")), patch(
                "src.mystery_short.record_story"
            ) as record:
                with self.assertRaises(TimeoutError):
                    youtube_uploader.upload_from_metadata(root)
            record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
