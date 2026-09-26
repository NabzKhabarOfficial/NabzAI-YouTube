import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .topic_engine import choose_topic
from .script_engine import build_script, make_title, make_description, make_short_script
from .voice_engine import generate_voice
from .thumbnail_engine import make_thumbnail
from .video_engine import render_video, render_short
from .quality_gate import validate_video

ROOT = Path(__file__).resolve().parents[1]
W, H = 1280, 720
BG = (9, 13, 24)
PANEL = (20, 27, 44)
PANEL2 = (28, 37, 58)
WHITE = (245, 247, 250)
MUTED = (166, 177, 198)
ACCENT = (80, 190, 255)
GREEN = (72, 214, 150)
YELLOW = (255, 198, 75)
RED = (255, 100, 110)

def load_settings():
    return json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))

def font(size, bold=True):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for fp in candidates:
        if Path(fp).exists():
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()

def wrap(draw, text, fnt, max_width):
    lines, line = [], ""
    for word in str(text).split():
        test = (line + " " + word).strip()
        if draw.textbbox((0, 0), test, font=fnt)[2] <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines

def text_box(draw, xy, text, size, fill=WHITE, max_width=1000, gap=10):
    fnt = font(size)
    x, y = xy
    for line in wrap(draw, text, fnt, max_width):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += size + gap
    return y

def panel(draw, box, fill=PANEL2, outline=(48, 61, 88), radius=24):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)

def arrow(draw, a, b, fill=ACCENT):
    x1, y1 = a
    x2, y2 = b
    draw.line((x1, y1, x2, y2), fill=fill, width=7)
    r = 13
    if x2 >= x1:
        draw.polygon([(x2, y2), (x2-r*2, y2-r), (x2-r*2, y2+r)], fill=fill)
    else:
        draw.polygon([(x2, y2), (x2+r*2, y2-r), (x2+r*2, y2+r)], fill=fill)

def make_scene(title, label, index, output):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # Everything stays inside a generous central safe zone for mobile playback.
    d.text((80, 52), "NABZ AI", font=font(25), fill=ACCENT)
    d.text((220, 52), f"{label}  /  {index:02d}", font=font(25), fill=MUTED)
    d.line((80, 100, 1200, 100), fill=(43, 54, 78), width=2)

    if index == 1:
        d.text((80, 145), "THE OUTCOME", font=font(22), fill=ACCENT)
        text_box(d, (80, 185), title, 52, max_width=760, gap=8)
        for x, name, color in [(80, "AI TOOL", ACCENT), (440, "WORKFLOW", GREEN), (800, "TIME SAVED", YELLOW)]:
            panel(d, (x, 485, x+320, 615))
            d.ellipse((x+25, 510, x+55, 540), fill=color)
            d.text((x+75, 507), name, font=font(22), fill=WHITE)
        panel(d, (875, 155, 1200, 430), fill=(16, 23, 38))
        d.text((915, 190), "7", font=font(96), fill=ACCENT)
        d.text((915, 300), "useful tools", font=font(27), fill=WHITE)
        d.text((915, 350), "not hype", font=font(27), fill=MUTED)
    elif index == 2:
        d.text((80, 140), "THE PROBLEM", font=font(22), fill=RED)
        text_box(d, (80, 180), title, 46, max_width=760)
        panel(d, (80, 420, 370, 590))
        d.text((115, 450), "INPUT", font=font(21), fill=MUTED)
        d.text((115, 500), "too much noise", font=font(25), fill=WHITE)
        arrow(d, (390, 505), (520, 505), RED)
        panel(d, (540, 420, 850, 590), fill=(48, 24, 34), outline=(100, 55, 65))
        d.text((575, 450), "RISK", font=font(21), fill=RED)
        d.text((575, 500), "confident mistake", font=font(25), fill=WHITE)
        arrow(d, (870, 505), (1000, 505), GREEN)
        panel(d, (1020, 420, 1200, 590), fill=(18, 48, 39), outline=(48, 100, 80))
        d.text((1040, 450), "FIX", font=font(21), fill=GREEN)
        d.text((1040, 500), "clear goal", font=font(22), fill=WHITE)
    elif index == 3:
        d.text((80, 140), "THE METHOD", font=font(22), fill=ACCENT)
        text_box(d, (80, 180), title, 46, max_width=1060)
        steps = [("01", "GOAL"), ("02", "CONTEXT"), ("03", "TEST"), ("04", "CHECK")]
        xs = [80, 365, 650, 935]
        for j, (num, name) in enumerate(steps):
            panel(d, (xs[j], 430, xs[j]+220, 575))
            d.text((xs[j]+22, 448), num, font=font(27), fill=ACCENT)
            d.text((xs[j]+22, 500), name, font=font(23), fill=WHITE)
            if j < 3:
                arrow(d, (xs[j]+225, 505), (xs[j+1]-10, 505))
    elif index == 4:
        d.text((80, 140), "REAL EXAMPLE", font=font(22), fill=GREEN)
        text_box(d, (80, 180), title, 46, max_width=1060)
        panel(d, (80, 370, 575, 590), fill=(43, 29, 31), outline=(92, 58, 65))
        d.text((115, 400), "BEFORE", font=font(22), fill=RED)
        d.text((115, 455), "generic request", font=font(27), fill=WHITE)
        d.text((115, 505), "↓ unclear output", font=font(24), fill=MUTED)
        arrow(d, (610, 480), (670, 480), GREEN)
        panel(d, (705, 370, 1200, 590), fill=(18, 48, 39), outline=(48, 100, 80))
        d.text((740, 400), "AFTER", font=font(22), fill=GREEN)
        d.text((740, 455), "goal + context", font=font(27), fill=WHITE)
        d.text((740, 505), "✓ usable result", font=font(24), fill=GREEN)
    elif index == 5:
        d.text((80, 140), "QUALITY CHECK", font=font(22), fill=YELLOW)
        text_box(d, (80, 180), title, 46, max_width=1060)
        checks = ["Goal is clear", "Claims are verified", "Sensitive data removed", "Output matches the format"]
        y = 390
        for item in checks:
            panel(d, (80, y, 1200, y+55), fill=(17, 25, 40))
            d.ellipse((105, y+13, 135, y+43), fill=GREEN)
            d.text((112, y+10), "✓", font=font(23), fill=BG)
            d.text((165, y+12), item, font=font(22), fill=WHITE)
            y += 65
    else:
        d.text((80, 140), "TAKEAWAY", font=font(22), fill=ACCENT)
        text_box(d, (80, 180), title, 46, max_width=1060)
        for y, (num, name) in zip([400, 478, 556], [("01", "START SMALL"), ("02", "MEASURE"), ("03", "IMPROVE")]):
            panel(d, (80, y, 1200, y+65))
            d.text((110, y+17), num, font=font(22), fill=ACCENT)
            d.text((190, y+17), name, font=font(24), fill=WHITE)

    d.text((80, 665), "PRACTICAL AI  •  TOOLS  •  AUTOMATION", font=font(20), fill=MUTED)
    d.text((1130, 665), f"{index}/6", font=font(20), fill=MUTED)
    im.save(output, quality=95)

def make_short_card(title, path):
    im = Image.new("RGB", (1080, 1920), BG)
    d = ImageDraw.Draw(im)
    panel(d, (55, 55, 1025, 1865), fill=(15, 21, 35), outline=(52, 68, 98), radius=42)
    d.text((90, 110), "NABZ AI", font=font(34), fill=ACCENT)
    text_box(d, (90, 620), title, 60, max_width=880, gap=12)
    d.text((90, 1710), "Practical AI • Tools • Automation", font=font(25), fill=MUTED)
    im.save(path, quality=95)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["test", "short"], default="test")
    args = ap.parse_args()
    cfg = load_settings()
    topic = choose_topic()
    work = ROOT / "output" / topic["id"]
    work.mkdir(parents=True, exist_ok=True)

    script = build_script(topic, cfg["video"]["target_minutes"])
    title = make_title(topic)
    description = make_description(topic)
    (work / "script.txt").write_text(script, encoding="utf-8")
    (work / "metadata.json").write_text(json.dumps({"title": title, "description": description, "tags": topic["tags"], "keywords": topic["keywords"]}, ensure_ascii=False, indent=2), encoding="utf-8")

    labels = ["HOOK", "THE PROBLEM", "THE METHOD", "REAL EXAMPLE", "QUALITY CHECK", "TAKEAWAY"]
    scenes = []
    for i, label in enumerate(labels, 1):
        scene_title = title if i == 1 else topic["sections"][min(i - 2, len(topic["sections"]) - 1)]
        path = work / f"scene_{i}.png"
        make_scene(scene_title, label, i, path)
        scenes.append(path)

    audio = work / "voice.mp3"
    generate_voice(script, audio, cfg)
    video = work / "video.mp4"
    render_video(audio, scenes, video, cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"])
    make_thumbnail(title, work / "thumbnail.jpg")
    report = validate_video(video, cfg["video"]["width"], cfg["video"]["height"], 120)
    (work / "quality.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.mode == "short":
        short_audio = work / "short_voice.mp3"
        generate_voice(make_short_script(topic), short_audio, cfg)
        card = work / "short_card.png"
        make_short_card(title, card)
        render_short(short_audio, card, work / "short.mp4", cfg["shorts"]["width"], cfg["shorts"]["height"], cfg["shorts"]["fps"])

    print("READY:", video)
    print("TITLE:", title)
    print("DURATION_SECONDS:", report["duration"])
    print("MODE:", args.mode)

if __name__ == "__main__":
    main()
