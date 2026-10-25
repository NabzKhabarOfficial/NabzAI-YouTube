import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from src import ig_buffer


class BufferAmbiguousRetryTests(unittest.TestCase):
    def test_mutation_timeout_is_not_retried(self):
        with patch.dict(os.environ, {"BUFFER_API_KEY": "offline-buffer-token"}), patch(
            "src.ig_buffer.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline simulated timeout"),
        ) as urlopen:
            with self.assertRaises(ig_buffer.AmbiguousBufferError):
                ig_buffer.gql(ig_buffer.CREATE, {"input": {"text": "offline"}})
        urlopen.assert_called_once()

    def test_mutation_http_5xx_is_not_retried(self):
        failure = urllib.error.HTTPError(
            "https://buffer.invalid/graphql", 503, "offline simulated server error", {}, None
        )
        with patch.dict(os.environ, {"BUFFER_API_KEY": "offline-buffer-token"}), patch(
            "src.ig_buffer.urllib.request.urlopen", side_effect=failure
        ) as urlopen:
            with self.assertRaises(ig_buffer.AmbiguousBufferError):
                ig_buffer.gql(ig_buffer.CREATE, {"input": {"text": "offline"}})
        urlopen.assert_called_once()

    def test_ambiguous_story_create_does_not_try_alternate_payloads(self):
        with patch.object(ig_buffer, "gql", side_effect=ig_buffer.AmbiguousBufferError("ambiguous")) as gql:
            with self.assertRaises(ig_buffer.AmbiguousBufferError):
                ig_buffer.create_story(
                    "offline-channel", "https://example.invalid/video.mp4",
                    ig_buffer.datetime(2030, 1, 1, tzinfo=ig_buffer.timezone.utc),
                )
        gql.assert_called_once()

    def test_buffer_state_uses_atomic_json_writer(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            old_path = ig_buffer.STATE_FILE
            ig_buffer.STATE_FILE = path
            try:
                ig_buffer.save_state({"sent": {"story-1": {"post_id": "offline-id"}}})
                self.assertEqual(ig_buffer.load_json(path, {}), {"sent": {"story-1": {"post_id": "offline-id"}}})
                self.assertFalse(any(item.suffix == ".tmp" for item in path.parent.iterdir()))
            finally:
                ig_buffer.STATE_FILE = old_path


if __name__ == "__main__":
    unittest.main()
