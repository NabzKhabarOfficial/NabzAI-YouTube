import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from src.guarded_buffer import _cache_safe_url_ready


class CacheSafeVideoReadinessTests(unittest.TestCase):
    @patch("src.guarded_buffer.urllib.request.urlopen")
    def test_accepts_nonempty_partial_content_response(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 206
        response.headers = {"Content-Length": "1"}
        response.read.return_value = b"x"
        urlopen.return_value = response

        self.assertTrue(_cache_safe_url_ready("https://example.test/video.mp4", 500000))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Range"), "bytes=0-0")
        self.assertEqual(request.get_header("Cache-control"), "no-cache")
        self.assertIn("ready=", request.full_url)

    @patch("src.guarded_buffer.urllib.request.urlopen")
    def test_rejects_short_full_response_when_range_is_ignored(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = {"Content-Length": "10"}
        response.read.return_value = b"x"

        urlopen.return_value = response
        self.assertFalse(_cache_safe_url_ready("https://example.test/video.mp4", 500000))

    @patch("src.guarded_buffer.urllib.request.urlopen")
    def test_rejects_empty_response_body(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 206
        response.headers = {"Content-Length": "0"}
        response.read.return_value = b""

        urlopen.return_value = response
        self.assertFalse(_cache_safe_url_ready("https://example.test/video.mp4", 500000))

    @patch("src.guarded_buffer.urllib.request.urlopen")
    def test_rejects_http_errors(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            "https://example.test/video.mp4", 404, "not found", {}, None
        )
        self.assertFalse(_cache_safe_url_ready("https://example.test/video.mp4", 500000))


if __name__ == "__main__":
    unittest.main()
