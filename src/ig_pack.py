"""Weekly Instagram pack for «نبض معما»: everything is made automatically, nothing is posted.

Owner rule (Oct 10 2026): no unofficial Instagram posting at all (no instagrapi, no bots, no
simulated clicks). This script only PREPARES a week of Persian Reels; the owner schedules
them himself in Meta Business Suite (or the Instagram app's Schedule option).

One run (workflow ig-pack.yml) does:
  1. Plans the target week (next Monday .. Sunday): 2 or 3 reels a day, each one a different,
     fact-checked story from content/mysteries_fa.json that was never posted or packed before.
     Posting times move every day (13:00-14:10 and 20:30-22:40 Tehran, plus 21:40-22:55 for a
     third reel), never the same minute two days running.
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
up the run stops and the next run continues. Every beat is listened to (src.voice_check); a
beat with a doubtful word is read again with respellings, and any word still doubtful is
listed in the pack (schedule.csv, release notes). State: content/ig_pack_state.json.
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
OUT = ROOT / "output" / "ig-pack"
TEHRAN = timezone(timedelta(hours=3, minutes=30))
REPO = os.getenv("GITHUB_REPOSITORY", "NabzKhabarOfficial/NabzAI-YouTube")
TIME_BUDGET = float(os.getenv("NABZ_PACK_SECONDS", str(4.4 * 3600)))  # stop starting new reels after this
REEL_SECONDS = 420  # a reel needs up to ~7 minutes; do not start one we cannot finish

# Posting slots (Tehran): (earliest, latest) in minutes after midnight.
SLOTS = {
    2: [(13 * 60, 14 * 60 + 10), (20 * 60 + 30, 22 * 60 + 40)],
    3: [(12 * 60 + 50, 14 * 60 + 10), (19 * 60 + 50, 21 * 60), (21 * 60 + 40, 22 * 60 + 55)],
}
MIN_DAY_SHIFT = 4  # minutes: the same slot never repeats yesterday's time this closely

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


def schedule_times(week: date, per_day: int) -> list[list[str]]:
    """Seven days of posting times ("HH:MM"), shifted every day, reproducible for a week."""
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
    fresh = [sid for sid in fa_bank if sid not in used and sid in en_ids]
    want = per_day * 7
    if len(fresh) < want:
        print(f"::warning title=Persian bank low::only {len(fresh)} unused Persian stories for "
              f"week {key} (needed {want}); the next fact-checked batch must be written.", flush=True)
        if not allow_partial:  # wait for the new batch instead of locking in a short week
            return None
    if len(fresh) < 7:
        raise RuntimeError(f"only {len(fresh)} unused Persian stories: not enough for a week")
    per_day = per_day if len(fresh) >= want else max(2, min(per_day, len(fresh) // 7))
    times = schedule_times(week, per_day)
    plan, n = [], 0
    for day in range(7):
        for slot in range(per_day):
            if n >= len(fresh):
                break
            d = week + timedelta(days=day)
            plan.append({"n": n + 1, "id": fresh[n], "date": d.isoformat(), "time": times[day][slot]})
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
MAX_REPAIR_BEATS = 2  # at most this many beats of one reel are re-read (each costs voice quota)


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


def repair_beats(beats: list[str], segs: list, seg_words: list) -> list[str]:
    """Pronunciation check (owner rule: one voice, no wrong words). Every beat of the one-take
    narration is listened to; a beat with a doubtful word is read again on its own by the SAME
    Gemini voice, trying respellings (src.voice_check), and kept only if it is heard better.
    Returns the words that are still doubtful (shown in the pack so they can be checked)."""
    rf, m, _, vc = _modules()
    if not vc.available():
        return ["(voice check unavailable)"]
    flagged, repaired = [], 0
    for i, text in enumerate(beats):
        wav = rf.WORK / f"check_{i}.wav"
        _write_mono(wav, segs[i], rf.SR)
        try:
            weak = _weak_words(text, wav)
        except Exception as exc:
            log(f"beat {i}: listening failed ({type(exc).__name__}); not checked")
            flagged.append(f"(beat {i + 1} not checked)")
            continue
        if not weak:
            continue
        log(f"beat {i}: doubtful {weak}; reading this beat again")
        if repaired >= MAX_REPAIR_BEATS or not gemini_left():
            flagged += weak
            continue
        repaired += 1
        bw = rf.WORK / f"beat_{i}.wav"
        say = rf.spoken(text)
        try:
            bwords = rf._gemini_synth(say, bw)
            vc.review_beat(text, say.split(), bwords, bw, "fa", rf._gemini_synth)
            weak2 = _weak_words(text, bw)
        except Exception as exc:
            if "out of quota" in str(exc):
                flagged += weak
                continue
            log(f"beat {i}: re-read failed ({type(exc).__name__}: {str(exc)[:160]})")
            flagged += weak
            continue
        if len(weak2) < len(weak):
            new = m.read_wav(bw)
            real = vc.align(text, bw, "fa") or m.estimate_words(text, len(new) / rf.SR)
            segs[i] = new
            seg_words[i] = [{"start": w["start"], "end": w["end"]} for w in real]
            log(f"beat {i}: kept the re-read ({len(weak)} -> {len(weak2)} doubtful words)")
            weak = weak2
        flagged += weak
    return flagged


def narrate_whole(beats: list[str]):
    """The whole script in ONE Gemini request (the free tier allows ~10 a day), cut back into
    beats at the pauses the listening model hears, then every beat is pronunciation-checked.
    Same return value as reel_fa.narrate."""
    import numpy as np
    global LAST_FLAGS
    rf, m, _, vc = _modules()
    say = "\n".join(rf.spoken(b) for b in beats)
    wav = rf.WORK / "voice_all.wav"
    rf._gemini_synth(say, wav)  # voice filter + silence trim + length sanity check
    script = " ".join(beats)
    real = vc.align(script, wav, "fa")
    tokens = script.split()
    if not real or len(real) != len(tokens):
        raise RuntimeError("could not find the beat boundaries in the one-take narration")
    audio = m.read_wav(wav)
    sr = rf.SR
    counts = [len(b.split()) for b in beats]
    ranges, c = [], 0
    for k in counts:
        ranges.append((c, c + k - 1))
        c += k
    cuts = []
    for i in range(len(beats) - 1):
        a, b = real[ranges[i][1]], real[ranges[i + 1][0]]
        cuts.append((a["end"] + b["start"]) / 2)
    segs, seg_words = [], []
    total_len = len(audio) / sr
    for i, (first, last) in enumerate(ranges):
        lo = cuts[i - 1] if i > 0 else 0.0
        hi = cuts[i] if i < len(cuts) else total_len
        start = max(lo, real[first]["start"] - 0.08)
        end = min(hi, real[last]["end"] + (0.25 if i == len(ranges) - 1 else 0.12))
        if end - start < 0.4:
            raise RuntimeError(f"beat {i} came out too short in the one-take narration")
        segs.append(audio[int(start * sr):int(end * sr)])
        seg_words.append([{"start": max(0.0, w["start"] - start), "end": max(0.05, w["end"] - start)}
                          for w in real[first:last + 1]])
    LAST_FLAGS = repair_beats(beats, segs, seg_words)
    pieces, durations, words, clock = [], [], [], 0.0
    for i, seg in enumerate(segs):
        gap = m.TAIL if i == len(beats) - 1 else m.BEAT_GAP
        pieces.append(np.concatenate([seg, np.zeros(int(gap * sr), dtype=np.float32)]))
        for tok, w in zip(beats[i].split(), seg_words[i]):
            words.append({"text": tok, "start": clock + w["start"], "end": clock + w["end"], "beat": i,
                          "punct": bool(re.search(r"[.?!,:;،؟]$", tok))})
        dur = len(seg) / sr
        durations.append(dur + gap)
        clock += dur + gap
    voice = np.concatenate(pieces)
    peak = float(np.max(np.abs(voice))) or 1.0
    return voice * (0.92 / peak), durations, words


def install_narrator(allow_edge: bool):
    """reel_fa.build asks narrate(beats, "gemini") and falls back to narrate(beats, "edge").
    Here: Gemini one-take first, the per-beat Gemini path if the cut fails, and Edge only when
    allowed; otherwise StopPack ends the run so the next one (new quota) continues."""
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
                if "out of quota" in str(exc) or not gemini_left():
                    raise StopPack("Gemini voice quota is used up for today") from None
                log(f"one-take narration not usable ({type(exc).__name__}: {str(exc)[:200]}); per beat")
                LAST_FLAGS[:] = []  # the per-beat path runs the same voice check on every beat
                return original(beats, "gemini")
        if not allow_edge:
            if gemini_left():  # quota is there, so this story itself failed: count it as a failure
                raise RuntimeError("the Gemini voice could not read this story")
            raise StopPack("Gemini voice unavailable; waiting for tomorrow's quota (one voice only)")
        return original(beats, engine)

    rf.narrate = narrate


def build_reel(item: dict, story: dict, fa: dict, folder: Path) -> dict:
    rf, m, _, vc = _modules()
    work = OUT / "work" / item["id"]
    pics = work / "pics"
    shutil.rmtree(work, ignore_errors=True)
    pics.mkdir(parents=True, exist_ok=True)
    seed_base = int.from_bytes(item["id"].encode()[:6].ljust(6, b"_"), "big") % 900_000 + 101
    for i, beat in enumerate(story["beats"]):  # new seeds: these pictures differ from the YouTube Short's
        src = m.generate_image(f"{beat['visual']}, {m.STYLE}", seed_base + i * 7, pics / f"img_{i}.jpg")
        log(f"{item['id']}: picture {i + 1}/{len(story['beats'])} via {src}")
        angle = m.SECOND_SHOT[(seed_base + i) % len(m.SECOND_SHOT)]
        try:
            m.generate_image(f"{beat['visual']}, {angle}, {m.STYLE}", seed_base + i * 7 + 3, pics / f"img_{i}_b.jpg")
        except Exception as exc:
            log(f"{item['id']}: second shot {i + 1} skipped ({type(exc).__name__})")
    rf.SRC_WORK, rf.WORK, rf.OUT = pics, work / "reel", work / "out"
    rf.WORK.mkdir(parents=True, exist_ok=True)
    if getattr(vc, "_MODEL", None) is not None:
        vc._START = time.time()  # a fresh listening budget for every reel
    vc._TRIES = vc._FIXES = 0  # respelling tries are counted per reel, not per run
    LAST_FLAGS[:] = []
    meta = rf.build(story, fa)
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
    started = time.time()
    state = load_json(STATE_FILE, {})
    per_day = int(os.getenv("NABZ_PACK_PER_DAY", "2") or 2)
    per_day = 3 if per_day >= 3 else 2
    week = pick_week(state, os.getenv("NABZ_PACK_WEEK", "").strip())
    tag = f"week-{week.isoformat()}"
    info = (state.get("weeks") or {}).get(week.isoformat())
    if info and info.get("done"):
        log(f"{tag} is already complete; nothing to do")
        return 0
    rf, m, _, vc = _modules()
    vc.REPORT = OUT / "voice_check.json"  # keep the daily Short's review report untouched
    fa_bank = rf.load_fa()
    en = {s["id"]: s for s in m.load_bank()}
    late = now_tehran() >= deadline(week)
    info = plan_week(state, week, per_day, fa_bank, set(en), allow_partial=late)
    if info is None:
        log(f"{tag}: waiting for more Persian stories (a short week is planned only after the deadline)")
        return 0
    allow_edge = os.getenv("NABZ_PACK_ALLOW_EDGE", "0") == "1"  # owner rule: one voice, so never by default
    install_narrator(allow_edge)
    ensure_release(tag, week)
    folder = OUT / tag
    stopped = ""
    for item in info["plan"]:
        if item["id"] in info["built"]:
            continue
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
            fails = info.setdefault("fails", {})
            fails[item["id"]] = int(fails.get(item["id"], 0)) + 1
            if fails[item["id"]] >= 2:  # failed twice: give this slot to the next unused story
                taken = used_ids(state, week.isoformat()) | {p["id"] for p in info["plan"]}
                spare = [sid for sid in fa_bank if sid not in taken and sid in en]
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
                                     "at": now_tehran().isoformat(timespec="minutes")}
        info.get("errors", {}).pop(item["id"], None)
        save_state(state)
        log(f"{item['n']:02d}/{len(info['plan'])} ready: {item['id']} ({built['voice']}, {built['duration']} s)")
    left = [p["id"] for p in info["plan"] if p["id"] not in info["built"]]
    if left:
        why = stopped or "some reels failed (see warnings)"
        print(f"::notice title=Pack not finished yet::{len(info['built'])}/{len(info['plan'])} reels ready; "
              f"{why}. The next run continues.", flush=True)
        return 0
    zpath = finish(tag, week, info)
    info["done"] = True
    info["zip"] = f"https://github.com/{REPO}/releases/tag/{tag}"
    save_state(state)
    log(f"{tag} complete: {zpath.name} ({zpath.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
