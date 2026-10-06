"""NABZ Mysteries: vertical YouTube Shorts (1080x1920, ~30 s).

Pipeline: curated script -> AI images (Pollinations FLUX, Hugging Face fallback)
-> deep native-English narration (Gemini TTS, Edge TTS fallback) with word timings -> procedural dark ambient music with
ducking -> Ken Burns motion + crossfades -> word-by-word burned captions ->
quality gate -> metadata for upload. No paid service is required.

Scripts open with the hook and end on a half sentence that flows back into the
first line, so the Short loops seamlessly (higher average view percentage).
Long beats get a second camera angle (a new picture every ~2-3 s) and the story
title is shown big for the first seconds, to cut early swipes.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat

from src import gemini_tts, voice_check

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "content" / "mysteries.json"
STATE = ROOT / "content" / "published.json"
OUT = ROOT / "output" / "mystery-short"
WORK = OUT / "work"

W, H, FPS = 1080, 1920, 30
SR = 44100
XFADE = 0.45
BEAT_GAP = 0.18
TAIL = 0.5  # short tail so the last line runs straight back into the first (loop)
VOICE = os.getenv("NABZ_MYSTERY_VOICE", "en-US-ChristopherNeural")
RATE = os.getenv("NABZ_MYSTERY_RATE", "+8%")
PITCH = os.getenv("NABZ_MYSTERY_PITCH", "-3Hz")
STYLE = (
    "cinematic photorealistic film still, dark moody atmosphere, dramatic chiaroscuro lighting, "
    "volumetric fog, muted teal and amber color grade, 35mm film grain, highly detailed, "
    "vertical composition, no text, no letters, no watermark, no logo"
)
FONT_CANDIDATES = [
    os.getenv("NABZ_CAPTION_FONT", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
MIN_WORDS, MAX_WORDS = 60, 95
# Pacing: a beat longer than this gets two shots (new picture every ~2-3 s keeps viewers watching).
SPLIT_MIN_SECONDS = float(os.getenv("NABZ_SPLIT_MIN_SECONDS", "2.6"))
SECOND_SHOT = [
    "extreme close-up detail shot of the key object",
    "wide establishing shot from a different angle",
    "low angle dramatic shot, different framing",
    "over-the-shoulder view, shallow depth of field",
]
HOOK_SECONDS = 2.8  # story title shown big at the very start, before anyone swipes


# ---------------------------------------------------------------- utilities
def log(msg: str) -> None:
    print(f"[mystery] {msg}", flush=True)


def ffmpeg_exe() -> str:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def run_ffmpeg(args: list[str]) -> None:
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + proc.stderr.strip()[-1500:])


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if path and Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise RuntimeError("No bold TrueType font found for captions (install fonts-dejavu-core).")


# ---------------------------------------------------------------- story bank
def validate_story(story: dict) -> None:
    for key in ("id", "title", "beats", "tags"):
        if not story.get(key):
            raise RuntimeError(f"story missing {key}")
    beats = story["beats"]
    if not 6 <= len(beats) <= 8:
        raise RuntimeError(f"{story['id']}: needs 6-8 beats")
    for b in beats:
        if not b.get("text", "").strip() or not b.get("visual", "").strip():
            raise RuntimeError(f"{story['id']}: every beat needs text and visual")
    words = sum(len(b["text"].split()) for b in beats)
    if not MIN_WORDS <= words <= MAX_WORDS:
        raise RuntimeError(f"{story['id']}: {words} words, expected {MIN_WORDS}-{MAX_WORDS}")
    if len(story["title"]) > 60:
        raise RuntimeError(f"{story['id']}: title too long for '#Shorts' suffix")


def load_bank(path: Path = BANK) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    stories = data["stories"]
    ids = [s["id"] for s in stories]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate story ids in bank")
    for s in stories:
        validate_story(s)
    return stories


def load_state(path: Path = STATE) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def pick_story(stories: list[dict], state: dict, forced: str = "") -> dict:
    if forced:
        for s in stories:
            if s["id"] == forced:
                return s
        raise RuntimeError(f"unknown story id {forced}")
    used = list(state.get("mysteries", []))
    fresh = [s for s in stories if s["id"] not in used]
    if fresh:
        return fresh[0]
    by_id = {s["id"]: s for s in stories}
    for sid in used:  # oldest first
        if sid in by_id:
            return by_id[sid]
    return stories[0]


def record_story(story_id: str, path: Path = STATE) -> None:
    state = load_state(path)
    used = [x for x in state.get("mysteries", []) if x != story_id]
    used.append(story_id)
    state["mysteries"] = used
    # lets the backup crons know today's Short is done (date in Tehran time)
    tehran = datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)
    state["last_built_date"] = tehran.date().isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- images
def _valid_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGB")
    if min(img.size) < 480:
        raise RuntimeError(f"image too small {img.size}")
    stat = ImageStat.Stat(img.convert("L"))
    if stat.stddev[0] < 8:
        raise RuntimeError("image is blank/uniform")
    return img


def _http(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "NabzAI/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _pollinations(prompt: str, seed: int) -> Image.Image:
    # Pollinations now requires a key (free account at enter.pollinations.ai).
    token = os.getenv("POLLINATIONS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("POLLINATIONS_TOKEN not configured")
    params = {"width": 1080, "height": 1920, "model": "flux", "nologo": "true", "private": "true",
              "enhance": "false", "seed": seed}
    url = "https://gen.pollinations.ai/image/" + urllib.parse.quote(prompt, safe="") + "?" + urllib.parse.urlencode(params)
    return _valid_image(_http(url, headers={"Authorization": f"Bearer {token}"}, timeout=240))


_SPACE_CLIENTS: dict = {}
_SPACE_DEAD: set = set()


def _hf_space(prompt: str, seed: int) -> Image.Image:
    """FLUX.1-schnell Gradio Space (free ZeroGPU quota of the HF account)."""
    from gradio_client import Client
    token = os.getenv("HF_TOKEN", "").strip() or None
    errors = []
    spaces = [x.strip() for x in os.getenv("NABZ_FLUX_SPACES", "black-forest-labs/FLUX.1-schnell").split(",") if x.strip()]
    for space in spaces:
        if space in _SPACE_DEAD:
            errors.append(f"{space}: quota exhausted earlier in this run")
            continue
        try:
            if space not in _SPACE_CLIENTS:
                _SPACE_CLIENTS[space] = Client(space, hf_token=token, verbose=False)
            result = _SPACE_CLIENTS[space].predict(prompt, int(seed) % 2147483647, False, 768, 1344, 4,
                                                   api_name="/infer")
            value = result[0] if isinstance(result, (list, tuple)) else result
            if isinstance(value, dict):
                value = value.get("path") or value.get("url")
            if isinstance(value, str) and value.startswith("http"):
                return _valid_image(_http(value, timeout=120))
            return _valid_image(Path(str(value)).read_bytes())
        except Exception as exc:
            if "quota" in str(exc).lower():
                _SPACE_DEAD.add(space)
            errors.append(f"{space}: {type(exc).__name__}: {str(exc)[:300]}")
    raise RuntimeError(" | ".join(errors))


def _huggingface(prompt: str, seed: int) -> Image.Image:
    """HF Inference Providers (routed; uses the account's monthly free credit)."""
    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        raise RuntimeError("HF_TOKEN not configured")
    from huggingface_hub import InferenceClient
    errors = []
    for provider in [x.strip() for x in os.getenv("NABZ_HF_PROVIDERS", "auto,nebius,together,fal-ai").split(",") if x.strip()]:
        try:
            client = InferenceClient(provider=provider, api_key=token, timeout=240)
            img = client.text_to_image(prompt, model="black-forest-labs/FLUX.1-schnell",
                                       width=768, height=1344, seed=seed)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return _valid_image(buf.getvalue())
        except Exception as exc:
            errors.append(f"{provider}: {type(exc).__name__}: {str(exc)[:160]}")
    raise RuntimeError(" | ".join(errors))


def cover(img: Image.Image, size=(W, H)) -> Image.Image:
    return ImageOps.fit(img, size, method=Image.LANCZOS, centering=(0.5, 0.45))


def generate_image(prompt: str, seed: int, target: Path) -> str:
    key = hashlib.sha1(f"{prompt}|{seed}".encode()).hexdigest()[:12]
    marker = target.with_suffix(".key")
    if target.exists() and marker.exists() and marker.read_text() == key:
        return "cache"
    providers = [p.strip() for p in os.getenv("NABZ_IMAGE_PROVIDERS", "hfspace,pollinations,huggingface").split(",") if p.strip()]
    funcs = {"hfspace": _hf_space, "pollinations": _pollinations, "huggingface": _huggingface}
    errors = []
    for name in providers:
        if name not in funcs:
            continue
        if name == "pollinations" and not os.getenv("POLLINATIONS_TOKEN", "").strip():
            continue
        attempts = 2 if name in ("hfspace", "pollinations") else 1
        for attempt in range(attempts):
            try:
                img = funcs[name](prompt, seed + attempt)
                cover(img).save(target, quality=93)
                marker.write_text(key)
                return name
            except Exception as exc:
                errors.append(f"{name}#{attempt + 1}: {type(exc).__name__}: {str(exc)[:200]}")
                log(errors[-1])
                if "quota" in str(exc).lower() or "credit" in str(exc).lower():
                    break
                time.sleep(5 + 10 * attempt)
    raise RuntimeError("all image providers failed: " + " || ".join(errors))


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


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        ch = wf.getnchannels()
    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return data.reshape(-1, ch).mean(axis=1) if ch > 1 else data


def write_wav(path: Path, stereo: np.ndarray) -> None:
    pcm = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def to_wav(src: Path, dst: Path) -> None:
    run_ffmpeg(["-i", str(src), "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(dst)])


def _norm(tok: str) -> str:
    return re.sub(r"[^a-z0-9]", "", tok.lower())


# Spoken-only respellings: the voice reads these, captions keep the real spelling.
PRONOUNCE = {
    "voynich": "Voynitch",
    "codebreakers": "code breakers",
    "ii": "Two",
    "königsberg": "Kernigsberg",
    "taos": "Touse",
    "valentich": "Valentitch",
    "hinterkaifeck": "Hinter Kyfeck",
    "cambyses": "Cambyseez",
    "baychimo": "Baycheemo",
    "tamam": "Tamahm",
    "shud": "Shood",
}
# respellings the listening check proved better in earlier runs (review/pron_learned.json)
PRONOUNCE.update({k.lower(): v for k, v in voice_check.learned("en").items()})
_EDGE = ".,?!:;\"'()"


def pronounce(text: str) -> tuple[str, list[str]]:
    """Text for the voice, plus what each script word is spoken as."""
    parts = []
    for tok in text.split():
        core = tok.strip(_EDGE)
        say = PRONOUNCE.get(core.lower())
        parts.append(tok.replace(core, say, 1) if say and core else tok)
    return " ".join(parts), parts


def restore_words(text: str, parts: list[str], bwords: list[dict], dur: float) -> list[dict]:
    """Map word timings of the respelled narration back onto the script's own words."""
    out, bi = [], 0
    for orig, spoken in zip(text.split(), parts):
        target = _norm(spoken)
        if not target:
            continue
        got, first, last = "", None, None
        while bi < len(bwords) and len(got) < len(target):
            w = bwords[bi]
            bi += 1
            nw = _norm(w["text"])
            if not nw:
                continue
            first = first or w
            last = w
            got += nw
        if got != target or first is None:
            log("pronunciation alignment failed; using estimated word timings")
            return estimate_words(text, dur)
        out.append({"text": orig.strip(_EDGE), "start": first["start"], "end": last["end"]})
    return out


def mark_punctuation(text: str, words: list[dict]) -> list[dict]:
    """Edge TTS word boundaries drop punctuation; copy sentence/clause ends from the script."""
    tokens = [t for t in text.split() if _norm(t)]
    ti, rest = 0, (_norm(tokens[0]) if tokens else "")
    for w in words:
        nw = _norm(w["text"])
        w["punct"] = False
        if not nw or ti >= len(tokens):
            continue
        if rest.startswith(nw):
            rest = rest[len(nw):]
            if not rest:
                w["punct"] = bool(re.search(r"[.?!,:;]$", tokens[ti]))
                ti += 1
                rest = _norm(tokens[ti]) if ti < len(tokens) else ""
    return words


def estimate_words(text: str, duration: float) -> list[dict]:
    tokens = text.split()
    weights = [len(t) + 2 + (4 if t[-1:] in ".,?!:;" else 0) for t in tokens]
    total = sum(weights) or 1
    t, out = 0.05, []
    span = max(0.5, duration - 0.1)
    for tok, w in zip(tokens, weights):
        d = span * w / total
        out.append({"text": tok.strip(".,?!:;\"'"), "start": t, "end": t + d * 0.9,
                    "punct": bool(re.search(r"[.?!,:;]$", tok))})
        t += d
    return out


def _synth(text: str, wav: Path) -> list[dict]:
    mp3 = wav.with_suffix(".mp3")
    words = asyncio.run(_tts(text, mp3))
    to_wav(mp3, wav)
    return words


def _gemini_synth(text: str, wav: Path) -> list[dict]:
    """Gemini narration for one beat; word timings are spread over the trimmed speech."""
    return estimate_words(text, gemini_tts.synth(text, wav, SR))


def narrate(story: dict, engine: str = "edge") -> tuple[np.ndarray, list[float], list[dict]]:
    """Returns mono narration, per-beat slot durations and global word timings."""
    pieces, durations, words = [], [], []
    clock = 0.0
    synth = _gemini_synth if engine == "gemini" else _synth
    for i, beat in enumerate(story["beats"]):
        mp3, wav = WORK / f"voice_{i}.mp3", WORK / f"voice_{i}.wav"
        spoken, parts = pronounce(beat["text"])
        if engine == "gemini":
            bwords = _gemini_synth(spoken, wav)
        else:
            bwords = asyncio.run(_tts(spoken, mp3))
            to_wav(mp3, wav)
        if voice_check.ENABLED:
            parts, bwords = voice_check.review_beat(beat["text"], parts, bwords, wav, "en", synth,
                                                    key=str.lower)
            spoken = " ".join(parts)
        audio = read_wav(wav)
        dur = len(audio) / SR
        if dur < 1.0:
            raise RuntimeError(f"beat {i} narration too short")
        if engine == "gemini":
            bwords = estimate_words(beat["text"], dur)  # no word boundaries: script words over the speech
        elif not bwords:
            bwords = estimate_words(beat["text"], dur)
        else:
            if spoken != beat["text"]:
                bwords = restore_words(beat["text"], parts, bwords, dur)
            mark_punctuation(beat["text"], bwords)
        gap = TAIL if i == len(story["beats"]) - 1 else BEAT_GAP
        slot = dur + gap
        pieces.append(np.concatenate([audio, np.zeros(int(gap * SR), dtype=np.float32)]))
        for w in bwords:
            words.append({"text": w["text"], "start": clock + w["start"], "end": clock + w["end"],
                          "beat": i, "punct": bool(w.get("punct"))})
        durations.append(slot)
        clock += slot
    voice = np.concatenate(pieces)
    peak = float(np.max(np.abs(voice))) or 1.0
    return voice * (0.92 / peak), durations, words


def make_music(seconds: float, seed: int) -> np.ndarray:
    """Dark ambient drone with a slow heartbeat pulse; returns stereo float (n, 2)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    root = float(rng.choice([49.0, 51.91, 55.0, 58.27]))
    left = np.zeros(n)
    right = np.zeros(n)
    for ratio, amp in ((1.0, 0.5), (1.5, 0.28), (2.0, 0.22), (2.378, 0.12), (3.0, 0.08)):
        f = root * ratio
        ph = rng.uniform(0, 2 * np.pi, 2)
        lfo = 0.65 + 0.35 * np.sin(2 * np.pi * rng.uniform(0.03, 0.09) * t + ph[0])
        left += amp * lfo * np.sin(2 * np.pi * f * t + ph[0])
        right += amp * lfo * np.sin(2 * np.pi * f * 1.003 * t + ph[1])
    brown = np.cumsum(rng.standard_normal(n))
    brown -= np.convolve(brown, np.ones(4410) / 4410, mode="same")
    brown /= (np.max(np.abs(brown)) or 1)
    left += 0.06 * brown
    right += 0.06 * np.roll(brown, 2205)
    period = 1.6
    beat = np.zeros(n)
    k = np.arange(int(0.35 * SR)) / SR
    thump = np.sin(2 * np.pi * 42 * k) * np.exp(-k * 14)
    for start in np.arange(1.0, seconds, period):
        for off in (0.0, 0.28):
            s = int((start + off) * SR)
            e = min(n, s + len(thump))
            if s < n:
                beat[s:e] += thump[: e - s] * (0.9 if off == 0 else 0.6)
    left += 0.35 * beat
    right += 0.35 * beat
    env = np.ones(n)
    fi, fo = int(1.5 * SR), int(2.0 * SR)
    env[:fi] = np.linspace(0, 1, fi)
    env[-fo:] = np.linspace(1, 0, fo)
    out = np.stack([left * env, right * env], axis=1)
    return out / (np.max(np.abs(out)) or 1)


def mix(voice: np.ndarray, music: np.ndarray, music_level: float = 0.2) -> np.ndarray:
    n = len(voice)
    music = music[:n] if len(music) >= n else np.pad(music, ((0, n - len(music)), (0, 0)))
    win = int(0.25 * SR)
    envelope = np.convolve(np.abs(voice), np.ones(win) / win, mode="same")
    envelope /= (np.max(envelope) or 1)
    duck = 1.0 - 0.55 * np.clip(envelope * 3, 0, 1)
    stereo = np.stack([voice, voice], axis=1) + music * (music_level * duck)[:, None]
    peak = float(np.max(np.abs(stereo))) or 1.0
    return stereo * (0.95 / peak)


# ---------------------------------------------------------------- captions
CAP_H = 560
CAP_Y = 1010


def chunk_words(words: list[dict], max_words: int = 3, max_chars: int = 16) -> list[list[dict]]:
    chunks, cur = [], []
    for w in words:
        text = w["text"].strip()
        if not text:
            continue
        candidate = " ".join(x["text"] for x in cur + [w])
        new_beat = cur and w.get("beat") != cur[-1].get("beat")
        if cur and (len(cur) >= max_words or len(candidate) > max_chars or new_beat):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if w.get("punct") or re.search(r"[.?!,:;]$", text):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def caption_timeline(words: list[dict], total: float) -> list[tuple[float, float, int, int]]:
    """List of (start, end, chunk_index, highlighted_word_index) covering speech; gaps are blank."""
    chunks = chunk_words(words)
    events = []
    for ci, ch in enumerate(chunks):
        nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else total
        for wi, w in enumerate(ch):
            start = w["start"]
            end = ch[wi + 1]["start"] if wi + 1 < len(ch) else min(nxt, w["end"] + 0.35)
            if end - start < 0.04:
                end = start + 0.04
            events.append((start, end, ci, wi))
    return events, chunks


def render_caption(chunk: list[dict], hi: int, path: Path) -> None:
    canvas = Image.new("RGBA", (W, CAP_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    words = [re.sub(r"[\"“”]", "", w["text"]).upper() for w in chunk]
    size = 104
    while size > 60:
        f = font(size)
        space = draw.textlength(" ", font=f)
        widths = [draw.textlength(x, font=f) for x in words]
        if sum(widths) + space * (len(words) - 1) <= W - 120:
            break
        size -= 6
    f = font(size)
    space = draw.textlength(" ", font=f)
    widths = [draw.textlength(x, font=f) for x in words]
    x = (W - (sum(widths) + space * (len(words) - 1))) / 2
    y = CAP_H / 2 - size * 0.6
    for i, (word, wd) in enumerate(zip(words, widths)):
        fill = (255, 214, 0, 255) if i == hi else (255, 255, 255, 255)
        dy = -6 if i == hi else 0
        draw.text((x + 4, y + dy + 6), word, font=f, fill=(0, 0, 0, 150))
        draw.text((x, y + dy), word, font=f, fill=fill, stroke_width=9, stroke_fill=(0, 0, 0, 255))
        x += wd + space
    canvas.save(path)


def build_caption_track(words: list[dict], total: float, target: Path) -> int:
    events, chunks = caption_timeline(words, total)
    cap_dir = WORK / "captions"
    cap_dir.mkdir(parents=True, exist_ok=True)
    blank = cap_dir / "blank.png"
    Image.new("RGBA", (W, CAP_H), (0, 0, 0, 0)).save(blank)
    lines, cursor, rendered = [], 0.0, {}
    for start, end, ci, wi in events:
        if start > cursor + 0.01:
            lines += [f"file '{blank.as_posix()}'", f"duration {start - cursor:.3f}"]
        key = (ci, wi)
        if key not in rendered:
            p = cap_dir / f"c{ci:03d}_{wi}.png"
            render_caption(chunks[ci], wi, p)
            rendered[key] = p
        lines += [f"file '{rendered[key].as_posix()}'", f"duration {end - start:.3f}"]
        cursor = end
    if total > cursor:
        lines += [f"file '{blank.as_posix()}'", f"duration {total - cursor:.3f}"]
    lines.append(f"file '{blank.as_posix()}'")
    listing = cap_dir / "list.txt"
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-vf", f"fps={FPS},format=rgba",
                "-t", f"{total:.3f}", "-c:v", "qtrle", str(target)])
    return len(rendered)


def render_badge(text: str, path: Path) -> None:
    f = font(46)
    pad_x, pad_y = 34, 18
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    tw = int(tmp.textlength(text, font=f))
    img = Image.new("RGBA", (tw + pad_x * 2, 46 + pad_y * 2 + 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=18, fill=(200, 16, 32, 235))
    d.text((pad_x, pad_y - 2), text, font=f, fill=(255, 255, 255, 255))
    img.save(path)


def render_hook_title(title: str, path: Path) -> None:
    """Big title card for the first seconds: the viewer knows the story before deciding to swipe."""
    words = re.sub(r"\s*#\w+", "", title).upper().split()
    size = 92
    while True:
        f = font(size)
        probe_draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if probe_draw.textlength(test, font=f) > W - 150 and cur:
                lines.append(cur)
                cur = w
            else:
                cur = test
        lines.append(cur)
        if len(lines) <= 3 or size <= 64:
            break
        size -= 6
    line_h = int(size * 1.18)
    img = Image.new("RGBA", (W, line_h * len(lines) + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 20
    for line in lines:
        tw = d.textlength(line, font=f)
        d.text(((W - tw) / 2 + 4, y + 6), line, font=f, fill=(0, 0, 0, 160))
        d.text(((W - tw) / 2, y), line, font=f, fill=(255, 255, 255, 255), stroke_width=9,
               stroke_fill=(0, 0, 0, 255))
        y += line_h
    img.save(path)


def render_watermark(path: Path) -> None:
    """Small premium brand mark; the box is sized to the text so it is never clipped."""
    f = font(34)
    text = "NABZ MYSTERIES"
    tw = int(ImageDraw.Draw(Image.new("RGBA", (10, 10))).textlength(text, font=f))
    w = 74 + tw + 22
    img = Image.new("RGBA", (w, 72), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, 71], radius=20, fill=(8, 8, 8, 150),
                        outline=(205, 155, 58, 180), width=2)
    d.ellipse([14, 14, 58, 58], fill=(190, 25, 35, 230), outline=(255, 215, 130, 220), width=2)
    d.text((36, 36), "?", font=font(31), fill=(255, 235, 180, 255), anchor="mm")
    d.text((74, 36), text, font=f, fill=(246, 220, 160, 235), anchor="lm")
    img.save(path)


# ---------------------------------------------------------------- video
MOTIONS = [
    ("1+0.13*on/{D}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    ("1.13-0.13*on/{D}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    ("1.14", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*(1-on/{D})"),
    ("1.12+0.04*on/{D}", "(iw-iw/zoom)*on/{D}", "ih/2-(ih/zoom/2)"),
    ("1.14", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/{D}"),
    ("1.12+0.04*on/{D}", "(iw-iw/zoom)*(1-on/{D})", "ih/2-(ih/zoom/2)"),
]


def render_segment(image: Path, seconds: float, motion: int, target: Path) -> None:
    frames = max(2, int(round(seconds * FPS)))
    z, x, y = (part.format(D=frames) for part in MOTIONS[motion % len(MOTIONS)])
    vf = (f"scale={W * 2}:{H * 2}:flags=lanczos,"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},"
          "eq=contrast=1.06:saturation=0.92,vignette=PI/5,format=yuv420p")
    run_ffmpeg(["-i", str(image), "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "16", "-r", str(FPS), str(target)])


def assemble(segments: list[Path], durations: list[float], captions: Path, badge: Path,
             watermark: Path, audio: Path, target: Path, hook: Path | None = None) -> None:
    total = sum(durations)
    args: list[str] = []
    for seg in segments:
        args += ["-i", str(seg)]
    n = len(segments)
    args += ["-i", str(captions), "-loop", "1", "-i", str(badge),
             "-loop", "1", "-i", str(watermark), "-i", str(audio)]
    if hook:
        args += ["-loop", "1", "-i", str(hook)]
    parts, last, offset = [], "[0:v]", 0.0
    for i in range(1, n):
        offset += durations[i - 1]
        out = f"[x{i}]"
        parts.append(f"{last}[{i}:v]xfade=transition=fade:duration={XFADE}:offset={offset - XFADE / 2:.3f}{out}")
        last = out
    parts.append(f"{last}[{n}:v]overlay=0:{CAP_Y}:format=auto[vc]")
    parts.append(f"[vc][{n + 1}:v]overlay=(W-w)/2:250:enable='lt(t,3.0)':format=auto[vb]")
    if hook:
        parts.append(f"[vb][{n + 4}:v]overlay=0:360:enable='lt(t,{HOOK_SECONDS})':format=auto[vh]")
        parts.append(f"[vh][{n + 2}:v]overlay=W-w-42:82:format=auto[vwm]")
    else:
        parts.append(f"[vb][{n + 2}:v]overlay=W-w-42:82:format=auto[vwm]")
    parts.append("[vwm]format=yuv420p[vout]")
    args += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", f"{n + 3}:a",
             "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
             "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-movflags", "+faststart", str(target)]
    run_ffmpeg(args)


def split_shots(images: list[Path], extras: list[Path | None], durations: list[float]):
    """Two shots for every long beat (second picture from another angle); sums stay identical."""
    shot_imgs, shot_durs = [], []
    for img, extra, d in zip(images, extras, durations):
        if extra is not None and d >= SPLIT_MIN_SECONDS:
            first = round(d * 0.5, 3)
            shot_imgs += [img, extra]
            shot_durs += [first, d - first]
        else:
            shot_imgs.append(img)
            shot_durs.append(d)
    return shot_imgs, shot_durs


def segment_lengths(durations: list[float]) -> list[float]:
    # every clip except the last overlaps the next one by XFADE (centred on the beat boundary)
    lengths = []
    for i, d in enumerate(durations):
        extra = (XFADE / 2 if i > 0 else 0) + (XFADE / 2 if i < len(durations) - 1 else 0)
        lengths.append(d + extra)
    return lengths


# ---------------------------------------------------------------- thumbnail
def make_thumbnail(image: Path, title: str, target: Path) -> None:
    img = Image.open(image).convert("RGB").resize((W, H))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    for i in range(700):
        d.line([(0, H - 700 + i), (W, H - 700 + i)], fill=(0, 0, 0, int(220 * i / 700)))
    img = Image.alpha_composite(img.convert("RGBA"), shade)
    d = ImageDraw.Draw(img)
    f = font(96)
    words, lines, cur = title.upper().split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d.textlength(test, font=f) > W - 140 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    lines.append(cur)
    y = H - 160 - len(lines) * 112
    for line in lines:
        tw = d.textlength(line, font=f)
        d.text(((W - tw) / 2, y), line, font=f, fill=(255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0))
        y += 112
    img.convert("RGB").save(target, quality=92)


# ---------------------------------------------------------------- quality gate
def probe(path: Path) -> dict:
    proc = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    text = proc.stderr
    info = {"duration": 0.0, "video_codec": "", "audio_codec": "", "resolution": ""}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", text)
    if m:
        info["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    m = re.search(r"Video: (\w+).*?(\d{3,4})x(\d{3,4})", text)
    if m:
        info["video_codec"], info["resolution"] = m[1], f"{m[2]}x{m[3]}"
    m = re.search(r"Audio: (\w+)", text)
    if m:
        info["audio_codec"] = m[1]
    return info


def quality_gate(final: Path, story: dict, image_sources: list[str], caption_frames: int) -> dict:
    info = probe(final)
    checks = {
        "file_ok": final.exists() and final.stat().st_size > 1_000_000,
        "vertical_1080x1920": info["resolution"] == f"{W}x{H}",
        "shorts_duration": 18.0 <= info["duration"] <= 59.5,
        "h264": info["video_codec"] == "h264",
        "aac": info["audio_codec"] == "aac",
        "all_images_generated": len(image_sources) == len(story["beats"]),
        "captions_rendered": caption_frames >= 20,
    }
    report = {**info, "story_id": story["id"], "image_sources": image_sources,
              "caption_frames": caption_frames, "checks": checks, "passed": all(checks.values())}
    return report


# ---------------------------------------------------------------- main
def build(story: dict) -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    seed_base = int(hashlib.sha1(story["id"].encode()).hexdigest()[:6], 16)
    log(f"story: {story['id']} - {story['title']}")

    images, sources = [], []
    for i, beat in enumerate(story["beats"]):
        target = WORK / f"img_{i}.jpg"
        src = generate_image(f"{beat['visual']}, {STYLE}", seed_base + i * 7, target)
        log(f"image {i + 1}/{len(story['beats'])} via {src}")
        images.append(target)
        sources.append(src)

    # second angle per beat; any failure just keeps the single shot (never blocks the build)
    extras: list[Path | None] = []
    for i, beat in enumerate(story["beats"]):
        target = WORK / f"img_{i}_b.jpg"
        angle = SECOND_SHOT[(seed_base + i) % len(SECOND_SHOT)]
        try:
            src = generate_image(f"{beat['visual']}, {angle}, {STYLE}", seed_base + i * 7 + 3, target)
            log(f"second shot {i + 1}/{len(story['beats'])} via {src}")
            extras.append(target)
        except Exception as exc:
            log(f"second shot {i + 1} skipped: {type(exc).__name__}: {str(exc)[:160]}")
            extras.append(None)

    engine = "edge"
    if gemini_tts.available():
        try:
            voice, durations, words = narrate(story, "gemini")
            engine = f"gemini:{gemini_tts.MODEL}:{gemini_tts.VOICE}"
        except Exception as exc:  # one voice for the whole Short: redo every beat with Edge
            log(f"Gemini voice failed, using Edge for the whole Short: {type(exc).__name__}: {str(exc)[:300]}")
            print(f"::warning title=English voice fallback::{type(exc).__name__}: {str(exc)[:300]}", flush=True)
            voice_check.EVENTS.clear()
    else:
        log("Gemini voice off (no GEMINI_API_KEY or NABZ_EN_TTS=edge): using Edge")
    if engine == "edge":
        voice, durations, words = narrate(story, "edge")
        engine = f"edge:{VOICE}"
    log(f"voice: {engine}")
    voice_check.write_report(story["id"], "en")
    total = sum(durations)
    log(f"narration {total:.1f}s, {len(words)} words")
    stereo = mix(voice, make_music(total + 0.5, seed_base))
    audio = WORK / "mix.wav"
    write_wav(audio, stereo)

    shot_imgs, shot_durs = split_shots(images, extras, durations)
    log(f"{len(shot_imgs)} shots, average {total / len(shot_imgs):.1f}s per picture")
    segs = []
    for i, (img, length) in enumerate(zip(shot_imgs, segment_lengths(shot_durs))):
        seg = WORK / f"seg_{i}.mp4"
        render_segment(img, length, (seed_base + i) % len(MOTIONS), seg)
        segs.append(seg)

    captions = WORK / "captions.mov"
    caption_frames = build_caption_track(words, total, captions)
    badge = WORK / "badge.png"
    render_badge(os.getenv("NABZ_MYSTERY_BADGE", "UNSOLVED"), badge)
    watermark = WORK / "watermark.png"
    render_watermark(watermark)
    hook = WORK / "hook_title.png"
    render_hook_title(story["title"], hook)

    final = OUT / "final_short.mp4"
    assemble(segs, shot_durs, captions, badge, watermark, audio, final, hook=hook)
    make_thumbnail(images[0], story["title"], OUT / "thumbnail.jpg")

    report = quality_gate(final, story, sources, caption_frames)
    report["voice"] = engine
    (OUT / "quality.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    meta = {
        "story_id": story["id"],
        "title": f"{story['title']} #Shorts",
        "description": (
            f"{story['beats'][0]['text']}\n\n"
            "NABZ Mysteries: one real unsolved mystery, explained in under a minute.\n"
            "Visuals are AI-generated illustrations; narration uses an AI voice.\n\n"
            "#Shorts #Mystery #Unsolved #History #TrueStory"
        ),
        "tags": story["tags"] + ["mystery", "unsolved mysteries", "shorts", "NABZ Mysteries"],
        "category_id": "27",
    }
    (OUT / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"quality: {'PASS' if report['passed'] else 'FAIL'} {report['checks']}")
    if not report["passed"]:
        raise RuntimeError("mystery short failed quality gate")
    return report


def precheck_youtube() -> None:
    """Fail fast (before spending free GPU quota) if YouTube credentials cannot refresh."""
    if os.getenv("NABZ_PRECHECK_YOUTUBE", "1") != "1":
        return
    if not (os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip() or os.getenv("YOUTUBE_TOKEN", "").strip()):
        return
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from src.youtube_uploader import SCOPES, load_credential_info
    info = load_credential_info()
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    try:
        creds.refresh(Request())
    except Exception as exc:
        raise RuntimeError(f"YouTube credentials rejected before build: {exc}") from None
    log("YouTube credentials OK")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    stories = load_bank()
    story = pick_story(stories, load_state(), os.getenv("NABZ_MYSTERY_ID", "").strip())
    try:
        precheck_youtube()
        build(story)
    except Exception as exc:
        message = re.sub(r"[\r\n]+", " ", f"{type(exc).__name__}: {exc}")[:1800]
        (OUT / "error.txt").write_text(message, encoding="utf-8")
        print(f"::error title=NABZ Mysteries build failed::{message}", flush=True)
        raise
    if os.getenv("NABZ_RECORD_STORY", "1") == "1":
        record_story(story["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
