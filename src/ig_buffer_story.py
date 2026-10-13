"""The professional Instagram story clip (Oct 13 2026, owner: "make the stories more professional").

Used by src/ig_buffer.py for every evening reel's story:
  * the reel's own opening (hook title, captions, voice), stopped at the end of a sentence between
    7.5 and 12.5 s (a pause in the voice), never in the middle of a word;
  * a red «ریلز جدید» badge at the top while it plays;
  * a soft cross-fade into a closing card (3.8 s, slow zoom): the reel's cover blurred and darkened,
    the page logo, the story title and «ادامه‌ی ماجرا رو توی پیج ببین» + @nabz.moamma; the sound
    fades out as the card comes in.
Instagram's API takes no stickers or links on a story, so all of it is drawn into the video.
Any failure raises; ig_buffer then uses the plain 15-second clip.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORY_CARD_SECONDS = 3.8


def log(msg):
    print(f"[ig-buffer] {msg}", flush=True)


def _find_pause(ff: str, src: Path, lo: float = 7.5, hi: float = 12.5, default: float = 11.5) -> float:
    """Where to stop the reel: the last pause between two sentences 7.5-12.5 s in (never mid-word)."""
    try:
        proc = subprocess.run([ff, "-hide_banner", "-nostats", "-i", str(src), "-t", f"{hi + 0.5:.1f}", "-vn",
                               "-af", "silencedetect=noise=-30dB:d=0.2", "-f", "null", "-"],
                              capture_output=True, text=True, timeout=120)
        starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", proc.stderr)]
        good = [s for s in starts if lo <= s <= hi]
        return round(max(good) + 0.12, 2) if good else default
    except Exception:
        return default


def _story_pictures(cover: Path, title: str, kind: str, work: Path) -> bool:
    """badge.png + card.png from src.story_card in a fresh Python (Pillow + Persian shaping are
    installed on the fly: the buffer job installs nothing)."""
    cmd = [sys.executable, "-m", "src.story_card", str(cover), title, kind, str(work)]
    for attempt in range(3):
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
        if proc.returncode == 0 and (work / "card.png").exists() and (work / "badge.png").exists():
            return True
        err = (proc.stderr or proc.stdout or "")[-300:]
        if "No module named 'PIL'" in err:
            log("story pictures: installing Pillow")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pillow"], capture_output=True, timeout=300)
        elif proc.returncode == 3:
            log("story pictures: installing the Persian shaping library")
            subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", "libfribidi0", "libraqm0"],
                           capture_output=True, timeout=300)
        else:
            log(f"story pictures failed: {err}")
            return False
    return False


def story_pro(ff: str, src: Path, cover: Path, title: str, kind: str, out: Path) -> float:
    """Build the story video at `out`; returns its length in seconds (see the module notes)."""
    work = out.with_name(out.stem + "_parts")
    work.mkdir(parents=True, exist_ok=True)
    if not _story_pictures(cover, title, kind, work):
        raise RuntimeError("story pictures not made")
    cut = _find_pause(ff, src)
    total = cut + STORY_CARD_SECONDS
    frames = int(STORY_CARD_SECONDS * 30) + 20
    fc = (f"[0:v]trim=0:{cut + 0.5:.2f},setpts=PTS-STARTPTS,fps=30,scale=1080:1920,setsar=1,format=yuv420p,settb=AVTB[v0];"
          f"[1:v]scale=1080:1920,setsar=1,zoompan=z='min(1+0.0008*on,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={frames}:s=1080x1920:fps=30,format=yuv420p,settb=AVTB[v1];"
          f"[v0][v1]xfade=transition=fade:duration=0.5:offset={cut:.2f}[vx];"
          f"[2:v]format=rgba,fade=t=in:st=0.3:d=0.4:alpha=1[bd];"
          f"[vx][bd]overlay=(W-w)/2:270:enable='lt(t,{cut:.2f})'[vb];"
          f"[vb]format=yuv420p[v];"
          f"[0:a]atrim=0:{cut + 0.5:.2f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0.5, cut - 0.35):.2f}:d=0.85,"
          f"apad=whole_dur={total:.2f}[a]")
    cmd = [ff, "-y", "-loglevel", "error", "-i", str(src), "-i", str(work / "card.png"),
           "-loop", "1", "-t", f"{total:.2f}", "-i", str(work / "badge.png"),
           "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or not out.exists() or out.stat().st_size < 100_000:
        raise RuntimeError("story video failed: " + proc.stderr.strip()[-300:])
    return total
