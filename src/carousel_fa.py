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
# part of the arc (hook -> rising tension -> peak on the reveal -> calm ending) on its own chord,
# and each slide lasts about as long as its text takes to read.
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


# ---------------------------------------------------------------- music (v2)
# Cinematic ambient score, composed fresh for every post: warm analogue-style pads that change
# chord on every slide, a soft sub bass, sparse felt-piano notes, a riser into the reveal and a
# long hall reverb. No clicks: every sound has a smooth attack, and every slide's part fades in
# and out (Instagram loops each video slide, so the loop point is silent and seamless).
PROGRESSIONS = {
    # (semitones from the key root, minor?) per slide; the last slide always returns home
    "dark": [(0, True), (8, False), (5, True), (7, False), (3, False), (10, False), (8, False), (7, False)],
    "mystery": [(0, True), (8, False), (3, False), (10, False), (5, True), (7, False), (8, False), (10, False)],
    "wonder": [(0, False), (9, True), (5, False), (7, False), (4, True), (2, True), (5, False), (7, False)],
}
KEY_ROOT = {"dark": 45, "mystery": 47, "wonder": 50}  # MIDI note of the key (A2, B2, D3)


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _lowpass(x, cutoff):
    """Gentle 4-pole-like low-pass in the frequency domain (no phase clicks)."""
    import numpy as np
    spec = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(x.shape[0], 1 / SR)
    spec *= (1 / (1 + (f / cutoff) ** 4))[:, None] if x.ndim == 2 else 1 / (1 + (f / cutoff) ** 4)
    return np.fft.irfft(spec, n=x.shape[0], axis=0)


def _reverb(stereo, rng, seconds=3.2, wet=0.38):
    import numpy as np
    n = int(seconds * SR)
    k = np.arange(n) / SR
    out = np.empty_like(stereo)
    size = stereo.shape[0] + n
    for ch in range(2):
        ir = rng.standard_normal(n) * np.exp(-k * 2.1)
        ir = _lowpass(ir, 5200.0)
        ir[: int(0.012 * SR)] = 0.0  # pre-delay
        ir /= np.sqrt(np.sum(ir ** 2)) or 1
        y = np.fft.irfft(np.fft.rfft(stereo[:, ch], size) * np.fft.rfft(ir, size), size)[: stereo.shape[0]]
        out[:, ch] = (1 - wet) * stereo[:, ch] + wet * y
    return out


def _env(n, attack, release):
    import numpy as np
    e = np.ones(n)
    a, r = min(n // 2, int(attack * SR)), min(n // 2, int(release * SR))
    if a:
        e[:a] = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a))
    if r:
        e[-r:] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, r))
    return e


def _pad_note(freq, n, rng):
    """Three slightly detuned soft saws (band-limited), like a warm analogue string pad."""
    import numpy as np
    t = np.arange(n) / SR
    out = np.zeros(n)
    for det in (-0.07, 0.0, 0.06):
        f = freq * 2 ** (det / 12)
        ph = rng.uniform(0, 2 * np.pi)
        for h in range(1, 9):
            if f * h > 6000:
                break
            out += np.sin(2 * np.pi * f * h * t + ph * h) / h
    return out / 6.0


def _piano(freq, n):
    import numpy as np
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t) + 0.12 * np.sin(2 * np.pi * freq * 3.01 * t)
    return tone * np.exp(-t * 2.4) * _env(n, 0.006, 0.4)


def compose(durations: list[float], mood: str, seed: int):
    import numpy as np
    rng = np.random.default_rng(seed)
    n_sl = len(durations)
    starts = np.cumsum([0.0] + list(durations[:-1]))
    total = float(sum(durations))
    N = int(total * SR) + int(4 * SR)  # reverb tail room, cut later
    L = np.zeros(N)
    R = np.zeros(N)
    prog = PROGRESSIONS.get(mood, PROGRESSIONS["mystery"])
    key = KEY_ROOT.get(mood, 47)
    xf = 1.2  # chords overlap across slide boundaries
    for k, (s0, d) in enumerate(zip(starts, durations)):
        last = k == n_sl - 1
        off, minor = (0, mood != "wonder") if last else prog[k % len(prog)]
        lv = intensity(k + 1, n_sl)
        root = key + off
        third = 3 if minor else 4
        chord = [root, root + 7, root + 12, root + 12 + third, root + 19]
        a = max(0, int((s0 - xf / 2) * SR))
        b = min(N, int((s0 + d + xf / 2 + (2.5 if last else 0)) * SR))
        n = b - a
        pad = np.zeros(n)
        for j, m in enumerate(chord):
            pad += _pad_note(_hz(m), n, rng) * (0.9 if j < 2 else 0.6)
        pad *= _env(n, xf, xf + (2.0 if last else 0)) * (0.5 + 0.5 * lv)
        cut = 700 + 1500 * lv
        pad = _lowpass(pad, cut)
        pan = 0.15 * np.sin(2 * np.pi * 0.07 * np.arange(n) / SR)
        L[a:b] += pad * (1 - pan)
        R[a:b] += pad * (1 + pan)
        # sub bass, felt more than heard
        t = np.arange(n) / SR
        sub = np.sin(2 * np.pi * _hz(root - 12) * t) * _env(n, xf, xf) * 0.35 * (0.6 + 0.4 * lv)
        L[a:b] += sub
        R[a:b] += sub
        # sparse felt-piano notes from the chord, denser as the story builds; never on the cut
        tones = [root + 12, root + 19, root + 24, root + 24 + third, root + 31]
        pos = s0 + 0.9
        while pos < s0 + d - 1.2:
            m = int(rng.choice(tones))
            nn = int(2.8 * SR)
            s = int(pos * SR)
            e = min(N, s + nn)
            note = _piano(_hz(m), nn)[: e - s] * (0.16 + 0.1 * lv)
            pl = rng.uniform(-0.4, 0.4)
            L[s:e] += note * (1 - pl)
            R[s:e] += note * (1 + pl)
            pos += float(rng.uniform(1.1, 2.2) - 0.7 * lv)
        # soft riser into the reveal (second-to-last slide), filtered noise swell
        if n_sl >= 3 and k == n_sl - 3:
            rs = int(max(s0, s0 + d - 3.0) * SR)
            re_ = int((s0 + d) * SR)
            noise = _lowpass(rng.standard_normal(re_ - rs), 2500.0)
            swell = np.linspace(0, 1, re_ - rs) ** 2 * 0.25
            L[rs:re_] += noise * swell
            R[rs:re_] += noise * swell
    st = np.stack([L, R], axis=1)
    st = _reverb(st, rng)
    st = st[: int(total * SR)]
    st = np.tanh(1.4 * st / (np.max(np.abs(st)) or 1)) / np.tanh(1.4)  # soft limiter
    return st * 0.85, starts


def slide_part(music, s0, d, last):
    """One slide's audio: smooth fade in/out so Instagram's loop is seamless (no click)."""
    import numpy as np
    seg = music[int(s0 * SR):int((s0 + d) * SR)].copy()
    n = len(seg)
    fi, fo = int(0.45 * SR), int((1.6 if last else 0.7) * SR)
    seg[:fi] *= (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fi)))[:, None]
    seg[-fo:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo)))[:, None]
    return seg


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
        seg = slide_part(music, s0, d, k == len(slides))
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
