"""Persian carousel (photo album) posts for «نبض معما», rendered from text.

Slides are drawn here from content/ig_carousels.json (texts written and
fact-checked by hand, never generated), so no images live in the repo.
Style: dark salt/crystal texture, gold kicker, big title, RTL body, brand pill.
"""
from __future__ import annotations

import math
import os
import random
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

W, H = 1080, 1350  # 4:5, the tallest feed format
GOLD = (230, 190, 110)
WHITE = (245, 240, 232)
BODY = (225, 220, 212)
RED = (200, 30, 45)
MUTED = (170, 165, 160)
BRAND = os.getenv("NABZ_IG_BRAND", "نبض معما")
HANDLE = os.getenv("NABZ_IG_HANDLE", "@nabz.moamma")
RAW = "https://raw.githubusercontent.com/NabzKhabarOfficial/NabzKhabar/main/"
FONT_DIR = Path(os.getenv("NABZ_FA_FONT_DIR", "output/fonts"))
FONTS = {"bold": "Vazirmatn-Bold.ttf", "regular": "Vazirmatn-Regular.ttf"}
_CACHE: dict = {}


def fa_digits(text) -> str:
    return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def ensure_fonts() -> None:
    if not features.check("raqm"):
        raise RuntimeError("Pillow has no raqm (Persian text shaping)")
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for name in FONTS.values():
        path = FONT_DIR / name
        if path.exists() and path.stat().st_size > 50_000:
            continue
        req = urllib.request.Request(RAW + name, headers={"User-Agent": "NabzAI/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if len(data) < 50_000:
            raise RuntimeError(f"font {name} download too small")
        path.write_bytes(data)


def F(size: int, bold: bool = False):
    key = (size, bold)
    if key not in _CACHE:
        path = FONT_DIR / FONTS["bold" if bold else "regular"]
        _CACHE[key] = ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)
    return _CACHE[key]


def background(seed: int, W: int = W, H: int = H) -> Image.Image:
    rnd = random.Random(seed)
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(16 + 20 * t), int(15 + 14 * t), int(22 + 8 * t)))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    for _ in range(140):
        cx, cy = rnd.randint(-50, W + 50), rnd.randint(int(H * 0.45), H + 50)
        r, n, a0 = rnd.randint(10, 70), rnd.choice([4, 5, 6]), rnd.random() * 6.28
        pts = [(cx + r * math.cos(a0 + i * 6.28 / n) * rnd.uniform(.7, 1.2),
                cy + r * math.sin(a0 + i * 6.28 / n) * rnd.uniform(.7, 1.2)) for i in range(n)]
        ld.polygon(pts, fill=(235, 225, 210, rnd.randint(14, 40)), outline=(255, 245, 230, rnd.randint(40, 90)))
    lay = lay.filter(ImageFilter.GaussianBlur(1.2))
    im = Image.alpha_composite(im.convert("RGBA"), lay)
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    for i in range(60):
        md.rectangle([i * 6, i * 6, W - i * 6, H - i * 6], outline=int(120 + 135 * i / 60))
    mask = mask.filter(ImageFilter.GaussianBlur(40))
    im = Image.composite(im, Image.new("RGBA", (W, H), (0, 0, 0, 255)), mask)
    q = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(q).text((60, 260), "؟", font=F(900, True), fill=(230, 190, 110, 22), direction="rtl", language="fa")
    return Image.alpha_composite(im, q).convert("RGB")


def tlen(d, text, font) -> float:
    return d.textlength(text, font=font, direction="rtl")


def wrap(d, text, font, maxw=900):
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for w in para.split(" "):
            t = (cur + " " + w).strip()
            if not cur or tlen(d, t, font) <= maxw:
                cur = t
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def block(d, text, font, y, fill, gap, maxw=900):
    for ln in wrap(d, text, font, maxw):
        d.text((W - 90 - tlen(d, ln, font), y), ln, font=font, fill=fill, direction="rtl", language="fa")
        y += int(font.size * gap)
    return y


def chrome(d, i, n):
    # Instagram draws its own "1/6" counter at the top right, so the brand pill sits top left
    # and there is no slide counter of our own.
    f = F(30, True)
    tw = tlen(d, BRAND, f)
    d.rounded_rectangle([90, 70, 90 + tw + 36, 124], radius=27, fill=RED)
    d.text((108, 76), BRAND, font=f, fill=WHITE, direction="rtl", language="fa")
    if i < n:
        # swipe hint bottom right, where the finger starts and the next slide comes in from
        hint = F(30, True)
        hw = tlen(d, "ورق بزن", hint)
        d.text((W - 90 - hw, H - 110), "ورق بزن", font=hint, fill=GOLD, direction="rtl", language="fa")
        ax = W - 90 - hw - 20
        d.polygon([(ax - 30, H - 90), (ax, H - 108), (ax, H - 72)], fill=GOLD)
    hf = F(28)
    d.text((90, H - 108), HANDLE, font=hf, fill=MUTED)


def render_slide(s: dict, i: int, n: int, path: Path) -> Path:
    big, last = bool(s.get("big")), i == n
    im = background(i * 7)
    d = ImageDraw.Draw(im)
    chrome(d, i, n)
    kf, tf, bf = F(40, True), F(86 if big else 76, True), F(44 if big else 40)
    height = 100 + len(wrap(d, s["title"], tf)) * int(tf.size * 1.35) + 40 + len(wrap(d, s["body"], bf)) * int(bf.size * 1.7)
    top, bottom = 150, (H - 260 if last and s.get("footer") else H - 160)
    y = int(top + (bottom - top - height) / 2)
    d.text((W - 90 - tlen(d, s["kicker"], kf), y), s["kicker"], font=kf, fill=GOLD, direction="rtl", language="fa")
    y += 90
    d.rectangle([W - 210, y - 18, W - 90, y - 12], fill=GOLD)
    y = block(d, s["title"], tf, y + 10, WHITE, 1.35) + 40
    block(d, s["body"], bf, y, BODY, 1.7)
    if last and s.get("footer"):
        block(d, s["footer"], F(30), H - 220, MUTED, 1.55)
    im.save(path, quality=92)
    return path


def render_post(post: dict, out_dir: Path) -> list[Path]:
    ensure_fonts()
    slides = post["slides"]
    if not 2 <= len(slides) <= 10:
        raise RuntimeError("a carousel needs 2-10 slides")
    out_dir.mkdir(parents=True, exist_ok=True)
    return [render_slide(s, i, len(slides), out_dir / f"slide_{i}.jpg") for i, s in enumerate(slides, 1)]


# ---------------------------------------------------------------- video slides with music
# Every slide becomes a short video. One continuous piece of music is composed for the whole
# post and cut at the slide boundaries, so swiping moves through it: each slide plays its own
# part of the arc (hook -> rising tension -> peak on the reveal -> calm ending), a soft chime
# marks each new slide, and each slide lasts about as long as its text takes to read.
SR = 44100
DARK_WORDS = ("مرگ", "جسد", "قتل", "قاتل", "کشته", "ناپدید", "گم شد", "خون", "زندان", "جنایت")
WONDER_WORDS = ("باستان", "هزار سال", "تمدن", "معبد", "شهر", "کتیبه", "گنج", "ستاره", "آسمان", "تاریخ")


def slide_seconds(s: dict) -> float:
    words = len(f"{s.get('kicker', '')} {s.get('title', '')} {s.get('body', '')} {s.get('footer', '')}".split())
    return round(min(10.0, max(5.0, 2.0 + words / 2.6)), 2)


def mood_of(post: dict) -> str:
    text = " ".join(f"{s.get('title', '')} {s.get('body', '')}" for s in post["slides"])
    dark = sum(text.count(w) for w in DARK_WORDS)
    wonder = sum(text.count(w) for w in WONDER_WORDS)
    return "dark" if dark > wonder else ("wonder" if wonder else "mystery")


def intensity(i: int, n: int) -> float:
    """Hook, a steady build to the reveal (second last slide), then a calm last slide."""
    if n <= 2:
        return 0.6 if i == 1 else 0.4
    if i == n:
        return 0.35
    return 0.55 + 0.45 * (i - 1) / max(1, n - 2)


def compose(durations: list[float], mood: str, seed: int):
    import numpy as np
    rng = np.random.default_rng(seed)
    total = sum(durations)
    t = np.arange(int(total * SR)) / SR
    n = len(durations)
    starts = np.cumsum([0.0] + durations[:-1])
    level = np.zeros_like(t)
    for k, (s0, d) in enumerate(zip(starts, durations), 1):
        level[int(s0 * SR):int((s0 + d) * SR)] = intensity(k, n)
    win = int(1.2 * SR)
    level = np.convolve(level, np.ones(win) / win, mode="same")  # smooth swells between slides
    root = {"dark": 46.25, "wonder": 55.0, "mystery": 49.0}[mood]
    voices = {"dark": ((1, .5), (1.189, .22), (1.5, .25), (2, .15)),         # minor colour
              "wonder": ((1, .45), (1.5, .3), (2, .2), (3, .12), (4.5, .06)),  # open fifths
              "mystery": ((1, .5), (1.5, .28), (2, .2), (2.378, .1))}[mood]
    left, right = np.zeros_like(t), np.zeros_like(t)
    for ratio, amp in voices:
        f = root * ratio
        ph = rng.uniform(0, 6.28, 2)
        lfo = 0.7 + 0.3 * np.sin(2 * np.pi * rng.uniform(0.04, 0.09) * t + ph[0])
        left += amp * lfo * np.sin(2 * np.pi * f * t + ph[0])
        right += amp * lfo * np.sin(2 * np.pi * f * 1.003 * t + ph[1])
    drone = 0.55 + 0.45 * level
    left, right = left * drone, right * drone
    if mood != "wonder":  # heartbeat that quickens as the story builds
        beat = np.zeros_like(t)
        k = np.arange(int(0.35 * SR)) / SR
        thump = np.sin(2 * np.pi * 42 * k) * np.exp(-k * 14)
        pos = 1.0
        while pos < total - 1.0:
            lv = float(level[int(pos * SR)])
            if lv > 0.5:
                for off, gain in ((0.0, 0.9), (0.28, 0.6)):
                    s = int((pos + off) * SR)
                    e = min(len(t), s + len(thump))
                    beat[s:e] += thump[: e - s] * gain * lv
            pos += 1.7 - 0.8 * lv
        left += 0.4 * beat
        right += 0.4 * beat
    scale = (0, 3, 5, 7, 10, 12, 15) if mood != "wonder" else (0, 2, 4, 7, 9, 12, 14)
    for k, s0 in enumerate(starts):  # a chime on every new slide, climbing towards the reveal
        last = k == n - 1
        f = root * 8 * 2 ** (scale[min(k, len(scale) - 1) if not last else 0] / 12)
        kk = np.arange(int(2.5 * SR)) / SR
        bell = (np.sin(2 * np.pi * f * kk) + 0.3 * np.sin(2 * np.pi * f * 2.01 * kk)) * np.exp(-kk * 2.2)
        s = int((s0 + 0.12) * SR)
        e = min(len(t), s + len(bell))
        g = 0.22 if not last else 0.3
        left[s:e] += bell[: e - s] * g
        right[s:e] += bell[: e - s] * g * 0.85
    fade = np.ones_like(t)
    fo = int(min(3.0, durations[-1] * 0.6) * SR)
    fade[-fo:] = np.linspace(1, 0, fo)
    out = np.stack([left * fade, right * fade], axis=1)
    return out / (np.max(np.abs(out)) or 1) * 0.8, starts


def _ffmpeg() -> str:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def render_post_video(post: dict, slides: list[Path], out_dir: Path) -> list[dict]:
    """-> [{"path", "thumb", "width", "height", "duration"}] for every slide."""
    import subprocess
    import wave
    import numpy as np
    durations = [slide_seconds(s) for s in post["slides"]]
    durations[0] = min(durations[0], 7.0)  # the hook slide stays short
    seed = sum(ord(c) for c in str(post.get("id", "")))
    music, starts = compose(durations, mood_of(post), seed)
    out = []
    for k, (img, s0, d) in enumerate(zip(slides, starts, durations), 1):
        seg = music[int(s0 * SR):int((s0 + d) * SR)].copy()
        fi, fo = int(0.15 * SR), int(0.35 * SR)
        seg[:fi] *= np.linspace(0, 1, fi)[:, None]
        if k < len(slides):
            seg[-fo:] *= np.linspace(1, 0.4, fo)[:, None]
        wav = out_dir / f"slide_{k}.wav"
        with wave.open(str(wav), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(SR)
            wf.writeframes((np.clip(seg, -1, 1) * 32767).astype(np.int16).tobytes())
        mp4 = out_dir / f"slide_{k}.mp4"
        vf = (f"scale=w='trunc(1080*(1+0.035*t/{d})/2)*2':h=-2:eval=frame,crop=1080:1350,"
              "fps=30,format=yuv420p")
        proc = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-loop", "1",
                               "-i", str(img), "-i", str(wav), "-vf", vf, "-t", f"{d:.2f}",
                               "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac",
                               "-b:a", "128k", "-ar", str(SR), "-movflags", "+faststart", "-shortest",
                               str(mp4)], capture_output=True, text=True)
        if proc.returncode != 0 or not mp4.exists() or mp4.stat().st_size < 50_000:
            raise RuntimeError("slide video failed: " + proc.stderr.strip()[-400:])
        out.append({"path": mp4, "thumb": img, "width": W, "height": H, "duration": d})
    return out
