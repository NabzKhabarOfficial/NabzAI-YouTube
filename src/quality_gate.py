from pathlib import Path
import json
import shutil
import subprocess
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FFPROBE = shutil.which("ffprobe")

def _probe(path):
    if not FFPROBE:
        raise RuntimeError("Quality gate: ffprobe is required but was not found on the runner.")
    r = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise RuntimeError("Quality gate: ffprobe probe failed: " + r.stderr[-800:])
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Quality gate: ffprobe returned invalid JSON.") from exc

def validate_video(path, expected_width=1280, expected_height=720, min_seconds=120):
    p = Path(path)
    if not p.exists() or p.stat().st_size < 10000:
        raise RuntimeError("Quality gate: invalid video file.")
    data = _probe(p)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise RuntimeError("Quality gate: video and audio streams are required.")
    duration = float(data.get("format", {}).get("duration", 0) or 0)
    if duration < min_seconds:
        raise RuntimeError(f"Quality gate: video is only {duration:.1f}s; expected at least {min_seconds}s.")
    if int(video.get("width", 0)) != expected_width or int(video.get("height", 0)) != expected_height:
        raise RuntimeError("Quality gate: unexpected video dimensions.")
    if video.get("codec_name") != "h264" or audio.get("codec_name") != "aac":
        raise RuntimeError("Quality gate: expected H.264 video and AAC audio.")
    decode = subprocess.run([FFMPEG, "-v", "error", "-i", str(p), "-f", "null", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if decode.returncode:
        raise RuntimeError("Quality gate: decode failed: " + decode.stderr[-800:])
    return {"duration": duration, "width": video["width"], "height": video["height"],
            "video_codec": video["codec_name"], "audio_codec": audio["codec_name"]}
