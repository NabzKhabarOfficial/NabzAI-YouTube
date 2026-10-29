"""NABZ Mysteries in Persian: an Instagram Reel built from the same day's Short.

Runs right after src.mystery_short in the same job and reuses its AI pictures.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, features

from src import gemini_tts
from src import mystery_short as m
from src import voice_check

ROOT = m.ROOT
FA_BANK = ROOT / "content" / "mysteries_fa.json"
OUT = ROOT / "output" / "reel-fa"
WORK = OUT / "work"
STATUS = ROOT / "review" / "reel_fa.json"
SRC_WORK = m.WORK
W, H, FPS, SR = m.W, m.H, m.FPS, m.SR
VOICE = os.getenv("NABZ_FA_VOICE", "fa-IR-FaridNeural")
RATE = os.getenv("NABZ_FA_RATE", "+6%")
PITCH = os.getenv("NABZ_FA_PITCH", "-8Hz")
FA_ENGINE = os.getenv("NABZ_FA_TTS", "gemini").strip().lower()
GEMINI_KEY = gemini_tts.KEY
GEMINI_MODEL = os.getenv("NABZ_FA_GEMINI_MODEL", "gemini-3.8-flash-tts")
GEMINI_VOICE = os.getenv("NABZ_FA_GEMINI_VOICE", "Algenib")
GEMINI_STYLE = os.getenv("NABZ_FA_GEMINI_STYLE", "A native Iranian Persian narrator, born and raised in Tehran, speaking flawless standard Persian like a top Iranian radio and documentary voice actor. Very deep, low, resonant bass voice with a warm chest tone. Calm, slow-burning and gripping, like telling a true mystery late at night. Perfect native pronunciation of every vowel and ezafe, crisp articulation, natural Persian rhythm and intonation, steady medium pace, no foreign accent, no exaggeration.")
DEEPEN = float(os.getenv("NABZ_FA_DEEPEN", "1.0"))
TEMPO = float(os.getenv("NABZ_FA_TEMPO", "1.16"))
FA_MAX = float(os.getenv("NABZ_FA_MAX_SECONDS", "57.5"))
FIT_LIMIT = 1.3
BRAND = os.getenv("NABZ_IG_BRAND", "نبض معما")
FONT_URLS = ["https://raw.githubusercontent.com/NabzKhabarOfficial/NabzKhabar/main/Vazirmatn-Bold.ttf"]
FONT_FILE = Path(os.getenv("NABZ_FA_FONT", str(WORK / "Vazirmatn-Bold.ttf")))
SAFE_X = 130
CAP_Y, CAP_H = 880, 420
HOOK_Y = 330
TEHRAN = timezone(timedelta(hours=3, minutes=30))
CTA_LINES = ["👈 فالو کن تا هر شب یک معمای واقعی ببینی.", "🔖 ذخیره کن و برای کسی بفرست که عاشق معماست."]
BASE_TAGS = ["#معما", "#دانستنی", "#نبض_معما"]
FA_MIN_WORDS, FA_MAX_WORDS = 50, 95
FA_HOOK_MAX_WORDS = 14


def log(msg): print(f"[reel-fa] {msg}", flush=True)

def ensure_font() -> Path:
    if FONT_FILE.exists() and FONT_FILE.stat().st_size > 50_000: return FONT_FILE
    FONT_FILE.parent.mkdir(parents=True, exist_ok=True)
    for url in FONT_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NabzAI/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp: data = resp.read()
            if len(data) > 50_000:
                FONT_FILE.write_bytes(data); return FONT_FILE
        except Exception as exc: log(f"font download failed: {type(exc).__name__}: {exc}")
    raise RuntimeError("Persian font not available")

_FONTS: dict = {}
def font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _FONTS:
        f = ImageFont.truetype(str(FONT_FILE), size)
        try: f.set_variation_by_name("Bold")
        except Exception: pass
        _FONTS[size] = f
    return _FONTS[size]

def tlen(draw, text, f): return draw.textlength(text, font=f, direction="rtl")
def wrap(draw, text, f, max_w):
    lines, cur = [], ""
    for w in text.split():
        test = (cur + " " + w).strip()
        if cur and tlen(draw, test, f) > max_w: lines.append(cur); cur = w
        else: cur = test
    if cur: lines.append(cur)
    return lines

def fa_digits(text): return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

def load_fa(path: Path = FA_BANK) -> dict:
    data = json.loads(path.read_text(encoding="utf-8")); return data.get("stories", {})

def validate_fa(story_id: str, fa: dict, en_beats: int) -> None:
    for key in ("title", "beats", "question", "tags"):
        if not fa.get(key): raise RuntimeError(f"{story_id}: Persian version missing {key}")
    beats = fa["beats"]
    if len(beats) != en_beats: raise RuntimeError(f"{story_id}: Persian has {len(beats)} beats, English has {en_beats}")
    if any(not str(b).strip() for b in beats): raise RuntimeError(f"{story_id}: empty Persian beat")
    total = sum(len(str(b).split()) for b in beats)
    if not FA_MIN_WORDS <= total <= FA_MAX_WORDS:
        raise RuntimeError(f"{story_id}: Persian script has {total} words, expected {FA_MIN_WORDS}-{FA_MAX_WORDS}")
    if len(str(beats[0]).split()) > FA_HOOK_MAX_WORDS:
        raise RuntimeError(f"{story_id}: Persian hook exceeds {FA_HOOK_MAX_WORDS} words")

async def _tts(text: str, mp3: Path) -> list[dict]:
    import edge_tts
    try: com = edge_tts.Communicate(text, voice=VOICE, rate=RATE, pitch=PITCH, boundary="WordBoundary")
    except TypeError: com = edge_tts.Communicate(text, voice=VOICE, rate=RATE, pitch=PITCH)
    words = []
    with open(mp3, "wb") as fh:
        async for chunk in com.stream():
            if chunk["type"] == "audio": fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7; words.append({"text": chunk["text"], "start": start, "end": start + chunk["duration"] / 1e7})
    return words

def spoken(text: str) -> str:
    return " ".join(str(text).split())

def _synth(text: str, wav: Path) -> list[dict]:
    mp3 = wav.with_suffix(".mp3"); words = asyncio.run(_tts(text, mp3)); m.to_wav(mp3, wav); return words

def use_gemini() -> bool: return FA_ENGINE == "gemini" and bool(gemini_tts.KEYS)

def _gemini_synth(text: str, wav: Path) -> list[dict]:
    audio, mime = gemini_tts.request(text, GEMINI_STYLE, GEMINI_VOICE, GEMINI_MODEL)
    raw = wav.with_name(wav.stem + "_gem.wav")
    if audio[:4] == b"RIFF": raw.write_bytes(audio)
    else:
        found = re.search(r"rate=(\d+)", mime); rate = int(found.group(1)) if found else 24000
        with wave.open(str(raw), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate); wf.writeframes(audio)
    m.to_wav(raw, wav); raw.unlink(missing_ok=True)
    dur = len(m.read_wav(wav)) / SR; words = len(text.split())
    if dur < max(1.0, words * .15) or dur > words * 1.1 + 2: raise RuntimeError(f"Gemini audio length {dur:.1f}s does not fit {words} words")
    return m.estimate_words(text, dur)

def narrate(beats: list[str], engine: str):
    pieces, durations, words, clock = [], [], [], 0.0
    synth = _gemini_synth if engine == "gemini" else _synth
    for i, text in enumerate(beats):
        wav = WORK / f"voice_{i}.wav"; bwords = synth(spoken(text), wav); audio = m.read_wav(wav); dur = len(audio) / SR
        if dur < 1.0: raise RuntimeError(f"Persian beat {i} narration too short")
        tokens = text.split(); bwords = m.estimate_words(text, dur) if len(bwords) != len(tokens) else bwords
        for w, tok in zip(bwords, tokens): w["text"] = tok
        gap = m.TAIL if i == len(beats) - 1 else m.BEAT_GAP
        pieces.append(np.concatenate([audio, np.zeros(int(gap * SR), dtype=np.float32)]))
        words += [{"text": w["text"], "start": clock + w["start"], "end": clock + w["end"], "beat": i, "punct": bool(re.search(r"[.?!,:;،؟]$", w["text"]))} for w in bwords]
        durations.append(dur + gap); clock += dur + gap
    voice = np.concatenate(pieces); peak = float(np.max(np.abs(voice))) or 1.0
    return voice * (.92 / peak), durations, words


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    today = datetime.now(TEHRAN).date().isoformat(); story_id = ""
    try:
        story = json.loads((m.OUT / "story.json").read_text(encoding="utf-8")); story_id = story.get("id", "")
        bank = load_fa(); fa = bank.get(story["id"])
        if not fa: raise RuntimeError(f"no Persian version of {story['id']} yet")
        meta = build(story, fa) if 'build' in globals() else {}
        write_status({"date": today, "story_id": story_id, "status": "built", "voice": meta.get("voice"), "duration": meta.get("duration")})
    except Exception as exc:
        msg = re.sub(r"[\r\n]+", " ", f"{type(exc).__name__}: {exc}")[:600]
        (OUT / "skip.txt").write_text(msg, encoding="utf-8")
        print(f"::warning title=Persian reel skipped::{msg}", flush=True)
        write_status({"date": today, "story_id": story_id, "status": "skipped", "reason": msg})
    return 0
