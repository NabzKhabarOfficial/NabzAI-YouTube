"""Offline ASR voice checker used by the Instagram pack and YouTube builds."""
from __future__ import annotations
import json, os, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEARNED = ROOT / "review" / "pron_learned.json"
REPORT = ROOT / "review" / "voice_check.json"
ENABLED = os.getenv("NABZ_VOICE_CHECK", "1") == "1"
MODEL_NAME = os.getenv("NABZ_ASR_MODEL", "small")
BUDGET = float(os.getenv("NABZ_VOICE_CHECK_SECONDS", "480"))
BAD, GOOD, GAIN = .60, .80, .25
MAX_FIXES, MAX_CANDIDATES = 6, 4
MAX_TRIES = int(os.getenv("NABZ_VOICE_CHECK_TRIES", "12"))
TEHRAN = timezone(timedelta(hours=3, minutes=30))
_EDGE = ".,!?:;\"'()،؛؟«»"
_FA_DIACRITICS = re.compile(r"[\u064b-\u0652\u0670]")
_MODEL = None
_FAILED = False
_START = None
_FIXES = _TRIES = _BEATS = 0
_REASON = ""
EVENTS = []
EN_SKIP = set("one two three four five six seven eight nine ten hundred thousand million".split())

def log(msg): print(f"[voice-check] {msg}", flush=True)

def _model():
    global _MODEL, _FAILED, _START, _REASON
    if _MODEL is not None or _FAILED or not ENABLED: return _MODEL
    try:
        from faster_whisper import WhisperModel
        _MODEL = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        _START = time.time()
        log(f"model ready: {MODEL_NAME}")
    except Exception as exc:
        _FAILED, _REASON = True, f"{type(exc).__name__}: {str(exc)[:200]}"
        log(f"disabled for this run: {_REASON}")
    return _MODEL

def available():
    if not ENABLED or _FAILED: return False
    if _START is not None and time.time() - _START > BUDGET: return False
    return _model() is not None

def _pcm16k(wav):
    import numpy as np
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        exe = get_ffmpeg_exe()
    except Exception:
        exe = "ffmpeg"
    raw = subprocess.run([exe, "-nostdin", "-v", "error", "-i", str(wav), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True, timeout=120).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

def transcribe(wav, lang):
    segments, _ = _model().transcribe(_pcm16k(wav), language=lang, beam_size=5, vad_filter=False, condition_on_previous_text=False)
    return " ".join(s.text for s in segments).strip()

def word_times(wav, lang):
    segments, _ = _model().transcribe(_pcm16k(wav), language=lang, beam_size=5, vad_filter=False, condition_on_previous_text=False, word_timestamps=True)
    return [{"text": str(w.word or "").strip(), "start": float(w.start), "end": float(w.end)} for s in segments for w in (getattr(s, "words", None) or []) if w.word and w.start is not None and w.end is not None]

def norm(text, lang):
    text = str(text)
    if lang == "fa":
        text = _FA_DIACRITICS.sub("", text).replace("\u200c", "")
        text = text.translate(str.maketrans({"ي":"ی","ك":"ک","ة":"ه","أ":"ا","إ":"ا","ؤ":"و"}))
        return re.sub(r"[^\u0600-\u06ff]", "", text)
    return re.sub(r"[^a-z]", "", text.lower())

def align(text, wav, lang="fa"):
    tokens = text.split()
    if not tokens or not available(): return None
    try: heard_words = word_times(wav, lang)
    except Exception as exc:
        log(f"timing check skipped: {type(exc).__name__}: {str(exc)[:200]}")
        return None
    if len(heard_words) < max(2, len(tokens)//3): return None
    h = [max(1, len(norm(x["text"], lang))) for x in heard_words]
    s = [max(1, len(norm(x, lang))) for x in tokens]
    if not 0.5 <= sum(h) / max(1, sum(s)) <= 2.0: return None
    bounds, cursor = [], 0.0
    total = float(sum(h))
    for item, size in zip(heard_words, h):
        lo = cursor / total; cursor += size
        bounds.append((lo, cursor / total, item["start"], max(item["end"], item["start"] + .02)))
    def at(frac, start_side):
        for lo, hi, t0, t1 in bounds:
            if (lo <= frac < hi) if start_side else (lo < frac <= hi):
                return t0 + (frac - lo) / max(.0001, hi - lo) * (t1 - t0)
        return bounds[0][2] if frac <= 0 else bounds[-1][3]
    out, cursor, last_end = [], 0.0, 0.0
    total_s = float(sum(s))
    for token, size in zip(tokens, s):
        start = max(at(cursor / total_s, True), last_end)
        cursor += size
        end = max(at(cursor / total_s, False), start + .05)
        out.append({"text": token, "start": round(start, 3), "end": round(end, 3)})
        last_end = end
    return out

def heard(word, asr, lang):
    w, a = norm(word, lang), norm(asr, lang)
    if not w: return 1.0
    if not a: return 0.0
    if w in a: return 1.0
    return max((SequenceMatcher(None, w, a[i:i+len(w)+2]).ratio() for i in range(max(1, len(a)-len(w)+1))), default=0.0)

def checkable(token, lang):
    core = token.strip(_EDGE)
    return bool(core and not re.search(r"[0-9۰-۹]", core) and len(norm(core, lang)) >= (4 if lang == "en" else 3) and (lang != "en" or core.lower() not in EN_SKIP))

def candidates(core, lang):
    out=[]
    if lang == "fa":
        base = _FA_DIACRITICS.sub("", core)
        out.extend(base[:1] + mark + base[1:] for mark in ("َ","ِ","ُ"))
        if "\u200c" in base: out.append(base.replace("\u200c", ""))
    else:
        rules = [(r"ch","k"),(r"ph","f"),(r"th","t"),(r"ai","eye"),(r"ou","oo"),(r"^j","y"),(r"w","v"),(r"x","ks"),(r"e$","eh"),(r"y","i")]
        for pat, rep in rules:
            value = re.sub(pat, rep, core.lower(), count=1)
            if value != core.lower(): out.append(value[:1].upper()+value[1:] if core[:1].isupper() else value)
    return list(dict.fromkeys(out))[:MAX_CANDIDATES]

def learned(lang):
    try: return dict(json.loads(LEARNED.read_text(encoding="utf-8")).get(lang, {}))
    except Exception: return {}

def _save_learned(lang, word, say):
    try: data = json.loads(LEARNED.read_text(encoding="utf-8")) if LEARNED.exists() else {}
    except Exception: data = {}
    data.setdefault(lang, {})[word] = say
    LEARNED.parent.mkdir(parents=True, exist_ok=True)
    LEARNED.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def write_report(story_id, lang):
    if not ENABLED: status = "disabled"
    elif _FAILED: status = "off"
    elif _MODEL is None: status = "not-run"
    elif _START is not None and time.time() - _START > BUDGET: status = "out-of-time"
    elif _BEATS == 0 and _REASON: status = "error"
    else: status = "ok"
    try: data = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else []
    except Exception: data = []
    data.append({"date": datetime.now(TEHRAN).date().isoformat(), "story": story_id, "lang": lang, "status": status, "beats_checked": _BEATS, "reason": _REASON, "events": list(EVENTS)})
    REPORT.parent.mkdir(parents=True, exist_ok=True); REPORT.write_text(json.dumps(data[-60:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    EVENTS.clear()

def review_beat(text, parts, bwords, wav, lang, synth, key=None):
    global _FIXES, _TRIES, _BEATS, _REASON
    if _FIXES >= MAX_FIXES or not available(): return parts, bwords
    try:
        tokens = text.split()
        if len(tokens) != len(parts): _REASON = _REASON or "script/audio token count mismatch"; return parts, bwords
        asr = transcribe(wav, lang); _BEATS += 1
        weak = sorted((heard(tok, asr, lang), i) for i, tok in enumerate(tokens) if checkable(tok, lang))
        for score, i in [x for x in weak if x[0] < BAD][:2]:
            core = tokens[i].strip(_EDGE); best = None
            event = {"word": core, "heard": asr, "score": round(score,2), "kept": None}
            for cand in candidates(core, lang):
                if _TRIES >= MAX_TRIES: break
                _TRIES += 1; trial = list(parts); trial[i] = tokens[i].replace(core, cand, 1)
                tmp = Path(wav).with_name(Path(wav).stem + "_try.wav")
                bw2 = synth(" ".join(trial), tmp); score2 = heard(core, transcribe(tmp, lang), lang)
                if score2 >= GOOD and score2 >= score + GAIN and (best is None or score2 > best[0]): best = (score2, cand, trial, bw2, tmp.read_bytes())
            if best:
                score2, cand, trial, bw2, audio = best; Path(wav).write_bytes(audio); parts, bwords = trial, bw2; _FIXES += 1
                event.update(kept=cand, new_score=round(score2,2)); _save_learned(lang, key(core) if key else core, cand)
            EVENTS.append(event)
    except Exception as exc:
        _REASON = _REASON or f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        try: Path(wav).with_name(Path(wav).stem + "_try.wav").unlink(missing_ok=True)
        except Exception: pass
    return parts, bwords
