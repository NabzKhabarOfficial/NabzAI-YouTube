"""Post the next due Persian carousel from content/ig_carousels.json.

Runs in instagram.yml before the reel step. Same account-safety rules as the
reels (src.ig_publish): saved session only, shared 24 h pause on any refusal,
never retries a post. Extra carousel rules:
  * only inside the midday window (default 12:00-16:00 Tehran), so it never
    sits next to the evening reel,
  * at most one carousel a day and at least MIN_GAP_DAYS between carousels,
  * a post goes out on/after its publish_on date, oldest first.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import os
from datetime import date
from pathlib import Path

from src import ig_publish as ig
from src.carousel_fa import render_post

ROOT = ig.ROOT
BANK = ROOT / "content" / "ig_carousels.json"
OUT = ROOT / "output" / "carousel"
WINDOW = os.getenv("IG_CAROUSEL_WINDOW", "12:00-16:00")
MIN_GAP_DAYS = int(os.getenv("IG_CAROUSEL_MIN_GAP_DAYS", "3"))


def load_posts(folder: Path = BANK.parent) -> list[dict]:
    """All content/ig_carousels*.json files, in name order. A later file can
    override a post by id (e.g. {"id": "x", "skip": true} to drop it)."""
    merged: dict = {}
    for path in sorted(folder.glob("ig_carousels*.json")):
        try:
            posts = json.loads(path.read_text(encoding="utf-8")).get("posts", [])
        except Exception as exc:
            print(f"::warning title=Carousel file unreadable::{path.name}: {exc}")
            continue
        for p in posts:
            if p.get("id"):
                merged[p["id"]] = {**merged.get(p["id"], {}), **p}
    return [p for p in merged.values() if not p.get("skip") and p.get("slides")]


def pick(posts, state, now=None):
    """-> (post|None, reason). Pure: no network."""
    now = now or ig.now_tehran()
    if not ig.in_window(now, WINDOW):
        return None, f"outside carousel window {WINDOW}"
    if time.time() < float(state.get("paused_until", 0) or 0):
        return None, f"safety pause ({state.get('pause_reason', '')})"
    done = set(state.get("carousels_posted", []))
    last = (state.get("last_carousel") or {}).get("date")
    if last:
        try:
            if (now.date() - date.fromisoformat(last)).days < MIN_GAP_DAYS:
                return None, f"last carousel {last}; waiting {MIN_GAP_DAYS} days between carousels"
        except ValueError:
            pass
    due = [p for p in posts if p.get("id") and p["id"] not in done
           and str(p.get("publish_on", "9999")) <= now.date().isoformat()]
    if not due:
        return None, "no carousel due"
    due.sort(key=lambda p: str(p.get("publish_on", "")))
    return due[0], "ok"


def main() -> int:
    state = ig.load_state()
    post, reason = pick(load_posts(), state)
    if not post:
        print(f"IG CAROUSEL: not posting: {reason}")
        return 0
    shutil.rmtree(OUT, ignore_errors=True)
    try:
        slides = render_post(post, OUT)
    except Exception as exc:
        print(f"::warning title=Carousel not rendered::{type(exc).__name__}: {exc}")
        return 0
    try:
        client = ig.login_client()
    except Exception as exc:
        ig.pause(state, f"login refused: {type(exc).__name__}: {exc}")
        return 0
    today = ig.now_tehran().date().isoformat()
    state["carousels_posted"] = (list(state.get("carousels_posted", [])) + [post["id"]])[-200:]
    try:
        media = client.album_upload(slides, caption=post["caption"])
    except Exception as exc:
        # It may have gone through: never retry the same carousel.
        state["last_carousel"] = {"id": post["id"], "date": today, "error": str(exc)[:200]}
        if ig.is_block(exc):
            ig.pause(state, f"carousel upload refused: {type(exc).__name__}: {exc}")
        else:
            ig.save_state(state)
        print(f"IG CAROUSEL: upload failed ({type(exc).__name__}: {exc}); not retrying")
        return 0
    state["last_carousel"] = {"id": post["id"], "date": today, "media_pk": str(getattr(media, "pk", ""))}
    ig.save_state(state)
    print(f"IG CAROUSEL: published {getattr(media, 'pk', '?')} -> {post['id']} ({len(slides)} slides)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            ig.SESSION_FILE.unlink(missing_ok=True)
        except Exception:
            pass
