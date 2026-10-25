"""First comment on each new NABZ Mysteries Short, posted automatically.

Runs from .github/workflows/yt-comment.yml shortly after the 22:30 Tehran
publish time (cron-job.org calls workflow_dispatch), and again as a catch-up
right after the next day's upload (src.youtube_uploader), so a Short whose
evening run was missed still gets its comment. It finds the newest public
upload of the channel that has not been commented yet and posts one
story-specific question, so viewers have something to answer. YouTube's API
cannot pin comments: the owner pins it from the app.

Needs a refresh token that includes the youtube.force-ssl scope (the upload
token alone is not enough). Rules: at most one comment per run, never twice
on the same video, only public videos from the last 3 days. Never fails the
workflow; problems become warnings.
State: content/yt_comments.json, mirrored in review/yt_comments.json (the daily
YouTube run only commits review/); both are merged when read.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from src.atomic_state import load_json as _atomic_load_json, save_json as _atomic_save_json

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "content" / "yt_comments.json"
MIRROR = ROOT / "review" / "yt_comments.json"
BANK = ROOT / "content" / "mysteries.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
MAX_AGE = timedelta(days=3)
WAIT_STEP = 150      # seconds between re-checks while a scheduled Short is still flipping public
WAIT_TRIES = 3
QUESTIONS = [
    "What's your theory? The best answer gets pinned 📌",
    "Be honest: what do you think REALLY happened? 👇 Best theory gets pinned 📌",
    "If this was your case, where would you start? 🕵️ Best answer gets pinned 📌",
    "Accident, crime, or something stranger? Vote below 👇 Best answer gets pinned 📌",
]


def _read(path: Path) -> dict:
    data = _atomic_load_json(path, {})
    return data if isinstance(data, dict) else {}


def load_state(path: Path = STATE) -> dict:
    state = _read(path)
    if path == STATE:
        other = _read(MIRROR)
        done = list(dict.fromkeys(list(state.get("commented", [])) + list(other.get("commented", []))))
        state["commented"] = done[-200:]
        if str((other.get("last") or {}).get("at", "")) > str((state.get("last") or {}).get("at", "")):
            state["last"] = other["last"]
    return state


def save_state(state: dict, path: Path = STATE) -> None:
    targets = [path, MIRROR] if path == STATE else [path]
    for target in targets:
        _atomic_save_json(target, state)


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def find_story(title: str, bank_path: Path = BANK) -> dict | None:
    try:
        stories = json.loads(bank_path.read_text(encoding="utf-8")).get("stories", [])
    except Exception:
        return None
    want = _norm(re.sub(r"#\w+", "", title))
    for s in stories:
        if _norm(s.get("title")) == want:
            try:  # the comment challenge lives with the rewritten narration
                extra = json.loads((bank_path.parent / "mysteries_override.json").read_text(encoding="utf-8"))
                s = dict(s, **{k: v for k, v in (extra.get("stories", {}).get(s.get("id")) or {}).items()
                               if k == "challenge"})
            except Exception:
                pass
            return s
    return None


def comment_text(video_id: str, title: str, story: dict | None = None) -> str:
    key = (story or {}).get("id") or video_id
    question = QUESTIONS[int(hashlib.sha1(key.encode()).hexdigest()[:4], 16) % len(QUESTIONS)]
    challenge = str((story or {}).get("challenge") or "").strip()
    if challenge:  # story-specific mind challenge (A/B/C), written with the story
        question = challenge
    clean = re.sub(r"\s*#\w+", "", str(title or "")).strip()
    return f"🕯 {clean}\n\n{question}" if clean else question


def pick_video(videos: list[dict], state: dict, now=None) -> dict | None:
    """Newest public video, at most MAX_AGE old, not commented yet."""
    now = now or datetime.now(timezone.utc)
    done = set(state.get("commented", []))
    best = None
    for v in videos:
        if v.get("id") in done or (v.get("status") or {}).get("privacyStatus") != "public":
            continue
        try:
            published = datetime.fromisoformat(str(v["snippet"]["publishedAt"]).replace("Z", "+00:00"))
        except Exception:
            continue
        if now - published > MAX_AGE:
            continue
        if best is None or published > best[0]:
            best = (published, v)
    return best[1] if best else None


def pending_publish(videos: list[dict], state: dict, now=None) -> bool:
    """A not-yet-commented upload whose scheduled publish time is near (YouTube can lag)."""
    now = now or datetime.now(timezone.utc)
    done = set(state.get("commented", []))
    for v in videos:
        status = v.get("status") or {}
        if v.get("id") in done or status.get("privacyStatus") == "public" or not status.get("publishAt"):
            continue
        try:
            at = datetime.fromisoformat(str(status["publishAt"]).replace("Z", "+00:00"))
        except Exception:
            continue
        if timedelta(minutes=-20) <= now - at <= timedelta(hours=3):
            return True
    return False


def describe(videos: list[dict]) -> str:
    parts = []
    for v in videos[:4]:
        st = v.get("status") or {}
        parts.append(f"{v.get('id')}:{st.get('privacyStatus')}" + (f"@{st['publishAt']}" if st.get("publishAt") else ""))
    return ", ".join(parts) or "no uploads"


def client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from src.youtube_uploader import load_credential_info
    creds = Credentials.from_authorized_user_info(load_credential_info(), SCOPES)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def recent_uploads(youtube, limit: int = 8) -> list[dict]:
    ch = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = ch.get("items") or []
    if not items:
        raise RuntimeError("no channel for this token")
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    pl = youtube.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=limit).execute()
    ids = [i["contentDetails"]["videoId"] for i in pl.get("items") or []]
    if not ids:
        return []
    return youtube.videos().list(part="snippet,status", id=",".join(ids)).execute().get("items") or []


def main() -> int:
    state = load_state()
    try:
        youtube = client()
        videos = recent_uploads(youtube)
        video = pick_video(videos, state)
        tries = 0
        while not video and tries < WAIT_TRIES and pending_publish(videos, state):
            tries += 1
            print(f"YT COMMENT: newest Short not public yet, re-checking in {WAIT_STEP}s ({tries}/{WAIT_TRIES})")
            time.sleep(WAIT_STEP)
            videos = recent_uploads(youtube)
            video = pick_video(videos, state)
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}"
        hint = (" The token has no comment permission: make a new refresh token with the "
                "youtube.force-ssl scope.") if re.search(r"scope|insufficient|403", text, re.I) else ""
        state["last_check"] = {"at": datetime.now(timezone.utc).isoformat(), "result": text[:200]}
        save_state(state)
        print(f"::warning title=YouTube comment skipped::{text[:300]}{hint}")
        return 0
    if not video:
        state["last_check"] = {"at": datetime.now(timezone.utc).isoformat(),
                               "result": "no new public video: " + describe(videos)[:200]}
        save_state(state)
        print(f"YT COMMENT: no new public video to comment on ({describe(videos)})")
        return 0
    vid, title = video["id"], video["snippet"].get("title", "")
    text = comment_text(vid, title, find_story(title))
    state["commented"] = (list(state.get("commented", [])) + [vid])[-200:]
    try:
        youtube.commentThreads().insert(part="snippet", body={"snippet": {
            "videoId": vid, "topLevelComment": {"snippet": {"textOriginal": text}}}}).execute()
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        hint = (" Comments are turned off: YouTube Studio > Settings > Upload defaults > Advanced > Comments."
                if "commentsDisabled" in msg or "disabled" in msg.lower() else "")
        state["last"] = {"video": vid, "error": msg[:200], "at": datetime.now(timezone.utc).isoformat()}
        # The id is marked before the call so a timeout (the comment may have gone through)
        # never posts twice. A clear refusal from YouTube (HTTP 4xx) means nothing was
        # posted: unmark it so the next run can try again.
        status = getattr(getattr(exc, "resp", None), "status", None)
        try:
            status = int(status)
        except (TypeError, ValueError):
            status = None
        if status is not None and 400 <= status < 500:
            state["commented"] = [v for v in state.get("commented", []) if v != vid]
        save_state(state)
        print(f"::warning title=YouTube comment failed::{msg[:300]}{hint}")
        return 0
    state["last"] = {"video": vid, "at": datetime.now(timezone.utc).isoformat()}
    save_state(state)
    print(f"YT COMMENT: posted on https://youtu.be/{vid} -> {text.splitlines()[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
