from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
def make_thumbnail(title,output_path):
    p=Path(output_path); p.parent.mkdir(parents=True,exist_ok=True)
    im=Image.new('RGB',(1280,720),(18,18,24)); d=ImageDraw.Draw(im)
    fp='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'; f=ImageFont.truetype(fp,58) if Path(fp).exists() else ImageFont.load_default()
    d.rounded_rectangle((45,45,1235,675),radius=35,outline='white',width=4)
    words=title.split(); lines=[]; line=''
    for w in words:
        t=(line+' '+w).strip()
        if d.textbbox((0,0),t,font=f)[2]>1080 and line: lines.append(line); line=w
        else: line=t
    if line: lines.append(line)
    y=250
    for line in lines[:4]:
        box=d.textbbox((0,0),line,font=f); d.text(((1280-(box[2]-box[0]))/2,y),line,font=f,fill='white'); y+=75
    im.save(p,quality=95); return p
