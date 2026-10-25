"""Claim-guarded production entry point for YouTube upload.

The YouTube API has no safe client-side retry for videos.insert: a lost response
may mean the video already exists. This entry point therefore blocks every
second insert attempt in one run and records the claim ambiguous instead of
creating a second video.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from src import youtube_uploader
from src.production_state import begin_claim, load_json, mark_ambiguous, mark_failed, mark_succeeded

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "content" / "publication_claims.json"


def _identity(root: Path) -> tuple[str, str]:
    story_id = ""
    try:
        value = json.loads((root / "story.json").read_text(encoding="utf-8"))
        story_id = str(value.get("id") or value.get("story_id") or "").strip()
    except (OSError, ValueError):
        pass
    video = next((root / name for name in ("final_short.mp4", "final_film.mp4") if (root / name).exists()), None)
    if video is None:
        raise RuntimeError(f"no final video in {root}")
    digest = hashlib.sha256(video.read_bytes()).hexdigest()[:24]
    return story_id or root.name, digest


def _quality_gate(root: Path) -> None:
    report = root / "quality.json"
    if not report.exists():
        raise RuntimeError("required quality report is missing")
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"quality report is invalid: {type(exc).__name__}") from None
    if data.get("passed") is not True or not all((data.get("checks") or {}).values()):
        raise RuntimeError("media quality gate failed")
    voice = str(data.get("voice") or "")
    required = os.getenv("NABZ_REQUIRE_VOICE", "kokoro").strip().lower()
    allowed = {"kokoro": voice.startswith("kokoro:"), "gemini": voice.startswith("gemini:"),
               "edge": voice.startswith("edge:"), "any": voice.startswith(("kokoro:", "gemini:", "edge:"))}
    if not allowed.get(required, False):
        raise RuntimeError(f"required voice gate failed: required={required}, generated={voice or 'missing'}")


def _existing_story_claim(story_id: str) -> dict | None:
    state = load_json(CLAIMS, {})
    for claim in (state.get("claims") or {}).values():
        if not isinstance(claim, dict):
            continue
        metadata = claim.get("metadata") or {}
        if metadata.get("provider") == "youtube" and metadata.get("story_id") == story_id:
            return claim
    return None


def _single_insert_only():
    """Install a per-run circuit breaker around videos.insert.

    This is deliberately conservative. Even a deterministic scheduling rejection
    is not retried here because the response may have been lost after acceptance.
    Reconciliation is safer than a second external create.
    """
    original = youtube_uploader._insert
    calls = {"count": 0}

    def guarded(youtube, body, video_path):
        calls["count"] += 1
        if calls["count"] > 1:
            raise RuntimeError("second YouTube videos.insert blocked; reconcile the first outcome")
        return original(youtube, body, video_path)

    youtube_uploader._insert = guarded
    return original, calls


def run(root: str, privacy: str = "private", publish_at: str | None = None) -> str:
    path = Path(root)
    if not path.is_absolute():
        path = ROOT / path
    _quality_gate(path)
    story_id, digest = _identity(path)
    existing = _existing_story_claim(story_id)
    if existing:
        status = str(existing.get("status") or "pending")
        external_id = str(existing.get("external_id") or "")
        raise RuntimeError(f"YouTube story already has a publication claim: status={status}, external_id={external_id or 'none'}. Reconcile before rerun.")
    key, fresh = begin_claim(CLAIMS, "youtube_upload", story_id, digest,
                             metadata={"provider": "youtube", "story_id": story_id,
                                       "video_sha256_24": digest, "publish_at": publish_at or ""})
    if not fresh:
        raise RuntimeError("YouTube publication claim already exists; reconcile before rerun")
    original_insert, calls = _single_insert_only()
    try:
        video_id = youtube_uploader.upload_from_metadata(path, privacy, publish_at)
    except Exception as exc:
        text = str(exc).lower()
        if any(word in text for word in ("credentials", "no youtube credentials", "invalid json", "client_id")):
            mark_failed(CLAIMS, key, str(exc))
        else:
            mark_ambiguous(CLAIMS, key, f"upload outcome unknown after {calls['count']} insert attempt(s): {type(exc).__name__}: {exc}")
        raise
    finally:
        youtube_uploader._insert = original_insert
    if not video_id:
        mark_ambiguous(CLAIMS, key, "YouTube returned no video id")
        raise RuntimeError("YouTube upload returned no video id")
    mark_succeeded(CLAIMS, key, video_id)
    print(f"YOUTUBE_CLAIM_CONFIRMED: {key}")
    return video_id


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m src.guarded_youtube_upload <output-root>")
    video_id = run(sys.argv[1], os.getenv("YOUTUBE_VISIBILITY", "private"), youtube_uploader.auto_publish_at())
    print("YOUTUBE_VIDEO_ID:", video_id)
    print("YOUTUBE_URL: https://youtu.be/" + video_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
