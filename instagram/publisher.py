"""Official Meta publisher with a Story-specific media-container flow."""
from __future__ import annotations
import os, time
from typing import Any
import requests

GRAPH_BASE = "https://graph.facebook.com"

class InstagramPublishError(RuntimeError):
    pass

def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise InstagramPublishError(f"Missing required environment variable: {name}")
    return value

def _version() -> str:
    return os.getenv("INSTAGRAM_API_VERSION", "v23.0").strip()

def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    last = None
    is_mutation = method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
    for attempt in range(3):
        try:
            response = requests.request(method, url, timeout=30, **kwargs)
            if is_mutation and response.status_code in (500, 502, 503, 504):
                raise InstagramPublishError(
                    f"Ambiguous {method.upper()} response (HTTP {response.status_code}); automatic retry blocked"
                )
            if response.status_code not in (429, 500, 502, 503, 504):
                return response
            last = response
            if attempt < 2:
                time.sleep(min(2 ** attempt, 8))
        except requests.RequestException:
            # The server may have accepted a mutation before its response was lost.
            # Never retry a create/publish/delete operation on a transport exception.
            if is_mutation:
                raise InstagramPublishError(
                    f"Ambiguous {method.upper()} transport outcome; automatic retry blocked"
                ) from None
            if attempt == 2:
                raise InstagramPublishError("Request transport failed after bounded retries") from None
            time.sleep(min(2 ** attempt, 8))
    if isinstance(last, requests.Response):
        return last
    raise InstagramPublishError("Request failed after bounded retries")

def create_story(image_url: str = "", video_url: str = "", api_version: str | None = None) -> str:
    if bool(image_url) == bool(video_url):
        raise InstagramPublishError("Provide exactly one public image_url or video_url")
    user_id = _require("INSTAGRAM_USER_ID")
    token = _require("INSTAGRAM_ACCESS_TOKEN")
    data = {"media_type": "STORIES", "access_token": token}
    data["image_url" if image_url else "video_url"] = image_url or video_url
    response = _request("POST", f"{GRAPH_BASE}/{api_version or _version()}/{user_id}/media", data=data)
    response.raise_for_status()
    creation_id = response.json().get("id")
    if not creation_id:
        raise InstagramPublishError(f"Instagram did not return a Story container id: {response.text[:500]}")
    return creation_id

def wait_until_ready(creation_id: str, api_version: str | None = None, attempts: int = 12) -> None:
    token = _require("INSTAGRAM_ACCESS_TOKEN")
    for _ in range(attempts):
        response = _request("GET", f"{GRAPH_BASE}/{api_version or _version()}/{creation_id}", params={"fields":"status_code,status", "access_token":token})
        response.raise_for_status()
        data = response.json()
        status = data.get("status_code")
        if status in ("FINISHED", "PUBLISHED"):
            return
        if status in ("ERROR", "EXPIRED"):
            raise InstagramPublishError(data.get("status") or f"Story container state: {status}")
        time.sleep(5)
    raise InstagramPublishError("Instagram Story media container did not become ready in time")

def publish(creation_id: str, api_version: str | None = None) -> str:
    user_id = _require("INSTAGRAM_USER_ID")
    token = _require("INSTAGRAM_ACCESS_TOKEN")
    response = _request("POST", f"{GRAPH_BASE}/{api_version or _version()}/{user_id}/media_publish", data={"creation_id":creation_id,"access_token":token})
    response.raise_for_status()
    media_id = response.json().get("id")
    if not media_id:
        raise InstagramPublishError(f"Instagram did not return a published media id: {response.text[:500]}")
    return media_id

def publish_story(image_url: str = "", video_url: str = "", dry_run: bool = True) -> dict[str, Any]:
    if dry_run:
        if bool(image_url) == bool(video_url):
            raise InstagramPublishError("Dry-run still requires exactly one media URL")
        return {"published": False, "dry_run": True, "media_type": "STORIES"}
    creation_id = create_story(image_url, video_url)
    wait_until_ready(creation_id)
    return {"published": True, "media_id": publish(creation_id)}

# Backward-compatible feed image helper.
def create_media(image_url: str, caption: str, api_version: str | None = None) -> str:
    user_id, token = _require("INSTAGRAM_USER_ID"), _require("INSTAGRAM_ACCESS_TOKEN")
    response = _request("POST", f"{GRAPH_BASE}/{api_version or _version()}/{user_id}/media", data={"image_url":image_url,"caption":caption,"access_token":token})
    response.raise_for_status()
    return response.json().get("id") or (_ for _ in ()).throw(InstagramPublishError("Missing creation id"))
