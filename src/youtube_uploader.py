import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
_QUOTES = {"\u201c": '"', "\u201d": '"', "\u201e": '"', "\u00ab": '"', "\u00bb": '"', "\u2018": "'", "\u2019": "'"}

# Daily Shorts go live at 22:30 Tehran: 20:00 London / 21:00 Berlin (Europe evening)
# and 15:00 New York / 12:00 Los Angeles (US afternoon), so both audiences are awake.
TEHRAN = timezone(timedelta(hours=3, minutes=30))
PUBLISH_HOUR, PUBLISH_MINUTE = 22, 30


def _clean(value) -> str:
    text = str(value or "")
    for bad, good in _QUOTES.items():
        text = text.replace(bad, good)
    return text.strip().strip('"').strip()


def next_publish_at(now=None, hour=PUBLISH_HOUR, minute=PUBLISH_MINUTE, min_lead_minutes=60):
    """Next hour:minute Tehran time at least min_lead_minutes away, as YouTube's UTC ISO string."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(TEHRAN)
    target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    while target - local < timedelta(minutes=min_lead_minutes):
        target += timedelta(days=1)
    return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def auto_publish_at(env=None):
    """Scheduled runs, and manual runs left on 'private' (rescue runs when GitHub drops
    a cron), go live at the next 22:30 Tehran. Manual 'unlisted'/'public' runs keep the
    chosen visibility. Set NABZ_AUTO_SCHEDULE=0 to turn it off."""
    env = os.environ if env is None else env
    if env.get("NABZ_AUTO_SCHEDULE", "1") == "0":
        return None
    event = env.get("GITHUB_EVENT_NAME")
    if event == "schedule":
        return next_publish_at()
    if event == "workflow_dispatch" and env.get("YOUTUBE_VISIBILITY", "private") == "private":
        return next_publish_at()
    return None


def load_credential_info(token_json=None, env=None) -> dict:
    """Accepts three separate secrets or one YOUTUBE_TOKEN JSON; tolerant of phone-typed quotes."""
    env = os.environ if env is None else env
    cid = _clean(env.get("YOUTUBE_CLIENT_ID"))
    secret = _clean(env.get("YOUTUBE_CLIENT_SECRET"))
    refresh = _clean(env.get("YOUTUBE_REFRESH_TOKEN"))
    if cid and secret and refresh:
        info = {"client_id": cid, "client_secret": secret, "refresh_token": refresh}
    else:
        raw = token_json if token_json is not None else env.get("YOUTUBE_TOKEN", "")
        if isinstance(raw, dict):
            info = dict(raw)
        else:
            text = str(raw or "")
            for bad, good in _QUOTES.items():
                text = text.replace(bad, good)
            text = text.strip()
            if not text:
                raise RuntimeError("No YouTube credentials: set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN secrets.")
            try:
                info = json.loads(text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"YOUTUBE_TOKEN is not valid JSON (position {exc.pos}). "
                                   "Easier fix: use the three separate secrets instead.") from None
        info = {k: _clean(v) for k, v in info.items() if isinstance(v, (str, int, float))}
    info.setdefault("token_uri", TOKEN_URI)
    missing = [k for k in ("client_id", "client_secret", "refresh_token") if not info.get(k)]
    if missing:
        raise RuntimeError("YouTube credentials are missing: " + ", ".join(missing))
    if not info["client_id"].endswith(".apps.googleusercontent.com"):
        raise RuntimeError("client_id does not look like a Google OAuth client id (should end with .apps.googleusercontent.com)")
    if info["client_id"].startswith("http"):
        raise RuntimeError("client_id must not start with http")
    return info


def _insert(youtube, body, video_path):
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return response


def upload_video(
    video_path,
    title,
    description,
    tags,
    token_json=None,
    privacy_status="private",
    category_id="24",
    thumbnail_path=None,
    contains_synthetic_media=True,
    publish_at=None,
):
    info = load_credential_info(token_json)
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    if contains_synthetic_media:
        body["status"]["containsSyntheticMedia"] = True
    if publish_at:
        # YouTube only accepts publishAt on private videos; it flips them public at that time.
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at

    try:
        response = _insert(youtube, body, video_path)
    except Exception as exc:
        if not publish_at:
            raise
        print(f"WARNING: scheduled upload rejected ({exc}); retrying as a plain private upload.")
        body["status"].pop("publishAt", None)
        response = _insert(youtube, body, video_path)
    if not response or not response.get("id"):
        raise RuntimeError("YouTube upload returned no video id.")

    video_id = response["id"]
    status = response.get("status") or {}
    if publish_at:
        if status.get("publishAt"):
            print(f"YOUTUBE_SCHEDULED: goes public at {status['publishAt']} (22:30 Tehran)")
        else:
            print("::warning title=Not scheduled::YouTube kept the video private without a publish time "
                  "(usually an unaudited API project). Publish it in YouTube Studio.")

    if thumbnail_path:
        thumb = Path(thumbnail_path)
        if thumb.exists() and thumb.stat().st_size >= 10_000:
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumb), mimetype="image/jpeg"),
                ).execute()
            except Exception as exc:  # unverified channels cannot set custom thumbnails
                print(f"WARNING: video uploaded but custom thumbnail was rejected: {exc}")
                print("Verify the channel at https://youtube.com/verify to enable custom thumbnails.")

    return video_id


# ---------------------------------------------------------------- Shorts SEO
# YouTube shows the first three description hashtags above the title, but only when the
# title itself has no hashtag. So the title stays clean and the story's own hashtags lead.
GENERIC_TAGS = {"mystery", "unsolved mystery", "unsolved mysteries", "history", "true story", "shorts"}
BASE_HASHTAGS = ["#UnsolvedMysteries", "#Shorts", "#Mystery", "#History", "#TrueStory"]
CTAS = [
    "What's your theory? Drop it in the comments.",
    "Which explanation do you believe? Tell me below.",
    "Could this ever be solved? Leave your best theory below.",
]


def hashtag(text) -> str:
    words = re.findall(r"[A-Za-z0-9]+", re.sub(r"['\u2019]", "", str(text or "")))
    if not words or all(w.isdigit() for w in words):
        return ""
    return "#" + "".join(w if w.isupper() else w[:1].upper() + w[1:] for w in words)


def story_hashtags(story: dict, limit: int = 8) -> list:
    out, seen = [], set()
    specific = [t for t in story.get("tags", []) if str(t).strip().lower() not in GENERIC_TAGS]
    for tag in [hashtag(t) for t in specific[:2]] + BASE_HASHTAGS:
        if tag and len(tag) <= 30 and tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return out[:limit]


def shorts_metadata(story: dict) -> dict:
    title = re.sub(r"\s*#\w+", "", str(story["title"])).strip()
    pick = int(hashlib.sha1(story["id"].encode()).hexdigest()[:4], 16) % len(CTAS)
    description = (
        f"{story['beats'][0]['text']}\n\n"
        f"{CTAS[pick]}\n\n"
        "NABZ Mysteries: one real unsolved mystery, explained in under a minute. Follow for a new one every day.\n"
        "Visuals are AI-generated illustrations; narration uses an AI voice.\n\n"
        + " ".join(story_hashtags(story))
    )
    tags, seen = [], set()
    for t in list(story.get("tags", [])) + ["mystery", "unsolved mysteries", "shorts", "NABZ Mysteries"]:
        if str(t).lower() not in seen:
            seen.add(str(t).lower())
            tags.append(str(t))
    return {"story_id": story["id"], "title": title[:100], "description": description,
            "tags": tags, "category_id": "27"}


def upload_from_metadata(root, privacy_status="private", publish_at=None):
    root = Path(root)
    meta = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    video = next((root / n for n in ("final_short.mp4", "final_film.mp4") if (root / n).exists()), None)
    if video is None:
        raise RuntimeError(f"no final video in {root}")
    story_file = root / "story.json"
    if video.name == "final_short.mp4" and story_file.exists():
        try:
            story = json.loads(story_file.read_text(encoding="utf-8"))
            if story.get("beats") and story.get("title"):
                meta = shorts_metadata(story)
                (root / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                print("SHORTS_SEO:", meta["title"], "|", meta["description"].splitlines()[-1])
        except Exception as exc:  # never block an upload over metadata polish
            print(f"WARNING: kept original metadata ({type(exc).__name__}: {exc})")
    return upload_video(
        video, meta["title"], meta["description"], meta["tags"],
        privacy_status=privacy_status, category_id=meta.get("category_id", "24"),
        thumbnail_path=root / "thumbnail.jpg", contains_synthetic_media=True,
        publish_at=publish_at,
    )


if __name__ == "__main__":
    import re
    import sys
    try:
        vid = upload_from_metadata(sys.argv[1], os.getenv("YOUTUBE_VISIBILITY", "private"), auto_publish_at())
    except Exception as exc:
        msg = re.sub(r"[\r\n]+", " ", f"{type(exc).__name__}: {exc}")[:1800]
        print(f"::error title=YouTube upload failed::{msg}", flush=True)
        raise
    print("YOUTUBE_VIDEO_ID:", vid)
    print("YOUTUBE_URL: https://youtu.be/" + vid)
