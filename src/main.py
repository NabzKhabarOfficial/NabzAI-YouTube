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
BG = (7, 12, 24)
PANEL = (18, 28, 48)
WHITE = (245, 247, 250)
MUTED = (158, 173, 198)
ACCENT = (77, 201, 255)
GREEN = (78, 220, 154)
YELLOW = (255, 198, 74)
RED = (255, 91, 110)
PURPLE = (167, 120, 255)

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

def panel(draw, box, fill=PANEL, outline=(47, 66, 96), radius=22):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)

def arrow(draw, a, b, fill=ACCENT, width=6):
    x1, y1 = a
    x2, y2 = b
    draw.line((x1, y1, x2, y2), fill=fill, width=width)
    r = 12
    direction = 1 if x2 >= x1 else -1
    d = ImageDraw.Draw(draw._image if hasattr(draw, "_image") else draw)
    d.polygon([(x2, y2), (x2-direction*r*2, y2-r), (x2-direction*r*2, y2+r)], fill=fill)

def header(d, label, index, total):
    d.text((70, 42), "NABZ AI", font=font(25), fill=ACCENT)
    d.text((220, 42), label, font=font(22), fill=MUTED)
    d.text((1115, 42), f"{index:02d}/{total:02d}", font=font(22), fill=MUTED)
    d.line((70, 88, 1210, 88), fill=(37, 53, 80), width=2)

def metric(d, box, number, caption, color):
    panel(d, box, fill=(15, 24, 42), outline=(42, 60, 88), radius=18)
    x1, y1, x2, y2 = box
    d.text((x1+22, y1+18), number, font=font(40), fill=color)
    d.text((x1+22, y1+70), caption, font=font(18), fill=MUTED)

def make_scene(title, label, index, total, topic, output):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    header(d, label, index, total)

    if index == 1:
        d.text((70, 135), "STOP SCROLLING", font=font(25), fill=RED)
        text_box(d, (70, 178), title, 52, max_width=760, gap=7)
        panel(d, (885, 130, 1210, 430), fill=(21, 31, 52), outline=(70, 92, 130))
        d.text((935, 165), "THE", font=font(22), fill=MUTED)
        d.text((930, 205), "REAL", font=font(55), fill=WHITE)
        d.text((930, 275), "TEST", font=font(55), fill=ACCENT)
        metric(d, (70, 500, 330, 630), "01", "REAL TASK", ACCENT)
        metric(d, (355, 500, 615, 630), "02", "LESS FRICTION", GREEN)
        metric(d, (640, 500, 900, 630), "03", "MEASURED", YELLOW)
        metric(d, (925, 500, 1210, 630), "04", "NO HYPE", PURPLE)

    elif index == 2:
        d.text((70, 130), "THE PAIN", font=font(25), fill=RED)
        text_box(d, (70, 170), "Most people add AI tools before they remove the actual bottleneck.", 42, max_width=1050)
        for x, label2 in [(90, "TASK"), (380, "TOOL"), (670, "TOOL"), (960, "TOOL")]:
            panel(d, (x, 400, x+220, 555), fill=(22, 27, 43), outline=(60, 65, 90))
            d.text((x+24, 425), label2, font=font(20), fill=MUTED)
            d.text((x+24, 470), "MORE WORK", font=font(25), fill=WHITE)
        arrow(d, (315, 477), (370, 477), RED)
        arrow(d, (605, 477), (660, 477), RED)
        arrow(d, (895, 477), (950, 477), RED)
        d.text((90, 600), "The goal is not more software. It is less wasted effort.", font=font(27), fill=WHITE)

    elif index in (3, 4, 5, 6, 7, 8):
        n = index - 2
        d.text((70, 125), f"CASE {n:02d}", font=font(24), fill=ACCENT)
        d.text((70, 165), f"CAPABILITY {n:02d}", font=font(46), fill=WHITE)
        task = ["RESEARCH", "WRITING", "MEETINGS", "AUTOMATION", "CODING", "DOCUMENTS"][n-1]
        d.text((70, 235), task, font=font(58), fill=ACCENT)
        panel(d, (70, 350, 500, 600), fill=(20, 29, 49))
        d.text((105, 385), "BEFORE", font=font(21), fill=RED)
        d.text((105, 440), "MANUAL STEPS", font=font(31), fill=WHITE)
        d.text((105, 495), "slow • repetitive", font=font(22), fill=MUTED)
        arrow(d, (535, 475), (680, 475), GREEN, 8)
        panel(d, (715, 350, 1210, 600), fill=(16, 43, 38), outline=(51, 111, 92))
        d.text((750, 385), "AFTER", font=font(21), fill=GREEN)
        d.text((750, 440), "AI-ASSISTED", font=font(31), fill=WHITE)
        d.text((750, 495), "faster • checked", font=font(22), fill=GREEN)
        metric(d, (70, 625, 360, 690), "INPUT", "clear goal", ACCENT)
        metric(d, (385, 625, 675, 690), "PROCESS", "one workflow", PURPLE)
        metric(d, (700, 625, 990, 690), "OUTPUT", "verified", GREEN)

    elif index == 9:
        d.text((70, 130), "THE FAILURE MODE", font=font(25), fill=RED)
        text_box(d, (70, 175), "Fast output is not automatically good output.", 46, max_width=1000)
        panel(d, (70, 350, 360, 570), fill=(48, 23, 31), outline=(100, 50, 65))
        d.text((105, 390), "AI ANSWER", font=font(23), fill=RED)
        d.text((105, 445), "sounds right", font=font(30), fill=WHITE)
        d.text((105, 495), "but may be wrong", font=font(22), fill=MUTED)
        arrow(d, (400, 460), (535, 460), YELLOW)
        panel(d, (570, 350, 850, 570), fill=(45, 39, 22), outline=(105, 90, 45))
        d.text((610, 390), "CHECK", font=font(23), fill=YELLOW)
        d.text((610, 445), "source", font=font(30), fill=WHITE)
        d.text((610, 495), "test • compare", font=font(22), fill=MUTED)
        arrow(d, (890, 460), (1025, 460), GREEN)
        panel(d, (1060, 350, 1210, 570), fill=(17, 48, 39), outline=(50, 105, 83))
        d.text((1085, 390), "OK", font=font(23), fill=GREEN)
        d.text((1085, 445), "✓", font=font(48), fill=GREEN)

    elif index == 10:
        d.text((70, 130), "THE WORKFLOW", font=font(25), fill=PURPLE)
        text_box(d, (70, 175), "A good AI workflow is a chain, not a magic button.", 44, max_width=1050)
        nodes = [("01", "INPUT"), ("02", "AI"), ("03", "CHECK"), ("04", "ACTION")]
        xs = [70, 355, 640, 925]
        for j, (num, name) in enumerate(nodes):
            panel(d, (xs[j], 390, xs[j]+220, 555), fill=(20, 29, 49))
            d.text((xs[j]+24, 412), num, font=font(23), fill=ACCENT)
            d.text((xs[j]+24, 470), name, font=font(27), fill=WHITE)
            if j < 3:
                arrow(d, (xs[j]+225, 472), (xs[j+1]-10, 472), PURPLE)

    elif index == 11:
        d.text((70, 130), "SCORECARD", font=font(25), fill=YELLOW)
        text_box(d, (70, 175), "Keep the workflow only if it wins on the things that matter.", 42, max_width=1060)
        rows = [("TIME", GREEN), ("QUALITY", ACCENT), ("EFFORT", YELLOW), ("RISK", RED)]
        y = 365
        for name, color in rows:
            d.text((90, y), name, font=font(22), fill=WHITE)
            d.rounded_rectangle((250, y+5, 1080, y+35), radius=14, fill=(27, 36, 56))
            width = {"TIME": 620, "QUALITY": 540, "EFFORT": 430, "RISK": 250}[name]
            d.rounded_rectangle((250, y+5, 250+width, y+35), radius=14, fill=color)
            y += 70

    else:
        d.text((70, 135), "TAKEAWAY", font=font(25), fill=ACCENT)
        text_box(d, (70, 180), title, 45, max_width=1080)
        d.text((75, 380), "START SMALL", font=font(38), fill=WHITE)
        d.text((75, 435), "MEASURE THE BASELINE", font=font(38), fill=ACCENT)
        d.text((75, 490), "KEEP ONLY WHAT WORKS", font=font(38), fill=GREEN)
        panel(d, (810, 350, 1210, 590), fill=(18, 28, 48), outline=(65, 83, 116))
        d.text((860, 395), "NABZ AI", font=font(34), fill=ACCENT)
        d.text((860, 455), "PRACTICAL", font=font(25), fill=WHITE)
        d.text((860, 500), "NOT HYPE", font=font(25), fill=MUTED)

    d.text((70, 690), "PRACTICAL AI  •  WORKFLOWS  •  EXPERIMENTS", font=font(17), fill=MUTED)
    im.save(output, quality=95)

def make_short_card(title, path):
    im = Image.new("RGB", (1080, 1920), BG)
    d = ImageDraw.Draw(im)
    panel(d, (45, 45, 1035, 1875), fill=(15, 22, 38), outline=(55, 75, 108), radius=44)
    d.text((85, 110), "NABZ AI", font=font(34), fill=ACCENT)
    d.text((85, 340), "ONE IDEA", font=font(26), fill=YELLOW)
    text_box(d, (85, 410), title, 58, max_width=880, gap=13)
    d.text((85, 1680), "Practical AI • Workflows • Experiments", font=font(25), fill=MUTED)
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

    labels = ["HOOK", "THE PAIN", "CASE 01", "CASE 02", "CASE 03", "CASE 04", "CASE 05", "CASE 06", "FAILURE", "WORKFLOW", "SCORECARD", "TAKEAWAY"]
    scenes = []
    for i, label in enumerate(labels, 1):
        path = work / f"scene_{i:02d}.png"
        make_scene(title, label, i, len(labels), topic, path)
        scenes.append(path)

    audio = work / "voice.mp3"
    generate_voice(script, audio, cfg)
    video = work / "video.mp4"
    render_video(audio, scenes, video, cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"])
    make_thumbnail(title, work / "thumbnail.jpg")
    report = validate_video(video, cfg["video"]["width"], cfg["video"]["height"], 120)
    report["scene_count"] = len(scenes)
    report["visual_storytelling"] = "12 visual beats with transitions"
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
    print("SCENE_COUNT:", len(scenes))
    print("MODE:", args.mode)

if __name__ == "__main__":
    main()
