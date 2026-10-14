"""Gemini TTS for the English Shorts: a deep, professional native-English narrator.

synth(text, wav) writes one beat as a mono 16-bit wav (project sample rate) with the leading
and trailing silence trimmed, and returns its length in seconds. Any problem raises, and the
caller (src.mystery_short) then builds the whole Short with the Edge voice instead, so the
daily upload never depends on this service.

Layers that keep the voice working (shared with the Persian reel, src.reel_fa):
  1. Audio cache: every narrated line is stored in .tts_cache (kept between runs by the
     workflow cache), so a rerun of the same story costs no quota at all.
  2. ONE API key only: GEMINI_API_KEY (owner rule, Oct 14 2026: no extra keys or projects to
     get around the free quota). GEMINI_API_KEY_2..5 / GEMINI_API_KEYS are ignored on purpose.
     When the daily quota is used up the voice waits for the next day (the pack rests).
  3. Short waits only for per-minute limits and server hiccups; a dead key is never retried.
  4. If the key fails, the caller switches the whole video to the Edge voice.

Free-tier budget (Oct 2026, per Google project, not per key): 3 requests/minute and 10/day for
the TTS model. One video is ~6-8 requests, so the daily quota goes to the Persian reel only:
the English Short uses the free Kokoro voice unless NABZ_EN_TTS=gemini. Requests are spaced
NABZ_GEMINI_GAP seconds apart (default 21) so the per-minute limit is never hit, and a
per-minute 429 only waits; only a real daily-quota answer retires a key.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import numpy as np

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _keys() -> list[str]:
    """Only GEMINI_API_KEY (owner rule: one key, never extra keys to dodge the free quota)."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return [key] if key else []


KEYS = _keys()
KEY = KEYS[0] if KEYS else ""
MODEL = os.getenv("NABZ_EN_GEMINI_MODEL", "gemini-3.8-flash-tts")
VOICE = os.getenv("NABZ_EN_GEMINI_VOICE", "Algenib")  # deep, gravelly male
STYLE = os.getenv(
    "NABZ_EN_GEMINI_STYLE",
    "A native American English narrator, like a top true-crime documentary and movie-trailer voice "
    "actor. Very deep, low, resonant bass voice with a warm chest tone. Calm, slow-burning and "
    "gripping, like telling a true unsolved mystery late at night. Crisp, natural General American "
    "pronunciation, confident pacing with short dramatic pauses at commas and full stops, "
    "no exaggeration, no cartoonish acting.",
)
DEEPEN = float(os.getenv("NABZ_EN_DEEPEN", "1.0"))  # extra depth in semitones, 0 = off
# Speed-up without pitch change: the deep narrator reads ~15% slower than Edge, which pushed
# the Oct 8 Short to 43.5 s (target 20-40 s for a tight loop). 1.0 = off.
TEMPO = float(os.getenv("NABZ_EN_TEMPO", "1.12"))
# English Shorts: Kokoro by default (the free Gemini TTS quota is kept for the Persian reel).
ENABLED = os.getenv("NABZ_EN_TTS", "kokoro").strip().lower() == "gemini"
GAP = float(os.getenv("NABZ_GEMINI_GAP", "21"))  # seconds between Gemini calls (free tier: 3/min)
CACHE = Path(os.getenv("NABZ_TTS_CACHE", str(Path(__file__).resolve().parents[1] / ".tts_cache")))
CACHE_DAYS = 21
_LAST_CALL = 0.0
_DEAD: set[int] = set()  # indexes of keys that ran out of quota in this run
STATS = {"cache_hits": 0, "calls": 0, "keys_used": [], "keys_dead": []}


def available() -> bool:
    return ENABLED and bool(KEYS)


def _ffmpeg() -> str:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _run(args: list[str]) -> None:
    proc = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + proc.stderr.strip()[-600:])


# ---------------------------------------------------------------- cache
def _prune_cache() -> None:
    try:
        limit = time.time() - CACHE_DAYS * 86400
        for f in CACHE.glob("*"):
            if f.is_file() and f.stat().st_mtime < limit:
                f.unlink(missing_ok=True)
    except Exception:
        pass


_prune_cache()


def _cache_key(text: str, style: str, voice: str, model: str) -> str:
    return hashlib.sha1(json.dumps([model, voice, style, text], ensure_ascii=False).encode("utf-8")).hexdigest()


def _cache_get(key: str):
    data, mime = CACHE / f"{key}.bin", CACHE / f"{key}.mime"
    if data.exists() and mime.exists() and data.stat().st_size > 1000:
        return data.read_bytes(), mime.read_text(encoding="utf-8")
    return None


def forget(text: str, style: str = STYLE, voice: str = VOICE, model: str = MODEL) -> None:
    """Drop a cached line (its audio turned out unusable), so the next try asks Gemini again."""
    key = _cache_key(text, style, voice, model)
    for ext in ("bin", "mime"):
        (CACHE / f"{key}.{ext}").unlink(missing_ok=True)


def _cache_put(key: str, audio: bytes, mime: str) -> None:
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / f"{key}.bin").write_bytes(audio)
        (CACHE / f"{key}.mime").write_text(mime, encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------- request
def _daily(body: str) -> bool:
    low = body.lower()
    return "perday" in low.replace(" ", "").replace("_", "") or "per day" in low or "daily" in low


def _mark_dead(i: int, why: str) -> None:
    _DEAD.add(i)
    if i + 1 not in STATS["keys_dead"]:
        STATS["keys_dead"].append(i + 1)
    alive = len(KEYS) - len(_DEAD)
    print(f"[gemini] key #{i + 1} out of quota ({why}); {alive} key(s) left", flush=True)


def request(text: str, style: str = STYLE, voice: str = VOICE, model: str = MODEL) -> tuple[bytes, str]:
    """Audio bytes + mime type for one line. Cache first, then every key in turn."""
    global _LAST_CALL
    ckey = _cache_key(text, style, voice, model)
    hit = _cache_get(ckey)
    if hit:
        STATS["cache_hits"] += 1
        return hit
    if not KEYS:
        raise RuntimeError("no Gemini API key configured")
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": text, "speech_metadata": {"style": style}}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"voice": voice}}},
    }).encode("utf-8")
    last, minute_hits = None, 0
    for attempt in range(10):
        alive = [i for i in range(len(KEYS)) if i not in _DEAD]
        if not alive:
            raise RuntimeError(f"every Gemini key is out of quota ({len(KEYS)} key(s))")
        i = alive[(minute_hits) % len(alive)]
        wait = GAP - (time.time() - _LAST_CALL)  # stay under the per-minute limit
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL = time.time()
        req = urllib.request.Request(URL.format(model=model), data=body,
                                     headers={"Content-Type": "application/json", "x-goog-api-key": KEYS[i]})
        try:
            STATS["calls"] += 1
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for part in data["candidates"][0]["content"]["parts"]:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    audio = base64.b64decode(inline["data"])
                    mime = str(inline.get("mimeType") or inline.get("mime_type") or "")
                    if i + 1 not in STATS["keys_used"]:
                        STATS["keys_used"].append(i + 1)
                    _cache_put(ckey, audio, mime)
                    return audio, mime
            raise RuntimeError("Gemini returned no audio")
        except urllib.error.HTTPError as exc:
            last = exc
            detail = ""
            try:
                detail = exc.read()[:600].decode("utf-8", "replace")
            except Exception:
                pass
            if exc.code in (401, 403):
                _mark_dead(i, f"HTTP {exc.code}: key rejected")
                continue
            if exc.code == 429:
                if _daily(detail):
                    _mark_dead(i, "HTTP 429 daily quota")
                    continue
                # per-minute limit: keys of one project share it, so wait instead of retiring keys
                minute_hits += 1
                if minute_hits > 4:
                    raise RuntimeError("Gemini TTS per-minute limit kept failing")
                time.sleep(35)
                continue
            if exc.code not in (500, 502, 503, 504):
                raise RuntimeError(f"Gemini TTS HTTP {exc.code}: {detail[:200]!r}")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
        time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"Gemini TTS kept failing: {type(last).__name__}: {last}")


def synth(text: str, wav: Path, sr: int = 44100, style: str = STYLE, voice: str = VOICE,
          deepen: float = DEEPEN) -> float:
    audio, mime = request(text, style, voice)
    raw = wav.with_name(wav.stem + "_gem.wav")
    if audio[:4] == b"RIFF":
        raw.write_bytes(audio)
    else:  # raw 16-bit PCM, e.g. "audio/L16;codec=pcm;rate=24000"
        found = re.search(r"rate=(\d+)", mime)
        with wave.open(str(raw), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(found.group(1)) if found else 24000)
            wf.writeframes(audio)
    af = []
    tempo = TEMPO if 0.8 <= TEMPO <= 1.4 else 1.0
    if deepen > 0:
        ratio = 2 ** (-deepen / 12)
        af = ["-af", f"aresample={sr},asetrate={sr * ratio:.0f},aresample={sr},atempo={tempo / ratio:.5f}"]
    elif abs(tempo - 1.0) > 0.001:
        af = ["-af", f"atempo={tempo:.5f}"]
    _run(["-i", str(raw), *af, "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(wav)])
    raw.unlink(missing_ok=True)
    with wave.open(str(wav), "rb") as wf:
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    peak = float(np.max(np.abs(pcm))) if pcm.size else 0.0
    loud = np.flatnonzero(np.abs(pcm) > 0.01 * peak) if peak else np.array([])
    if loud.size:  # trim leading/trailing silence so the word timings sit on the speech
        pad = int(0.06 * sr)
        pcm = pcm[max(0, int(loud[0]) - pad):int(loud[-1]) + pad]
        with wave.open(str(wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes((np.clip(pcm, -1, 1) * 32767).astype(np.int16).tobytes())
    dur = len(pcm) / sr
    words = len(text.split())
    if dur < max(1.0, words * 0.17) or dur > words * 1.0 + 2.0:
        forget(text, style, voice)
        raise RuntimeError(f"Gemini audio length {dur:.1f}s does not fit {words} words")
    return dur
