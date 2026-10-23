"""Automatic voice-check helpers with safe, monotonic caption timing."""
from __future__ import annotations
import json, os, re, time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEARNED = ROOT / "review" / "pron_learned.json"
REPORT = ROOT / "review" / "voice_check.json"
ENABLED = os.getenv("NABZ_VOICE_CHECK", "1") == "1"
BUDGET = float(os.getenv("NABZ_VOICE_CHECK_SECONDS", "480"))
BAD, GOOD, GAIN = .6, .8, .25
MAX_FIXES = 6
_MAX_TRIES = int(os.getenv("NABZ_VOICE_CHECK_TRIES", "12"))
TEHRAN = timezone(timedelta(hours=3, minutes=30))
_MODEL = None
_FAILED = False
_START = None
_FIXES = _TRIES = _BEATS = 0
_REASON = ""
EVENTS = []
_EDGE = ".,!?:;\"'()،؛؟«»"
_FA_DIACRITICS = re.compile("[\u064b-\u0652\u0670]")
EN_SKIP = set("one two three four five six seven eight nine ten hundred thousand million".split())

def log(msg): print(f"[voice-check] {msg}", flush=True)

def _model():
    global _MODEL, _FAILED, _START, _REASON
    if _MODEL is not None or _FAILED or not ENABLED: return _MODEL
    try:
        from faster_whisper import WhisperModel
        _MODEL = WhisperModel(os.getenv("NABZ_ASR_MODEL", "small"), device="cpu", compute_type="int8")
        _START = time.time()
    except Exception as exc:
        _FAILED, _REASON = True, f"{type(exc).__name__}: {str(exc)[:200]}"
        log(f"turned off for this run: {_REASON}")
    return _MODEL

def available():
    return bool(ENABLED and not _FAILED and (_START is None or time.time() - _START <= BUDGET) and _model())

def norm(text, lang):
    text = str(text)
    if lang == "fa":
        text = _FA_DIACRITICS.sub("", text).replace("\u200c", "")
        text = text.translate(str.maketrans({"ي":"ی","ك":"ک","ة":"ه","أ":"ا","إ":"ا","ؤ":"و"}))
        return re.sub(r"[^\u0600-\u06ff]", "", text)
    return re.sub(r"[^a-z]", "", text.lower())

def _pcm16k(wav):
    import numpy as np, subprocess
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(wav), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, check=True, timeout=120).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

def transcribe(wav, lang):
    segments, _ = _model().transcribe(_pcm16k(wav), language=lang, beam_size=5, vad_filter=False, condition_on_previous_text=False)
    return " ".join(s.text for s in segments).strip()

def word_times(wav, lang):
    segments, _ = _model().transcribe(_pcm16k(wav), language=lang, beam_size=5, vad_filter=False, condition_on_previous_text=False, word_timestamps=True)
    return [{"text":str(w.word or "").strip(),"start":float(w.start),"end":float(w.end)} for s in segments for w in (getattr(s,"words",None) or []) if w.word and w.start is not None and w.end is not None]

def align(text, wav, lang="fa"):
    tokens = text.split()
    if not tokens or not available(): return None
    try: heard_words = word_times(wav, lang)
    except Exception as exc: log(f"timing check skipped: {type(exc).__name__}"); return None
    if len(heard_words) < max(2, len(tokens)//3): return None
    total = max(1, sum(max(1, len(norm(w["text"],lang))) for w in heard_words))
    out, cursor = [], 0.0
    for i, token in enumerate(tokens):
        start = max(cursor, heard_words[min(i,len(heard_words)-1)]["start"])
        end = max(start + .05, heard_words[min(i,len(heard_words)-1)]["end"])
        out.append({"text":token,"start":round(start,3),"end":round(end,3)})
        cursor = end
    return out

def heard(word, asr, lang):
    w, a = norm(word,lang), norm(asr,lang)
    if not w: return 1.0
    if w in a: return 1.0
    return max((SequenceMatcher(None,w,a[i:i+len(w)+2]).ratio() for i in range(max(1,len(a)-len(w)+1))), default=0.0)

def checkable(token, lang):
    core = token.strip(_EDGE)
    return bool(core and not re.search(r"[0-9۰-۹]", core) and (len(norm(core,lang)) >= (4 if lang == "en" else 3)) and (lang != "en" or core.lower() not in EN_SKIP))

def candidates(core, lang): return []
def learned(lang):
    try: return dict(json.loads(LEARNED.read_text(encoding="utf-8")).get(lang,{}))
    except Exception: return {}
def write_report(story_id, lang):
    data=[]
    try: data=json.loads(REPORT.read_text(encoding="utf-8"))
    except Exception: pass
    data.append({"date":datetime.now(TEHRAN).date().isoformat(),"story":story_id,"lang":lang,"status":"off" if _FAILED else ("disabled" if not ENABLED else "ok"),"beats_checked":_BEATS,"reason":_REASON,"events":list(EVENTS)})
    REPORT.parent.mkdir(parents=True,exist_ok=True); REPORT.write_text(json.dumps(data[-60:],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def review_beat(text, parts, bwords, wav, lang, synth, key=None): return parts, bwords
