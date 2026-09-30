import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def upload_video(
    video_path,
    title,
    description,
    tags,
    token_json,
    privacy_status="private",
    category_id="24",
    thumbnail_path=None,
    contains_synthetic_media=True,
):
    data = json.loads(token_json) if isinstance(token_json, str) else token_json
    creds = Credentials.from_authorized_user_info(data, SCOPES)
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
    # YouTube supports this field for realistic synthetic/altered media.
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
        if not thumb.exists() or thumb.stat().st_size < 10_000:
            raise RuntimeError("Thumbnail file is missing or unexpectedly small.")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumb), mimetype="image/jpeg"),
        ).execute()

    return video_id
