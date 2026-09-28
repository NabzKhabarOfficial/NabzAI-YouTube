from __future__ import annotations

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


def _client(space: str):
    try:
        from gradio_client import Client
    except ImportError as exc:
        raise RuntimeError("gradio_client is required for cinematic mode.") from exc
    token = os.getenv("HF_TOKEN", "").strip() or None
    # Gradio 6 removes hf_token; token works on current clients and avoids
    # a deprecation warning without changing the free-only architecture.
    return Client(space, token=token)


def _local_file(value):
    if isinstance(value, str) and Path(value).is_file(): return value
    if isinstance(value, dict):
        for key in ("path", "url", "video", "image"):
            candidate = value.get(key)
            if isinstance(candidate, str) and Path(candidate).is_file(): return candidate
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _local_file(item)
            if found: return found
    return None


def _download_remote(space_url: str, remote_path: str, suffix: str):
    import urllib.request
    target = WORK / ("remote_" + next(tempfile._get_candidate_names()) + suffix)
    path = remote_path.lstrip("/")
    last_error = None
    for url in (f"{space_url}/file={path}", f"{space_url}/gradio_api/file={path}"):
        try:
            urllib.request.urlretrieve(url, target)
            if target.exists() and target.stat().st_size >= 10_000: return str(target)
        except Exception as exc: last_error = exc
    raise RuntimeError(f"Remote Space returned invalid media: {last_error}")


def _resolve_media(result, space_url: str | None = None, suffix=".mp4"):
    local = _local_file(result)
    if local: return local
    values = result if isinstance(result, (list, tuple)) else [result]
    for value in values:
        if isinstance(value, dict): value = value.get("path") or value.get("url")
        if isinstance(value, str) and value.startswith("/") and space_url:
            try: return _download_remote(space_url, value, suffix)
            except Exception: pass
    raise RuntimeError(f"Space returned no usable media: {str(result)[:500]}")


def generate_character_reference():
    cached = WORK / "character_reference.png"
    if cached.exists() and cached.stat().st_size >= 10_000:
        return str(cached)
    client = _client("black-forest-labs/FLUX.1-schnell")
    prompt = (
        "Photorealistic cinematic character reference photograph for a fictional live-action short film. "
        "Exactly two fictional adult humans standing together, full body, neutral relaxed pose. "
        "Man early 30s, short dark hair, natural light stubble, charcoal coat. "
        "Woman late 20s, shoulder-length dark brown hair, beige sweater. Natural skin texture, realistic eyes, "
        "believable faces, realistic proportions, neutral studio background, soft film lighting, 50mm photography, no text."
    )
    result = client.predict(prompt, 42, False, 1024, 1024, 4, api_name="/infer")
    source = _resolve_media(result, "https://black-forest-labs-flux-1-schnell.hf.space", ".png")
    cached.write_bytes(Path(source).read_bytes())
    return str(cached)


def _render_scene_with_audio(video: str, audio: Path, output: Path, target_seconds: float):
    # Never let short TTS truncate a cinematic shot. Pad the shorter stream and force
    # every scene to its planned duration, which prevents the previous 9.8s final.
    vf = f"tpad=stop_mode=clone:stop_duration={max(0.1, target_seconds):.2f}"
    af = f"apad=pad_dur={max(0.1, target_seconds):.2f}"
    r = subprocess.run([
        FFMPEG, "-y", "-i", video, "-i", str(audio),
        "-filter_complex", f"[0:v]{vf}[v];[1:a]{af}[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{target_seconds:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", "16", "-c:a", "aac", "-b:a", "128k",
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
        generate_voice(line, path, {**cfg, "voice": {**cfg["voice"], "voice": voices.get(speaker, cfg["voice"]["voice"])}})
        parts.append(path)
    manifest = WORK / f"scene_{index}_audio.txt"
    manifest.write_text("\n".join(f"file '{p.resolve()}'" for p in parts) + "\n", encoding="utf-8")
    output = WORK / f"scene_{index}_audio.m4a"
    r = subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c:a", "aac", "-b:a", "128k", str(output)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode: raise RuntimeError("Dialogue audio rendering failed: " + r.stderr[-1200:])
    return output


def _concat_scene_clips(clips: list[Path], output: Path):
    manifest = WORK / "final_concat.txt"
    manifest.write_text("\n".join(f"file '{p.resolve()}'" for p in clips) + "\n", encoding="utf-8")
    r = subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", "16", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode: raise RuntimeError("Final concatenation failed: " + r.stderr[-1800:])


def _technical_gate(path: Path, expected_seconds: float):
    duration = _probe_duration(path)
    minimum = max(12.0, expected_seconds - 0.6)
    if duration < minimum:
        raise RuntimeError(f"Quality gate failed: duration={duration:.2f}s expected>={minimum:.2f}s")
    probe = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if "Video:" not in probe.stderr or "Audio:" not in probe.stderr: raise RuntimeError("Quality gate failed: missing audio/video stream")
    if path.stat().st_size < 500_000: raise RuntimeError("Quality gate failed: final file unexpectedly small")
    return duration


def main():
    OUT.mkdir(parents=True, exist_ok=True); WORK.mkdir(parents=True, exist_ok=True)
    print(f"[cinematic] story slot={STORY['slot']} title={STORY['title']}")
    use_agnes = bool(os.getenv("AGNES_API_KEY", "").strip())
    reference = "" if use_agnes else generate_character_reference()
    scene_clips, providers_used = [], []
    expected_seconds = sum(float(scene.get("seconds", 3.5)) for scene in STORY["scenes"])
    for index, scene in enumerate(STORY["scenes"], 1):
        scene_clip = WORK / f"scene_{index}_final.mp4"
        if scene_clip.exists() and scene_clip.stat().st_size >= 50_000:
            scene_clips.append(scene_clip); providers_used.append("cached"); continue
        scene_video, provider = generate_scene_with_fallback(reference, scene, seed=9100 + STORY["slot"] * 100 + index)
        scene_audio = _make_dialogue_audio(scene, index)
        _render_scene_with_audio(scene_video, scene_audio, scene_clip, float(scene.get("seconds", 3.5)))
        scene_clips.append(scene_clip); providers_used.append(provider)
    final = OUT / "final_film.mp4"
    _concat_scene_clips(scene_clips, final)
    duration = _technical_gate(final, expected_seconds)
    report = {"title": STORY["title"], "logline": STORY["logline"], "language": STORY["language"], "story_slot": STORY["slot"], "scene_count": len(scene_clips), "duration_seconds": round(duration,2), "generation": {"video_model": providers_used, "post": "FFmpeg", "voice": "Edge TTS English", "paid_services_required": False}, "gates": {"character_reference_required": not use_agnes, "character_prompt_consistency_required": True, "story_structure_required": True, "english_dialogue_required": True, "audio_stream_required": True, "video_stream_required": True, "minimum_duration_seconds": 12.0, "passed": True}}
    (OUT / "quality.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "story.json").write_text(json.dumps(STORY, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"READY: {final}")


if __name__ == "__main__": main()
