"""NABZ Mysteries in Persian: an Instagram Reel built from the same day's Short.

Runs right after src.mystery_short in the same job and reuses its AI pictures
(no extra image quota). The narration, captions, title hook and cover are in
Persian (content/mysteries_fa.json, written and fact-checked by hand, never
generated). Output: output/reel-fa/{reel.mp4, cover.jpg, caption.txt, meta.json}.

Never fails the workflow: any problem writes output/reel-fa/skip.txt and exits 0.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, features

from src import mystery_short as m

ROOT = m.ROOT
FA_BANK = ROOT / "content" / "mysteries_fa.json"
OUT = ROOT / "output" / "reel-fa"
WORK = OUT / "work"
SRC_WORK = m.WORK
W, H, FPS, SR = m.W, m.H, m.FPS, m.SR
VOICE = os.getenv("NABZ_FA_VOICE", "fa-IR-FaridNeural")
RATE = os.getenv("NABZ_FA_RATE", "+6%")
PITCH = os.getenv("NABZ_FA_PITCH", "-2Hz")
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
}
_FA_EDGE = ".,!?:;\u060c\u061b\u061f\u00ab\u00bb\"'()"


def spoken(text: str) -> str:
    """What the voice reads: whitespace tidied, ambiguous words respelled (same word count)."""
    out = []
    for tok in text.split():
        core = tok.strip(_FA_EDGE)
        say = FA_PRONOUNCE.get(core)
        out.append(tok.replace(core, say, 1) if say and core else tok)
    return " ".join(out)


def narrate(beats: list[str]):
    pieces, durations, words = [], [], []
    clock = 0.0
    for i, text in enumerate(beats):
        mp3, wav = WORK / f"voice_{i}.mp3", WORK / f"voice_{i}.wav"
        bwords = asyncio.run(_tts(spoken(text), mp3))
        m.to_wav(mp3, wav)
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
    voice, durations, words = narrate(fa["beats"])
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
            "built_date": datetime.now(TEHRAN).date().isoformat(), "shots": len(shots), "checks": checks}
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Persian reel ready: {meta}")
    return meta


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        story = json.loads((m.OUT / "story.json").read_text(encoding="utf-8"))
        bank = load_fa()
        fa = bank.get(story["id"])
        if not fa:
            raise RuntimeError(f"no Persian version of {story['id']} yet")
        left = [k for k in bank if k not in set(m.load_state().get("mysteries", []))]
        if len(left) <= 5:
            print(f"::warning title=Persian bank low::only {len(left)} Persian stories left; translate the next batch.")
        build(story, fa)
    except Exception as exc:
        msg = re.sub(r"[\r\n]+", " ", f"{type(exc).__name__}: {exc}")[:600]
        (OUT / "skip.txt").write_text(msg, encoding="utf-8")
        print(f"::warning title=Persian reel skipped::{msg}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
