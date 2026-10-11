"""Slide (carousel) posts for «نبض معما», published through Buffer like the reels.

Owner's choice (Oct 11 2026): three slide posts a week, fully automatic, photos only (Buffer's API
cannot add Instagram music to a photo post; music would need a manual step every time).

 * Texts come from content/ig_carousels*.json (written and fact-checked by hand, never generated;
   a later file overrides a post by id). Posts already published earlier (content/ig_state.json
   "carousels_posted") are never used again.
 * plan(): every post not planned yet gets a day: Tuesday, Thursday and Saturday, 17:00-17:40
   Tehran (between the noon and the evening reel, at least ~3 hours from both).
 * render(): the pack job (ig-pack.yml, which has Pillow + the Persian fonts) draws the slides
   with src.carousel_fa and keeps them in the GitHub release "carousels" (c_<id>_<n>.jpg).
 * src.ig_buffer puts the slides of every waiting post on the public nabz-reels site and creates
   the Buffer post (Instagram photo carousel, 4:5) at its time.
The plan lives in content/ig_pack_state.json under "carousels", so both jobs already commit it.
This module needs only the standard library at import time (the Buffer job has no extra packages).
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
IG_STATE = CONTENT / "ig_state.json"
OUT = ROOT / "output" / "slides"
TEHRAN = timezone(timedelta(hours=3, minutes=30))
REPO = os.getenv("GITHUB_REPOSITORY", "NabzKhabarOfficial/NabzAI-YouTube")
RELEASE = "carousels"
DAYS = (1, 3, 5)  # Tuesday, Thursday, Saturday
SLOT = (17 * 60, 17 * 60 + 40)  # Tehran minutes after midnight
LOW_WARN = 3  # warn when fewer planned posts than this are still ahead


def log(msg: str) -> None:
    print(f"[ig-slides] {msg}", flush=True)


def _load(path: Path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def load_posts(folder: Path = CONTENT) -> list[dict]:
    """All content/ig_carousels*.json in name order; a later file overrides a post by id
    ({"id": "x", "skip": true} drops it)."""
    merged: dict = {}
    for path in sorted(folder.glob("ig_carousels*.json")):
        for p in _load(path, {}).get("posts", []) or []:
            if isinstance(p, dict) and p.get("id"):
                merged[p["id"]] = {**merged.get(p["id"], {}), **p}
    return [p for p in merged.values() if not p.get("skip") and p.get("slides") and p.get("caption")]


def posts_by_id() -> dict:
    return {p["id"]: p for p in load_posts()}


def file_name(post_id: str, k: int) -> str:
    return f"c_{post_id}_{k}.jpg"


def plan(state: dict, today: date | None = None) -> list[dict]:
    """Gives every unplanned post the next free Tuesday / Thursday / Saturday."""
    car = state.setdefault("carousels", {})
    items = car.setdefault("plan", [])
    planned = {p["id"] for p in items}
    done = set(_load(IG_STATE, {}).get("carousels_posted", []))
    fresh = [p for p in load_posts() if p["id"] not in planned | done]
    fresh.sort(key=lambda p: (str(p.get("publish_on", "9999")), p["id"]))
    today = today or datetime.now(TEHRAN).date()
    last = max((date.fromisoformat(p["date"]) for p in items), default=today)
    d = max(last, today) + timedelta(days=1)
    for p in fresh:
        while d.weekday() not in DAYS:
            d += timedelta(days=1)
        t = random.Random(f"nabz-slides-{p['id']}").randint(*SLOT)
        items.append({"id": p["id"], "date": d.isoformat(), "time": f"{t // 60:02d}:{t % 60:02d}"})
        log(f"planned {p['id']} on {d} {t // 60:02d}:{t % 60:02d}")
        d += timedelta(days=1)
    ahead = [p for p in items if p["date"] >= today.isoformat()]
    if len(ahead) < LOW_WARN:
        print(f"::warning title=Slide posts running out::only {len(ahead)} slide post(s) left; "
              "a new fact-checked batch for content/ig_carousels_4.json is needed.", flush=True)
    return items


def gh(*args, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "--repo", REPO], capture_output=True, text=True, check=check)


def render(state: dict) -> int:
    """Draws the slides of every planned post that has none yet and keeps them in the release."""
    items = (state.get("carousels") or {}).get("plan") or []
    posts = posts_by_id()
    todo = [p for p in items if not p.get("slides") and p["id"] in posts]
    if not todo:
        return 0
    from src.carousel_fa import render_post
    if gh("release", "view", RELEASE, check=False).returncode != 0:
        gh("release", "create", RELEASE, "--title", "Instagram slide posts",
           "--notes", "اسلایدهای پست‌های «نبض معما» (خودکار؛ از اینجا به Buffer می‌روند).", "--prerelease")
    made = 0
    for item in todo:
        folder = OUT / item["id"]
        shutil.rmtree(folder, ignore_errors=True)
        paths = render_post(posts[item["id"]], folder)
        files = []
        for k, path in enumerate(paths, 1):
            dst = folder / file_name(item["id"], k)
            path.rename(dst)
            files.append(dst)
        proc = gh("release", "upload", RELEASE, *[str(f) for f in files], "--clobber", check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"slides of {item['id']} not uploaded: {proc.stderr.strip()[:300]}")
        item["slides"] = len(files)
        made += 1
        log(f"{item['id']}: {len(files)} slides ready")
    return made
