import unittest
from unittest.mock import patch

from src import youtube_uploader


class FakeResponse:
    status = 400


class FakeScheduleValidationError(Exception):
    resp = FakeResponse()
    content = b'{"error":{"errors":[{"reason":"invalidPublishAt"}],"message":"Invalid publishAt"}}'


class YouTubeUploaderRetryTests(unittest.TestCase):
    def _mock_credentials(self):
        return (
            patch.object(youtube_uploader, "load_credential_info", return_value={"client_id": "offline"}),
            patch.object(youtube_uploader.Credentials, "from_authorized_user_info", return_value=object()),
            patch.object(youtube_uploader, "build", return_value=object()),
        )

    def test_timeout_is_not_retried(self):
        patches = self._mock_credentials()
        with patches[0], patches[1], patches[2], patch.object(
            youtube_uploader, "_insert", side_effect=TimeoutError("simulated ambiguous upload")
        ) as insert:
            with self.assertRaises(TimeoutError):
                youtube_uploader.upload_video("offline.mp4", "title", "description", [], publish_at="2030-01-01T00:00:00Z")
        insert.assert_called_once()

    def test_only_known_schedule_validation_gets_fallback(self):
        patches = self._mock_credentials()
        with patches[0], patches[1], patches[2], patch.object(
            youtube_uploader, "_insert",
            side_effect=[FakeScheduleValidationError("invalid publishAt"), {"id": "video-123", "status": {}}],
        ) as insert:
            result = youtube_uploader.upload_video(
                "offline.mp4", "title", "description", [],
                publish_at="2030-01-01T00:00:00Z",
            )
        self.assertEqual(result, "video-123")
        self.assertEqual(insert.call_count, 2)
        self.assertNotIn("publishAt", insert.call_args_list[1].args[1]["status"])

    def test_combined_tag_length_is_bounded(self):
        tags = ["a" * 300, "b" * 250, "short"]
        bounded = youtube_uploader._bounded_tags(tags)
        self.assertLessEqual(sum(len(tag) for tag in bounded) + len(bounded) - 1, 500)
        self.assertIn("short", bounded)


if __name__ == "__main__":
    unittest.main()
