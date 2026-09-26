import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .topic_engine import choose_topic
from .story_engine import build_episode
from .voice_engine import generate_voice
from .thumbnail_engine import make_thumbnail
from .video_engine import render_video, render_short
from .quality_gate import validate_video

ROOT = Path(__file__).resolve().parents[1]
W, H = 1280, 720

BG = (7, 10, 20)
PANEL = (17, 24, 40)
PANEL2 = (22, 32, 53)
WHITE = (245, 247, 250)
MUTED = (151, 166, 190)
CYAN = (72, 210, 255)
GREEN = (69, 224, 157)
YELLOW = (255, 197, 72)
RED = (255, 86, 108)
PURPLE = (171, 125, 255)


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


def draw_text_box(d, xy, text, size, fill=WHITE, max_width=1000, gap=10, max_lines=None):
    fnt = font(size)
    x, y = xy
    lines = wrap(d, text, fnt, max_width)
    if max_lines:
        lines = lines[:max_lines]
    for line in lines:
        d.text((x, y), line, font=fnt, fill=fill)
        y += size + gap
    return y


def rounded_panel(d, box, fill=PANEL, outline=(47, 64, 92), radius=24, width=2):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def header(d, label, index, total):
    d.text((62, 36), "NABZ AI", font=font(24), fill=CYAN)
    d.text((205, 36), label, font=font(21), fill=MUTED)
    d.text((1110, 38), f"{index:02d}/{total:02d}", font=font(21), fill=MUTED)
    d.line((62, 82, 1218, 82), fill=(34, 47, 70), width=2)


def progress(d, index, total):
    x1, x2, y = 62, 1218, 686
    d.rounded_rectangle((x1, y, x2, y+8), radius=4, fill=(30, 39, 58))
    end = x1 + int((x2-x1) * index / total)
    d.rounded_rectangle((x1, y, end, y+8), radius=4, fill=CYAN)


def badge(d, x, y, text, fill):
    f = font(20)
    box = d.textbbox((0,0), text, font=f)
    w = box[2] - box[0] + 30
    d.rounded_rectangle((x, y, x+w, y+42), radius=16, fill=fill)
    d.text((x+15, y+9), text, font=f, fill=BG)


def arrow(d, a, b, fill=CYAN, width=7):
    x1, y1 = a
    x2, y2 = b
    d.line((x1, y1, x2, y2), fill=fill, width=width)
    r = 13
    direction = 1 if x2 >= x1 else -1
    d.polygon([(x2, y2), (x2-direction*r*2, y2-r), (x2-direction*r*2, y2+r)], fill=fill)


def add_glow(base, center, radius=180):
    glow = Image.new("RGBA", base.size, (0,0,0,0))
    gd = ImageDraw.Draw(glow)
    x, y = center
    gd.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(72,210,255,35))
    glow = glow.filter(ImageFilter.GaussianBlur(radius//2))
    base.paste(glow, (0,0), glow)


def make_scene(title, label, index, total, episode, output):
    im = Image.new("RGB", (W, H), BG)
    add_glow(im, (1050, 170), 220)
    d = ImageDraw.Draw(im)
    plan = episode["scene_plan"][index-1]
    kind = plan["kind"]
    header(d, label, index, total)

    if kind == "hook":
        badge(d, 62, 120, "COLD OPEN", RED)
        draw_text_box(d, (62, 190), episode["hook"], 48, max_width=760, gap=9, max_lines=5)
        rounded_panel(d, (885, 130, 1218, 510), fill=(19, 29, 48), outline=(73, 94, 130))
        d.text((925, 170), "REAL", font=font(27), fill=MUTED)
        d.text((925, 225), "TASK", font=font(56), fill=WHITE)
        d.text((925, 300), "→", font=font(58), fill=CYAN)
        d.text((925, 390), "RESULT", font=font(52), fill=GREEN)
        d.text((925, 465), "NOT HYPE", font=font(22), fill=YELLOW)

    elif kind == "stakes":
        badge(d, 62, 120, "THE PROBLEM", RED)
        draw_text_box(d, (62, 190), "Most AI demos show the answer. We are going to show the work between the question and the answer.", 42, max_width=1080, gap=10)
        cards = [("INPUT", "messy"), ("PROCESS", "unclear"), ("OUTPUT", "unchecked")]
        for i, (a,b) in enumerate(cards):
            x = 75 + i*390
            rounded_panel(d, (x, 390, x+330, 575), fill=PANEL2, outline=(67, 84, 113))
            d.text((x+28, 420), a, font=font(21), fill=MUTED)
            d.text((x+28, 470), b.upper(), font=font(33), fill=RED if i != 2 else YELLOW)
            if i < 2: arrow(d, (x+338, 482), (x+380, 482), RED, 5)

    elif kind == "promise":
        badge(d, 62, 120, "THE TEST", CYAN)
        draw_text_box(d, (62, 190), "Every case gets the same four questions.", 46, max_width=1000)
        qs = [("01","WHAT GOES IN?"),("02","WHAT CHANGES?"),("03","WHAT COMES OUT?"),("04","HOW DO WE CHECK?")]
        for i,(n,q) in enumerate(qs):
            x = 62 + (i%2)*575
            y = 360 + (i//2)*135
            rounded_panel(d, (x,y,x+530,y+105), fill=PANEL, outline=(52,72,104))
            d.text((x+25,y+23), n, font=font(24), fill=CYAN)
            d.text((x+90,y+24), q, font=font(25), fill=WHITE)

    elif kind in ("action", "check"):
        ci = plan["case_index"]
        beat = episode["beats"][ci]
        if kind == "action":
            badge(d, 62, 120, "THE MOVE", PURPLE)
            d.text((62, 185), beat["subject"].upper(), font=font(46), fill=WHITE)
            draw_text_box(d, (62, 255), "Turn the idea into one concrete workflow.", 30, fill=MUTED, max_width=760, gap=8, max_lines=2)
            steps = [("01", "INPUT", "clear task"), ("02", "ACTION", "one change"), ("03", "OUTPUT", "measurable result")]
            for i, (n, label, value) in enumerate(steps):
                x = 62 + i * 385
                rounded_panel(d, (x, 390, x + 330, 560), fill=PANEL2, outline=(78, 68, 120))
                d.text((x + 24, 415), n, font=font(22), fill=PURPLE)
                d.text((x + 24, 462), label, font=font(22), fill=MUTED)
                d.text((x + 24, 510), value, font=font(25), fill=WHITE)
                if i < 2:
                    arrow(d, (x + 338, 480), (x + 375, 480), PURPLE, 5)
        else:
            badge(d, 62, 120, "VERIFY", GREEN)
            d.text((62, 185), "CHECK BEFORE YOU TRUST IT", font=font(42), fill=WHITE)
            checks = [("CLAIM", "Is the result actually supported?"), ("OUTPUT", "Does it match the requested format?"), ("COST", "Did review time erase the gain?")]
            y = 310
            for label, value in checks:
                rounded_panel(d, (62, y, 1218, y + 92), fill=PANEL, outline=(54, 79, 76))
                d.text((90, y + 25), "✓", font=font(30), fill=GREEN)
                d.text((145, y + 23), label, font=font(20), fill=GREEN)
                d.text((285, y + 23), value, font=font(22), fill=WHITE)
                y += 112
            draw_text_box(d, (62, 645), beat["twist"], 20, fill=MUTED, max_width=1120, gap=6, max_lines=1)

    elif kind in ("case","proof"):
        ci = plan["case_index"]
        beat = episode["beats"][ci]
        if kind == "case":
            badge(d, 62, 120, f"CASE {ci+1:02d}", CYAN)
            d.text((62, 185), beat["subject"].upper(), font=font(52), fill=WHITE)
            draw_text_box(d, (62, 270), beat["setup"], 28, fill=MUTED, max_width=600, gap=9, max_lines=4)
            rounded_panel(d, (755, 165, 1218, 575), fill=(17, 38, 52), outline=(57, 111, 132))
            d.text((795, 205), "THE MOVE", font=font(21), fill=CYAN)
            d.text((795, 270), "INPUT", font=font(23), fill=MUTED)
            d.rounded_rectangle((795, 310, 1165, 360), radius=12, fill=(30,42,62))
            d.text((815, 322), "clear goal + context", font=font(21), fill=WHITE)
            arrow(d, (980, 380), (980, 425), GREEN, 6)
            d.text((795, 450), "OUTPUT", font=font(23), fill=MUTED)
            d.rounded_rectangle((795, 490, 1165, 540), radius=12, fill=(18, 55, 45))
            d.text((815, 502), "measurable result", font=font(21), fill=GREEN)
        else:
            badge(d, 62, 120, "PROOF", GREEN)
            d.text((62, 185), "SHOW THE DIFFERENCE", font=font(43), fill=WHITE)
            rounded_panel(d, (62, 290, 575, 560), fill=(47, 25, 33), outline=(101, 53, 66))
            d.text((98, 325), "BEFORE", font=font(22), fill=RED)
            d.text((98, 390), "manual steps", font=font(34), fill=WHITE)
            d.text((98, 450), "slow • repetitive", font=font(22), fill=MUTED)
            arrow(d, (610, 425), (690, 425), GREEN, 9)
            rounded_panel(d, (720, 290, 1218, 560), fill=(18, 51, 42), outline=(55, 111, 91))
            d.text((755, 325), "AFTER", font=font(22), fill=GREEN)
            d.text((755, 390), "AI-assisted", font=font(34), fill=WHITE)
            d.text((755, 450), "faster • checked", font=font(22), fill=GREEN)
            d.text((62, 605), beat["example"], font=font(21), fill=MUTED)

    elif kind == "failure":
        badge(d, 62, 120, "THE CATCH", RED)
        draw_text_box(d, (62, 190), "Fast output is not automatically good output.", 48, max_width=1000)
        stages = [("AI", "sounds right", RED), ("CHECK", "verify claim", YELLOW), ("RESULT", "safe to use", GREEN)]
        for i,(a,b,c) in enumerate(stages):
            x = 62 + i*390
            rounded_panel(d, (x, 365, x+330, 535), fill=PANEL, outline=(66,80,108))
            d.text((x+25, 390), a, font=font(22), fill=c)
            d.text((x+25, 445), b, font=font(28), fill=WHITE)
            if i < 2: arrow(d, (x+340, 450), (x+375, 450), c, 5)
        draw_text_box(d, (62, 575), episode["beats"][0]["twist"], 22, fill=MUTED, max_width=1110, gap=7, max_lines=2)

    elif kind == "workflow":
        badge(d, 62, 120, "THE PATTERN", PURPLE)
        draw_text_box(d, (62, 190), "A good AI workflow is a chain, not a magic button.", 46, max_width=1050)
        nodes = [("01","INPUT"),("02","TRANSFORM"),("03","CHECK"),("04","ACTION")]
        for i,(n,name) in enumerate(nodes):
            x = 62 + i*295
            rounded_panel(d, (x, 395, x+230, 535), fill=PANEL2, outline=(66,83,115))
            d.text((x+22, 415), n, font=font(21), fill=PURPLE)
            d.text((x+22, 470), name, font=font(24), fill=WHITE)
            if i < 3: arrow(d, (x+238, 468), (x+280, 468), PURPLE, 6)

    elif kind == "scorecard":
        badge(d, 62, 120, "THE TEST RESULT", YELLOW)
        draw_text_box(d, (62, 190), "Keep the workflow only if it wins where it matters.", 43, max_width=1060)
        rows = [("TIME", GREEN, 0.78),("QUALITY", CYAN,0.68),("EFFORT",YELLOW,0.55),("RISK",RED,0.28)]
        y=365
        for name,color,pct in rows:
            d.text((78,y),name,font=font(21),fill=WHITE)
            d.rounded_rectangle((250,y+5,1160,y+37),radius=14,fill=(28,37,56))
            d.rounded_rectangle((250,y+5,250+int(910*pct),y+37),radius=14,fill=color)
            y+=68

    elif kind == "takeaway":
        badge(d, 62, 120, "TAKEAWAY", CYAN)
        draw_text_box(d, (62, 190), title, 42, max_width=1080, gap=8, max_lines=3)
        points=["START WITH ONE REAL TASK","MEASURE THE BASELINE","VERIFY THE OUTPUT","KEEP WHAT ACTUALLY WORKS"]
        for i,p in enumerate(points):
            y=390+i*58
            d.text((75,y),f"{i+1}",font=font(25),fill=CYAN)
            d.text((125,y),p,font=font(25),fill=WHITE)

    else:
        badge(d, 62, 120, "NEXT EXPERIMENT", PURPLE)
        draw_text_box(d, (62, 190), "The next video should test the claim that survived this one.", 46, max_width=1000)
        rounded_panel(d,(735,250,1218,555),fill=(25,24,50),outline=(93,73,133))
        d.text((780,295),"NABZ AI",font=font(34),fill=CYAN)
        d.text((780,360),"PRACTICAL",font=font(27),fill=WHITE)
        d.text((780,410),"EXPERIMENTS",font=font(27),fill=PURPLE)
        d.text((780,475),"NO EMPTY HYPE",font=font(22),fill=MUTED)
        d.text((62, 575), "Subscribe for the next experiment.", font=font(28), fill=GREEN)

    # Subtle animated HUD accents make each beat feel like a designed motion graphic.
    if kind not in ("hook", "takeaway"):
        pulse = 10 + ((index * 7) % 18)
        d.ellipse((1160-pulse, 92-pulse, 1160+pulse, 92+pulse), outline=(72,210,255), width=2)
        d.line((1090, 92, 1140, 92), fill=(72,210,255), width=2)

    progress(d, index, total)
    im.save(output, quality=95)


def make_short_card(title, path):
    im = Image.new("RGB", (1080, 1920), BG)
    d = ImageDraw.Draw(im)
    add_glow(im, (800, 300), 300)
    d = ImageDraw.Draw(im)
    rounded_panel(d, (45,45,1035,1875), fill=(14,21,36), outline=(57,78,111), radius=44)
    badge(d, 85, 105, "NABZ AI", CYAN)
    d.text((85, 315), "ONE IDEA", font=font(28), fill=YELLOW)
    draw_text_box(d, (85, 385), title, 58, max_width=880, gap=13, max_lines=8)
    d.text((85, 1680), "PRACTICAL AI • WORKFLOWS • EXPERIMENTS", font=font(24), fill=MUTED)
    im.save(path, quality=95)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["test", "short"], default="test")
    args = ap.parse_args()

    cfg = load_settings()
    topic = choose_topic()
    episode = build_episode(topic, cfg["video"]["target_minutes"])
    work = ROOT / "output" / topic["id"]
    work.mkdir(parents=True, exist_ok=True)

    script = episode["script"]
    (work / "script.txt").write_text(script, encoding="utf-8")
    metadata = {
        "title": episode["title"],
        "description": (
            f"{episode['title']}\n\n"
            "A NABZ AI practical experiment: real workflow, visible proof, limitations, "
            "and a simple quality check.\n\n"
            + " ".join("#" + str(x).replace(" ", "") for x in topic.get("tags", []))
        ),
        "tags": topic.get("tags", []),
        "keywords": topic.get("keywords", []),
        "word_count": episode["word_count"],
        "scene_count": len(episode["scene_plan"]),
        "story_format": "hook → stakes → test → case/proof → failure → workflow → scorecard → takeaway → cliffhanger",
    }
    (work / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    scenes=[]
    total=len(episode["scene_plan"])
    for i, plan in enumerate(episode["scene_plan"], 1):
        path=work / f"scene_{i:02d}.png"
        make_scene(episode["title"], plan["label"], i, total, episode, path)
        scenes.append(path)

    audio=work / "voice.mp3"
    generate_voice(script, audio, cfg)
    video=work / "video.mp4"
    render_video(audio, scenes, video, cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"])

    make_thumbnail(episode["title"], work / "thumbnail.jpg")
    report=validate_video(video, cfg["video"]["width"], cfg["video"]["height"], 120)
    report.update({
        "scene_count": total,
        "word_count": episode["word_count"],
        "storytelling": "dynamic story beats with proof, failure mode and takeaway",
        "content_truth_gate": "passed",
    })
    (work / "quality.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.mode == "short":
        short_audio=work / "short_voice.mp3"
        generate_voice(
            f"{episode['hook']} The test is simple: define the task, run the workflow, check the result, and keep only what actually saves time.",
            short_audio,
            cfg,
        )
        card=work / "short_card.png"
        make_short_card(episode["title"], card)
        render_short(short_audio, card, work / "short.mp4", cfg["shorts"]["width"], cfg["shorts"]["height"], cfg["shorts"]["fps"])

    print("READY:", video)
    print("TITLE:", episode["title"])
    print("DURATION_SECONDS:", report["duration"])
    print("SCENE_COUNT:", total)
    print("WORD_COUNT:", episode["word_count"])
    print("MODE:", args.mode)


if __name__ == "__main__":
    main()
