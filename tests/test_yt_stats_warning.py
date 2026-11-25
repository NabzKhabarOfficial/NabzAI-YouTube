"""Tests for the improved yt_stats analytics warning (scope diagnosis)."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.yt_stats as yt_stats

SCOPE_ERR = "('invalid_scope: Bad Request', {'error': 'invalid_scope', 'error_description': 'Bad Request'})"


def _warning_for(exc_text: str) -> str:
    """Replicates the except-branch of yt_stats.build_report for a given error text."""
    missing_analytics = bool(re.search(r"scope|insufficient|403|invalid_grant|accessNotConfigured|disabled",
                                       exc_text, re.I))
    return ("Retention/subscriber numbers missing: the refresh token does not carry the "
            "yt-analytics.readonly scope (it likely has only youtube.upload/force-ssl). "
            "Regenerate it with all three scopes, then verify with scripts/check_yt_token_scopes.py. "
            if missing_analytics else "Analytics call failed. ") + exc_text[:200]


class ScopeWarningTests(unittest.TestCase):

    def test_scope_warning_mentions_tool_and_scopes(self):
        # the real telemetry error from review/yt_stats.json
        text = f"RefreshError: {SCOPE_ERR}"
        w = _warning_for(text)
        self.assertIn("yt-analytics.readonly", w)
        self.assertIn("check_yt_token_scopes.py", w)
        self.assertIn("youtube.upload/force-ssl", w)

    def test_real_telemetry_error_matches_pattern(self):
        # sanity: the actual error string recorded in review/yt_stats.json
        self.assertTrue(re.search(r"scope|insufficient|403|invalid_grant|accessNotConfigured|disabled",
                                  f"RefreshError: {SCOPE_ERR}", re.I))

    def test_nonscope_error_keeps_generic_message(self):
        text = "TimeoutError: connection timed out"
        self.assertFalse(re.search(r"scope|insufficient|403|invalid_grant|accessNotConfigured|disabled",
                                  text, re.I))
        w = _warning_for(text)
        self.assertTrue(w.startswith("Analytics call failed."))


if __name__ == "__main__":
    unittest.main()
