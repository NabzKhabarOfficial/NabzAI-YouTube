#!/usr/bin/env python3
"""Check which OAuth scopes a YouTube refresh token actually carries.

The pipeline needs THREE scopes on one refresh token:
    youtube.upload           (Shorts upload - works today)
    youtube.force-ssl        (comment catch-up - works today)
    yt-analytics.readonly    (retention stats - currently MISSING -> invalid_scope)

This script refreshes an access token and reads the `scope` field Google returns,
so you know BEFORE the daily run whether yt_stats will fall back to public
numbers only. Run it with the same secrets the workflow has:

    python3 scripts/check_yt_token_scopes.py

Exit codes: 0 = all scopes present, 1 = scopes missing (printed), 2 = bad credentials.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.youtube_uploader import load_credential_info, TOKEN_URI

REQUIRED_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def probe_scopes(info: dict, timeout: float = 15.0) -> list[str]:
    """Exchange the refresh token for an access token and return granted scopes."""
    import requests

    resp = requests.post(
        TOKEN_URI,
        data={
            "client_id": info["client_id"],
            "client_secret": info["client_secret"],
            "refresh_token": info["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=timeout,
    )
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code != 200:
        raise RuntimeError(f"token refresh failed: HTTP {resp.status_code}: {str(body)[:200]}")
    granted = [s.strip() for s in (body.get("scope") or "").split() if s.strip()]
    if not granted:
        raise RuntimeError("token endpoint returned no scope field (unexpected response shape)")
    return granted


def _fmt(scopes: list[str]) -> str:
    name = lambda u: u.rsplit("/", 1)[-1]
    return ", ".join(name(s) for s in scopes) or "(none)"


def main(env=None) -> int:
    env = os.environ if env is None else env
    try:
        info = load_credential_info(env=env)
    except Exception as exc:
        print(f"NO CREDENTIALS: {exc}")
        return 2
    try:
        granted = probe_scopes(info)
    except Exception as exc:
        print(f"REFRESH FAILED: {exc}")
        print("The refresh token itself is rejected; generate a new one with the "
              "three scopes listed in docs/ONBOARDING or the runbook.")
        return 2

    print("Granted scopes:", _fmt(granted))
    missing = [s for s in REQUIRED_SCOPES if s not in granted]
    extra = [s for s in granted if s not in REQUIRED_SCOPES]
    if extra:
        print("Also granted (unused by this pipeline):", _fmt(extra))
    if not missing:
        print("OK: token covers upload, comments AND analytics - yt_stats will get retention data.")
        return 0
    print("MISSING:")
    for s in missing:
        print(f"  - {s.rsplit('/', 1)[-1]}  ({s})")
    print("Fix: regenerate the refresh token with all three scopes, then update the "
          "YOUTUBE_REFRESH_TOKEN / YOUTUBE_TOKEN secret. See docs/ONBOARDING.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
