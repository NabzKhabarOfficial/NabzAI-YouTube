"""Pre-publish listening check, fully automatic.

An offline speech recognizer (faster-whisper) listens to every narrated beat right after
it is synthesized and compares what it hears with the script. If it clearly hears a word
wrong, it tries a few voice-only respellings of that word, re-synthesizes the beat, listens
again and keeps the version it hears correctly. Captions always keep the real spelling.

Fixes that worked are saved in review/pron_learned.json, so later videos start with them,
and every run is logged in review/voice_check.json. Any error, or running out of the time
budget, simply turns the check off for this run: it never blocks a build.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEARNED = ROOT / "review" / "pron_learned.json"
REPORT = ROOT / "review" / "voice_check.json"
ENABLED = os.getenv("NABZ_VOICE_CHECK", "1") == "1"
MODEL_NAME = os.getenv("NABZ_ASR_MODEL", "small")
BUDGET = float(os.getenv("NABZ_VOICE_CHECK_SECONDS", "480"))
BAD = 0.6        # a word heard with less similarity than this is suspicious
GOOD = 0.8       # a respelling is kept only if heard at least this well ...
GAIN = 0.25      # ... and clearly better than the original
MAX_FIXES = 6    # words per process
MAX_CANDIDATES = 4
# Re-synthesis attempts per process: keeps a paid/quota-limited voice (Gemini) from being
# called dozens of times when the recognizer struggles with a name.
MAX_TRIES = int(os.getenv("NABZ_VOICE_CHECK_TRIES", "12"))
TEHRAN = timezone(timedelta(hours=3, minutes=30))

_MODEL = None
_FAILED = False
_START: float | None = None
_FIXES = 0
_TRIES = 0
_BEATS = 0
_REASON = ""
EVENTS: list[dict] = []

EN_SKIP = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
    "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
    "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "hundreds",
    "thousand", "thousands", "million", "millions",
}
_FA_DIACRITICS = re.compile("[\u064b-\u0652\u0670]")
_EDGE = ".,!?:;\"'()\u060c\u061b\u061f\u00ab\u00bb"


def log(msg: str) -> None:
    print(f"[voice-check] {msg}", flush=True)


# ---------------------------------------------------------------- model
def _model():
    global _MODEL, _FAILED, _START, _REASON
    if _MODEL is not None or _FAILED or not ENABLED:
        return _MODEL
    try:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "faster-whisper"],
                           check=True, timeout=420)
            from faster_whisper import WhisperModel
        _MODEL = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        _START = time.time()
        log(f"listening model ready ({MODEL_NAME})")
    except Exception as exc:
        _FAILED = True
        _REASON = f"{type(exc).__name__}: {str(exc)[:200]}"
        log(f"turned off for this run: {type(exc).__name__}: {str(exc)[:200]}")
    return _MODEL


def available() -> bool:
    if not ENABLED or _FAILED:
        return False
    if _START is not None and time.time() - _START > BUDGET:
        return False
    return _model() is not None


def _pcm16k(wav: Path):
    """Decode audio with ffmpeg into the 16 kHz mono float array whisper expects.

    faster-whisper's own decoder calls av.open(..., metadata_errors=...), which newer PyAV
    releases removed (Oct 2026: every beat failed with TypeError). Passing the samples
    directly skips PyAV entirely.
    """
    import numpy as np
    try:  # the runner has no system ffmpeg; the project uses the one bundled with imageio
        from imageio_ffmpeg import get_ffmpeg_exe
        exe = get_ffmpeg_exe()
    except Exception:
        exe = "ffmpeg"
    raw = subprocess.run([exe, "-nostdin", "-v", "error", "-i", str(wav), "-f", "s16le",
                          "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True,
                         timeout=120).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(wav: Path, lang: str) -> str:
    segments, _ = _model().transcribe(_pcm16k(wav), language=lang, beam_size=5, vad_filter=False,
                                      condition_on_previous_text=False)
    return " ".join(s.text for s in segments).strip()


def word_times(wav: Path, lang: str) -> list[dict]:
    """Words the recognizer hears in a beat, with their real start/end times (seconds)."""
    segments, _ = _model().transcribe(_pcm16k(wav), language=lang, beam_size=5, vad_filter=False,
                                      condition_on_previous_text=False, word_timestamps=True)
    out = []
    for seg in segments:
        for w in getattr(seg, "words", None) or []:
            text = str(w.word or "").strip()
            if text and w.end is not None and w.start is not None:
                out.append({"text": text, "start": float(w.start), "end": float(w.end)})
    return out


def align(text: str, wav: Path, lang: str = "fa") -> list[dict] | None:
    """Real caption timings for the script words of one beat, or None.

    The Gemini voice returns no word timings, so captions used to be spread evenly over the
    beat and drifted ahead of the voice (owner, Oct 9: "the voice is a few ms behind the
    text"). Here the recognizer's own word times are mapped onto the script by position in
    the spoken letters, so pauses and changes of pace land where the narrator makes them,
    even when a word is heard with a slightly different spelling.
    """
    tokens = text.split()
    if not tokens or not available():
        return None
    try:
        heard_words = word_times(wav, lang)
    except Exception as exc:
        log(f"timing check skipped: {type(exc).__name__}: {str(exc)[:200]}")
        return None
    if len(heard_words) < max(2, len(tokens) // 3):
        return None

    def size(s: str) -> int:
        return max(1, len(norm(s, lang)))

    h_len = [size(w["text"]) for w in heard_words]
    s_len = [size(t) for t in tokens]
    total_h, total_s = float(sum(h_len)), float(sum(s_len))
    if not 0.5 <= total_h / total_s <= 2.0:
        return None  # heard something very different: keep the even spread
    bounds, c = [], 0.0
    for w, n in zip(heard_words, h_len):
        bounds.append((c / total_h, (c + n) / total_h, w["start"], max(w["end"], w["start"] + 0.02)))
        c += n

    def at(f: float, start_side: bool) -> float:
        for lo, hi, t0, t1 in bounds:
            if (lo <= f < hi) if start_side else (lo < f <= hi):
                return t0 + (f - lo) / (hi - lo) * (t1 - t0)
        return bounds[0][2] if f <= 0 else bounds[-1][3]

    out, c, last = [], 0.0, 0.0
    for tok, n in zip(tokens, s_len):
        start = max(at(c / total_s, True), last)
        end = max(at((c + n) / total_s, False), start + 0.05)
        out.append({"text": tok, "start": round(start, 3), "end": round(end, 3)})
        last = start
        c += n
    return out


# ---------------------------------------------------------------- scoring
def norm(text: str, lang: str) -> str:
    text = str(text)
    if lang == "fa":
        text = _FA_DIACRITICS.sub("", text).replace("\u200c", "")
        text = text.translate(str.maketrans({"\u064a": "\u06cc", "\u0643": "\u06a9", "\u0629": "\u0647",
                                             "\u0623": "\u0627", "\u0625": "\u0627", "\u0624": "\u0648"}))
        return re.sub(r"[^\u0600-\u06ff]", "", text)
    return re.sub(r"[^a-z]", "", text.lower())


def heard(word: str, asr: str, lang: str) -> float:
    """How well a script word is found anywhere in what the recognizer heard (0..1)."""
    w, a = norm(word, lang), norm(asr, lang)
    if not w:
        return 1.0
    if not a:
        return 0.0
    if w in a:
        return 1.0
    best = 0.0
    for size in {len(w) - 1, len(w), len(w) + 1, len(w) + 2}:
        if size <= 0:
            continue
        for i in range(0, max(1, len(a) - size + 1)):
            r = SequenceMatcher(None, w, a[i:i + size]).ratio()
            if r > best:
                best = r
    return best


def checkable(token: str, lang: str) -> bool:
    core = token.strip(_EDGE)
    if not core or re.search(r"[0-9\u06f0-\u06f9]", core):
        return False
    if lang == "en":
        return len(norm(core, "en")) >= 4 and core.lower() not in EN_SKIP
    return len(norm(core, "fa")) >= 3


# ---------------------------------------------------------------- respelling candidates
_EN_RULES = [
    (r"(?<!t)ch", "tch"), (r"ch", "k"), (r"ai", "eye"), (r"ei", "eye"), (r"ie", "ee"), (r"oe", "er"),
    (r"\u00f6", "er"), (r"\u00fc", "oo"), (r"\u00e4", "eh"), (r"ou", "oo"), (r"ph", "f"), (r"th", "t"),
    (r"sz", "sh"), (r"cz", "ch"), (r"^j", "y"), (r"w", "v"), (r"x", "ks"), (r"ses$", "seez"),
    (r"es$", "eez"), (r"e$", "eh"), (r"y", "i"), (r"a", "ah"), (r"i", "ee"), (r"u", "oo"),
]


def candidates(core: str, lang: str) -> list[str]:
    out: list[str] = []
    if lang == "fa":
        base = _FA_DIACRITICS.sub("", core)
        first = base[:1]
        for mark in ("\u064e", "\u0650", "\u064f"):
            out.append(first + mark + base[1:])
        if "\u200c" in base:
            out.append(base.replace("\u200c", ""))
    else:
        low = core.lower()
        for pat, rep in _EN_RULES:
            new = re.sub(pat, rep, low, count=1)
            if new != low:
                out.append(new[:1].upper() + new[1:] if core[:1].isupper() else new)
    seen, uniq = {core}, []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq[:MAX_CANDIDATES]


# ---------------------------------------------------------------- learned fixes
def learned(lang: str) -> dict:
    try:
        return dict(json.loads(LEARNED.read_text(encoding="utf-8")).get(lang, {}))
    except Exception:
        return {}


def _save_learned(lang: str, word: str, say: str) -> None:
    try:
        data = json.loads(LEARNED.read_text(encoding="utf-8")) if LEARNED.exists() else {}
    except Exception:
        data = {}
    data.setdefault(lang, {})[word] = say
    LEARNED.parent.mkdir(parents=True, exist_ok=True)
    LEARNED.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_report(story_id: str, lang: str) -> None:
    """Log every run, even a clean one, so a health check can tell 'all heard fine' from 'off'."""
    global _BEATS, _REASON
    if not ENABLED:
        status = "disabled"
    elif _FAILED:
        status = "off"
    elif _MODEL is None:
        status = "not-run"
    elif _START is not None and time.time() - _START > BUDGET:
        status = "out-of-time"
    elif _BEATS == 0 and _REASON:
        status = "error"  # the model loaded but no beat could be checked; reason says why
    else:
        status = "ok"
    try:
        data = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else []
    except Exception:
        data = []
    data.append({"date": datetime.now(TEHRAN).date().isoformat(), "story": story_id, "lang": lang,
                 "status": status, "beats_checked": _BEATS, "reason": _REASON,
                 "events": list(EVENTS)})
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(data[-60:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    EVENTS.clear()
    _BEATS = 0
    if not _FAILED:
        _REASON = ""


# ---------------------------------------------------------------- main entry
def review_beat(text: str, parts: list[str], bwords: list, wav: Path, lang: str, synth, key=None):
    """Listen to one synthesized beat and repair clearly misheard words.

    parts[i] is what the voice says for script token i. synth(spoken_text, wav_path) must
    write the audio and return its word boundaries. Returns (parts, bwords); wav is updated
    in place when a respelling is kept. key(core) gives the learned-fix key for a word.
    """
    global _FIXES, _BEATS, _TRIES, _REASON
    if _FIXES >= MAX_FIXES or not available():
        return parts, bwords
    try:
        tokens = text.split()
        if len(tokens) != len(parts):
            _REASON = _REASON or f"beat skipped: {len(tokens)} script words vs {len(parts)} spoken parts"
            return parts, bwords
        asr = transcribe(wav, lang)
        _BEATS += 1
        weak = [(heard(tok, asr, lang), i) for i, tok in enumerate(tokens) if checkable(tok, lang)]
        weak = sorted((s, i) for s, i in weak if s < BAD)[:2]
        for score, i in weak:
            if _FIXES >= MAX_FIXES or not available():
                break
            core = tokens[i].strip(_EDGE)
            event = {"word": core, "heard": asr, "score": round(score, 2), "kept": None}
            best = None
            for cand in candidates(core, lang):
                if _TRIES >= MAX_TRIES:
                    break
                _TRIES += 1
                trial = list(parts)
                trial[i] = tokens[i].replace(core, cand, 1)
                tmp = wav.with_name(wav.stem + "_try.wav")
                bw2 = synth(" ".join(trial), tmp)
                s2 = heard(core, transcribe(tmp, lang), lang)
                if s2 >= GOOD and s2 >= score + GAIN and (best is None or s2 > best[0]):
                    best = (s2, cand, trial, bw2, tmp.read_bytes())
                if best and best[0] >= 0.95:
                    break
            if best:
                s2, cand, trial, bw2, audio = best
                wav.write_bytes(audio)
                parts, bwords = trial, bw2
                _FIXES += 1
                event.update(kept=cand, new_score=round(s2, 2))
                _save_learned(lang, key(core) if key else core, cand)
                log(f"fixed '{core}' -> spoken '{cand}' ({score:.2f} -> {s2:.2f})")
            else:
                log(f"'{core}' heard as \"{asr}\" ({score:.2f}); no respelling sounded better, kept as is")
            EVENTS.append(event)
    except Exception as exc:
        log(f"beat check skipped: {type(exc).__name__}: {str(exc)[:200]}")
        _REASON = _REASON or f"beat check failed: {type(exc).__name__}: {str(exc)[:200]}"
    finally:
        try:
            wav.with_name(wav.stem + "_try.wav").unlink(missing_ok=True)
        except Exception:
            pass
    return parts, bwords
