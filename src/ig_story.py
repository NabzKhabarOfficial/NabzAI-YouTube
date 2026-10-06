"""Two automatic Instagram stories a day for «نبض معما».

  teaser  (midday/afternoon, default 13:00-19:30 Tehran): a branded card announcing
          tonight's mystery (title from the queued reel), built here.
  share   (evening, after the reel is up): a card with the reel itself attached
          as a tappable post sticker, so viewers jump straight to the reel.

Interactive stickers (poll / countdown / questions) are left to the human:
they are what make the account look and feel alive.
Same safety as the reels (src.ig_publish): saved session only, the shared
24 h pause on any refusal, at most one teaser and one share per day, and a
story is never retried. Every attempt is logged in state["story_log"] so a
missing story can always be explained from the committed state.
Usage: python -m src.ig_story teaser|share [queue_dir]
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from src import carousel_fa as cf
from src import ig_publish as ig

ROOT = ig.ROOT
OUT = ROOT / "output" / "stories"
SW, SH = 1080, 1920
# The reliable triggers are the 13:05 and 20:05 runs (cron-job.org), so the teaser goes out
# with the midday run and the share story with the evening one.
TEASER_WINDOW = os.getenv("IG_TEASER_WINDOW", "13:00-19:30")
SHARE_WINDOW = os.getenv("IG_SHARE_WINDOW", "20:00-23:59")


def load_meta(queue: Path) -> dict:
    try:
        return json.loads((queue / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def stories_state(state: dict) -> dict:
    st = state.setdefault("stories", {})
    st.setdefault("teaser", [])
    st.setdefault("share", [])
    return st


def note(state: dict, kind: str, result: str, save: bool = True) -> None:
    log = state.setdefault("story_log", {})
    log[kind] = {"at": ig.now_tehran().isoformat(timespec="seconds"), "result": str(result)[:300]}
    if save:
        ig.save_state(state)


def decide(kind: str, state: dict, meta: dict, now=None):
    """-> (ok, reason). Pure: no network."""
    now = now or ig.now_tehran()
    window = TEASER_WINDOW if kind == "teaser" else SHARE_WINDOW
    if not ig.in_window(now, window):
        return False, f"outside {kind} window {window}"
    if time.time() < float(state.get("paused_until", 0) or 0):
        return False, f"safety pause ({state.get('pause_reason', '')})"
    sid = meta.get("story_id")
    if not sid:
        return False, "nothing queued"
    if sid in set((state.get("stories") or {}).get(kind, [])):
        return False, f"{kind} story for {sid} already done"
    today = now.date().isoformat()
    if kind == "teaser":
        if meta.get("built_date") != today:
            return False, "no reel built today"
        if sid in set(state.get("posted", [])):
            return False, "tonight's reel is already up"
        return True, "ok"
    last = state.get("last_post") or {}
    if last.get("story_id") != sid or not str(last.get("at", "")).startswith(today):
        return False, "tonight's reel is not up yet"
    if not last.get("media_pk"):
        return False, "reel id unknown"
    return True, "ok"


def _center(d, text, font, y, fill, rtl=True):
    kw = {"direction": "rtl", "language": "fa"} if rtl else {}
    w = d.textlength(text, font=font, **({"direction": "rtl"} if rtl else {}))
    d.text(((SW - w) / 2, y), text, font=font, fill=fill, **kw)


def _brand(d, y):
    f = cf.F(40, True)
    tw = d.textlength(cf.BRAND, font=f, direction="rtl")
    d.rounded_rectangle([(SW - tw) / 2 - 36, y, (SW + tw) / 2 + 36, y + 74], radius=37, fill=cf.RED)
    _center(d, cf.BRAND, f, y + 8, cf.WHITE)


def render_teaser(title: str, path: Path) -> Path:
    cf.ensure_fonts()
    im = cf.background(int(time.time()) // 86400, SW, SH)
    d = ImageDraw.Draw(im)
    _brand(d, 260)
    _center(d, "معمای امشب", cf.F(64, True), 470, cf.GOLD)
    size = 100
    while True:
        tf = cf.F(size, True)
        lines = cf.wrap(d, title, tf, 880)
        if len(lines) <= 4 or size <= 70:
            break
        size -= 8
    y = 600
    for ln in lines:
        _center(d, ln, tf, y, cf.WHITE)
        y += int(size * 1.4)
    _center(d, "ساعت ۸ شب", cf.F(56, True), y + 40, cf.GOLD)
    _center(d, "فقط در نبض معما", cf.F(40), 1520, cf.BODY)
    _center(d, cf.HANDLE, cf.F(34), 1760, cf.MUTED, rtl=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=92)
    return path


def render_share(cover: Path, path: Path) -> Path:
    cf.ensure_fonts()
    base = Image.open(cover).convert("RGB").resize((SW, SH))
    base = ImageEnhance.Brightness(base.filter(ImageFilter.GaussianBlur(28))).enhance(0.45)
    d = ImageDraw.Draw(base)
    _brand(d, 170)
    _center(d, "ریل جدید", cf.F(72, True), 290, cf.WHITE)
    _center(d, "روی ریل بزن و ببین", cf.F(50, True), 1560, cf.GOLD)
    d.polygon([(SW / 2, 1490), (SW / 2 - 26, 1530), (SW / 2 + 26, 1530)], fill=cf.GOLD)
    _center(d, cf.HANDLE, cf.F(34), 1760, cf.MUTED, rtl=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    base.save(path, quality=92)
    return path


def media_sticker(media_pk):
    """StoryMedia built only from the fields this instagrapi version knows."""
    from instagrapi.types import StoryMedia
    fields = getattr(StoryMedia, "model_fields", None) or getattr(StoryMedia, "__fields__", {})
    wanted = {"media_pk": int(media_pk), "x": 0.5, "y": 0.5, "z": 0, "width": 0.62,
              "height": 0.56, "rotation": 0.0}
    return StoryMedia(**{k: v for k, v in wanted.items() if k in fields})


def main(kind: str, queue_dir: str = "ig_queue") -> int:
    if kind not in ("teaser", "share"):
        print("usage: python -m src.ig_story teaser|share [queue_dir]")
        return 0
    queue = Path(queue_dir)
    meta = load_meta(queue)
    state = ig.load_state()
    ok, reason = decide(kind, state, meta)
    if not ok:
        print(f"IG STORY ({kind}): not posting: {reason}")
        if not reason.startswith("outside") and "already done" not in reason:
            note(state, kind, f"skipped: {reason}")
        return 0
    sid = meta["story_id"]
    try:
        if kind == "teaser":
            image = render_teaser(meta.get("title") or "", OUT / "teaser.jpg")
        else:
            cover = queue / "cover.jpg"
            if not cover.exists():
                print("IG STORY (share): no cover in queue")
                note(state, kind, "skipped: no cover in queue")
                return 0
            image = render_share(cover, OUT / "share.jpg")
    except Exception as exc:
        print(f"::warning title=Story not rendered::{type(exc).__name__}: {exc}")
        note(state, kind, f"render failed: {type(exc).__name__}: {exc}")
        return 0
    if kind == "share":
        try:
            posted_at = datetime.fromisoformat(state["last_post"]["at"])
            if (ig.now_tehran() - posted_at).total_seconds() < 300:
                time.sleep(random.randint(60, 150))  # do not fire the instant the reel lands
        except Exception:
            pass
    try:
        client = ig.login_client()
    except Exception as exc:
        note(state, kind, f"login refused: {type(exc).__name__}: {exc}", save=False)
        ig.pause(state, f"login refused: {type(exc).__name__}: {exc}")
        return 0
    st = stories_state(state)
    st[kind] = (st[kind] + [sid])[-60:]  # marked before upload: a story is never retried
    try:
        if kind == "teaser":
            story = client.photo_upload_to_story(image)
        else:
            story = client.photo_upload_to_story(image, medias=[media_sticker(state["last_post"]["media_pk"])])
    except Exception as exc:
        note(state, kind, f"upload failed: {type(exc).__name__}: {exc}", save=False)
        if ig.is_block(exc):
            ig.pause(state, f"{kind} story refused: {type(exc).__name__}: {exc}")
        else:
            ig.save_state(state)
        print(f"IG STORY ({kind}): failed ({type(exc).__name__}: {exc}); not retrying")
        return 0
    note(state, kind, f"published {getattr(story, 'pk', '?')} -> {sid}")
    print(f"IG STORY ({kind}): published {getattr(story, 'pk', '?')} -> {sid}")
    return 0


def run(kind: str, queue_dir: str = "ig_queue") -> int:
    """main() with a safety net: an unexpected bug is logged (and the story marked done, so it
    can never be posted twice) instead of silently killing the step."""
    try:
        return main(kind, queue_dir)
    except Exception as exc:
        print(f"::warning title=Story crashed::{type(exc).__name__}: {exc}")
        try:
            state = ig.load_state()
            sid = load_meta(Path(queue_dir)).get("story_id")
            if sid and kind in ("teaser", "share"):
                st = stories_state(state)
                if sid not in st[kind]:
                    st[kind] = (st[kind] + [sid])[-60:]
            note(state, kind or "?", f"crashed: {type(exc).__name__}: {exc}")
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    try:
        sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "", sys.argv[2] if len(sys.argv) > 2 else "ig_queue"))
    finally:
        try:
            ig.SESSION_FILE.unlink(missing_ok=True)
        except Exception:
            pass
