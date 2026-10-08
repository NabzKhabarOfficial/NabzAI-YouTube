"""Package setup.

Reel-only rescue: running the daily workflow with story_id "reel:<id>" rebuilds the
Persian Instagram reel of a Short that is ALREADY on YouTube, without uploading it
again and without touching the story state. Only allowed for the latest built story.
"""
import json
import os
import sys
from pathlib import Path


def _reel_only() -> None:
    if "pytest" in sys.modules:
        return
    raw = os.getenv("NABZ_MYSTERY_ID", "").strip()
    if not raw:
        try:
            event = json.loads(Path(os.getenv("GITHUB_EVENT_PATH", "")).read_text(encoding="utf-8"))
            raw = str((event.get("inputs") or {}).get("story_id") or "").strip()
        except Exception:
            return
    if not raw.lower().startswith("reel:"):
        return
    rid = raw.split(":", 1)[1].strip()
    try:
        state = json.loads((Path(__file__).resolve().parents[1] / "content" / "published.json")
                           .read_text(encoding="utf-8"))
        latest = (state.get("mysteries") or [""])[-1]
    except Exception:
        latest = ""
    if not rid or rid != latest:
        print(f"::error title=Reel-only refused::{rid!r} is not the latest built story ({latest!r})", flush=True)
        return
    os.environ.update({"NABZ_REEL_ONLY": "1", "NABZ_MYSTERY_ID": rid,
                       "NABZ_PRECHECK_YOUTUBE": "0", "NABZ_RECORD_STORY": "0"})
    print(f"REEL-ONLY RUN for {rid}: Persian reel only, no YouTube upload, state unchanged.", flush=True)


_reel_only()
