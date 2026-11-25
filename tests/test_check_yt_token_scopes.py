"""Tests for the YouTube OAuth scope probe (scripts/check_yt_token_scopes.py)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.check_yt_token_scopes as probe

UP = "https://www.googleapis.com/auth/youtube.upload"
SSL = "https://www.googleapis.com/auth/youtube.force-ssl"
AN = "https://www.googleapis.com/auth/yt-analytics.readonly"

CREDS = {
    "client_id": "abc.apps.googleusercontent.com",
    "client_secret": "s3cret",
    "refresh_token": "1//rt",
    "token_uri": "https://oauth2.googleapis.com/token",
}


def _fake_loader(token_json=None, env=None):
    return dict(CREDS)


class ScopeProbeTests(unittest.TestCase):

    def test_required_scopes_are_the_three_pipeline_scopes(self):
        self.assertEqual(probe.REQUIRED_SCOPES, [UP, SSL, AN])

    def test_main_zero_when_all_present(self):
        with mock.patch.object(probe, "load_credential_info", _fake_loader), \
                mock.patch.object(probe, "probe_scopes", lambda info, timeout=15.0: [UP, SSL, AN]):
            rc = probe.main(env=dict.fromkeys(CREDS))
        self.assertEqual(rc, 0)

    def test_main_one_when_analytics_missing(self):
        with mock.patch.object(probe, "load_credential_info", _fake_loader), \
                mock.patch.object(probe, "probe_scopes", lambda info, timeout=15.0: [UP, SSL]):
            rc = probe.main(env=dict.fromkeys(CREDS))
        self.assertEqual(rc, 1)

    def test_main_two_when_refresh_rejected(self):
        def boom(info, timeout=15.0):
            raise RuntimeError("token refresh failed: HTTP 400: invalid_grant")

        with mock.patch.object(probe, "load_credential_info", _fake_loader), \
                mock.patch.object(probe, "probe_scopes", boom):
            rc = probe.main(env=dict.fromkeys(CREDS))
        self.assertEqual(rc, 2)

    def test_main_two_when_no_credentials(self):
        def no_creds(token_json=None, env=None):
            raise RuntimeError("No YouTube credentials")

        with mock.patch.object(probe, "load_credential_info", no_creds):
            rc = probe.main(env={})
        self.assertEqual(rc, 2)

    def test_probe_scopes_parses_space_separated(self):
        import requests

        class FakeResp:
            status_code = 200

            def json(self):
                return {"scope": f"{UP} {SSL} {AN}"}

        with mock.patch.object(requests, "post", lambda url, data, timeout: FakeResp()):
            got = probe.probe_scopes({"client_id": "a", "client_secret": "b", "refresh_token": "c"})
        self.assertEqual(got, [UP, SSL, AN])

    def test_probe_scopes_error_on_empty_scope(self):
        import requests

        class EmptyResp:
            status_code = 200

            def json(self):
                return {}

        with mock.patch.object(requests, "post", lambda url, data, timeout: EmptyResp()):
            with self.assertRaisesRegex(RuntimeError, "no scope field"):
                probe.probe_scopes({"client_id": "a", "client_secret": "b", "refresh_token": "c"})

    def test_probe_scopes_error_on_http_400(self):
        import requests

        class BadResp:
            status_code = 400

            def json(self):
                return {"error": "invalid_grant"}

        with mock.patch.object(requests, "post", lambda url, data, timeout: BadResp()):
            with self.assertRaisesRegex(RuntimeError, "token refresh failed"):
                probe.probe_scopes({"client_id": "a", "client_secret": "b", "refresh_token": "c"})


if __name__ == "__main__":
    unittest.main()
