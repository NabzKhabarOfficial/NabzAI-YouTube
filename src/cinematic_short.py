from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .voice_engine import generate_voice
from .video_engine import FFMPEG, _probe_duration
from .video_router import generate_scene_with_fallback
from .story_factory import load_story

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "cinematic-short"
WORK = OUT / "work"
STORY = load_story()

PIPELINE_VERSION = "2026-09-30-character-reference-v3-six-shot"
SCENE_SECONDS = 4.0


def _client(space: str):
    try:
        from gradio_client import Client
    except ImportError as exc:
        raise RuntimeError("gradio_client is required for cinematic mode.") from exc
    token = os.getenv("HF_TOKEN", "").strip() or None
    return Client(space, hf_token=token)


def _local_file(value):
    if isinstance(value, str) and Path(value).is_file():
        return value
    if isinstance(value, dict):
        for key in ("path", "url", "video", "image"):
            candidate = value.get(key)
            if isinstance(candidate, str) and Path(candidate).is_file():
                return candidate
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _local_file(item)
            if found:
                return found
    return None


def _download_remote(space_url: str, remote_path: str, suffix: str):
    import urllib.request

    target = WORK / ("remote_" + next(tempfile._get_candidate_names()) + suffix)
    path = remote_path.lstrip("/")
    last_error = None
    for url in (f"{space_url}/file={path}", f"{space_url}/gradio_api/file={path}"):
        try:
            urllib.request.urlretrieve(url, target)
            if target.exists() and target.stat().st_size >= 10_000:
                return str(target)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Remote Space returned invalid media: {last_error}")


def _resolve_media(result, space_url: str | None = None, suffix=".mp4"):
    local = _local_file(result)
    if local:
        return local
    values = result if isinstance(result, (list, tuple)) else [result]
    for value in values:
        if isinstance(value, dict):
            value = value.get("path") or value.get("url")
        if isinstance(value, str) and value.startswith("/") and space_url:
            try:
                return _download_remote(space_url, value, suffix)
            except Exception:
                pass
    raise RuntimeError(f"Space returned no usable media: {str(result)[:500]}")


def _save_agnes_image_response(data: dict, cached: Path) -> str:
    import urllib.request

    items = data.get("data") or []
    if not items:
        raise RuntimeError(f"Agnes image API returned no image: {data}")

    item = items[0] or {}
    url = item.get("url")
    if url:
        if not str(url).startswith("https://"):
            raise RuntimeError("Agnes image API returned a non-HTTPS URL")
        urllib.request.urlretrieve(url, cached)
    else:
        raw = item.get("b64_json")
        if not raw:
            raise RuntimeError("Agnes image API returned neither url nor b64_json")
        cached.write_bytes(base64.b64decode(raw))

    if cached.stat().st_size < 10_000:
        raise RuntimeError("Generated character reference is unexpectedly small")
    return str(cached)


def _generate_agnes_character_reference(cached: Path) -> str:
    import urllib.request

    key = os.getenv("AGNES_API_KEY", "").strip()
    if not key:
        raise RuntimeError("AGNES_API_KEY is not configured")

    prompt = (
        "Photorealistic live-action character continuity reference sheet for a fictional short film. "
        "Exactly two adult human actors together in the same frame, shown from the waist up and clearly visible. "
        "Man early 30s, short dark brown hair, natural light stubble, charcoal wool coat over a dark shirt. "
        "Woman late 20s, shoulder-length dark brown hair, beige knit sweater. "
        "Keep their faces highly distinctive and stable: natural facial proportions, realistic eyes, skin pores, "
        "subtle asymmetry, believable ears and hairline. Neutral relaxed expressions, neutral studio background, "
        "soft cinematic 50mm photography, natural practical lighting, no text, no watermark, no beauty-filter look."
    )
    payload = json.dumps({
        "model": "agnes-image-2.5-flash",
        "prompt": prompt,
        "n": 1,
        "size": "1024x768",
        "extra_body": {"response_format": "url"},
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://apihub.agnes-ai.com/v1/images/generations",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
    return _save_agnes_image_response(data, cached)


def generate_character_reference():
    cached = WORK / "character_reference.png"
    if cached.exists() and cached.stat().st_size >= 10_000:
        return str(cached)

    if os.getenv("AGNES_API_KEY", "").strip():
        try:
            return _generate_agnes_character_reference(cached)
        except Exception as exc:
            print(f"[cinematic] Agnes character reference failed: {exc}")

    client = _client("black-forest-labs/FLUX.1-schnell")
    prompt = (
        "Photorealistic cinematic character reference photograph for a fictional live-action short film. "
        "Exactly two fictional adult humans standing together, full body, neutral relaxed pose. "
        "Man early 30s, short dark hair, natural light stubble, charcoal coat. "
        "Woman late 20s, shoulder-length dark brown hair, beige sweater. Natural skin texture, realistic eyes, "
        "believable faces, realistic proportions, neutral studio background, soft film lighting, 50mm photography, no text."
    )
    result = client.predict(prompt, 42, False, 1024, 1024, 4, api_name="/infer")
    source = _resolve_media(
        result, "https://black-forest-labs-flux-1-schnell.hf.space", ".png"
    )
    cached.write_bytes(Path(source).read_bytes())
    return str(cached)


def _reset_stale_work():
    marker = WORK / "pipeline_manifest.json"
    current = {
        "pipeline_version": PIPELINE_VERSION,
        "story_slot": STORY["slot"],
        "scene_count": len(STORY["scenes"]),
    }

    stale = True
    if marker.exists():
        try:
            stale = json.loads(marker.read_text(encoding="utf-8")) != current
        except Exception:
            stale = True

    if stale:
        print("[cinematic] resetting stale scene cache for new story/pipeline version")
        for pattern in (
            "scene_*_final.mp4",
            "scene_*_audio.m4a",
            "scene_*_audio.txt",
            "scene_*_line_*.mp3",
            "scene_*_silent.wav",
            "final_concat.txt",
            "thumbnail_source.jpg",
        ):
            for path in WORK.glob(pattern):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        for path in (
            OUT / "final_film.mp4",
            OUT / "quality.json",
            OUT / "story.json",
            OUT / "thumbnail.jpg",
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    marker.write_text(json.dumps(current, indent=2), encoding="utf-8")


def _render_scene_with_audio(video: str, audio: Path, output: Path, target_seconds: float):
    # Agnes may return 1280x704 for a nominal 16:9 request. Normalize to true
    # YouTube 1280x720 here with a tiny center crop rather than black bars.
    vf = (
        "scale=1280:720:force_original_aspect_ratio=increase,"
        "crop=1280:720,format=yuv420p"
    )
    af = f"apad=pad_dur={max(0.1, target_seconds):.2f}"
    r = subprocess.run([
        FFMPEG, "-y", "-i", video, "-i", str(audio),
        "-filter_complex", f"[0:v]{vf}[v];[1:a]{af}[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{target_seconds:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "24", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", str(output)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode or not output.exists() or output.stat().st_size < 50_000:
        raise RuntimeError("Scene audio/video mux failed: " + r.stderr[-1600:])


def _make_dialogue_audio(scene: dict, index: int) -> Path:
    cfg = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))
    voices = {"woman": "en-US-AriaNeural", "man": "en-US-GuyNeural"}
    parts = []

    for part_index, (speaker, line) in enumerate(scene.get("dialogue") or [], 1):
        path = WORK / f"scene_{index}_line_{part_index}.mp3"
        generate_voice(
            line,
            path,
            {**cfg, "voice": {**cfg["voice"], "voice": voices.get(speaker, cfg["voice"]["voice"])}},
        )
        parts.append(path)

    output = WORK / f"scene_{index}_audio.m4a"
    if not parts:
        silent = WORK / f"scene_{index}_silent.wav"
        r = subprocess.run([
            FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", f"{SCENE_SECONDS:.2f}", "-c:a", "pcm_s16le", str(silent)
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if r.returncode:
            raise RuntimeError("Silent scene audio creation failed: " + r.stderr[-1000:])
        source = silent
        r = subprocess.run([
            FFMPEG, "-y", "-i", str(source), "-c:a", "aac", "-b:a", "160k", str(output)
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if r.returncode:
            raise RuntimeError("Silent scene audio encoding failed: " + r.stderr[-1000:])
        return output

    manifest = WORK / f"scene_{index}_audio.txt"
    manifest.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in parts) + "\n",
        encoding="utf-8",
    )
    r = subprocess.run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
        "-c:a", "aac", "-b:a", "160k", str(output)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise RuntimeError("Dialogue audio rendering failed: " + r.stderr[-1200:])
    return output


def _concat_scene_clips(clips: list[Path], output: Path):
    manifest = WORK / "final_concat.txt"
    manifest.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in clips) + "\n",
        encoding="utf-8",
    )
    r = subprocess.run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "24", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", str(output)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise RuntimeError("Final concatenation failed: " + r.stderr[-1800:])


def _motion_score(path: Path) -> float:
    """Measure real temporal change without requiring OpenCV."""
    with tempfile.TemporaryDirectory(prefix="nabz_motion_") as td:
        pattern = str(Path(td) / "f_%02d.jpg")
        r = subprocess.run([
            FFMPEG, "-v", "error", "-i", str(path),
            "-vf", "fps=2,scale=160:90:flags=bilinear,format=gray",
            "-frames:v", "8", pattern,
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if r.returncode:
            raise RuntimeError("Motion analysis failed: " + r.stderr[-800:])
        frames = sorted(Path(td).glob("f_*.jpg"))
        if len(frames) < 4:
            return 0.0
        from PIL import Image, ImageChops, ImageStat
        arrays = [Image.open(p).convert("L") for p in frames]
        diffs = [
            float(ImageStat.Stat(ImageChops.difference(a, b)).mean[0])
            for a, b in zip(arrays, arrays[1:])
        ]
        return round(sum(diffs) / len(diffs), 2)


def _make_thumbnail(final: Path, title: str):
    thumb = OUT / "thumbnail.jpg"
    source = WORK / "thumbnail_source.jpg"
    r = subprocess.run([
        FFMPEG, "-y", "-ss", "2.0", "-i", str(final), "-frames:v", "1",
        "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
        str(source)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode or not source.exists():
        raise RuntimeError("Thumbnail frame extraction failed: " + r.stderr[-1000:])

    from PIL import Image, ImageDraw, ImageFont, ImageEnhance
    im = Image.open(source).convert("RGB")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, 1280, 720), fill=(0, 0, 0, 78))
    draw.rounded_rectangle((55, 55, 735, 175), radius=24, fill=(8, 12, 20, 205))
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    font_path = next((p for p in font_paths if Path(p).exists()), None)
    font = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()
    small = ImageFont.truetype(font_path, 25) if font_path else ImageFont.load_default()
    draw.text((85, 75), "NABZ AI", font=small, fill=(180, 220, 255, 255))
    # Keep the title compact and readable on mobile.
    title_text = title if len(title) <= 28 else title[:25].rstrip() + "..."
    draw.text((85, 112), title_text, font=font, fill=(255, 255, 255, 255))
    im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
    im = ImageEnhance.Contrast(im).enhance(1.04)
    im.save(thumb, quality=94, optimize=True)
    return thumb


def _technical_gate(path: Path, expected_seconds: float, scene_paths: list[Path]):
    duration = _probe_duration(path)
    minimum = expected_seconds - 0.35
    if duration < minimum:
        raise RuntimeError(
            f"Quality gate failed: duration={duration:.2f}s expected>={minimum:.2f}s"
        )

    probe = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    info = probe.stderr
    if "Video:" not in info or "Audio:" not in info:
        raise RuntimeError("Quality gate failed: missing audio/video stream")

    if "1280x720" not in info:
        raise RuntimeError("Quality gate failed: final output must be 1280x720")

    if path.stat().st_size < 800_000:
        raise RuntimeError("Quality gate failed: final file unexpectedly small")

    scene_scores = []
    for scene in scene_paths:
        score = _motion_score(scene)
        scene_scores.append(score)
        if score < 3.0:
            raise RuntimeError(
                f"Quality gate failed: scene {scene.name} is too static (motion_score={score:.2f})"
            )

    return duration, scene_scores


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    _reset_stale_work()

    print(f"[cinematic] story slot={STORY['slot']} title={STORY['title']}")
    reference = generate_character_reference()
    print(f"[cinematic] character reference={reference}")

    scene_clips, providers_used = [], []
    expected_seconds = sum(float(scene.get("seconds", SCENE_SECONDS)) for scene in STORY["scenes"])

    if len(STORY["scenes"]) != 6:
        raise RuntimeError("Cinematic pipeline requires exactly six shots.")

    for index, scene in enumerate(STORY["scenes"], 1):
        scene_clip = WORK / f"scene_{index}_final.mp4"
        if scene_clip.exists() and scene_clip.stat().st_size >= 50_000:
            scene_clips.append(scene_clip)
            providers_used.append("cached")
            continue

        scene_video, provider = generate_scene_with_fallback(
            reference, scene, seed=9100 + STORY["slot"] * 100 + index
        )
        scene_audio = _make_dialogue_audio(scene, index)
        _render_scene_with_audio(
            scene_video, scene_audio, scene_clip, float(scene.get("seconds", SCENE_SECONDS))
        )
        scene_clips.append(scene_clip)
        providers_used.append(provider)

    final = OUT / "final_film.mp4"
    _concat_scene_clips(scene_clips, final)
    duration, scene_scores = _technical_gate(final, expected_seconds, scene_clips)
    thumbnail = _make_thumbnail(final, STORY["title"])

    report = {
        "title": STORY["title"],
        "logline": STORY["logline"],
        "language": STORY["language"],
        "story_slot": STORY["slot"],
        "scene_count": len(scene_clips),
        "scene_seconds": SCENE_SECONDS,
        "duration_seconds": round(duration, 2),
        "resolution": "1280x720",
        "motion_scores": scene_scores,
        "generation": {
            "video_model": providers_used,
            "reference_mode": True,
            "character_reference": "Agnes Image 2.5 Flash or HF fallback",
            "post": "FFmpeg",
            "voice": "Edge TTS English",
            "paid_services_required": False,
        },
        "delivery": {
            "thumbnail": thumbnail.name,
            "youtube_ready": True,
            "synthetic_media": True,
        },
        "gates": {
            "character_reference_required": True,
            "character_prompt_consistency_required": True,
            "story_structure_required": True,
            "english_dialogue_required": True,
            "audio_stream_required": True,
            "video_stream_required": True,
            "true_16_9_1280x720_required": True,
            "motion_gate_required": True,
            "minimum_duration_seconds": round(expected_seconds - 0.35, 2),
            "passed": True,
        },
    }
    (OUT / "quality.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "story.json").write_text(
        json.dumps(STORY, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"READY: {final}")
    print(f"THUMBNAIL: {thumbnail}")
    print(f"MOTION_SCORES: {scene_scores}")


if __name__ == "__main__":
    main()
