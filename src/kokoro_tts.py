"""Kokoro: a free, open-source English narrator (Apache-2.0, 82M parameters) that runs on the
GitHub runner's own CPU. No API key, no account, no quota.

Second voice layer for the English Shorts:  Gemini (best) -> Kokoro (free, unlimited) -> Edge.
The model files (~340 MB) are downloaded once and kept in .tts_cache/models by the workflow
cache. synth(text, wav) writes one beat (mono 16-bit, project sample rate, silence trimmed,
slightly deepened like the Gemini narrator) and returns its length; any problem raises and
the caller moves on to the next layer.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODELS = Path(os.getenv("NABZ_KOKORO_DIR", str(ROOT / ".tts_cache" / "models")))
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_FILE = os.getenv("NABZ_KOKORO_MODEL", "kokoro-v1.0.onnx")
VOICES_FILE = "voices-v1.0.bin"
VOICE = os.getenv("NABZ_KOKORO_VOICE", "am_michael")  # warm, natural US male
SPEED = float(os.getenv("NABZ_KOKORO_SPEED", "1.0"))
DEEPEN = float(os.getenv("NABZ_KOKORO_DEEPEN", "1.5"))  # semitones lower, speed kept
ENABLED = os.getenv("NABZ_KOKORO", "1") == "1"
_ENGINE = None


def log(msg: str) -> None:
    print(f"[kokoro] {msg}", flush=True)


def available() -> bool:
    return ENABLED


def _download(name: str) -> Path:
    target = MODELS / name
    if target.exists() and target.stat().st_size > 1_000_000:
        return target
    MODELS.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    req = urllib.request.Request(BASE + name, headers={"User-Agent": "NabzAI/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    if tmp.stat().st_size < 1_000_000:
        raise RuntimeError(f"download of {name} looks broken")
    tmp.replace(target)
    log(f"downloaded {name} ({target.stat().st_size // 1_000_000} MB)")
    return target


def engine():
    global _ENGINE
    if _ENGINE is None:
        try:
            from kokoro_onnx import Kokoro
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "kokoro-onnx"],
                           check=True, timeout=600)
            from kokoro_onnx import Kokoro
        _ENGINE = Kokoro(str(_download(MODEL_FILE)), str(_download(VOICES_FILE)))
        log(f"ready (voice {VOICE})")
    return _ENGINE


def synth(text: str, wav: Path, sr: int = 44100) -> float:
    from src import gemini_tts  # shared ffmpeg helper
    samples, rate = engine().create(text, voice=VOICE, speed=SPEED, lang="en-us")
    pcm = np.clip(np.asarray(samples, dtype=np.float32).reshape(-1), -1, 1)
    raw = wav.with_name(wav.stem + "_kok.wav")
    with wave.open(str(raw), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(rate))
        wf.writeframes((pcm * 32767).astype(np.int16).tobytes())
    af = []
    if DEEPEN > 0:
        ratio = 2 ** (-DEEPEN / 12)
        af = ["-af", f"aresample={sr},asetrate={sr * ratio:.0f},aresample={sr},atempo={1 / ratio:.5f}"]
    gemini_tts._run(["-i", str(raw), *af, "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(wav)])
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
        raise RuntimeError(f"Kokoro audio length {dur:.1f}s does not fit {words} words")
    return dur
