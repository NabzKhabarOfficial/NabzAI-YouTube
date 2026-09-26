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

ROOT=Path(__file__).resolve().parents[1]

def load_settings():
    return json.loads((ROOT/"config/settings.json").read_text(encoding="utf-8"))

def font(size):
    fp="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    return ImageFont.truetype(fp,size) if Path(fp).exists() else ImageFont.load_default()

def make_scene(title, label, index, output):
    im=Image.new("RGB",(1280,720),(12,16,28)); d=ImageDraw.Draw(im)
    d.rounded_rectangle((45,45,1235,675),radius=35,outline=(235,235,235),width=3)
    d.text((75,75),f"NABZ AI  /  {label}",font=font(28),fill=(210,210,210))
    d.text((75,220),title,font=font(58),fill=(245,245,245))
    d.text((75,570),f"Scene {index}  •  Practical AI workflow",font=font(26),fill=(210,210,210))
    im.save(output,quality=95)

def make_short_card(title,path):
    im=Image.new("RGB",(1080,1920),(12,16,28)); d=ImageDraw.Draw(im)
    d.rounded_rectangle((55,55,1025,1865),radius=42,outline=(235,235,235),width=4)
    d.text((90,100),"NABZ AI",font=font(34),fill=(235,235,235))
    d.text((90,620),title,font=font(62),fill=(245,245,245))
    d.text((90,1420),"Practical AI • Tools • Automation",font=font(30),fill=(210,210,210))
    im.save(path,quality=95)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",choices=["test","short"],default="test")
    args=ap.parse_args()
    cfg=load_settings()
    topic=choose_topic()
    work=ROOT/"output"/topic["id"]; work.mkdir(parents=True,exist_ok=True)
    target=cfg["video"]["target_minutes"]
    script=build_script(topic,target)
    title=make_title(topic); description=make_description(topic)
    (work/"script.txt").write_text(script,encoding="utf-8")
    (work/"metadata.json").write_text(json.dumps({"title":title,"description":description,"tags":topic["tags"],"keywords":topic["keywords"]},ensure_ascii=False,indent=2),encoding="utf-8")
    scenes=[]
    for i,label in enumerate(["HOOK","THE PROBLEM","THE METHOD","REAL EXAMPLE","QUALITY CHECK","TAKEAWAY"],1):
        path=work/f"scene_{i}.png"; make_scene(title if i==1 else topic["sections"][min(i-2,len(topic["sections"])-1)].title(),label,i,path); scenes.append(path)
    audio=work/"voice.mp3"; generate_voice(script,audio,cfg)
    video=work/"video.mp4"; render_video(audio,scenes,video,cfg["video"]["width"],cfg["video"]["height"],cfg["video"]["fps"])
    thumb=make_thumbnail(title,work/"thumbnail.jpg")
    report=validate_video(video,cfg["video"]["width"],cfg["video"]["height"],120)
    (work/"quality.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    if args.mode=="short":
        short_script=make_short_script(topic)
        short_audio=work/"short_voice.mp3"; generate_voice(short_script,short_audio,cfg)
        card=work/"short_card.png"; make_short_card(title,card)
        render_short(short_audio,card,work/"short.mp4",cfg["shorts"]["width"],cfg["shorts"]["height"],cfg["shorts"]["fps"])
    print("READY:",video)
    print("TITLE:",title)
    print("DURATION_SECONDS:",report["duration"])
    print("MODE:",args.mode)

if __name__=="__main__":
    main()
