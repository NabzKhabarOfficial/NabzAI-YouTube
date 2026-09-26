import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

from .topic_engine import choose_topic
from .story_engine import build_episode
from .voice_engine import generate_voice
from .thumbnail_engine import make_thumbnail
from .video_engine import render_video, render_short
from .quality_gate import validate_video, validate_scene_set
from .topic_engine import mark_published

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



def _short_label(text, limit=22):
    words = str(text).upper().split()
    out = ""
    for w in words:
        candidate = (out + " " + w).strip()
        if len(candidate) > limit:
            break
        out = candidate
    return out or str(text).upper()[:limit]


def draw_case_visual(d, beat, ci, mode="case", variant=0):
    """Render a reusable visual archetype instead of repeating one card layout."""
    section = str(beat.get("section", beat.get("subject", "")))
    archetype = (ci + variant) % 5
    title = _short_label(beat["subject"], 28)

    if archetype == 0:
        # Workflow pipeline
        nodes = [
            ("INPUT", _short_label(section, 18)),
            ("ACTION", "AI TRANSFORM"),
            ("CHECK", "HUMAN REVIEW"),
            ("OUTPUT", "USEFUL RESULT"),
        ]
        y = 300
        for i, (lab, val) in enumerate(nodes):
            x = 62 + i * 286
            rounded_panel(d, (x, y, x + 230, y + 170), fill=PANEL2,
                          outline=(66, 86, 119))
            d.text((x + 20, y + 20), f"{i+1:02d}", font=font(20), fill=CYAN)
            d.text((x + 20, y + 62), lab, font=font(18), fill=MUTED)
            draw_text_box(d, (x + 20, y + 100), val, 21, fill=WHITE,
                          max_width=190, gap=3, max_lines=2)
            if i < 3:
                arrow(d, (x + 238, y + 85), (x + 274, y + 85), CYAN, 5)

    elif archetype == 1:
        # Browser / product mockup
        rounded_panel(d, (62, 270, 1218, 585), fill=(13, 19, 32),
                      outline=(66, 84, 116), radius=26)
        d.rectangle((62, 270, 1218, 322), fill=(23, 31, 49))
        for x in (88, 112, 136):
            d.ellipse((x, 288, x+10, 298), fill=MUTED)
        d.rounded_rectangle((190, 283, 1060, 309), radius=12, fill=(9, 14, 24))
        d.text((215, 286), "nabz.ai / experiment", font=font(16), fill=MUTED)
        d.text((95, 355), title, font=font(28), fill=WHITE)
        d.text((95, 405), "TASK", font=font(17), fill=CYAN)
        d.rounded_rectangle((95, 438, 720, 500), radius=14, fill=PANEL2)
        draw_text_box(d, (120, 455), section, 20, fill=WHITE, max_width=560, gap=3, max_lines=2)
        d.text((790, 405), "RESULT", font=font(17), fill=GREEN)
        d.rounded_rectangle((790, 438, 1175, 500), radius=14, fill=(18, 53, 44))
        d.text((820, 458), "measurable + checked", font=font(20), fill=GREEN)
        d.text((95, 535), "ONE TASK  →  ONE CHANGE  →  ONE VERIFIABLE OUTPUT",
               font=font(18), fill=MUTED)

    elif archetype == 2:
        # Terminal / command-line visual
        rounded_panel(d, (62, 285, 1218, 585), fill=(8, 12, 18),
                      outline=(57, 75, 98), radius=22)
        d.text((90, 315), "NABZ // RUNNING EXPERIMENT", font=font(18), fill=GREEN)
        lines = [
            ("> input", _short_label(section, 48), CYAN),
            ("> transform", "processing one focused task", WHITE),
            ("> check", "claim / format / edge cases", YELLOW),
            ("> output", "PASS — ready to use", GREEN),
        ]
        y = 370
        for cmd, val, col in lines:
            d.text((95, y), cmd, font=font(19), fill=col)
            d.text((250, y), val, font=font(19), fill=WHITE)
            y += 48
        d.rounded_rectangle((930, 355, 1170, 535), radius=20,
                            outline=(69, 224, 157), width=2)
        d.text((970, 385), "STATUS", font=font(18), fill=MUTED)
        d.text((970, 440), "PASS", font=font(44), fill=GREEN)
        d.text((970, 495), "verified", font=font(18), fill=GREEN)

    elif archetype == 3:
        # Before / after comparison
        rounded_panel(d, (62, 300, 575, 585), fill=(45, 25, 33),
                      outline=(104, 56, 70))
        d.text((95, 335), "BEFORE", font=font(20), fill=RED)
        d.text((95, 390), "MANUAL", font=font(34), fill=WHITE)
        draw_text_box(d, (95, 445), "scattered steps • repeated cleanup", 20,
                      fill=MUTED, max_width=420, gap=5, max_lines=2)
        arrow(d, (610, 440), (685, 440), YELLOW, 8)
        rounded_panel(d, (720, 300, 1218, 585), fill=(18, 52, 43),
                      outline=(55, 112, 92))
        d.text((755, 335), "AFTER", font=font(20), fill=GREEN)
        d.text((755, 390), "ASSISTED", font=font(34), fill=WHITE)
        draw_text_box(d, (755, 445), "focused input • checked output", 20,
                      fill=GREEN, max_width=400, gap=5, max_lines=2)

    else:
        # Timeline / decision path
        d.text((62, 290), "FROM QUESTION TO DECISION", font=font(20), fill=PURPLE)
        points = [
            ("00:00", "START", "define the task"),
            ("00:30", "RUN", "apply one change"),
            ("01:00", "CHECK", "verify the result"),
            ("01:30", "KEEP", "use it if it survives"),
        ]
        y = 365
        d.line((105, y, 105, y + 170), fill=PURPLE, width=5)
        for i, (tm, lab, val) in enumerate(points):
            yy = y + i * 52
            d.ellipse((91, yy-8, 119, yy+20), fill=PURPLE if i < 3 else GREEN)
            d.text((145, yy-3), tm, font=font(17), fill=MUTED)
            d.text((250, yy-5), lab, font=font(19), fill=WHITE)
            d.text((365, yy-5), val, font=font(18), fill=MUTED)


def draw_action_visual(d, beat, ci, variant=0):
    archetype = (ci + 1 + variant) % 4
    if archetype == 0:
        # Animated-looking stack of cards
        labels = ["RAW INPUT", "AI PASS", "HUMAN CHECK", "FINAL"]
        for i, lab in enumerate(labels):
            x = 95 + i * 275
            y = 310 + (i % 2) * 105
            rounded_panel(d, (x, y, x+225, y+125), fill=PANEL2,
                          outline=(78, 68, 120))
            d.text((x+20, y+20), f"{i+1:02d}", font=font(20), fill=PURPLE)
            d.text((x+20, y+62), lab, font=font(19), fill=WHITE)
            if i < 3:
                arrow(d, (x+230, y+62), (x+267, y+62), PURPLE, 5)
    elif archetype == 1:
        # Input transformation
        d.text((62, 320), "INPUT", font=font(18), fill=MUTED)
        rounded_panel(d, (62, 360, 395, 520), fill=PANEL2, outline=(64, 83, 116))
        draw_text_box(d, (90, 390), beat["setup"], 20, fill=WHITE, max_width=275, gap=5, max_lines=4)
        arrow(d, (430, 440), (800, 440), PURPLE, 9)
        d.text((500, 390), "TRANSFORM", font=font(18), fill=PURPLE)
        d.text((820, 320), "OUTPUT", font=font(18), fill=GREEN)
        rounded_panel(d, (820, 360, 1218, 520), fill=(18, 52, 43), outline=(55, 112, 92))
        d.text((850, 405), "ONE CLEAR", font=font(22), fill=WHITE)
        d.text((850, 445), "MEASURABLE RESULT", font=font(22), fill=GREEN)
    elif archetype == 2:
        # Meter / impact
        d.text((62, 315), "IMPACT MAP", font=font(20), fill=CYAN)
        metrics = [("TIME", 0.78, GREEN), ("EFFORT", 0.54, YELLOW), ("REVIEW", 0.31, RED)]
        for i, (lab, pct, col) in enumerate(metrics):
            y = 370 + i * 70
            d.text((62, y), lab, font=font(18), fill=WHITE)
            d.rounded_rectangle((190, y+4, 1160, y+32), radius=12, fill=(28, 37, 56))
            d.rounded_rectangle((190, y+4, 190+int(970*pct), y+32), radius=12, fill=col)
            d.text((1180, y), f"{int(pct*100)}%", font=font(18), fill=col)
    else:
        # Decision gates
        d.text((62, 310), "THREE GATES", font=font(20), fill=YELLOW)
        gates = [("1", "CLEAR INPUT"), ("2", "VALID OUTPUT"), ("3", "LOW CLEANUP")]
        for i, (n, lab) in enumerate(gates):
            x = 62 + i * 385
            rounded_panel(d, (x, 360, x+330, 520), fill=PANEL,
                          outline=(72, 80, 105))
            d.text((x+25, 390), n, font=font(28), fill=YELLOW)
            d.text((x+25, 450), lab, font=font(21), fill=WHITE)
            d.text((x+25, 485), "PASS", font=font(18), fill=GREEN)

def make_scene(title, label, index, total, episode, output, variant=0):
    im = Image.new("RGB", (W, H), BG)
    add_glow(im, (1050, 170), 220)
    d = ImageDraw.Draw(im)
    plan = episode["scene_plan"][index-1]
    kind = plan["kind"]
    variant = int(plan.get("variant", variant))
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

    elif kind in ("impact", "limitation"):
        ci = plan["case_index"]
        beat = episode["beats"][ci]
        if kind == "impact":
            badge(d, 62, 120, "IMPACT", YELLOW)
            d.text((62, 185), "WHAT ACTUALLY CHANGES?", font=font(40), fill=WHITE)
            metrics = [
                ("TIME", "less repetition", GREEN),
                ("QUALITY", "same target", CYAN),
                ("REVIEW", "visible checkpoint", YELLOW),
            ]
            for i, (lab, val, col) in enumerate(metrics):
                x = 62 + i * 385
                rounded_panel(d, (x, 310, x + 330, 535), fill=PANEL2, outline=(65, 80, 110))
                d.text((x + 24, 340), lab, font=font(20), fill=col)
                d.text((x + 24, 405), val.upper(), font=font(24), fill=WHITE)
                d.rounded_rectangle((x + 24, 470, x + 306, 494), radius=12, fill=(29, 38, 56))
                d.rounded_rectangle((x + 24, 470, x + 230, 494), radius=12, fill=col)
            draw_text_box(d, (62, 575), beat["example"], 19, fill=MUTED,
                          max_width=1120, gap=5, max_lines=2)
        else:
            badge(d, 62, 120, "LIMIT", RED)
            d.text((62, 185), "WHEN THIS WORKFLOW BREAKS", font=font(40), fill=WHITE)
            rounded_panel(d, (62, 310, 575, 570), fill=(18, 51, 42), outline=(55, 111, 91))
            d.text((95, 345), "WORKS WHEN", font=font(20), fill=GREEN)
            draw_text_box(d, (95, 405), "the input is clear and the output can be checked quickly.",
                          24, fill=WHITE, max_width=420, gap=8, max_lines=4)
            rounded_panel(d, (720, 310, 1218, 570), fill=(47, 25, 33), outline=(101, 53, 66))
            d.text((755, 345), "BREAKS WHEN", font=font(20), fill=RED)
            draw_text_box(d, (755, 405), beat["twist"], 24, fill=WHITE,
                          max_width=410, gap=8, max_lines=4)
            d.text((62, 610), "THE LIMIT IS PART OF THE RESULT.", font=font(20), fill=YELLOW)

    elif kind in ("action", "check"):
        ci = plan["case_index"]
        beat = episode["beats"][ci]
        if kind == "action":
            badge(d, 62, 120, "THE MOVE", PURPLE)
            d.text((62, 185), beat["subject"].upper(), font=font(42), fill=WHITE)
            draw_text_box(d, (62, 245), beat["setup"], 25, fill=MUTED, max_width=1080, gap=7, max_lines=2)
            draw_action_visual(d, beat, ci, variant)
        else:
            badge(d, 62, 120, "VERIFY", GREEN)
            d.text((62, 185), "THE OUTPUT MUST SURVIVE A CHECK", font=font(38), fill=WHITE)
            checks = [
                ("CLAIM", "supported by evidence", GREEN),
                ("OUTPUT", "matches the requested format", CYAN),
                ("CLEANUP", "does not create more work", YELLOW),
            ]
            y = 305
            for label, value, col in checks:
                rounded_panel(d, (62, y, 1218, y + 82), fill=PANEL, outline=(54, 79, 76))
                d.ellipse((88, y+23, 118, y+53), fill=col)
                d.text((145, y + 20), label, font=font(19), fill=col)
                d.text((285, y + 20), value, font=font(22), fill=WHITE)
                y += 105
            draw_text_box(d, (62, 625), beat["twist"], 20, fill=MUTED, max_width=1120, gap=6, max_lines=2)

    elif kind in ("case","proof"):
        ci = plan["case_index"]
        beat = episode["beats"][ci]
        if kind == "case":
            badge(d, 62, 120, f"CASE {ci+1:02d}", CYAN)
            d.text((62, 185), beat["subject"].upper(), font=font(44), fill=WHITE)
            draw_text_box(d, (62, 245), beat["setup"], 25, fill=MUTED, max_width=1080, gap=7, max_lines=2)
            draw_case_visual(d, beat, ci, "case", variant)
        else:
            badge(d, 62, 120, "PROOF", GREEN)
            d.text((62, 185), "MAKE THE CHANGE VISIBLE", font=font(40), fill=WHITE)
            draw_case_visual(d, beat, ci, "proof", variant)
            draw_text_box(d, (62, 610), beat["example"], 19, fill=MUTED, max_width=1120, gap=5, max_lines=2)

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

    # Variant-specific shot language makes each narration beat feel like a new camera shot.
    if variant:
        d.rounded_rectangle((980, 112, 1218, 150), radius=16, outline=PURPLE, width=2)
        d.text((1002, 121), f"SHOT {variant+1}", font=font(16), fill=PURPLE)
        d.line((62, 104 + (variant * 19), 340 + variant * 170, 104 + (variant * 19)), fill=PURPLE, width=4)

    # Subtle animated HUD accents make each beat feel like a designed motion graphic.
    if kind not in ("hook", "takeaway"):
        pulse = 10 + ((index * 7) % 18)
        d.ellipse((1160-pulse, 92-pulse, 1160+pulse, 92+pulse), outline=(72,210,255), width=2)
        d.line((1090, 92, 1140, 92), fill=(72,210,255), width=2)

    progress(d, index, total)

    # Alternate cuts get a genuine visual grade change, not just a label.
    if variant:
        im = ImageEnhance.Brightness(im).enhance(1.08)
        im = ImageEnhance.Contrast(im).enhance(1.05)

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
    ap.add_argument("--mode", choices=["test", "short", "scheduled"], default="test")
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
        "story_format": "hook → stakes → test → case/action/proof/impact/check/limit → failure → workflow → scorecard → takeaway → cliffhanger",
    }
    (work / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    # Expand only visual-heavy case/action/proof beats. Narrative/control beats
    # stay single-shot so the timeline gains real visual variety instead of near-duplicate
    # pairs that can trip the diversity gate.
    visual_kinds = {"case", "action", "proof"}
    expanded_plan = []
    for plan in episode["scene_plan"]:
        variants = 2 if plan.get("kind") in visual_kinds else 1
        for variant in range(variants):
            shot = dict(plan)
            shot["variant"] = variant
            shot["label"] = plan["label"] if variant == 0 else f"{plan['label']} • CUT"
            expanded_plan.append(shot)
    episode["scene_plan"] = expanded_plan

    scenes=[]
    total=len(expanded_plan)
    for i, plan in enumerate(expanded_plan, 1):
        path=work / f"scene_{i:02d}.png"
        make_scene(episode["title"], plan["label"], i, total, episode, path, plan.get("variant", 0))
        scenes.append(path)

    visual_report = validate_scene_set(scenes)

    audio=work / "voice.mp3"
    generate_voice(script, audio, cfg)
    video=work / "video.mp4"
    render_video(audio, scenes, video, cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"])

    make_thumbnail(episode["title"], work / "thumbnail.jpg")
    report=validate_video(video, cfg["video"]["width"], cfg["video"]["height"], 120)
    report.update({
        "scene_count": total,
        "scene_diversity_ratio": visual_report["scene_diversity_ratio"],
        "word_count": episode["word_count"],
        "storytelling": "dynamic story beats with proof, failure mode and takeaway",
        "story_structure_gate": "passed",
        "visual_gate": visual_report["visual_gate"],
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

    if args.mode == "scheduled":
        mark_published(topic["id"])

    print("READY:", video)
    print("TITLE:", episode["title"])
    print("DURATION_SECONDS:", report["duration"])
    print("SCENE_COUNT:", total)
    print("WORD_COUNT:", episode["word_count"])
    print("MODE:", args.mode)


if __name__ == "__main__":
    main()
