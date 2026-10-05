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
