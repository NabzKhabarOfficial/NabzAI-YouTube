"""Claim-guarded Buffer entry point with per-operation idempotency.

Every real Buffer mutation gets its own durable claim before the external
request. Confirmed claims are reused; pending or ambiguous claims hard-stop.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from src import ig_buffer
from src.idempotency import claim, finish, fingerprint, get

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "content" / "publication_claims.json"
BUFFER_STATE = ROOT / "content" / "ig_buffer_state.json"


def _identity(kind: str, *parts: object) -> str:
    raw = "\x1f".join(str(part or "").strip() for part in parts)
    return hashlib.sha256((kind + "\x1f" + raw).encode("utf-8")).hexdigest()[:32]


def _reserve(kind: str, identity: str, metadata: dict):
    key = fingerprint("buffer_" + kind, identity)
    current = get(CLAIMS, key)
    if current is not None:
        if current.status == "succeeded":
            return key, {"id": current.external_id, "_already_confirmed": True}
        raise RuntimeError(f"Buffer {kind} claim is {current.status}; manual reconciliation required: {key}")
    if not claim(CLAIMS, key, metadata):
        raise RuntimeError(f"Buffer {kind} claim appeared concurrently; manual reconciliation required: {key}")
    return key, None


def _confirmed(key: str, post_id: str) -> dict:
    finish(CLAIMS, key, post_id, status="succeeded")
    return {"id": post_id}


def _wrap_mutations() -> None:
    if getattr(ig_buffer, "_NABZ_GUARDED", False):
        return

    original_post = ig_buffer.create_post
    original_story = ig_buffer.create_story
    original_carousel = ig_buffer.create_carousel

    def guarded_post(channel, text, video_url, due):
        identity = _identity("reel", video_url, due.isoformat(), text)
        key, cached = _reserve("reel", identity, {"provider": "buffer", "kind": "reel", "identity": identity, "video_url": video_url, "due": due.isoformat()})
        if cached:
            return cached
        try:
            post = original_post(channel, text, video_url, due)
        except Exception as exc:
            finish(CLAIMS, key, "", status="ambiguous")
            raise RuntimeError(f"Buffer reel outcome ambiguous for claim {key}: {exc}") from exc
        post_id = str((post or {}).get("id") or "")
        if not post_id:
            finish(CLAIMS, key, "", status="ambiguous")
            raise RuntimeError(f"Buffer reel returned no post id for claim {key}")
        return _confirmed(key, post_id)

    def guarded_story(channel, video_url, due):
        identity = _identity("story", video_url, due.isoformat())
        key, cached = _reserve("story", identity, {"provider": "buffer", "kind": "story", "identity": identity, "video_url": video_url, "due": due.isoformat()})
        if cached:
            return cached
        try:
            post = original_story(channel, video_url, due)
        except Exception as exc:
            finish(CLAIMS, key, "", status="ambiguous")
            raise RuntimeError(f"Buffer story outcome ambiguous for claim {key}: {exc}") from exc
        post_id = str((post or {}).get("id") or "")
        if not post_id:
            finish(CLAIMS, key, "", status="ambiguous")
            raise RuntimeError(f"Buffer story returned no post id for claim {key}")
        return _confirmed(key, post_id)

    def guarded_carousel(channel, text, image_urls, due):
        identity = _identity("carousel", "|".join(image_urls), due.isoformat(), text)
        key, cached = _reserve("carousel", identity, {"provider": "buffer", "kind": "carousel", "identity": identity, "due": due.isoformat(), "images": list(image_urls)})
        if cached:
            return cached
        try:
            post = original_carousel(channel, text, image_urls, due)
        except Exception as exc:
            finish(CLAIMS, key, "", status="ambiguous")
            raise RuntimeError(f"Buffer carousel outcome ambiguous for claim {key}: {exc}") from exc
        post_id = str((post or {}).get("id") or "")
        if not post_id:
            finish(CLAIMS, key, "", status="ambiguous")
            raise RuntimeError(f"Buffer carousel returned no post id for claim {key}")
        return _confirmed(key, post_id)

    ig_buffer.create_post = guarded_post
    ig_buffer.create_story = guarded_story
    ig_buffer.create_carousel = guarded_carousel
    ig_buffer._NABZ_GUARDED = True


def run() -> int:
    if not os.getenv("BUFFER_API_KEY", "").strip():
        raise RuntimeError("BUFFER_API_KEY is missing; refusing to report a successful Buffer run")
    if not os.getenv("REELS_PAT", "").strip():
        raise RuntimeError("REELS_PAT is missing; refusing to publish without public video hosting")

    _wrap_mutations()
    result = ig_buffer.main()
    state = ig_buffer.load_json(BUFFER_STATE, {})
    if int(state.get("fail_streak", 0) or 0) > 0:
        raise RuntimeError("Buffer recorded a failed run; claims require reconciliation")
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(run())
