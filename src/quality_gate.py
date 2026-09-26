from pathlib import Path
import json
import re
import subprocess
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

def _probe_with_ffmpeg(path):
    """Probe media using the bundled FFmpeg; no system ffprobe dependency."""
    r = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stderr = r.stderr
    if not stderr:
        raise RuntimeError("Quality gate: FFmpeg returned no media information.")

    duration_match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr
    )
    if not duration_match:
        raise RuntimeError(
            "Quality gate: could not read video duration from FFmpeg."
        )
    h, minutes, seconds = duration_match.groups()
    duration = int(h) * 3600 + int(minutes) * 60 + float(seconds)

    video_match = re.search(
        r"Stream #\S+.*?Video:\s*([^,\s]+).*?(\d{2,5})x(\d{2,5})",
        stderr,
        re.IGNORECASE,
    )
    audio_match = re.search(
        r"Stream #\S+.*?Audio:\s*([^,\s]+)",
        stderr,
        re.IGNORECASE,
    )

    if not video_match:
        raise RuntimeError("Quality gate: video stream information not found.")
    if not audio_match:
        raise RuntimeError("Quality gate: audio stream information not found.")

    return {
        "format": {"duration": duration},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": video_match.group(1).lower(),
                "width": int(video_match.group(2)),
                "height": int(video_match.group(3)),
            },
            {
                "codec_type": "audio",
                "codec_name": audio_match.group(1).lower(),
            },
        ],
    }

def validate_video(path, expected_width=1280, expected_height=720, min_seconds=120):
    p = Path(path)
    if not p.exists() or p.stat().st_size < 10000:
        raise RuntimeError("Quality gate: invalid video file.")

    data = _probe_with_ffmpeg(p)
    streams = data["streams"]
    video = next((s for s in streams if s["codec_type"] == "video"), None)
    audio = next((s for s in streams if s["codec_type"] == "audio"), None)

    if not video or not audio:
        raise RuntimeError("Quality gate: video and audio streams are required.")

    duration = float(data["format"]["duration"])
    if duration < min_seconds:
        raise RuntimeError(
            f"Quality gate: video is only {duration:.1f}s; expected at least {min_seconds}s."
        )

    if (
        int(video["width"]) != expected_width
        or int(video["height"]) != expected_height
    ):
        raise RuntimeError("Quality gate: unexpected video dimensions.")

    if video["codec_name"] != "h264" or audio["codec_name"] != "aac":
        raise RuntimeError(
            "Quality gate: expected H.264 video and AAC audio."
        )

    decode = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(p), "-f", "null", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if decode.returncode:
        raise RuntimeError(
            "Quality gate: decode failed: " + decode.stderr[-1200:]
        )

    return {
        "duration": duration,
        "width": video["width"],
        "height": video["height"],
        "video_codec": video["codec_name"],
        "audio_codec": audio["codec_name"],
    }
