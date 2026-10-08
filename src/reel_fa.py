"""NABZ Mysteries in Persian: an Instagram Reel built from the same day's Short.

Runs right after src.mystery_short in the same job and reuses its AI pictures
(no extra image quota). The narration, captions, title hook and cover are in
Persian (content/mysteries_fa.json, written and fact-checked by hand, never
generated). Output: output/reel-fa/{reel.mp4, cover.jpg, caption.txt, meta.json}.

Never fails the workflow: any problem writes output/reel-fa/skip.txt and exits 0.
Every run (built or skipped, with the reason) is also logged in review/reel_fa.json,
which the workflow commits, so a missing reel is always visible in the repo.
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
PITCH = os.getenv("NABZ_FA_PITCH", "-8Hz")  # fallback voice kept low too
# Main Persian voice: Gemini TTS. It is a language model that reads the whole sentence, so it
# puts the unwritten short vowels and ezafe where a native speaker would (Edge's Farid often
# guesses them wrong). Edge stays as the automatic fallback: no key, quota, or any error.
FA_ENGINE = os.getenv("NABZ_FA_TTS", "gemini").strip().lower()
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("NABZ_FA_GEMINI_MODEL", "gemini-3.8-flash-tts")
GEMINI_VOICE = os.getenv("NABZ_FA_GEMINI_VOICE", "Algenib")  # deep, gravelly male
GEMINI_STYLE = os.getenv(
    "NABZ_FA_GEMINI_STYLE",
    "A native Iranian Persian narrator, born and raised in Tehran, speaking flawless standard Persian "
    "like a top Iranian radio and documentary voice actor. Very deep, low, resonant bass voice with a "
    "warm chest tone. Calm, slow-burning and gripping, like telling a true mystery late at night. "
    "Perfect native pronunciation of every vowel and ezafe, crisp articulation, natural Persian "
    "rhythm and intonation, steady medium pace, no foreign accent, no exaggeration.",
)
# Extra depth after synthesis, in semitones (0 = off). One semitone sounds lower but still natural.
DEEPEN = float(os.getenv("NABZ_FA_DEEPEN", "1.0"))
# The Gemini narrator is slow and dramatic; a little faster keeps the reel tight (pitch unchanged).
TEMPO = float(os.getenv("NABZ_FA_TEMPO", "1.08"))
# Instagram Reel limit we keep under. Longer narration is gently sped up to fit instead of failing.
FA_MAX = float(os.getenv("NABZ_FA_MAX_SECONDS", "57.5"))
FIT_LIMIT = 1.3  # never speed the voice up more than 30%
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BRAND = os.getenv("NABZ_IG_BRAND", "نبض معما")
FONT_URLS = [
    "https://raw.githubusercontent.com/NabzKhabarOfficial/NabzKhabar/main/Vazirmatn-Bold.ttf",
]
FONT_FILE = Path(os.getenv("NABZ_FA_FONT", str(WORK / "Vazirmatn-Bold.ttf")))
# Instagram's Reels UI covers the bottom ~20% and a column of buttons on the right.
SAFE_X = 130
CAP_Y, CAP_H = 880, 420
HOOK_Y = 330
TEHRAN = timezone(timedelta(hours=3, minutes=30))
CTA_LINES = [
    "👈 فالو کن تا هر شب یک معمای واقعی ببینی.",
    "🔖 ذخیره کن و برای کسی بفرست که عاشق معماست.",
]
BASE_TAGS = ["#معما", "#دانستنی", "#نبض_معما"]


def log(msg):
    print(f"[reel-fa] {msg}", flush=True)


# ---------------------------------------------------------------- fonts
def ensure_font() -> Path:
    if FONT_FILE.exists() and FONT_FILE.stat().st_size > 50_000:
        return FONT_FILE
    FONT_FILE.parent.mkdir(parents=True, exist_ok=True)
    for url in FONT_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NabzAI/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if len(data) > 50_000:
                FONT_FILE.write_bytes(data)
                return FONT_FILE
        except Exception as exc:
            log(f"font download failed: {type(exc).__name__}: {exc}")
    raise RuntimeError("Persian font not available")


_FONTS: dict = {}


def font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _FONTS:
        f = ImageFont.truetype(str(FONT_FILE), size)
        try:
            f.set_variation_by_name("Bold")
        except Exception:
            pass
        _FONTS[size] = f
    return _FONTS[size]


def tlen(draw, text, f):
    return draw.textlength(text, font=f, direction="rtl")


def wrap(draw, text, f, max_w):
    lines, cur = [], ""
    for w in text.split():
        test = (cur + " " + w).strip()
        if cur and tlen(draw, test, f) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def fa_digits(text):
    return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


# ---------------------------------------------------------------- bank
def load_fa(path: Path = FA_BANK) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("stories", {})


def validate_fa(story_id: str, fa: dict, en_beats: int) -> None:
    for key in ("title", "beats", "question", "tags"):
        if not fa.get(key):
            raise RuntimeError(f"{story_id}: Persian version missing {key}")
    if len(fa["beats"]) != en_beats:
        raise RuntimeError(f"{story_id}: Persian has {len(fa['beats'])} beats, English has {en_beats}")
    if any(not str(b).strip() for b in fa["beats"]):
        raise RuntimeError(f"{story_id}: empty Persian beat")


# ---------------------------------------------------------------- audio
async def _tts(text: str, mp3: Path) -> list[dict]:
    import edge_tts
    try:
        com = edge_tts.Communicate(text, voice=VOICE, rate=RATE, pitch=PITCH, boundary="WordBoundary")
    except TypeError:
        com = edge_tts.Communicate(text, voice=VOICE, rate=RATE, pitch=PITCH)
    words = []
    with open(mp3, "wb") as fh:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append({"text": chunk["text"], "start": start, "end": start + chunk["duration"] / 1e7})
    return words


# Voice-only respellings (diacritics for ambiguous words, foreign names); captions keep the script.
FA_PRONOUNCE = {
    "کت": "کُت",
    "کت\u200cوشلوار": "کُت\u200cوشلوار",
    "کشتی": "کَشتی",
    "برده": "بُرده",
    "مرده": "مُرده",
    "وب": "وِب",
    "واو": "وائو",
    "جعل": "جَعل",
    "سرب": "سُرب",
    "قسر": "قِسر",
    "اهله\u200cی": "اَهِلّه\u200cی",
}
FA_SUFFIXES = [("\u200cاند", "\u200cاَند")]  # «افتاده‌اند», «آب‌تنی‌اند»: verb ending, not the word «اند»
_FA_EDGE = ".,!?:;\u060c\u061b\u061f\u00ab\u00bb\"'()"
# respellings the listening check proved better in earlier runs (review/pron_learned.json)
FA_PRONOUNCE.update(voice_check.learned("fa"))


def spoken(text: str) -> str:
    """What the voice reads: whitespace tidied, ambiguous words respelled (same word count)."""
    out = []
    for tok in text.split():
        core = tok.strip(_FA_EDGE)
        say = FA_PRONOUNCE.get(core)
        if not say:
            for end, fix in FA_SUFFIXES:
                if core.endswith(end) and len(core) > len(end):
                    say = core[: -len(end)] + fix
                    break
        out.append(tok.replace(core, say, 1) if say and core else tok)
    return " ".join(out)


def _synth(text: str, wav: Path) -> list[dict]:
    mp3 = wav.with_suffix(".mp3")
    words = asyncio.run(_tts(text, mp3))
    m.to_wav(mp3, wav)
    return words


def _gemini_request(text: str) -> tuple[bytes, str]:
    body = {
        "contents": [{"role": "user", "parts": [{"text": text, "speech_metadata": {"style": GEMINI_STYLE}}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"voice": GEMINI_VOICE}}},
    }
    req = urllib.request.Request(GEMINI_URL.format(model=GEMINI_MODEL), data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for part in data["candidates"][0]["content"]["parts"]:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"]), str(inline.get("mimeType") or inline.get("mime_type") or "")
            raise RuntimeError("Gemini returned no audio")
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"Gemini TTS HTTP {exc.code}: {exc.read()[:200]!r}")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
        time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"Gemini TTS kept failing: {type(last).__name__}: {last}")


def voice_filter() -> str:
    """ffmpeg filter for the Gemini voice: deepen (pitch down) and tempo, or '' when both are off."""
    tempo = TEMPO if 0.5 <= TEMPO <= 2.0 else 1.0
    if DEEPEN > 0:
        ratio = 2 ** (-DEEPEN / 12)
        return f"asetrate={SR * ratio:.0f},aresample={SR},atempo={tempo / ratio:.5f}"
    if abs(tempo - 1.0) > 0.001:
        return f"atempo={tempo:.5f}"
    return ""


def _gemini_synth(text: str, wav: Path) -> list[dict]:
    """Gemini voice for one beat -> wav (project format, edge silences trimmed) + word timings."""
    audio, mime = _gemini_request(text)
    raw = wav.with_name(wav.stem + "_gem.wav")
    if audio[:4] == b"RIFF":
        raw.write_bytes(audio)
    else:  # raw 16-bit PCM, e.g. "audio/L16;codec=pcm;rate=24000"
        found = re.search(r"rate=(\d+)", mime)
        rate = int(found.group(1)) if found else 24000
        with wave.open(str(raw), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(audio)
    m.to_wav(raw, wav)
    raw.unlink(missing_ok=True)
    chain = voice_filter()
    if chain:
        low = wav.with_name(wav.stem + "_low.wav")
        m.run_ffmpeg(["-i", str(wav), "-af", chain, "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(low)])
        low.replace(wav)
    audio = m.read_wav(wav)
    loud = np.flatnonzero(np.abs(audio) > 0.01 * (float(np.max(np.abs(audio))) if audio.size else 0.0))
    if loud.size:  # trim leading/trailing silence so the word timings sit on the speech
        pad = int(0.06 * SR)
        audio = audio[max(0, int(loud[0]) - pad):int(loud[-1]) + pad]
        with wave.open(str(wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SR)
            wf.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    dur = len(audio) / SR
    words = len(text.split())
    if dur < max(1.0, words * 0.15) or dur > words * 1.1 + 2.0:
        raise RuntimeError(f"Gemini audio length {dur:.1f}s does not fit {words} words")
    return m.estimate_words(text, dur)


def use_gemini() -> bool:
    return FA_ENGINE == "gemini" and bool(GEMINI_KEY)


def narrate(beats: list[str], engine: str = "edge"):
    pieces, durations, words = [], [], []
    clock = 0.0
    synth = _gemini_synth if engine == "gemini" else _synth
    for i, text in enumerate(beats):
        mp3, wav = WORK / f"voice_{i}.mp3", WORK / f"voice_{i}.wav"
        say = spoken(text)
        if engine == "gemini":
            bwords = _gemini_synth(say, wav)
        else:
            bwords = asyncio.run(_tts(say, mp3))
            m.to_wav(mp3, wav)
        if voice_check.ENABLED:
            _, bwords = voice_check.review_beat(text, say.split(), bwords, wav, "fa", synth)
        audio = m.read_wav(wav)
        dur = len(audio) / SR
        if dur < 1.0:
            raise RuntimeError(f"Persian beat {i} narration too short")
        tokens = text.split()
        if len(bwords) != len(tokens):
            # Word boundaries do not line up with the script: spread the script's own words over the audio.
            bwords = m.estimate_words(text, dur)
            for w, tok in zip(bwords, tokens):
                w["text"] = tok
        else:
            for w, tok in zip(bwords, tokens):
                w["text"] = tok
        gap = m.TAIL if i == len(beats) - 1 else m.BEAT_GAP
        pieces.append(np.concatenate([audio, np.zeros(int(gap * SR), dtype=np.float32)]))
        for w in bwords:
            words.append({"text": w["text"], "start": clock + w["start"], "end": clock + w["end"], "beat": i,
                          "punct": bool(re.search(r"[.?!,:;،؟]$", w["text"]))})
        durations.append(dur + gap)
        clock += dur + gap
    voice = np.concatenate(pieces)
    peak = float(np.max(np.abs(voice))) or 1.0
    return voice * (0.92 / peak), durations, words


def fit_length(voice, durations, words, limit: float = FA_MAX):
    """Too long for a Reel? Speed the whole narration up evenly (pitch kept) and rescale every
    beat length and word time, instead of losing the day's reel. Returns (..., factor)."""
    total = sum(durations)
    if total <= limit:
        return voice, durations, words, 1.0
    factor = total / (limit - 0.3)
    if factor > FIT_LIMIT:
        raise RuntimeError(f"Persian narration {total:.1f}s is too long to fit {limit:.0f}s naturally")
    src, dst = WORK / "fit_in.wav", WORK / "fit_out.wav"
    dst.unlink(missing_ok=True)
    m.write_wav(src, voice)
    m.run_ffmpeg(["-i", str(src), "-af", f"atempo={factor:.5f}", "-ac", "1", "-ar", str(SR),
                  "-c:a", "pcm_s16le", str(dst)])
    fast = m.read_wav(dst).astype(np.float32)
    durations = [d / factor for d in durations]
    words = [dict(w, start=w["start"] / factor, end=w["end"] / factor) for w in words]
    need = int(round(sum(durations) * SR))
    if len(fast) < need:
        fast = np.concatenate([fast, np.zeros(need - len(fast), dtype=np.float32)])
    fast = fast[:need]
    peak = float(np.max(np.abs(fast))) or 1.0
    log(f"Persian narration {total:.1f}s sped up x{factor:.3f} to {sum(durations):.1f}s")
    return fast * (0.92 / peak), durations, words, round(factor, 3)


# ---------------------------------------------------------------- captions (RTL)
def chunk_words(words, max_words=3, max_chars=20):
    chunks, cur = [], []
    for w in words:
        if not w["text"].strip():
            continue
        cand = " ".join(x["text"] for x in cur + [w])
        if cur and (len(cur) >= max_words or len(cand) > max_chars or w["beat"] != cur[-1]["beat"]):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if w.get("punct"):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def render_caption(chunk, hi, path):
    canvas = Image.new("RGBA", (W, CAP_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    words = [re.sub(r"[«»\"]", "", w["text"]) for w in chunk]
    max_w = W - 2 * SAFE_X
    size = 92
    while size > 54:
        f = font(size)
        total = sum(tlen(d, x, f) for x in words) + tlen(d, " ", f) * (len(words) - 1)
        if total <= max_w:
            break
        size -= 6
    f = font(size)
    space = tlen(d, " ", f)
    widths = [tlen(d, x, f) for x in words]
    total = sum(widths) + space * (len(words) - 1)
    x = (W + total) / 2  # right edge, words run right-to-left
    y = CAP_H / 2
    for i, (word, wd) in enumerate(zip(words, widths)):
        fill = (255, 214, 0, 255) if i == hi else (255, 255, 255, 255)
        d.text((x + 3, y + 5), word, font=f, fill=(0, 0, 0, 150), anchor="rm", direction="rtl")
        d.text((x, y), word, font=f, fill=fill, anchor="rm", direction="rtl", stroke_width=8,
               stroke_fill=(0, 0, 0, 255))
        x -= wd + space
    canvas.save(path)


def build_caption_track(words, total, target):
    chunks = chunk_words(words)
    cap_dir = WORK / "captions"
    cap_dir.mkdir(parents=True, exist_ok=True)
    blank = cap_dir / "blank.png"
    Image.new("RGBA", (W, CAP_H), (0, 0, 0, 0)).save(blank)
    lines, cursor, rendered = [], 0.0, 0
    for ci, ch in enumerate(chunks):
        nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else total
        for wi, w in enumerate(ch):
            start = max(w["start"], cursor)
            end = ch[wi + 1]["start"] if wi + 1 < len(ch) else min(nxt, w["end"] + 0.35)
            end = max(end, start + 0.04)
            if start > cursor + 0.01:
                lines += [f"file '{blank.as_posix()}'", f"duration {start - cursor:.3f}"]
            p = cap_dir / f"c{ci:03d}_{wi}.png"
            render_caption(ch, wi, p)
            rendered += 1
            lines += [f"file '{p.as_posix()}'", f"duration {end - start:.3f}"]
            cursor = end
    if total > cursor:
        lines += [f"file '{blank.as_posix()}'", f"duration {total - cursor:.3f}"]
    lines.append(f"file '{blank.as_posix()}'")
    listing = cap_dir / "list.txt"
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    m.run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-vf", f"fps={FPS},format=rgba",
                  "-t", f"{total:.3f}", "-c:v", "qtrle", str(target)])
    return rendered


# ---------------------------------------------------------------- overlays
def render_hook(title, path):
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    size = 84
    while True:
        lines = wrap(probe, title, font(size), W - 2 * SAFE_X)
        if len(lines) <= 3 or size <= 60:
            break
        size -= 6
    f = font(size)
    line_h = int(size * 1.5)
    img = Image.new("RGBA", (W, line_h * len(lines) + 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    badge = "حل\u200cنشده"
    bf = font(40)
    bw = tlen(d, badge, bf)
    d.rounded_rectangle([(W - bw) / 2 - 30, 0, (W + bw) / 2 + 30, 76], radius=18, fill=(200, 16, 32, 235))
    d.text((W / 2, 38), badge, font=bf, fill=(255, 255, 255, 255), anchor="mm", direction="rtl")
    y = 110 + line_h / 2
    for line in lines:
        d.text((W / 2 + 3, y + 5), line, font=f, fill=(0, 0, 0, 160), anchor="mm", direction="rtl")
        d.text((W / 2, y), line, font=f, fill=(255, 255, 255, 255), anchor="mm", direction="rtl",
               stroke_width=8, stroke_fill=(0, 0, 0, 255))
        y += line_h
    img.save(path)


def render_brand(path):
    f = font(34)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    tw = int(tlen(probe, BRAND, f))
    w = 74 + tw + 26
    img = Image.new("RGBA", (w, 72), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, 71], radius=20, fill=(8, 8, 8, 150), outline=(205, 155, 58, 180), width=2)
    d.ellipse([w - 58, 14, w - 14, 58], fill=(190, 25, 35, 230), outline=(255, 215, 130, 220), width=2)
    d.text((w - 36, 36), "؟", font=font(32), fill=(255, 235, 180, 255), anchor="mm", direction="rtl")
    d.text((w - 74, 36), BRAND, font=f, fill=(246, 220, 160, 235), anchor="rm", direction="rtl")
    img.save(path)


def render_cover(image, title, path):
    """Cover: title in the middle so the 3:4 profile-grid crop keeps it."""
    img = Image.open(image).convert("RGB").resize((W, H)).convert("RGBA")
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(H):
        a = int(170 * (1 - abs(y - H / 2) / (H / 2)) ** 0.6)
        sd.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    img = Image.alpha_composite(img, shade)
    d = ImageDraw.Draw(img)
    size = 96
    while True:
        lines = wrap(d, title, font(size), W - 160)
        if len(lines) <= 4 or size <= 64:
            break
        size -= 6
    f = font(size)
    line_h = int(size * 1.45)
    y = H / 2 - (len(lines) - 1) * line_h / 2
    for line in lines:
        d.text((W / 2, y), line, font=f, fill=(255, 255, 255, 255), anchor="mm", direction="rtl",
               stroke_width=9, stroke_fill=(0, 0, 0, 255))
        y += line_h
    bf = font(40)
    bw = tlen(d, BRAND, bf)
    d.rounded_rectangle([(W - bw) / 2 - 30, H / 2 + len(lines) * line_h / 2 + 30,
                         (W + bw) / 2 + 30, H / 2 + len(lines) * line_h / 2 + 106], radius=20, fill=(200, 16, 32, 235))
    d.text((W / 2, H / 2 + len(lines) * line_h / 2 + 68), BRAND, font=bf, fill=(255, 255, 255, 255),
           anchor="mm", direction="rtl")
    img.convert("RGB").save(path, quality=92)


def caption_text(fa):
    tags = []
    for t in list(fa.get("tags", []))[:3] + BASE_TAGS:
        if t not in tags:
            tags.append(t)
    return (
        f"🕯 {fa['title']}\n\n"
        f"❓ {fa['question']}\n"
        "نظرت رو تو کامنت بنویس.\n\n"
        + "\n".join(CTA_LINES)
        + "\n\n🎨 تصویرها بازسازی شده\u200cاند؛ ماجرا کاملاً واقعی است.\n\n"
        + " ".join(tags[:6])
    )


# ---------------------------------------------------------------- build
def assemble(segments, durations, captions, hook, brand, audio, target, hook_seconds=2.8):
    total = sum(durations)
    args = []
    for seg in segments:
        args += ["-i", str(seg)]
    n = len(segments)
    args += ["-i", str(captions), "-loop", "1", "-i", str(hook), "-loop", "1", "-i", str(brand), "-i", str(audio)]
    parts, last, offset = [], "[0:v]", 0.0
    for i in range(1, n):
        offset += durations[i - 1]
        out = f"[x{i}]"
        parts.append(f"{last}[{i}:v]xfade=transition=fade:duration={m.XFADE}:offset={offset - m.XFADE / 2:.3f}{out}")
        last = out
    parts.append(f"{last}[{n}:v]overlay=0:{CAP_Y}:format=auto[vc]")
    parts.append(f"[vc][{n + 1}:v]overlay=0:{HOOK_Y}:enable='lt(t,{hook_seconds})':format=auto[vh]")
    parts.append(f"[vh][{n + 2}:v]overlay={SAFE_X - 60}:150:format=auto[vb]")
    parts.append("[vb]format=yuv420p[vout]")
    args += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", f"{n + 3}:a",
             "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), "-movflags", "+faststart", str(target)]
    m.run_ffmpeg(args)


def build(story: dict, fa: dict) -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    validate_fa(story["id"], fa, len(story["beats"]))
    if not features.check("raqm"):
        raise RuntimeError("Pillow has no raqm (Persian text shaping)")
    ensure_font()
    seed_base = int(hashlib.sha1(story["id"].encode()).hexdigest()[:6], 16)
    images, extras = [], []
    for i in range(len(story["beats"])):
        a, b = SRC_WORK / f"img_{i}.jpg", SRC_WORK / f"img_{i}_b.jpg"
        if not a.exists():
            raise RuntimeError(f"picture {i} from today's Short is missing")
        images.append(a)
        extras.append(b if b.exists() else None)
    engine = "edge"
    if use_gemini():
        try:
            voice, durations, words = narrate(fa["beats"], "gemini")
            engine = f"gemini:{GEMINI_MODEL}:{GEMINI_VOICE}"
        except Exception as exc:  # one voice for the whole reel: redo every beat with Edge
            log(f"Gemini voice failed, using Edge for the whole reel: {type(exc).__name__}: {str(exc)[:300]}")
            print(f"::warning title=Persian voice fallback::{type(exc).__name__}: {str(exc)[:300]}", flush=True)
            voice_check.EVENTS.clear()
    else:
        log("Gemini voice off (no GEMINI_API_KEY or NABZ_FA_TTS=edge): using Edge")
    if engine == "edge":
        voice, durations, words = narrate(fa["beats"], "edge")
        engine = f"edge:{VOICE}"
    log(f"Persian voice: {engine}")
    voice_check.write_report(story["id"], "fa")
    raw_total = sum(durations)
    voice, durations, words, fit = fit_length(voice, durations, words)
    total = sum(durations)
    log(f"Persian narration {total:.1f}s, {len(words)} words")
    if not 15 <= total <= 59:
        raise RuntimeError(f"Persian narration {total:.1f}s is outside 15-59 s")
    audio = WORK / "mix.wav"
    m.write_wav(audio, m.mix(voice, m.make_music(total + 0.5, seed_base + 11)))
    shots, shot_durs = m.split_shots(images, extras, durations)
    segs = []
    for i, (img, length) in enumerate(zip(shots, m.segment_lengths(shot_durs))):
        seg = WORK / f"seg_{i}.mp4"
        m.render_segment(img, length, (seed_base + i + 2) % len(m.MOTIONS), seg)
        segs.append(seg)
    captions = WORK / "captions.mov"
    frames = build_caption_track(words, total, captions)
    hook, brand = WORK / "hook.png", WORK / "brand.png"
    render_hook(fa["title"], hook)
    render_brand(brand)
    OUT.mkdir(parents=True, exist_ok=True)
    video, cover = OUT / "reel.mp4", OUT / "cover.jpg"
    assemble(segs, shot_durs, captions, hook, brand, audio, video)
    render_cover(images[0], fa["title"], cover)
    info = m.probe(video)
    checks = {
        "file_ok": video.exists() and video.stat().st_size > 500_000,
        "vertical_1080x1920": info["resolution"] == f"{W}x{H}",
        "reel_duration": 15.0 <= info["duration"] <= 59.5,
        "h264": info["video_codec"] == "h264",
        "aac": info["audio_codec"] == "aac",
        "captions_rendered": frames >= 20,
        "cover_ok": cover.exists() and cover.stat().st_size > 20_000,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Persian reel failed checks: {checks}")
    caption = caption_text(fa)
    (OUT / "caption.txt").write_text(caption, encoding="utf-8")
    meta = {"story_id": story["id"], "title": fa["title"], "duration": round(info["duration"], 2),
            "built_date": datetime.now(TEHRAN).date().isoformat(), "shots": len(shots), "voice": engine,
            "narration_raw": round(raw_total, 1), "speedup": fit, "checks": checks}
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Persian reel ready: {meta}")
    return meta


def write_status(entry: dict, path: Path = STATUS) -> None:
    """Keep the last 14 runs in review/reel_fa.json (committed by the workflow)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        runs = old.get("runs", []) if isinstance(old, dict) else []
        runs = [r for r in runs if isinstance(r, dict) and r.get("date") != entry.get("date")] + [entry]
        path.write_text(json.dumps({"last": entry, "runs": runs[-14:]}, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    except Exception as exc:
        log(f"could not write {path.name}: {type(exc).__name__}: {exc}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    today = datetime.now(TEHRAN).date().isoformat()
    story_id = ""
    try:
        story = json.loads((m.OUT / "story.json").read_text(encoding="utf-8"))
        story_id = story.get("id", "")
        bank = load_fa()
        fa = bank.get(story["id"])
        if not fa:
            raise RuntimeError(f"no Persian version of {story['id']} yet")
        left = [k for k in bank if k not in set(m.load_state().get("mysteries", []))]
        if len(left) <= 5:
            print(f"::warning title=Persian bank low::only {len(left)} Persian stories left; translate the next batch.")
        meta = build(story, fa)
        write_status({"date": today, "story_id": story_id, "status": "built", "voice": meta.get("voice"),
                      "duration": meta.get("duration"), "speedup": meta.get("speedup")})
    except Exception as exc:
        msg = re.sub(r"[\r\n]+", " ", f"{type(exc).__name__}: {exc}")[:600]
        (OUT / "skip.txt").write_text(msg, encoding="utf-8")
        print(f"::warning title=Persian reel skipped::{msg}", flush=True)
        write_status({"date": today, "story_id": story_id, "status": "skipped", "reason": msg})
    return 0


if __name__ == "__main__":
    sys.exit(main())
