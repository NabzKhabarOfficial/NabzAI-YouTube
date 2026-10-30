"""Hands the finished «نبض معما» reels to Buffer, which publishes them on Instagram through
Meta's official API. Nothing here logs in to Instagram, and the owner uploads nothing.

Every run:
 1. reads content/ig_pack_state.json and takes the reels that are built but not yet sent;
 2. puts the videos of every reel that is still waiting in Buffer on the public site of the
    repo nabz-reels (GitHub Pages; one fresh commit, so the repo never grows);
 3. creates one Buffer post per reel, never more than Buffer's free queue of 10 scheduled posts;
 4. records everything in content/ig_buffer_state.json.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import time
import hashlib
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_STATE = ROOT / "content" / "ig_pack_state.json"
STATE_FILE = ROOT / "content" / "ig_buffer_state.json"
WORK = ROOT / "output" / "ig-buffer"
TEHRAN = timezone(timedelta(hours=3, minutes=30))
REPO = os.getenv("GITHUB_REPOSITORY", "NabzKhabarOfficial/NabzAI-YouTube")
SITE_REPO = os.getenv("NABZ_REELS_REPO", "NabzKhabarOfficial/nabz-reels")
SITE_URL = os.getenv("NABZ_REELS_URL", "https://nabzkhabarofficial.github.io/nabz-reels")
API = "https://api.buffer.com"
QUEUE_MAX = int(os.getenv("NABZ_BUFFER_QUEUE_MAX", "10"))
LEAD_MIN = 30
STUCK_MIN = 20
MAX_NEW = int(os.getenv("NABZ_BUFFER_MAX_NEW", "10"))
SLOTS = [(13 * 60, 14 * 60 + 10), (20 * 60 + 30, 22 * 60 + 40)]
GAP_MIN = 150
STOP_FILE = ROOT / "STOP"
CAPTIONS = ROOT / "content" / "ig_captions_fa.json"
FILMS = ROOT / "content" / "ig_films_fa.json"
FILM_CTA = "🎬 از این ماجرای واقعی فیلم ساختن! اسمش رو می‌خوای؟ کامنت بذار «فیلم» تا برات دایرکت بشه 👇"
FA_BANK = ROOT / "content" / "mysteries_fa.json"
STATS_FILE = ROOT / "content" / "ig_stats.json"
REPORT_MD = ROOT / "review" / "ig_weekly.md"
FAIL_ALERT = 3
PUSH_TRIES = 4
STORIES = os.getenv("NABZ_STORIES", "1") != "0"
STORY_SECONDS = float(os.getenv("NABZ_STORY_SECONDS", "15"))
STORY_AFTER_MIN = 15
STORY_FROM_HOUR = 17
STORY_V = 2
CAR_AHEAD_DAYS = int(os.getenv("NABZ_CAROUSEL_AHEAD_DAYS", "4"))


def log(msg: str) -> None:
    print(f"[ig-buffer] {msg}", flush=True)


def warn(title: str, msg: str) -> None:
    print(f"::warning title={title}::{msg}", flush=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class BufferError(RuntimeError):
    pass


def gql(query: str, variables: dict | None = None) -> dict:
    key = os.getenv("BUFFER_API_KEY", "").strip()
    if not key:
        raise BufferError("BUFFER_API_KEY secret is missing")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    for attempt in range(3):
        req = urllib.request.Request(API, data=body, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}", "User-Agent": "nabz-reels/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            text = exc.read().decode(errors="replace")[:400]
            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(20 * (attempt + 1)); continue
            raise BufferError(f"HTTP {exc.code}: {text}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 2:
                time.sleep(15); continue
            raise BufferError(f"network: {exc}") from None
        if data.get("errors"):
            raise BufferError("; ".join(str(e.get("message", e)) for e in data["errors"])[:500])
        return data.get("data") or {}
    raise BufferError("no answer")


def find_channel(state: dict) -> tuple[str, str]:
    if state.get("channel_id") and state.get("org_id"):
        return state["org_id"], state["channel_id"]
    orgs = gql("query { account { organizations { id name } } }")["account"]["organizations"]
    for org in orgs:
        chans = gql('query { channels(input: {organizationId: %s}) { id name service } }' % json.dumps(org["id"]))["channels"]
        for ch in chans:
            if str(ch.get("service", "")).lower() == "instagram":
                state["org_id"], state["channel_id"], state["channel_name"] = org["id"], ch["id"], ch.get("name")
                log(f"Instagram channel in Buffer: {ch.get('name')}")
                return org["id"], ch["id"]
    raise BufferError("no Instagram channel is connected in Buffer")


def scheduled_posts(org: str, channel: str) -> list[dict]:
    q = """query { posts(first: 50, input: {organizationId: %s, filter: {status: [scheduled], channelIds: [%s]}}) { edges { node { id dueAt } } } }""" % (json.dumps(org), json.dumps(channel))
    return [e["node"] for e in gql(q)["posts"]["edges"]]


def post_status(org: str, channel: str, status: str) -> set:
    q = """query { posts(first: 50, input: {organizationId: %s, filter: {status: [%s], channelIds: [%s]}}) { edges { node { id } } } }""" % (json.dumps(org), status, json.dumps(channel))
    try:
        return {e["node"]["id"] for e in gql(q)["posts"]["edges"]}
    except BufferError as exc:
        log(f"could not read {status} posts: {exc}"); return set()


# ... unchanged Buffer scheduling, hosting, story, carousel, and reporting functions ...


def url_ready(url: str, size: int) -> bool:
    """Verify a GitHub Pages asset without trusting HEAD Content-Length.

    GitHub Pages/CDN responses commonly omit or rewrite Content-Length on HEAD, and a
    stale edge can briefly return an older length after the force-push. A successful GET
    of the first byte range proves that the current asset is reachable; when a reliable
    Content-Length is present, it is used only as an additional check, never as the
    sole readiness criterion.
    """
    headers = {"User-Agent": "nabz-reels/1.0", "Cache-Control": "no-cache", "Range": "bytes=0-0"}
    probe = url + ("&" if "?" in url else "?") + f"ready={int(time.time())}"
    req = urllib.request.Request(probe, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            body = resp.read(1)
            length = resp.headers.get("Content-Length", "")
            if status not in (200, 206) or not body:
                return False
            # A range response length is normally 1, so do not compare it with the full file.
            # If the server returns a full response with a trustworthy length, accept it.
            if status == 200 and length:
                try:
                    reported = int(length)
                    if reported < max(1, min(size, 100_000)):
                        return False
                except ValueError:
                    pass
            return True
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return False


def wait_public(urls: dict[str, int], minutes: int = 12) -> bool:
    end = time.time() + minutes * 60
    while time.time() < end:
        if all(url_ready(u, s) for u, s in urls.items()):
            return True
        time.sleep(20)
    return False
