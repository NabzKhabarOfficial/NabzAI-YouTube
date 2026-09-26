from pathlib import Path
import re
import shutil
import subprocess
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FFPROBE = shutil.which("ffprobe")


def _probe_duration(path):
    if FFPROBE:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if r.returncode == 0 and r.stdout.strip():
            try:
                return float(r.stdout.strip())
            except ValueError:
                pass

    r = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        raise RuntimeError("Could not read media duration.")
    h, minutes, seconds = m.groups()
    return int(h) * 3600 + int(minutes) * 60 + float(seconds)


def _duration(audio_path):
    duration = _probe_duration(audio_path)
    if duration <= 0:
        raise RuntimeError("Audio duration is zero.")
    return duration


def _motion_filters(i, total, each, width, height, fps):
    """Return a reusable motion-graphics layer for one visual beat.

    The base scene remains readable while lightweight animated accents create
    continuous movement: a camera drift, a moving light sweep, and a progress
    marker that advances through the beat. The animation is generated locally
    by FFmpeg, so it adds no external service or model dependency.
    """
    motion = i % 4
    if motion == 0:
        z = "min(zoom+0.00022,1.055)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif motion == 1:
        z = "min(zoom+0.00018,1.045)"
        x = "iw/2-(iw/zoom/2)+18"
        y = "ih/2-(ih/zoom/2)-10"
    elif motion == 2:
        z = "max(zoom-0.00016,1.015)"
        x = "iw/2-(iw/zoom/2)-18"
        y = "ih/2-(ih/zoom/2)+10"
    else:
        z = "min(zoom+0.00020,1.050)"
        x = "iw/2-(iw/zoom/2)-12"
        y = "ih/2-(ih/zoom/2)+14"

    # Different beats get different sweep directions to avoid a repetitive
    # "Ken Burns only" feeling.
    sweep_x = (
        "900+180*sin(t*1.35)"
        if motion in (0, 2)
        else "380+220*sin(t*1.10)"
    )
    sweep_y = (
        "120+520*abs(sin(t*0.62))"
        if motion in (1, 3)
        else "118"
    )

    start = i / total
    end = (i + 1) / total
    progress_x = (
        f"62+1156*({start:.6f}+"
        f"({end-start:.6f})*min(t/{each:.6f},1))-4"
    )

    return (
        f"scale={int(width*1.07)}:{int(height*1.07)},"
        f"zoompan=z='{z}':x='{x}':y='{y}':"
        f"d=1:s={width}x{height}:fps={fps},format=yuv420p,"
        # Animated light sweep.
        f"drawbox=x='{sweep_x}':y='{sweep_y}':w=3:h=500:"
        f"color=0x48d2ff@0.18:t=fill,"
        # A second, slower accent makes the motion visible without obscuring
        # the text or cards.
        f"drawbox=x='64+80*sin(t*0.75)':y=94:w=120:h=2:"
        f"color=0x48d2ff@0.24:t=fill,"
        # A short mid-beat sweep creates a visible event instead of leaving
        # the viewer on one static card for the entire narration beat.
        f"drawbox=x='62+1156*min(t/{each:.6f},1)':y=96:w=4:h=580:"
        f"color=0x48d2ff@0.42:t=fill:"
        f"enable='between(t,{each*0.44:.3f},{each*0.54:.3f})',"
        # Progress marker moves continuously during each beat.
        f"drawbox=x='{progress_x}':y=681:w=8:h=18:"
        f"color=0x48d2ff@0.90:t=fill"
    )


def render_video(audio_path, scene_paths, output_path, width=1280, height=720, fps=30):
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    duration = _duration(audio_path)
    if not scene_paths:
        raise RuntimeError("At least one scene is required.")

    transition = 0.28 if len(scene_paths) > 1 else 0.0
    each = max(
        1.5,
        (duration + transition * max(0, len(scene_paths) - 1)) / len(scene_paths),
    )

    inputs, filters = [], []
    total = len(scene_paths)
    for i, scene in enumerate(scene_paths):
        inputs += [
            "-loop", "1", "-framerate", str(fps), "-t", f"{each:.3f}", "-i", str(scene)
        ]
        filters.append(
            f"[{i}:v]{_motion_filters(i, total, each, width, height, fps)}[v{i}]"
        )

    current = "v0"
    for i in range(1, len(scene_paths)):
        out = f"x{i}"
        offset = i * each - i * transition
        transitions = ("fade", "smoothleft", "wipeleft", "slideright", "circleopen")
        transition_name = transitions[(i - 1) % len(transitions)]
        filters.append(
            f"[{current}][v{i}]xfade=transition={transition_name}:duration={transition:.2f}:offset={offset:.3f}[{out}]"
        )
        current = out

    cmd = [
        FFMPEG, "-y", *inputs, "-i", str(audio_path),
        "-filter_complex", ";".join(filters),
        "-map", f"[{current}]", "-map", f"{len(scene_paths)}:a",
        "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart", str(p)
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise RuntimeError("Video rendering failed: " + r.stderr[-2200:])
    if not p.exists() or p.stat().st_size < 10000:
        raise RuntimeError("Video rendering produced an invalid file.")
    return p


def render_short(audio_path, card_path, output_path, width=1080, height=1920, fps=30):
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG, "-y", "-loop", "1", "-i", str(card_path), "-i", str(audio_path),
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
               f"zoompan=z='min(zoom+0.00025,1.04)':d=1:s={width}x{height}:fps={fps},"
               f"drawbox=x='80+70*sin(t*0.8)':y=120:w=4:h=1450:"
               f"color=0x48d2ff@0.16:t=fill",
        "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart", str(p)
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise RuntimeError("Short rendering failed: " + r.stderr[-1200:])
    return p
