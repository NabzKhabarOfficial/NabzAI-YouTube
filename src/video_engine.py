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
    """Generate real per-frame camera motion for a still scene.

    Each scene enters zoompan as one still frame and zoompan produces the
    complete beat duration. Using output-time expressions keeps the camera
    moving across the whole beat instead of resetting on every source frame.
    """
    motion = i % 4
    if motion == 0:
        z = "min(1.0+0.14*(time/each),1.14)"
        x = "((iw-iw/zoom)/2)+55*sin(time*0.42)"
        y = "((ih-ih/zoom)/2)+28*cos(time*0.35)"
    elif motion == 1:
        z = "min(1.13,1.0+0.13*(time/each))"
        x = "((iw-iw/zoom)/2)-60*sin(time*0.36)"
        y = "((ih-ih/zoom)/2)+34*sin(time*0.30)"
    elif motion == 2:
        z = "max(1.01,1.13-0.12*(time/each))"
        x = "((iw-iw/zoom)/2)+65*cos(time*0.32)"
        y = "((ih-ih/zoom)/2)-30*sin(time*0.40)"
    else:
        z = "min(1.15,1.0+0.15*(time/each))"
        x = "((iw-iw/zoom)/2)-55*cos(time*0.38)"
        y = "((ih-ih/zoom)/2)-34*cos(time*0.29)"

    sweep_x = (
        "900+180*sin(t*1.35)"
        if motion in (0, 2)
        else "380+220*sin(t*1.10)"
    )
    sweep_y = (
        "120+420*abs(sin(t*0.62))"
        if motion in (1, 3)
        else "118"
    )

    start = i / total
    end = (i + 1) / total
    progress_x = (
        f"62+1156*({start:.6f}+"
        f"({end-start:.6f})*min(t/{each:.6f},1))-4"
    )
    sweep_start = each * 0.38
    sweep_end = each * 0.50

    return (
        f"zoompan=z='{z}':x='{x}':y='{y}':"
        f"d={max(1, int(each*fps))}:s={width}x{height}:fps={fps},"
        f"format=yuv420p,"
        f"drawbox=x='{sweep_x}':y='{sweep_y}':w=6:h=560:"
        f"color=0x48d2ff@0.20:t=fill,"
        f"drawbox=x='760+220*sin(t*0.95)':"
        f"y='155+55*cos(t*0.80)':w=170:h=170:"
        f"color=0x48d2ff@0.07:t=fill,"
        f"drawbox=x='64+420*sin(t*0.55)':y=96:w=260:h=4:"
        f"color=0x48d2ff@0.28:t=fill,"
        f"drawbox=x='62+1156*min(t/{each:.6f},1)':y=681:w=8:h=18:"
        f"color=0x48d2ff@0.90:t=fill,"
        f"drawbox=x='62':y=96:w=1156:h=2:"
        f"color=0x48d2ff@0.30:t=fill:"
        f"enable='between(time,{sweep_start:.3f},{sweep_end:.3f})'"
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
            "-loop", "1", "-framerate", "1", "-t", "1", "-i", str(scene)
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
