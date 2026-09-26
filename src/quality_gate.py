from pathlib import Path
import subprocess
import imageio_ffmpeg
def validate_video(path):
    p=Path(path)
    if not p.exists() or p.stat().st_size<10000: raise RuntimeError('Quality gate: invalid video file.')
    r=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(p),'-f','null','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if r.returncode: raise RuntimeError('Quality gate: FFmpeg decode failed: '+r.stderr[-500:])
    return True
