"""Weekly Instagram pack for «نبض معما»: everything is made automatically, nothing is posted.

Owner rule (Oct 10 2026): no unofficial Instagram posting at all (no instagrapi, no bots, no
simulated clicks). This script only PREPARES a week of Persian Reels; the owner schedules
them himself in Meta Business Suite (or the Instagram app's Schedule option).

One run (workflow ig-pack.yml) does:
  1. Plans the target week (next Monday .. Sunday): 2 or 3 reels a day, each one a different,
     fact-checked story from content/mysteries_fa.json that was never posted or packed before.
     Posting times: from the week of Oct 19 2026 the owner's golden hours per weekday (GOLDEN);
     before that (and for 3 reels a day) 13:00-14:10 and 20:30-22:40 Tehran, plus 21:40-22:55.
  2. Builds every planned reel that is not built yet: fresh AI pictures, the deep Gemini voice
     (ONE request per reel: the whole script is read in one go and cut back into beats with the
     listening model, then checked word by word), Persian captions, cover. 1080x1920, H.264 + AAC, 15-90 s, checked.
     Every finished reel is uploaded at once to the GitHub release "week-YYYY-MM-DD", so a run
     that stops (daily voice quota, time limit) loses nothing and the next run continues.
  3. When all reels are there: a folder week-YYYY-MM-DD with the videos, covers, ready captions,
     schedule.csv (Persian columns), metricool.csv and a short Persian guide, zipped as
     week-YYYY-MM-DD.zip on the same release.

Voice policy (owner rule, Oct 10 2026): ONE voice on every reel, the deep Gemini narrator, and
no wrong words. A reel never falls back to another voice: when the daily free quota is used
up the run stops and the next run continues. Every beat is listened to (src.voice_check).
Oct 12 2026: the voice is ALWAYS one continuous take, never pieces glued together (a re-read
beat spliced into the take was what still made the voice cut in and out). A take with doubtful
words is read again whole and the better full take is kept; words still doubtful are listed in
the pack (schedule.csv, release notes). State: content/ig_pack_state.json.

Picture budget (Oct 12 2026): at most MAX_PER_DAY reels are built per Tehran day. On Oct 11 the
pack used 11.1k of Cloudflare's 10k free neurons, and the next morning every picture service
refused, so neither the queued reel nor the YouTube Short could be built.

Story lock (Oct 12 2026): only stories rewritten to the owner's six-step template, i.e. listed in
content/story_notes_fa.json, are planned. New batches go in content/mysteries_fa_add.json and are
merged into the bank by the next run (merge_fa_bank).
"""
from __future__ import annotations

import csv
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "content" / "ig_pack_state.json"
IG_STATE = ROOT / "content" / "ig_state.json"
FA_BANK = ROOT / "content" / "mysteries_fa.json"
FA_ADD = ROOT / "content" / "mysteries_fa_add.json"
NOTES = ROOT / "content" / "story_notes_fa.json"
# Oct 12 2026: an edit on Oct 11 kept only 22 of the 63 Persian stories. Last full version:
FA_RESTORE_REF = "9eea3697a9cfc8d7f11c7a707066eb4eb3ed9182"
FILMS = ROOT / "content" / "ig_films_fa.json"
# Owner's choice (Oct 11): noon = a true story that became a film, night = a mystery. Film reels
# look like a movie, say the «فیلم» call at the end and show it on an end card.
FILM_LOOK = "cinematic movie still, anamorphic widescreen film look, dramatic movie lighting, 35mm film grain, "
FILM_SPOKEN = "اسم فیلمش رو می\u200cخوای؟ کامنت کن: فیلم."
FILM_BADGE = "ماجرای واقعی"
FILM_END = "اسم فیلمش رو می\u200cخوای؟\nکامنت کن «فیلم»"


def film_ids() -> set:
    try:
        return set((json.loads(FILMS.read_text(encoding="utf-8")).get("films") or {}))
    except (OSError, ValueError):
        return set()


OUT = ROOT / "output" / "ig-pack"
TEHRAN = timezone(timedelta(hours=3, minutes=30))
REPO = os.getenv("GITHUB_REPOSITORY", "NabzKhabarOfficial/NabzAI-YouTube")
TIME_BUDGET = float(os.getenv("NABZ_PACK_SECONDS", str(4.4 * 3600)))  # stop starting new reels after this
REEL_SECONDS = 420  # a reel needs up to ~7 minutes; do not start one we cannot finish
# ~6 pictures per reel: 6 reels (36 pictures) + the daily Short (12) stay well under the free quotas
MAX_PER_DAY = int(os.getenv("NABZ_PACK_MAX_PER_DAY", "6"))

# Posting slots (Tehran): (earliest, latest) in minutes after midnight.
SLOTS = {
    2: [(13 * 60, 14 * 60 + 10), (20 * 60 + 30, 22 * 60 + 40)],
    3: [(12 * 60 + 50, 14 * 60 + 10), (19 * 60 + 50, 21 * 60), (21 * 60 + 40, 22 * 60 + 55)],
}
MIN_DAY_SHIFT = 4  # minutes: the same slot never repeats yesterday's time this closely

# Owner's golden hours (Oct 12 2026), Tehran, per weekday (Monday = 0): [day slot, night slot].
# A range is used as given; a single time gets +-5 minutes so posts do not look automated.
# Friday's day time is 10:00 (the owner's second Friday time, 18:00, is not used with 2 reels a day).
GOLDEN = {
    5: [(10 * 60 + 30, 14 * 60 + 30), (21 * 60 + 25, 21 * 60 + 35)],  # Saturday
    6: [(14 * 60, 15 * 60 + 30), (20 * 60 + 55, 21 * 60 + 5)],         # Sunday
    0: [(13 * 60 + 25, 13 * 60 + 35), (17 * 60 + 55, 18 * 60 + 5)],    # Monday
    1: [(13 * 60 + 10, 14 * 60), (20 * 60 + 55, 21 * 60 + 5)],         # Tuesday
    2: [(13 * 60 + 30, 16 * 60), (18 * 60 + 55, 19 * 60 + 5)],         # Wednesday
    3: [(13 * 60 + 45, 15 * 60), (22 * 60 + 45, 22 * 60 + 55)],        # Thursday
    4: [(9 * 60 + 55, 10 * 60 + 5), (22 * 60 + 5, 22 * 60 + 15)],      # Friday
}
GOLDEN_FROM = date(2026, 10, 19)  # weeks already planned and queued in Buffer keep their times

WEEKDAYS_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
BRAND_TAGS = ["#نبض_معما", "#معما"]
TAG_POOL = ["#دانستنی", "#رازهای_تاریخ", "#داستان_واقعی", "#حقایق_جالب", "#معماهای_جهان",
            "#ناشناخته", "#رازهای_ناگشوده", "#تاریخ_جهان", "#اسرار", "#جهان_عجیب"]


class StopPack(Exception):
    """Stop building for now (voice quota or time); the next run continues."""


def log(msg: str) -> None:
    print(f"[ig-pack] {msg}", flush=True)


def now_tehran() -> datetime:
    return datetime.now(TEHRAN)


# ---------------------------------------------------------------- dates
def target_week(today: date | None = None, forced: str = "") -> date:
    """The Monday the pack is for: NABZ_PACK_WEEK, else the next Monday after today."""
    if forced:
        d = date.fromisoformat(forced)
        return d - timedelta(days=d.weekday())
    today = today or now_tehran().date()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def pick_week(state: dict, forced: str = "", today: date | None = None) -> date:
    """An unfinished week that is not over yet comes first (so a week the voice quota could not
    finish before its Monday is completed, not skipped); otherwise the next Monday."""
    if forced:
        return target_week(forced=forced)
    today = today or now_tehran().date()
    for key in sorted((state.get("weeks") or {})):
        info = state["weeks"][key]
        try:
            monday = date.fromisoformat(key)
        except ValueError:
            continue
        if not info.get("done") and info.get("plan") and monday + timedelta(days=6) >= today:
            return monday
    return target_week(today)


YT_STATE = ROOT / "content" / "published.json"
YT_FIRST_UNTIL = 15  # Tehran hour: before this, the daily YouTube Short gets the free quotas first


def youtube_first(now: datetime | None = None) -> bool:
    """True while today's YouTube Short is not built yet (it runs ~12:00 Tehran). The free picture
    and voice quotas are shared, so the pack never eats them before the Short has its share."""
    now = now or now_tehran()
    built = load_json(YT_STATE, {}).get("last_built_date", "")
    return built != now.date().isoformat() and now.hour < YT_FIRST_UNTIL


def deadline(week: date) -> datetime:
    """Sunday 18:00 Tehran before the week: from then on a short week may be planned."""
    return datetime.combine(week - timedelta(days=1), datetime.min.time(), TEHRAN) + timedelta(hours=18)


def jalali(d: date) -> str:
    """Gregorian -> Persian (Solar Hijri) date, e.g. 2026-10-12 -> ۱۴۰۵/۰۷/۲۰."""
    gy, gm, gd = d.year, d.month, d.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return fa_digits(f"{jy}/{jm:02d}/{jd:02d}")


def fa_digits(text: str) -> str:
    return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def golden_times(week: date) -> list[list[str]]:
    """Seven days of the owner's golden posting times (2 a day), reproducible for a week."""
    rng = random.Random(f"nabz-ig-golden-{week.isoformat()}")
    days = []
    for day in range(7):
        wins = GOLDEN[(week + timedelta(days=day)).weekday()]
        days.append([f"{t // 60:02d}:{t % 60:02d}" for t in (rng.randint(lo, hi) for lo, hi in wins)])
    return days


def schedule_times(week: date, per_day: int) -> list[list[str]]:
    """Seven days of posting times ("HH:MM"), shifted every day, reproducible for a week."""
    if per_day == 2 and week >= GOLDEN_FROM:
        return golden_times(week)
    rng = random.Random(f"nabz-ig-{week.isoformat()}-{per_day}")
    slots = SLOTS[per_day]
    days, prev = [], [None] * len(slots)
    for _ in range(7):
        times = []
        for k, (lo, hi) in enumerate(slots):
            for _try in range(50):
                t = rng.randint(lo, hi)
                if prev[k] is None or abs(t - prev[k]) >= MIN_DAY_SHIFT:
                    break
            if times and t - _minutes(times[-1]) < 75:  # keep reels of one day well apart
                t = min(hi, _minutes(times[-1]) + 75)
            prev[k] = t
            times.append(f"{t // 60:02d}:{t % 60:02d}")
        days.append(times)
    return days


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


# ---------------------------------------------------------------- state
def load_json(path: Path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def built_today(state: dict, now: datetime | None = None) -> int:
    """Reels built (or rebuilt) today, Tehran date, across every week of the pack."""
    today = (now or now_tehran()).date().isoformat()
    return sum(1 for info in (state.get("weeks") or {}).values()
               for b in (info.get("built") or {}).values()
               if str((b or {}).get("at", "")).startswith(today))


def approved_ids() -> set:
    """Stories rewritten to the owner's six-step template (they have fact notes)."""
    return set(load_json(NOTES, {}).get("stories") or {})


def _fa_text(stories: dict) -> str:
    rows = [f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}" for k, v in stories.items()]
    return '{"version": 1, "stories": {\n' + ",\n".join(rows) + "\n}}\n"


def merge_fa_bank() -> None:
    """Before planning: put back the Persian stories lost on Oct 11 (copy at FA_RESTORE_REF) and
    merge a new batch from content/mysteries_fa_add.json. The new batch wins over the bank, the
    bank wins over the old copy. The result is committed so every later job sees it."""
    if os.getenv("GITHUB_ACTIONS") != "true":
        return
    try:
        cur = load_json(FA_BANK, {}).get("stories") or {}
        add = load_json(FA_ADD, {}).get("stories") or {}
        old = {}
        if len(cur) < 40:
            proc = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.raw",
                                   f"repos/{REPO}/contents/content/mysteries_fa.json?ref={FA_RESTORE_REF}"],
                                  capture_output=True, text=True, timeout=120)
            if proc.returncode == 0:
                old = json.loads(proc.stdout).get("stories") or {}
            else:
                log(f"old Persian bank not readable: {proc.stderr.strip()[:200]}")
        if not add and not old:
            return
        merged = {}
        for src in (old, cur, add):
            for sid in src:
                merged.setdefault(sid, None)
        for sid in list(merged):
            s = add.get(sid) or cur.get(sid) or old.get(sid)
            if not isinstance(s, dict) or str(s.get("title", "")).strip() in ("", "placeholder"):
                merged.pop(sid)
            else:
                merged[sid] = s
        FA_BANK.write_text(_fa_text(merged), encoding="utf-8")
        log(f"Persian bank: {len(cur)} -> {len(merged)} stories ({len(add)} new, {len(old)} in the old copy)")
        git = ["git", "-c", "user.name=github-actions[bot]",
               "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"]
        if FA_ADD.exists():
            subprocess.run(git + ["rm", "-q", "--cached", "content/mysteries_fa_add.json"], cwd=ROOT, check=False)
            FA_ADD.unlink(missing_ok=True)
        subprocess.run(git + ["add", "content/mysteries_fa.json"], cwd=ROOT, check=True)
        subprocess.run(git + ["commit", "-q", "-m",
                              "content: Persian bank merged (lost stories back, new batch in) [skip ci]"],
                       cwd=ROOT, check=True)
        subprocess.run(git + ["pull", "-q", "--rebase", "--autostash"], cwd=ROOT, check=False)
        subprocess.run(git + ["push", "-q"], cwd=ROOT, check=True)
    except Exception as exc:
        print(f"::warning title=Persian bank merge::{type(exc).__name__}: {str(exc)[:300]}", flush=True)


def used_ids(state: dict, except_week: str = "") -> set:
    """Every story already on Instagram or reserved by another week's pack: never reused."""
    used = set(load_json(IG_STATE, {}).get("posted", []))
    for wk, info in (state.get("weeks") or {}).items():
        if wk != except_week:
            used.update(p["id"] for p in info.get("plan", []))
    used.update(state.get("retired", []))
    return used


def plan_week(state: dict, week: date, per_day: int, fa_bank: dict, en_ids: set,
              allow_partial: bool = False) -> dict | None:
    key = week.isoformat()
    weeks = state.setdefault("weeks", {})
    if key in weeks and weeks[key].get("plan"):
        return weeks[key]
    used = used_ids(state, key)
    ready = approved_ids()
    fresh = [sid for sid in fa_bank if sid not in used and sid in en_ids and sid in ready]
    want = per_day * 7
    if len(fresh) < want:
        print(f"::warning title=Persian bank low::only {len(fresh)} unused Persian stories written to the "
              f"six-step template for week {key} (needed {want}); the next batch must be written.", flush=True)
        if not allow_partial:  # wait for the new batch instead of locking in a short week
            return None
    if len(fresh) < 7:
        print(f"::warning title=Persian bank empty::only {len(fresh)} ready Persian stories: "
              f"week {key} waits for the next batch.", flush=True)
        return None
    per_day = per_day if len(fresh) >= want else max(2, min(per_day, len(fresh) // 7))
    times = schedule_times(week, per_day)
    films = film_ids()
    want_n = min(len(fresh), per_day * 7)
    film_q = [x for x in fresh if x in films][:7]  # one film story a day at most
    other_q = [x for x in fresh if x not in films][:want_n - len(film_q)]
    if len(film_q) + len(other_q) < want_n:
        film_q += [x for x in fresh if x in films and x not in film_q][:want_n - len(film_q) - len(other_q)]
    plan, n = [], 0
    for day in range(7):
        for slot in range(per_day):
            if not film_q and not other_q:
                break
            # the noon slot takes a film story, the evening ones a mystery, when there are enough
            q = (film_q or other_q) if slot == 0 else (other_q or film_q)
            d = week + timedelta(days=day)
            plan.append({"n": n + 1, "id": q.pop(0), "date": d.isoformat(), "time": times[day][slot]})
            n += 1
    weeks[key] = {"per_day": per_day, "plan": plan, "built": {}, "done": False,
                  "planned_at": now_tehran().isoformat(timespec="minutes")}
    save_state(state)
    log(f"week {key}: planned {len(plan)} reels ({per_day} a day)")
    return weeks[key]


# ---------------------------------------------------------------- captions
def hashtags(fa: dict, n: int) -> list[str]:
    """8 tags: brand, up to 3 about this story, the rest rotating so no two reels match."""
    tags = list(BRAND_TAGS)
    for t in fa.get("tags", [])[:3]:
        t = "#" + str(t).lstrip("#").replace(" ", "_")
        if t not in tags:
            tags.append(t)
    k = n * 3
    while len(tags) < 8:
        t = TAG_POOL[k % len(TAG_POOL)]
        k += 1
        if t not in tags:
            tags.append(t)
    return tags[:10]


def caption(fa: dict) -> str:
    q = str(fa["question"]).strip()
    ask = q if re.match(r"^[^\w\u0600-\u06FF]", q) else f"❓ {q}"  # the challenge has its own 🧩
    cta = "" if "بنویس" in q else "\nنظرت رو تو کامنت بنویس 👇"
    return (
        f"🕯 {fa['title']}\n\n"
        f"{ask}{cta}\n\n"
        "🔖 ذخیره کن تا گمش نکنی\n"
        "📤 برای کسی بفرست که عاشق معماست\n\n"
        "🎨 تصویرها بازسازی شده با هوش مصنوعی‌اند؛ ماجرا کاملاً واقعی است."
    )


def file_stem(item: dict) -> str:
    """File name of a reel in the release; a plan item may name an already finished video ("file"),
    e.g. a reel moved to a new time without building it again (Oct 12 2026, same as ig_buffer.stem)."""
    if item.get("file"):
        return str(item["file"])
    return f"{item['n']:02d}_{item['date']}_{item['time'].replace(':', '')}_{item['id']}"


# ---------------------------------------------------------------- GitHub release (storage)
def gh(*args, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "--repo", REPO], capture_output=True, text=True, check=check)


def ensure_release(tag: str, week: date) -> None:
    if gh("release", "view", tag, check=False).returncode == 0:
        return
    notes = (f"بسته‌ی ریلز هفته‌ی {jalali(week)} تا {jalali(week + timedelta(days=6))} "
             "(در حال ساخت؛ فایل ZIP وقتی همه‌ی ریلزها آماده شد اینجا اضافه می‌شود).")
    gh("release", "create", tag, "--title", f"Instagram pack {tag}", "--notes", notes, "--prerelease")


def upload(tag: str, *files: Path) -> None:
    for attempt in range(3):
        proc = gh("release", "upload", tag, *[str(f) for f in files], "--clobber", check=False)
        if proc.returncode == 0:
            return
        log(f"upload retry {attempt + 1}: {proc.stderr.strip()[:300]}")
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"could not upload {[f.name for f in files]} to release {tag}")


def download(tag: str, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    gh("release", "download", tag, "--dir", str(folder), "--skip-existing", "--pattern", "[0-9]*")


# ---------------------------------------------------------------- building one reel
_RF = None  # src.reel_fa, imported lazily (heavy)


def _modules():
    global _RF
    if _RF is None:
        from src import reel_fa as rf
        _RF = rf
    from src import gemini_tts, voice_check
    from src import mystery_short as m
    return _RF, m, gemini_tts, voice_check


def gemini_left() -> bool:
    _, _, g, _ = _modules()
    return bool(g.KEYS) and len(g._DEAD) < len(g.KEYS)


LAST_FLAGS: list[str] = []  # words the listening model still doubts in the last reel
_QUOTA = {"hit": False}  # the voice quota (daily or per-minute) ran out during this reel
# Free picture services give a limited number of pictures a day, so a reel uses one picture per
# beat by default (NABZ_PACK_SECOND_SHOTS=1 adds a second angle per beat, twice the quota).
SECOND_SHOTS = os.getenv("NABZ_PACK_SECOND_SHOTS", "0") == "1"
_QUOTA_WORDS = ("quota", "402", "payment required", "credit", "429", "limit kept failing", "rate limit",
                "resource_exhausted")


def _is_quota(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(w in text for w in _QUOTA_WORDS)


def _write_mono(path: Path, audio, sr: int) -> None:
    import wave
    import numpy as np
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


def _weak_words(text: str, wav: Path) -> list[str]:
    """Script words the listening model could not clearly hear in this beat."""
    _, _, _, vc = _modules()
    asr = vc.transcribe(wav, "fa")
    return [t.strip(vc._EDGE) for t in text.split()
            if vc.checkable(t, "fa") and vc.heard(t, asr, "fa") < vc.BAD]


def check_take(beats: list[str], segs: list) -> list[str]:
    """Listen to every beat of a take; nothing is changed, only the doubtful words are returned."""
    rf, _, _, vc = _modules()
    if not vc.available():
        return ["(voice check unavailable)"]
    flagged = []
    for i, text in enumerate(beats):
        wav = rf.WORK / f"check_{i}.wav"
        _write_mono(wav, segs[i], rf.SR)
        try:
            weak = _weak_words(text, wav)
        except Exception as exc:
            log(f"beat {i}: listening failed ({type(exc).__name__}); not checked")
            flagged.append(f"(beat {i + 1} not checked)")
            continue
        if weak:
            log(f"beat {i}: doubtful {weak}")
        flagged += weak
    return flagged


# Oct 11 2026 (v2): the one-take narration is no longer chopped and padded.
# Oct 12 2026 (v3): a re-read beat is never spliced into the take any more; that splice (a second,
# separate reading glued in the middle) was the cut the owner still heard in flight-19.
AUDIO_V = 3
# Oct 12 2026: 120 -> 60 min. The 13:45 reel of Oct 12 fell inside the old 2 h window and would have
# aired with the old voice cutting; a rebuild takes ~10 min and Buffer needs 30 min before airtime.
REDO_LEAD = int(os.getenv("NABZ_REDO_LEAD", "60"))  # minutes: an old-way reel is rebuilt only if it airs later than this


def _quiet_point(audio, sr: int, lo: float, hi: float) -> float:
    """Time (s) of the quietest 20 ms between lo and hi, so a cut never lands inside a sound
    (the listening model's word times are often 0.1-0.3 s off)."""
    import numpy as np
    a, b = max(0, int(lo * sr)), min(len(audio), int(hi * sr))
    win = max(1, int(0.02 * sr))
    if b - a <= win:
        return (lo + hi) / 2
    energy = np.convolve(np.abs(audio[a:b]), np.ones(win) / win, mode="valid")
    return (a + int(np.argmin(energy)) + win // 2) / sr


def one_take(beats: list[str], sep: str):
    """The whole script read in ONE Gemini request, split at the quietest moment between beats
    (for picture timing only: the pieces are consecutive slices of the same take, so put back
    together they are exactly the original reading). Returns (segs, seg_words, flags)."""
    import numpy as np
    rf, m, _, vc = _modules()
    say = sep.join(rf.spoken(b) for b in beats)
    wav = rf.WORK / "voice_all.wav"
    rf._gemini_synth(say, wav)  # voice filter + silence trim + length sanity check
    script = " ".join(beats)
    real = vc.align(script, wav, "fa")
    tokens = script.split()
    if not real or len(real) != len(tokens):
        raise RuntimeError("could not find the beat boundaries in the one-take narration")
    audio = m.read_wav(wav).astype(np.float32)
    sr = rf.SR
    counts = [len(b.split()) for b in beats]
    ranges, c = [], 0
    for k in counts:
        ranges.append((c, c + k - 1))
        c += k
    total_len = len(audio) / sr
    cuts = [0.0]
    for i in range(len(beats) - 1):
        a, b = real[ranges[i][1]], real[ranges[i + 1][0]]
        lo = max(a["start"] + 0.05, min(a["end"], b["start"]) - 0.2, cuts[-1] + 0.3)
        hi = min(b["end"] - 0.05, max(a["end"], b["start"]) + 0.2, total_len - 0.3)
        cuts.append(_quiet_point(audio, sr, lo, hi) if hi > lo else (a["end"] + b["start"]) / 2)
    cuts.append(total_len)
    segs, seg_words = [], []
    for i, (first, last) in enumerate(ranges):
        start, end = cuts[i], cuts[i + 1]
        if end - start < 0.4:
            raise RuntimeError(f"beat {i} came out too short in the one-take narration")
        segs.append(audio[int(round(start * sr)):int(round(end * sr))])
        seg_words.append([{"start": min(max(0.0, w["start"] - start), end - start - 0.05),
                           "end": min(max(0.05, w["end"] - start), end - start)}
                          for w in real[first:last + 1]])
    return segs, seg_words, check_take(beats, segs)


def narrate_whole(beats: list[str]):
    """Same return value as reel_fa.narrate. The voice is ALWAYS one continuous take.

    Oct 11 fix: the take is cut only at quiet points and never padded or trimmed.
    Oct 12 fix (owner: "again it cuts in one place"): a beat with a doubtful word used to be read
    again on its own and glued into the take: a different reading with its own pace, loudness and
    breath, so the voice jumped there. Now nothing is ever glued in: when the take has doubtful
    words the WHOLE script is read once more and the full take with fewer doubtful words is kept."""
    import numpy as np
    global LAST_FLAGS
    rf, m, _, _ = _modules()
    take, last_exc = None, None
    for sep in ("\n", "\n\n"):  # a different separator = a fresh reading, not the cached one
        if take is not None and (not take[2] or not gemini_left()):
            break
        try:
            other = one_take(beats, sep)
        except Exception as exc:
            if _is_quota(exc) or not gemini_left():
                if take is None:
                    raise
                break
            log(f"one-take reading not usable ({type(exc).__name__}: {str(exc)[:200]})")
            last_exc = exc
            continue
        if take is None or len(other[2]) < len(take[2]):
            if take is not None:
                log(f"second full take kept ({len(take[2])} -> {len(other[2])} doubtful words)")
            take = other
    if take is None:
        raise RuntimeError(f"no clean one-take narration: {last_exc}")
    segs, seg_words, LAST_FLAGS = take
    sr = rf.SR
    pieces, durations, words, clock = [], [], [], 0.0
    for i, seg in enumerate(segs):
        if i == len(segs) - 1:
            seg = np.concatenate([seg, np.zeros(int(m.TAIL * sr), dtype=np.float32)])
        pieces.append(seg)
        for tok, w in zip(beats[i].split(), seg_words[i]):
            words.append({"text": tok, "start": clock + w["start"], "end": clock + w["end"], "beat": i,
                          "punct": bool(re.search(r"[.?!,:;،؟]$", tok))})
        dur = len(seg) / sr
        durations.append(dur)
        clock += dur
    voice = np.concatenate(pieces)
    peak = float(np.max(np.abs(voice))) or 1.0
    return voice * (0.92 / peak), durations, words


def install_narrator(allow_edge: bool):
    """reel_fa.build asks narrate(beats, "gemini") and falls back to narrate(beats, "edge").
    Here: only the Gemini one-take (never beats read separately and glued, never Edge unless
    allowed); StopPack ends the run when the quota is out so the next one (new quota) continues."""
    rf, _, _, _ = _modules()
    original = getattr(rf, "_pack_original_narrate", None) or rf.narrate
    rf._pack_original_narrate = original

    def narrate(beats, engine="edge"):
        if engine == "gemini":
            if not gemini_left():
                raise StopPack("Gemini voice quota is used up for today")
            try:
                return narrate_whole(beats)
            except Exception as exc:
                if _is_quota(exc) or not gemini_left():
                    _QUOTA["hit"] = True
                    raise StopPack("Gemini voice quota is used up for now") from None
                raise
        if not allow_edge:
            if _QUOTA["hit"] or not gemini_left():
                raise StopPack("Gemini voice unavailable; waiting for the next quota (one voice only)")
            raise RuntimeError("the Gemini voice could not read this story in one take")  # a real failure
        return original(beats, engine)

    rf.narrate = narrate


def build_reel(item: dict, story: dict, fa: dict, folder: Path) -> dict:
    rf, m, _, vc = _modules()
    work = OUT / "work" / item["id"]
    pics = work / "pics"
    shutil.rmtree(work, ignore_errors=True)
    pics.mkdir(parents=True, exist_ok=True)
    seed_base = int.from_bytes(item["id"].encode()[:6].ljust(6, b"_"), "big") % 900_000 + 101
    _QUOTA["hit"] = False
    film = item["id"] in film_ids()
    look = FILM_LOOK if film else ""
    for i, beat in enumerate(story["beats"]):  # new seeds: these pictures differ from the YouTube Short's
        try:
            src = m.generate_image(f"{look}{beat['visual']}, {m.STYLE}", seed_base + i * 7, pics / f"img_{i}.jpg")
        except Exception as exc:
            if _is_quota(exc):  # the free picture services are used up for today: wait, not a failure
                raise StopPack("free picture quota is used up for now") from None
            raise
        log(f"{item['id']}: picture {i + 1}/{len(story['beats'])} via {src}")
        if not SECOND_SHOTS:
            continue
        angle = m.SECOND_SHOT[(seed_base + i) % len(m.SECOND_SHOT)]
        try:
            m.generate_image(f"{look}{beat['visual']}, {angle}, {m.STYLE}", seed_base + i * 7 + 3, pics / f"img_{i}_b.jpg")
        except Exception as exc:
            log(f"{item['id']}: second shot {i + 1} skipped ({type(exc).__name__})")
    rf.SRC_WORK, rf.WORK, rf.OUT = pics, work / "reel", work / "out"
    rf.WORK.mkdir(parents=True, exist_ok=True)
    if getattr(vc, "_MODEL", None) is not None:
        vc._START = time.time()  # a fresh listening budget for every reel
    vc._TRIES = vc._FIXES = 0  # respelling tries are counted per reel, not per run
    LAST_FLAGS[:] = []
    told = fa
    if film:  # the call to comment «فیلم» is also spoken (many viewers never open the caption)
        told = dict(fa, beats=list(fa["beats"][:-1]) + [f"{str(fa['beats'][-1]).strip()} {FILM_SPOKEN}"])
    rf.HOOK_BADGE, rf.END_CARD = (FILM_BADGE, FILM_END) if film else ("حل\u200cنشده", "")
    try:
        meta = rf.build(story, told)
    finally:
        rf.HOOK_BADGE, rf.END_CARD = "حل\u200cنشده", ""
    if not str(meta.get("voice", "")).startswith("gemini"):
        raise StopPack("the reel did not get the Gemini voice")  # one voice on every reel
    if not 15 <= float(meta.get("duration", 0)) <= 90:
        raise RuntimeError(f"{item['id']}: reel is {meta.get('duration')} s, outside 15-90 s")
    stem = file_stem(item)
    folder.mkdir(parents=True, exist_ok=True)
    video, cover = folder / f"{stem}.mp4", folder / f"{stem}_cover.jpg"
    shutil.copy2(rf.OUT / "reel.mp4", video)
    shutil.copy2(rf.OUT / "cover.jpg", cover)
    tags = hashtags(fa, item["n"])
    info = {"n": item["n"], "id": item["id"], "date": item["date"], "time": item["time"],
            "title": fa["title"], "caption": caption(fa), "hashtags": tags, "cover_text": fa["title"],
            "duration": meta.get("duration"), "voice": meta.get("voice"), "checks": meta.get("checks"),
            "check_words": list(LAST_FLAGS)}
    (folder / f"{stem}_caption.txt").write_text(info["caption"] + "\n\n" + " ".join(tags) + "\n", encoding="utf-8")
    (folder / f"{stem}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return info


# ---------------------------------------------------------------- the weekly files
def write_tables(folder: Path, infos: list[dict]) -> None:
    rows = sorted(infos, key=lambda x: x["n"])
    with open(folder / "schedule.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["شماره", "اسم فایل ویدیو", "کپشن", "هشتگ‌ها", "تاریخ انتشار", "ساعت انتشار (تهران)",
                    "روز هفته", "تاریخ شمسی", "متن کاور", "فایل کاور", "مدت (ثانیه)", "کلمه برای گوش دادن"])
        for r in rows:
            d = date.fromisoformat(r["date"])
            stem = f"{r['n']:02d}_{r['date']}_{r['time'].replace(':', '')}_{r['id']}"
            w.writerow([r["n"], f"{stem}.mp4", r["caption"], " ".join(r["hashtags"]), r["date"], r["time"],
                        WEEKDAYS_FA[d.weekday()], jalali(d), r["cover_text"], f"{stem}_cover.jpg",
                        round(float(r.get("duration") or 0), 1), "، ".join(r.get("check_words") or [])])
    # Metricool's import columns (Instagram only, Reel). Its template wants a PUBLIC link to each
    # video in "Picture Url 1"; fill that column after uploading the videos (see the guide).
    with open(folder / "metricool.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Text", "Date", "Time", "Draft", "Facebook", "Twitter", "LinkedIn", "GBP", "Instagram",
                    "Pinterest", "TikTok", "YouTube", "Threads", "Bluesky", "Picture Url 1",
                    "Video Thumbnail Url", "Instagram Post Type", "Instagram Show Reel On Feed"])
        for r in rows:
            w.writerow([r["caption"] + "\n\n" + " ".join(r["hashtags"]), r["date"], r["time"] + ":00", "FALSE",
                        "FALSE", "FALSE", "FALSE", "FALSE", "TRUE", "FALSE", "FALSE", "FALSE", "FALSE", "FALSE",
                        "", "", "REEL", "TRUE"])


GUIDE = """راهنمای زمان‌بندی این بسته در Meta Business Suite
================================================

فایل‌ها: هر ریلز سه فایل دارد که اسمشان با «شماره_تاریخ_ساعت» شروع می‌شود:
  .mp4 = ویدیو    _cover.jpg = کاور    _caption.txt = کپشن + هشتگ‌ها (آماده‌ی کپی)
schedule.csv = جدول کل هفته (با Excel یا Google Sheets باز کن).

هر هفته (حدود ۳۰ دقیقه برای ۱۴ ریلز):
۱. business.facebook.com را روی کامپیوتر باز کن و از منوی چپ «Planner» یا «Content» را بزن.
۲. روی «Create reel» بزن و فقط حساب اینستاگرام را انتخاب کن.
۳. فایل .mp4 ریلز شماره‌ی ۱ را آپلود کن.
۴. متن فایل _caption.txt همان شماره را کامل کپی کن و در جای کپشن بگذار.
۵. در بخش Thumbnail / Cover، گزینه‌ی آپلود تصویر را بزن و فایل _cover.jpg همان شماره را بده.
۶. اگر گزینه‌ی «AI info / برچسب هوش مصنوعی» بود روشنش کن (تصویرها ساخته‌ی هوش مصنوعی‌اند).
۷. پایین صفحه به‌جای Publish، «Schedule» را بزن و تاریخ و ساعت را دقیقاً از اسم فایل
   (یا ستون‌های تاریخ و ساعت schedule.csv) وارد کن. منطقه‌ی زمانی باید تهران باشد.
۸. «Schedule» را بزن. برای شماره‌ی بعدی همین کار را تکرار کن.
۹. آخر کار در Planner همه‌ی ریلزهای هفته را در تقویم می‌بینی؛ ساعت‌ها را یک بار چک کن.

با گوشی: در اپ اینستاگرام ریلز را انتخاب کن، کپشن را بگذار، در «Advanced settings»
گزینه‌ی «Schedule this reel» را روشن کن و تاریخ و ساعت را بزن.

Metricool (اختیاری): metricool.csv ستون‌های قالب Metricool را دارد. Metricool لینک عمومی ویدیو
می‌خواهد: ویدیوها را در Google Drive بگذار، اشتراک را «Anyone with the link» کن و لینک هر ویدیو
را در ستون «Picture Url 1» همان ردیف بگذار؛ بعد در Metricool: Planning > سه‌نقطه > Import CSV.
"""


def finish(tag: str, week: date, info: dict) -> Path:
    folder = OUT / tag
    download(tag, folder)
    infos = []
    for item in info["plan"]:
        meta_file = folder / f"{file_stem(item)}.json"
        if not (meta_file.exists() and (folder / f"{file_stem(item)}.mp4").exists()):
            raise RuntimeError(f"{item['id']} is missing from the release")
        infos.append(json.loads(meta_file.read_text(encoding="utf-8")))
    write_tables(folder, infos)
    (folder / "راهنما.txt").write_text(GUIDE, encoding="utf-8")
    zpath = OUT / f"{tag}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:  # mp4 is already compressed
        for f in sorted(folder.iterdir()):
            if f.suffix != ".json":
                z.write(f, f"{tag}/{f.name}")
    upload(tag, zpath, folder / "schedule.csv")
    voices = {}
    for x in infos:
        v = "Gemini" if str(x.get("voice", "")).startswith("gemini") else "Edge"
        voices[v] = voices.get(v, 0) + 1
    notes = (f"✅ بسته‌ی هفته‌ی {jalali(week)} تا {jalali(week + timedelta(days=6))}: {fa_digits(len(infos))} ریلز.\n\n"
             f"فایل {tag}.zip را دانلود کن؛ راهنما داخلش است (راهنما.txt).\n"
             f"صدای راوی: " + "، ".join(f"{k} {fa_digits(v)}" for k, v in voices.items()))
    doubtful = [f"{fa_digits(x['n'])}: {'، '.join(x['check_words'])}" for x in infos if x.get("check_words")]
    if doubtful:
        notes += "\n\nکلمه‌هایی که بهتر است یک بار گوش داده شوند:\n" + "\n".join(doubtful)
    gh("release", "edit", tag, "--notes", notes, "--prerelease=false", check=False)
    return zpath


# ---------------------------------------------------------------- main
def main() -> int:
    """Owner rule (Oct 11): use the whole free daily quota. When a week is finished and quota and
    time are left, the same run goes straight on to the next week instead of stopping.
    Oct 12: within MAX_PER_DAY reels a day (see the module notes)."""
    started = time.time()
    merge_fa_bank()
    prepare_slides()
    forced = os.getenv("NABZ_PACK_WEEK", "").strip()
    for _ in range(3):
        if not run_week(started) or forced:
            break
        if time.time() - started > TIME_BUDGET - REEL_SECONDS:
            break
        log("week complete and quota left: going on with the next week")
    return 0


def prepare_slides() -> None:
    """Slide posts (src.ig_slides): plan the coming Tuesdays/Thursdays/Saturdays and draw the slides.
    No voice or picture quota is used. A problem here never stops the reels."""
    state = load_json(STATE_FILE, {})
    try:
        from src import ig_slides
        ig_slides.plan(state)
        made = ig_slides.render(state)
        if made:
            log(f"slide posts: {made} drawn and stored")
    except Exception as exc:
        msg = re.sub(r"[\r\n]+", " ", f"{type(exc).__name__}: {exc}")[:300]
        print(f"::warning title=Slide posts not ready::{msg}", flush=True)
    finally:
        save_state(state)


def needs_redo(item: dict, info: dict) -> bool:
    """A reel built before the latest voice fix that has not aired yet (and has time to be rebuilt)."""
    b = (info.get("built") or {}).get(item["id"])
    if not b or int(b.get("audio_v", 1)) >= AUDIO_V or b.get("redo_failed"):
        return False
    due = datetime.fromisoformat(f"{item['date']}T{item['time']}:00").replace(tzinfo=TEHRAN)
    return due > now_tehran() + timedelta(minutes=REDO_LEAD)


URGENT_HOURS = 8  # a queued old-voice reel airing within this many hours is rebuilt even before the Short


def urgent_redo(state: dict, now: datetime | None = None) -> list[str]:
    """Owner's choice (Oct 11): a queued reel built with the old voice cutting that airs soon is
    rebuilt in the morning run, before the daily YouTube Short (it costs ~6 pictures, the voice
    usually comes from the cache). Returns those reel ids."""
    now = now or now_tehran()
    week = pick_week(state, os.getenv("NABZ_PACK_WEEK", "").strip(), now.date())
    info = (state.get("weeks") or {}).get(week.isoformat()) or {}
    out = []
    for item in info.get("plan") or []:
        due = datetime.fromisoformat(f"{item['date']}T{item['time']}:00").replace(tzinfo=TEHRAN)
        if needs_redo(item, info) and due <= now + timedelta(hours=URGENT_HOURS):
            out.append(item["id"])
    return out


def run_week(started: float) -> bool:
    """Builds the current week as far as possible. True only when it completed a week just now."""
    state = load_json(STATE_FILE, {})
    per_day = int(os.getenv("NABZ_PACK_PER_DAY", "2") or 2)
    per_day = 3 if per_day >= 3 else 2
    week = pick_week(state, os.getenv("NABZ_PACK_WEEK", "").strip())
    tag = f"week-{week.isoformat()}"
    info = (state.get("weeks") or {}).get(week.isoformat())
    if info and info.get("done"):
        log(f"{tag} is already complete; nothing to do")
        return False
    urgent = []
    if youtube_first():
        urgent = urgent_redo(state)
        if not urgent:
            log("today's YouTube Short is not built yet; it gets the free quotas first. Later run continues.")
            return False
        log(f"before the Short: only rebuilding {urgent} (old voice, airs soon)")
    rf, m, _, vc = _modules()
    vc.REPORT = OUT / "voice_check.json"  # keep the daily Short's review report untouched
    fa_bank = rf.load_fa()
    en = {s["id"]: s for s in m.load_bank()}
    late = now_tehran() >= deadline(week)
    info = plan_week(state, week, per_day, fa_bank, set(en), allow_partial=late)
    if info is None:
        log(f"{tag}: waiting for more Persian stories (a short week is planned only after the deadline)")
        return False
    allow_edge = os.getenv("NABZ_PACK_ALLOW_EDGE", "0") == "1"  # owner rule: one voice, so never by default
    install_narrator(allow_edge)
    ensure_release(tag, week)
    folder = OUT / tag
    stopped = ""
    for item in info["plan"]:
        redo = needs_redo(item, info)
        if item["id"] in info["built"] and not redo:
            continue
        if urgent and item["id"] not in urgent:
            continue  # the rest waits until the Short has its share of the quotas
        if built_today(state) >= MAX_PER_DAY:
            stopped = f"{MAX_PER_DAY} reels built today (daily cap that keeps the free picture quota from running out)"
            break
        if redo:
            log(f"{item['id']}: built before the latest voice fix; rebuilding it before it airs")
        if time.time() - started > TIME_BUDGET - REEL_SECONDS:
            stopped = "time limit of this run"
            break
        try:
            built = build_reel(item, en[item["id"]], fa_bank[item["id"]], folder)
        except StopPack as exc:
            stopped = str(exc)
            break
        except Exception as exc:
            msg = re.sub(r"[\r\n]+", " ", f"{type(exc).__name__}: {exc}")[:400]
            print(f"::warning title=Reel not built::{item['id']}: {msg}", flush=True)
            info.setdefault("errors", {})[item["id"]] = msg
            if redo:  # the old video stays in Buffer; never give a queued reel's slot away
                info["built"][item["id"]]["redo_failed"] = True
                save_state(state)
                continue
            fails = info.setdefault("fails", {})
            fails[item["id"]] = int(fails.get(item["id"], 0)) + 1
            if fails[item["id"]] >= 2:  # failed twice: give this slot to the next unused story
                taken = used_ids(state, week.isoformat()) | {p["id"] for p in info["plan"]}
                ready = approved_ids()
                spare = [sid for sid in fa_bank if sid not in taken and sid in en and sid in ready]
                if spare:
                    log(f"{item['id']} failed twice; slot {item['n']} goes to {spare[0]}")
                    item["id"] = spare[0]
            save_state(state)
            continue
        stem = file_stem(item)
        upload(tag, folder / f"{stem}.mp4", folder / f"{stem}_cover.jpg", folder / f"{stem}_caption.txt",
               folder / f"{stem}.json")
        info["built"][item["id"]] = {"voice": built["voice"], "duration": built["duration"],
                                     "check_words": built.get("check_words", []),
                                     "audio_v": AUDIO_V,
                                     "at": now_tehran().isoformat(timespec="minutes")}
        info.get("errors", {}).pop(item["id"], None)
        save_state(state)
        log(f"{item['n']:02d}/{len(info['plan'])} ready: {item['id']} ({built['voice']}, {built['duration']} s)")
    left = [p["id"] for p in info["plan"] if p["id"] not in info["built"]]
    if left:
        why = stopped or "some reels failed (see warnings)"
        print(f"::notice title=Pack not finished yet::{len(info['built'])}/{len(info['plan'])} reels ready; "
              f"{why}. The next run continues.", flush=True)
        return False
    zpath = finish(tag, week, info)
    info["done"] = True
    info["zip"] = f"https://github.com/{REPO}/releases/tag/{tag}"
    save_state(state)
    log(f"{tag} complete: {zpath.name} ({zpath.stat().st_size / 1e6:.0f} MB)")
    return True


if __name__ == "__main__":
    sys.exit(main())
