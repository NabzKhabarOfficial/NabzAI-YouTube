import argparse,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from .topic_engine import choose_topic
from .script_engine import build_script,make_title,make_description
from .voice_engine import generate_voice
from .thumbnail_engine import make_thumbnail
from .video_engine import render_video
from .quality_gate import validate_video
ROOT=Path(__file__).resolve().parents[1]
def load_settings(): return json.loads((ROOT/'config/settings.json').read_text(encoding='utf-8'))
def make_card(title,path):
    im=Image.new('RGB',(1280,720),(18,18,24)); d=ImageDraw.Draw(im); fp='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'; f=ImageFont.truetype(fp,48) if Path(fp).exists() else ImageFont.load_default()
    d.text((70,270),title,font=f,fill='white'); d.text((70,350),'آموزش کاربردی هوش مصنوعی | NABZ AI',font=ImageFont.load_default(),fill='white'); im.save(path)
def main():
    cfg=load_settings(); topic=choose_topic(); work=ROOT/'output'/topic['id']; work.mkdir(parents=True,exist_ok=True)
    script=build_script(topic); (work/'script.txt').write_text(script,encoding='utf-8')
    title=make_title(topic); description=make_description(topic)
    (work/'metadata.json').write_text(json.dumps({'title':title,'description':description,'tags':topic['tags']},ensure_ascii=False,indent=2),encoding='utf-8')
    card=work/'card.png'; make_card(title,card); audio=work/'voice.mp3'; generate_voice(script,audio,cfg)
    video=work/'video.mp4'; render_video(audio,card,video,cfg['video']['width'],cfg['video']['height'],cfg['video']['fps']); make_thumbnail(title,work/'thumbnail.jpg'); validate_video(video)
    print('READY',video); print('TITLE',title)
if __name__=='__main__': argparse.ArgumentParser().parse_args(); main()
