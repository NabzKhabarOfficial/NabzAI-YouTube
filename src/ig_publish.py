"""Post the queued Persian mystery Reel to Instagram, once a day, gently.

The daily YouTube run builds output/reel-fa and pushes it to the `ig-queue`
branch. This script (instagram.yml, evening crons) posts it inside the Iranian
evening window. Account-safety rules carried over from NabzKhabar:
  * reuse the saved session only (no automatic password login),
  * at most one post per day,
  * any login/upload refusal pauses everything for 24 hours.
State: content/ig_state.json (committed by the workflow).
"""
from __future__ import annotations

import base64
import inspect
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "content" / "ig_state.json"
SESSION_FILE = ROOT / ".ig_session.json"
TEHRAN = timezone(timedelta(hours=3, minutes=30))
POST_WINDOW = os.getenv("IG_POST_WINDOW", "20:00-23:30")
MAX_POSTS_PER_DAY = int(os.getenv("IG_MAX_POSTS_PER_DAY", "1"))
MAX_QUEUE_AGE_DAYS = 2
PAUSE_HOURS = int(os.getenv("IG_PAUSE_HOURS", "24"))
BLOCK_WORDS = ("challenge", "feedback", "login_required", "loginrequired", "please wait",
               "rate", "spam", "checkpoint", "401", "403", "429")


def now_tehran():
    return datetime.now(TEHRAN)


def in_window(now=None, window=POST_WINDOW):
    try:
        a, b = [tuple(int(x) for x in p.split(":")) for p in window.split("-")]
    except Exception:
        return True
    now = now or now_tehran()
    cur = now.hour * 60 + now.minute
    lo, hi = a[0] * 60 + a[1], b[0] * 60 + b[1]
    return lo <= cur <= hi if lo <= hi else (cur >= lo or cur <= hi)


def load_state():
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_block(exc):
    text = f"{type(exc).__name__} {exc}".lower()
    return any(w in text for w in BLOCK_WORDS)


def pause(state, reason):
    state["paused_until"] = time.time() + PAUSE_HOURS * 3600
    state["pause_reason"] = str(reason)[:300]
    save_state(state)
    until = datetime.fromtimestamp(state["paused_until"], TEHRAN).strftime("%Y-%m-%d %H:%M")
    print(f"IG SAFETY: paused until {until} Tehran ({reason})")


def decide(state, meta, now=None):
    """-> (ok, reason). Pure: no network, easy to test."""
    now = now or now_tehran()
    if not in_window(now):
        return False, f"outside posting window {POST_WINDOW}"
    if time.time() < float(state.get("paused_until", 0) or 0):
        return False, f"safety pause ({state.get('pause_reason', '')})"
    day = now.date().isoformat()
    if int((state.get("daily") or {}).get(day, 0)) >= MAX_POSTS_PER_DAY:
        return False, "daily limit reached"
    if not meta or not meta.get("story_id"):
        return False, "nothing queued"
    if meta["story_id"] in set(state.get("posted", [])):
        return False, f"{meta['story_id']} already posted"
    try:
        built = datetime.fromisoformat(meta.get("built_date", "")).date()
    except Exception:
        return False, "queued reel has no build date"
    if (now.date() - built).days > MAX_QUEUE_AGE_DAYS:
        return False, f"queued reel is stale ({built})"
    return True, "ok"


def login_client():
    from instagrapi import Client
    username = os.getenv("IG_USERNAME", "").strip()
    session_b64 = os.getenv("IG_SESSION_B64", "").strip()
    if not username or not session_b64:
        raise RuntimeError("IG_USERNAME / IG_SESSION_B64 secrets are missing")
    SESSION_FILE.write_bytes(base64.b64decode(session_b64, validate=True))
    client = Client()
    client.load_settings(str(SESSION_FILE))
    if not getattr(client, "user_id", None):
        raise RuntimeError("saved session has no user_id")
    client.user_info(client.user_id)  # validates the session; never logs in with a password
    print("IG: saved session validated and reused without relogin")
    return client


def patch_analyzer(duration, width=1080, height=1920):
    """instagrapi probes clips with moviepy; we already know the numbers."""
    try:
        import instagrapi.mixins.clip as clipmod
        src = inspect.getsource(clipmod)
        found = re.search(r"\n\s*([\w ,()]+?)=\s*analyze_video\(", src)
        if not found or not hasattr(clipmod, "analyze_video"):
            return False
        names = [n.strip(" ()") for n in found.group(1).split(",") if n.strip(" ()")]
        if not names or set(names) - {"thumbnail", "width", "height", "duration"}:
            return False

        def analyze_video(path, thumbnail=None, *args, **kwargs):
            values = {"thumbnail": thumbnail, "width": width, "height": height, "duration": float(duration)}
            return tuple(values[n] for n in names)

        clipmod.analyze_video = analyze_video
        return True
    except Exception as exc:
        print(f"IG: analyzer patch skipped ({type(exc).__name__})")
        return False


def main(queue_dir="ig_queue"):
    queue = Path(queue_dir)
    meta = {}
    try:
        meta = json.loads((queue / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    state = load_state()
    ok, reason = decide(state, meta)
    if not ok:
        print(f"IG: not posting: {reason}")
        return 0
    video, cover, caption_file = queue / "reel.mp4", queue / "cover.jpg", queue / "caption.txt"
    if not (video.exists() and cover.exists() and caption_file.exists()):
        print("IG: queued files incomplete; not posting")
        return 0
    caption = caption_file.read_text(encoding="utf-8")
    try:
        client = login_client()
    except Exception as exc:
        pause(state, f"login refused: {type(exc).__name__}: {exc}")
        return 0
    patch_analyzer(meta.get("duration", 30))
    try:
        media = client.clip_upload(video, caption=caption, thumbnail=cover)
    except Exception as exc:
        # It may have gone through: never retry the same reel.
        state["posted"] = (list(state.get("posted", [])) + [meta["story_id"]])[-200:]
        if is_block(exc):
            pause(state, f"reel upload refused: {type(exc).__name__}: {exc}")
        else:
            save_state(state)
        print(f"IG: upload failed ({type(exc).__name__}: {exc}); not retrying this reel")
        return 0
    day = now_tehran().date().isoformat()
    state["posted"] = (list(state.get("posted", [])) + [meta["story_id"]])[-200:]
    daily = {k: v for k, v in (state.get("daily") or {}).items() if k >= (now_tehran().date() - timedelta(days=7)).isoformat()}
    daily[day] = int(daily.get(day, 0)) + 1
    state["daily"] = daily
    state["last_post"] = {"story_id": meta["story_id"], "media_pk": str(getattr(media, "pk", "")), "at": now_tehran().isoformat()}
    state.pop("pause_reason", None)
    save_state(state)
    print(f"IG: published reel {getattr(media, 'pk', '?')} -> {meta['story_id']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "ig_queue"))
    finally:
        try:
            SESSION_FILE.unlink(missing_ok=True)
        except Exception:
            pass
