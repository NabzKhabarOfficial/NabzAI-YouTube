"""Gemini TTS for the English Shorts: a deep, professional native-English narrator.

synth(text, wav) writes one beat as a mono 16-bit wav (project sample rate) with the leading
and trailing silence trimmed, and returns its length in seconds. Any problem raises, and the
caller (src.mystery_short) then builds the whole Short with the Edge voice instead, so the
daily upload never depends on this service.
"""
from __future__ import annotations

import base64
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
KEY = os.getenv("GEMINI_API_KEY", "").strip()
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
ENABLED = os.getenv("NABZ_EN_TTS", "gemini").strip().lower() == "gemini"
_LAST_CALL = 0.0


def available() -> bool:
    return ENABLED and bool(KEY)


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


def request(text: str, style: str = STYLE, voice: str = VOICE) -> tuple[bytes, str]:
    global _LAST_CALL
    body = {
        "contents": [{"role": "user", "parts": [{"text": text, "speech_metadata": {"style": style}}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"voice": voice}}},
    }
    req = urllib.request.Request(URL.format(model=MODEL), data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": KEY})
    last = None
    for attempt in range(4):
        wait = 2.0 - (time.time() - _LAST_CALL)  # stay gentle with the free quota
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL = time.time()
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
    if deepen > 0:
        ratio = 2 ** (-deepen / 12)
        af = ["-af", f"aresample={sr},asetrate={sr * ratio:.0f},aresample={sr},atempo={1 / ratio:.5f}"]
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
        raise RuntimeError(f"Gemini audio length {dur:.1f}s does not fit {words} words")
    return dur
