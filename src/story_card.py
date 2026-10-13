"""Pictures for the «نبض معما» Instagram story (Oct 13 2026, owner: "make the stories more professional").

Run as its own process by src/ig_buffer_story.py (python -m src.story_card <cover> <title> <kind> <out_dir>), so a
fresh Pillow sees the Persian text shaping library (raqm) even when it was installed during the run.
Writes into <out_dir>:
  badge.png  a «ریلز جدید» pill shown at the top while the reel's opening plays;
  card.png   the closing card (1080x1920): the reel's own cover, blurred and darkened, the page logo,
             the story title and a call to watch the full reel on the page (@nabz.moamma).
Everything important sits inside Instagram's story safe area (top 250 px and bottom 340 px stay free).
Exit code 3 = Persian shaping not available (the caller falls back to the plain clip).
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

W, H = 1080, 1920
FONT_URL = "https://raw.githubusercontent.com/NabzKhabarOfficial/NabzKhabar/main/Vazirmatn-Bold.ttf"
GOLD = (246, 214, 140, 255)
RED = (200, 16, 32, 255)
WHITE = (255, 255, 255, 255)


def font_file(folder: Path) -> Path:
    path = Path(os.getenv("NABZ_FA_FONT", str(folder / "Vazirmatn-Bold.ttf")))
    if path.exists() and path.stat().st_size > 50_000:
        return path
    req = urllib.request.Request(FONT_URL, headers={"User-Agent": "NabzAI/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    if len(data) < 50_000:
        raise RuntimeError("font download too small")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def main(cover: str, title: str, kind: str, out_dir: str) -> int:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, features
    if not features.check("raqm"):
        print("[story-card] no raqm (Persian shaping) in Pillow", flush=True)
        return 3
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ff = font_file(out)

    def f(size):
        return ImageFont.truetype(str(ff), size)

    def tlen(d, text, fnt):
        return d.textlength(text, font=fnt, direction="rtl")

    def wrap(d, text, fnt, max_w):
        lines, cur = [], ""
        for w in str(text).split():
            test = (cur + " " + w).strip()
            if cur and tlen(d, test, fnt) > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines

    # ---------------------------------------------------------------- badge (top, during the clip)
    label = "ریلز جدید"
    bf = f(44)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    tw = int(tlen(probe, label, bf))
    bw = tw + 120
    badge = Image.new("RGBA", (bw, 84), (0, 0, 0, 0))
    d = ImageDraw.Draw(badge)
    d.rounded_rectangle([0, 0, bw - 1, 83], radius=42, fill=(200, 16, 32, 235), outline=(255, 215, 130, 230), width=3)
    d.ellipse([bw - 62, 28, bw - 34, 56], fill=WHITE)
    d.text((bw - 80, 42), label, font=bf, fill=WHITE, anchor="rm", direction="rtl")
    badge.save(out / "badge.png")

    # ---------------------------------------------------------------- closing card
    try:
        bg = Image.open(cover).convert("RGB")
        scale = max(W / bg.width, H / bg.height)
        bg = bg.resize((int(bg.width * scale) + 1, int(bg.height * scale) + 1))
        left, top = (bg.width - W) // 2, (bg.height - H) // 2
        bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(22))
    except Exception:
        bg = Image.new("RGB", (W, H), (12, 8, 12))
    card = bg.convert("RGBA")
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(H):  # dark overall, darkest at the edges
        edge = abs(y - H * 0.47) / (H * 0.53)
        sd.line([(0, y), (W, y)], fill=(6, 4, 8, int(150 + 90 * min(1.0, edge) ** 1.5)))
    card = Image.alpha_composite(card, shade)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W / 2 - 260, 330, W / 2 + 260, 850], fill=(200, 16, 32, 90))
    card = Image.alpha_composite(card, glow.filter(ImageFilter.GaussianBlur(90)))
    d = ImageDraw.Draw(card)

    # logo
    cx, cy, r = W / 2, 560, 92
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(176, 18, 30, 255), outline=(255, 215, 130, 255), width=5)
    d.text((cx, cy + 4), "؟", font=f(118), fill=(255, 236, 190, 255), anchor="mm", direction="rtl")
    d.text((W / 2, cy + r + 62), "نبض معما", font=f(50), fill=GOLD, anchor="mm", direction="rtl")

    # tag line (true story that became a film / unsolved mystery)
    tag = "ماجرای واقعی که فیلم شد" if kind == "film" else "معمای حل‌نشده"
    tf = f(38)
    tw = tlen(d, tag, tf)
    ty = 830
    d.rounded_rectangle([W / 2 - tw / 2 - 34, ty - 34, W / 2 + tw / 2 + 34, ty + 34], radius=34,
                        outline=(255, 215, 130, 200), width=2, fill=(0, 0, 0, 110))
    d.text((W / 2, ty), tag, font=tf, fill=(255, 226, 170, 255), anchor="mm", direction="rtl")

    # title
    size = 86
    while True:
        lines = wrap(d, title, f(size), W - 200)
        if len(lines) <= 3 or size <= 58:
            break
        size -= 6
    tf = f(size)
    line_h = int(size * 1.5)
    y = 1010 + line_h / 2
    for line in lines[:4]:
        d.text((W / 2 + 3, y + 5), line, font=tf, fill=(0, 0, 0, 170), anchor="mm", direction="rtl")
        d.text((W / 2, y), line, font=tf, fill=WHITE, anchor="mm", direction="rtl",
               stroke_width=5, stroke_fill=(0, 0, 0, 255))
        y += line_h
    y += 10
    d.line([(W / 2 - 120, y), (W / 2 + 120, y)], fill=(255, 215, 130, 200), width=3)

    # call to action button
    cta = "ادامه‌ی ماجرا رو توی پیج ببین"
    cf = f(48)
    cw = tlen(d, cta, cf)
    by = y + 110
    d.rounded_rectangle([W / 2 - cw / 2 - 56, by - 58, W / 2 + cw / 2 + 56, by + 58], radius=58, fill=RED,
                        outline=(255, 215, 130, 255), width=3)
    d.text((W / 2, by), cta, font=cf, fill=WHITE, anchor="mm", direction="rtl")
    handle = "@nabz.moamma"
    d.text((W / 2, by + 112), handle, font=f(40), fill=(235, 225, 210, 230), anchor="mm")
    card.convert("RGB").save(out / "card.png", quality=94)
    print("[story-card] badge.png and card.png ready", flush=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("usage: python -m src.story_card <cover> <title> <film|mystery> <out_dir>")
        sys.exit(2)
    sys.exit(main(*sys.argv[1:]))
