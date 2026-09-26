from pathlib import Path
import subprocess
import imageio_ffmpeg
def render_video(audio_path,card_path,output_path,width=1280,height=720,fps=30):
    p=Path(output_path); p.parent.mkdir(parents=True,exist_ok=True)
    cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loop','1','-i',str(card_path),'-i',str(audio_path),'-vf',f'scale={width}:{height}','-r',str(fps),'-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(p)]
    subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if not p.exists() or p.stat().st_size<10000: raise RuntimeError('Video rendering failed.')
    return p
