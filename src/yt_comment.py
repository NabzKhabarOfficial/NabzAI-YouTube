"""First comment on each new NABZ Mysteries Short, posted automatically.

Runs from .github/workflows/yt-comment.yml shortly after the 22:30 Tehran
publish time (cron-job.org calls workflow_dispatch). It finds the newest
public upload of the channel that has not been commented yet and posts one
story-specific question, so viewers have something to answer. YouTube's API
cannot pin comments: the owner pins it from the app.

Needs a refresh token that includes the youtube.force-ssl scope (the upload
token alone is not enough). Rules: at most one comment per run, never twice
on the same video, only public videos from the last 3 days. Never fails the
workflow; problems become warnings.
State: content/yt_comments.json.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "content" / "yt_comments.json"
BANK = ROOT / "content" / "mysteries.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
MAX_AGE = timedelta(days=3)
QUESTIONS = [
    "What's your theory? The best answer gets pinned 📌",
    "Be honest: what do you think REALLY happened? 👇 Best theory gets pinned 📌",
    "If this was your case, where would you start? 🕵️ Best answer gets pinned 📌",
    "Accident, crime, or something stranger? Vote below 👇 Best answer gets pinned 📌",
]


def load_state(path: Path = STATE) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(state: dict, path: Path = STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
            return s
    return None


def comment_text(video_id: str, title: str, story: dict | None = None) -> str:
    key = (story or {}).get("id") or video_id
    question = QUESTIONS[int(hashlib.sha1(key.encode()).hexdigest()[:4], 16) % len(QUESTIONS)]
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
        video = pick_video(recent_uploads(youtube), state)
    except Exception as exc:
        text = f"{type(exc).__name__}: {exc}"
        hint = (" The token has no comment permission: make a new refresh token with the "
                "youtube.force-ssl scope.") if re.search(r"scope|insufficient|403", text, re.I) else ""
        print(f"::warning title=YouTube comment skipped::{text[:300]}{hint}")
        return 0
    if not video:
        print("YT COMMENT: no new public video to comment on")
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
        save_state(state)
        print(f"::warning title=YouTube comment failed::{msg[:300]}{hint}")
        return 0
    state["last"] = {"video": vid, "at": datetime.now(timezone.utc).isoformat()}
    save_state(state)
    print(f"YT COMMENT: posted on https://youtu.be/{vid} -> {text.splitlines()[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
