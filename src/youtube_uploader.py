import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
_QUOTES = {"\u201c": '"', "\u201d": '"', "\u201e": '"', "\u00ab": '"', "\u00bb": '"', "\u2018": "'", "\u2019": "'"}


def _clean(value) -> str:
    text = str(value or "")
    for bad, good in _QUOTES.items():
        text = text.replace(bad, good)
    return text.strip().strip('"').strip()


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

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    if not response or not response.get("id"):
        raise RuntimeError("YouTube upload returned no video id.")

    video_id = response["id"]

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


def upload_from_metadata(root, privacy_status="private"):
    root = Path(root)
    meta = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    video = next((root / n for n in ("final_short.mp4", "final_film.mp4") if (root / n).exists()), None)
    if video is None:
        raise RuntimeError(f"no final video in {root}")
    return upload_video(
        video, meta["title"], meta["description"], meta["tags"],
        privacy_status=privacy_status, category_id=meta.get("category_id", "24"),
        thumbnail_path=root / "thumbnail.jpg", contains_synthetic_media=True,
    )


if __name__ == "__main__":
    import re
    import sys
    try:
        vid = upload_from_metadata(sys.argv[1], os.getenv("YOUTUBE_VISIBILITY", "private"))
    except Exception as exc:
        msg = re.sub(r"[\r\n]+", " ", f"{type(exc).__name__}: {exc}")[:1800]
        print(f"::error title=YouTube upload failed::{msg}", flush=True)
        raise
    print("YOUTUBE_VIDEO_ID:", vid)
    print("YOUTUBE_URL: https://youtu.be/" + vid)
