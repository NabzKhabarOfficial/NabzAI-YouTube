"""Claim-guarded production entry point for YouTube upload."""
from __future__ import annotations
import hashlib, json, os, sys
from pathlib import Path
from src import youtube_uploader
from src.production_state import begin_claim, mark_ambiguous, mark_failed, mark_succeeded
ROOT = Path(__file__).resolve().parents[1]; CLAIMS = ROOT / "content" / "publication_claims.json"

def _identity(root):
    story_id = ""
    try: story_id = str((json.loads((root / "story.json").read_text(encoding="utf-8")) or {}).get("id") or "").strip()
    except (OSError, ValueError): pass
    video = next((root / n for n in ("final_short.mp4", "final_film.mp4") if (root / n).exists()), None)
    if video is None: raise RuntimeError(f"no final video in {root}")
    return story_id or root.name, hashlib.sha256(video.read_bytes()).hexdigest()[:24]

def _quality_gate(root):
    report = root / "quality.json"
    if not report.exists(): raise RuntimeError("required quality report is missing")
    data = json.loads(report.read_text(encoding="utf-8"))
    if data.get("passed") is not True or not all((data.get("checks") or {}).values()): raise RuntimeError("media quality gate failed")
    if os.getenv("NABZ_REQUIRE_GEMINI_VOICE", "1") == "1" and not str(data.get("voice") or "").startswith("gemini"): raise RuntimeError("required Gemini voice gate failed")

def run(root, privacy="private", publish_at=None):
    path = Path(root); _quality_gate(path); story, digest = _identity(path)
    key, fresh = begin_claim(CLAIMS, "youtube_upload", story, digest, metadata={"provider":"youtube","story_id":story,"video_sha256_24":digest})
    if not fresh: raise RuntimeError("YouTube publication claim already exists; reconcile before rerun")
    try: video_id = youtube_uploader.upload_from_metadata(path, privacy, publish_at)
    except Exception as exc:
        text = str(exc).lower()
        (mark_failed if any(w in text for w in ("credentials", "no youtube credentials", "invalid json", "client_id")) else mark_ambiguous)(CLAIMS, key, str(exc)); raise
    if not video_id: mark_ambiguous(CLAIMS, key, "YouTube returned no video id"); raise RuntimeError("YouTube upload returned no video id")
    mark_succeeded(CLAIMS, key, video_id); print(f"YOUTUBE_CLAIM_CONFIRMED: {key}"); return video_id

def main():
    if len(sys.argv) < 2: raise SystemExit("usage: python -m src.guarded_youtube_upload <output-root>")
    vid = run(sys.argv[1], os.getenv("YOUTUBE_VISIBILITY", "private"), youtube_uploader.auto_publish_at())
    print("YOUTUBE_VIDEO_ID:", vid); print("YOUTUBE_URL: https://youtu.be/" + vid); return 0

if __name__ == "__main__": raise SystemExit(main())
