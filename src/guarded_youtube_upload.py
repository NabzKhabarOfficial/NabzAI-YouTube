"""Claim-guarded production entry point for YouTube upload."""
from __future__ import annotations
import hashlib, json, os, sys
from pathlib import Path
from src import youtube_uploader
from src.production_state import begin_claim, load_json, mark_ambiguous, mark_failed, mark_succeeded
ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "content" / "publication_claims.json"

def _identity(root: Path) -> tuple[str, str]:
    story_id = ""
    try:
        value = json.loads((root / "story.json").read_text(encoding="utf-8")); story_id = str(value.get("id") or value.get("story_id") or "").strip()
    except (OSError, ValueError): pass
    video = next((root / name for name in ("final_short.mp4", "final_film.mp4") if (root / name).exists()), None)
    if video is None: raise RuntimeError(f"no final video in {root}")
    return story_id or root.name, hashlib.sha256(video.read_bytes()).hexdigest()[:24]

def _quality_gate(root: Path) -> None:
    report = root / "quality.json"
    if not report.exists(): raise RuntimeError("required quality report is missing")
    try: data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc: raise RuntimeError(f"quality report is invalid: {type(exc).__name__}") from None
    if data.get("passed") is not True or not all((data.get("checks") or {}).values()): raise RuntimeError("media quality gate failed")
    voice = str(data.get("voice") or ""); required = os.getenv("NABZ_REQUIRE_VOICE", "kokoro").strip().lower()
    allowed = {"kokoro": voice.startswith("kokoro:"), "gemini": voice.startswith("gemini:"), "edge": voice.startswith("edge:"), "any": voice.startswith(("kokoro:", "gemini:", "edge:"))}
    if not allowed.get(required, False): raise RuntimeError(f"required voice gate failed: required={required}, generated={voice or 'missing'}")

def _existing_story_claim(story_id: str) -> dict | None:
    for claim in (load_json(CLAIMS, {}).get("claims") or {}).values():
        if not isinstance(claim, dict): continue
        metadata = claim.get("metadata") or {}
        if metadata.get("provider") == "youtube" and metadata.get("story_id") == story_id and claim.get("status") != "failed": return claim
    return None

def _safe_scheduling_rejection(exc: Exception) -> bool:
    resp = getattr(exc, "resp", None); status = getattr(resp, "status", None); text = str(exc).lower()
    return status in (400, 422) and any(x in text for x in ("publishat", "publish at", "scheduled", "schedule"))

def _single_insert_only():
    original = youtube_uploader._insert; state = {"count": 0, "safe_fallback": False, "expected_schedule": False}
    def guarded(youtube, body, video_path):
        state["count"] += 1
        state["expected_schedule"] = state["expected_schedule"] or bool((body.get("status") or {}).get("publishAt"))
        if state["count"] > 1 and not state["safe_fallback"]: raise RuntimeError("second YouTube videos.insert blocked; reconcile the first outcome")
        try: response = original(youtube, body, video_path)
        except Exception as exc:
            if state["count"] == 1 and _safe_scheduling_rejection(exc): state["safe_fallback"] = True
            raise
        if state["expected_schedule"] and not (response or {}).get("status", {}).get("publishAt"):
            raise RuntimeError("YouTube upload returned no publishAt; scheduled claim is not confirmed")
        return response
    youtube_uploader._insert = guarded
    return original, state

def run(root: str, privacy: str = "private", publish_at: str | None = None) -> str:
    path = Path(root); path = path if path.is_absolute() else ROOT / path
    _quality_gate(path); story_id, digest = _identity(path)
    if _existing_story_claim(story_id): raise RuntimeError("YouTube story already has a publication claim; reconcile before rerun")
    key, fresh = begin_claim(CLAIMS, "youtube_upload", story_id, digest, metadata={"provider":"youtube","story_id":story_id,"video_sha256_24":digest,"publish_at":publish_at or ""})
    if not fresh: raise RuntimeError("YouTube publication claim already exists; reconcile before rerun")
    original_insert, state = _single_insert_only()
    try: video_id = youtube_uploader.upload_from_metadata(path, privacy, publish_at)
    except Exception as exc:
        text = str(exc).lower()
        if any(word in text for word in ("credentials", "no youtube credentials", "invalid json", "client_id")): mark_failed(CLAIMS, key, str(exc))
        else: mark_ambiguous(CLAIMS, key, f"upload outcome unknown after {state['count']} insert attempt(s): {type(exc).__name__}: {exc}")
        raise
    finally: youtube_uploader._insert = original_insert
    if not video_id: mark_ambiguous(CLAIMS, key, "YouTube upload returned no video id"); raise RuntimeError("YouTube upload returned no video id")
    if publish_at and state["safe_fallback"]:
        mark_ambiguous(CLAIMS, key, "YouTube scheduling was rejected and fallback produced a private upload; schedule not confirmed")
        raise RuntimeError("YouTube upload exists but scheduling was not confirmed; manual reconciliation required")
    if publish_at and not state["expected_schedule"]:
        mark_ambiguous(CLAIMS, key, "scheduled upload did not carry an expected publishAt")
        raise RuntimeError("scheduled YouTube claim missing publishAt confirmation")
    mark_succeeded(CLAIMS, key, video_id); print(f"YOUTUBE_CLAIM_CONFIRMED: {key}"); return video_id

def main() -> int:
    if len(sys.argv) < 2: raise SystemExit("usage: python -m src.guarded_youtube_upload <output-root>")
    video_id = run(sys.argv[1], os.getenv("YOUTUBE_VISIBILITY", "private"), youtube_uploader.auto_publish_at()); print("YOUTUBE_VIDEO_ID:", video_id); print("YOUTUBE_URL: https://youtu.be/" + video_id); return 0
if __name__ == "__main__": raise SystemExit(main())
