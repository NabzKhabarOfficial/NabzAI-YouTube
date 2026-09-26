from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def _font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
    ]
    for fp in candidates:
        if Path(fp).exists():
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()

def _wrap(draw, text, font, max_width):
    lines=[]; line=""
    for word in text.split():
        test=(line+" "+word).strip()
        if draw.textbbox((0,0),test,font=font)[2] <= max_width:
            line=test
        else:
            if line: lines.append(line)
            line=word
    if line: lines.append(line)
    return lines

def make_thumbnail(title, output_path):
    p=Path(output_path); p.parent.mkdir(parents=True,exist_ok=True)
    im=Image.new("RGB",(1280,720),(12,16,28)); d=ImageDraw.Draw(im)
    d.rounded_rectangle((35,35,1245,685),radius=38,outline=(235,235,235),width=3)
    badge_font=_font(28); title_font=_font(68)
    d.rounded_rectangle((70,70,330,125),radius=18,fill=(235,235,235))
    d.text((92,82),"NABZ AI",font=badge_font,fill=(12,16,28))
    lines=_wrap(d,title,title_font,1050)
    y=230
    for line in lines[:4]:
        box=d.textbbox((0,0),line,font=title_font)
        d.text(((1280-(box[2]-box[0]))/2,y),line,font=title_font,fill=(245,245,245))
        y += 88
    d.text((70,620),"PRACTICAL AI • TOOLS • AUTOMATION",font=_font(25),fill=(210,210,210))
    im.save(p,quality=95,optimize=True)
    return p
