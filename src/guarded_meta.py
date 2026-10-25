"""Claim-guarded adapter for the real Meta/Instagram Story publisher."""
from __future__ import annotations

from pathlib import Path

from instagram import publisher
from src.production_state import begin_claim, mark_ambiguous, mark_failed, mark_succeeded

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "content" / "publication_claims.json"


def publish_story(image_url: str = "", video_url: str = "", *, dry_run: bool = True) -> dict:
    media_url = image_url or video_url
    media_kind = "image" if image_url else "video"
    key, fresh = begin_claim(CLAIMS, "meta_story", media_kind, media_url,
                              metadata={"provider": "meta", "media_type": "STORIES", "media_kind": media_kind})
    if not fresh:
        raise RuntimeError("Meta Story claim already exists; reconcile content/publication_claims.json before rerun")
    try:
        result = publisher.publish_story(image_url=image_url, video_url=video_url, dry_run=dry_run)
    except publisher.InstagramPublishError as exc:
        text = str(exc).lower()
        if "missing required" in text or "exactly one" in text:
            mark_failed(CLAIMS, key, str(exc))
        else:
            mark_ambiguous(CLAIMS, key, f"Meta Story outcome unknown: {exc}")
        raise
    except Exception as exc:
        mark_ambiguous(CLAIMS, key, f"Meta Story outcome unknown: {type(exc).__name__}: {exc}")
        raise
    if result.get("published") and result.get("media_id"):
        mark_succeeded(CLAIMS, key, str(result["media_id"]))
    elif result.get("dry_run"):
        mark_succeeded(CLAIMS, key, "dry-run")
    else:
        mark_ambiguous(CLAIMS, key, "Meta returned no definitive publication id")
        raise RuntimeError("Meta Story publication was not confirmed")
    return result
