import unittest
from unittest.mock import patch
import requests

from instagram import publisher


class MetaAmbiguousRetryTests(unittest.TestCase):
    def test_post_timeout_is_not_retried(self):
        with patch("instagram.publisher.requests.request", side_effect=requests.Timeout("offline timeout")) as request:
            with self.assertRaises(publisher.InstagramPublishError):
                publisher._request("POST", "https://example.invalid/offline", data={"test": "1"})
        request.assert_called_once()

    def test_post_server_error_is_not_retried(self):
        response = type("Response", (), {"status_code": 503})()
        with patch("instagram.publisher.requests.request", return_value=response) as request:
            with self.assertRaises(publisher.InstagramPublishError):
                publisher._request("POST", "https://example.invalid/offline", data={"test": "1"})
        request.assert_called_once()

    def test_get_transport_retries_are_bounded(self):
        with patch("instagram.publisher.requests.request", side_effect=requests.Timeout("offline timeout")) as request:
            with self.assertRaises(publisher.InstagramPublishError):
                publisher._request("GET", "https://example.invalid/offline")
        self.assertEqual(request.call_count, 3)


if __name__ == "__main__":
    unittest.main()
