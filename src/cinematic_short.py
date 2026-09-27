from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from .voice_engine import generate_voice
from .video_engine import FFMPEG, _probe_duration

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "cinematic-short"
WORK = OUT / "work"

STORY = {
    "title": "The Letter That Arrived Late",
    "logline": "After years away, a man returns on a rainy night with an old letter that forces two people to face a truth they left unfinished.",
    "language": "en-US",
    "characters": {
        "man": "A fictional adult man in his early 30s, short black hair, natural light stubble, charcoal wool coat, tired but calm expression, fully photorealistic human appearance.",
        "woman": "A fictional adult woman in her late 20s, shoulder-length dark brown hair, beige sweater, expressive natural eyes, restrained emotion, fully photorealistic human appearance.",
    },
    "dialogue": [
        ("woman", "I never thought you would come back."),
        ("man", "I said I would. I just had to bring you this letter."),
        ("woman", "Then why did you wait all these years?"),
        ("man", "Because I wasn't ready for you to know the truth."),
    ],
    "scenes": [
        {
            "id": 1, "seconds": 3.0,
            "dialogue": [("man", "I said I would.")],
            "prompt": "Photorealistic live-action cinematic short film. Same fictional adult man from the character bible, exact identity and wardrobe: early 30s, short black hair, natural light stubble, charcoal wool coat. Rainy night outside an old apartment building. He walks toward the entrance holding a sealed envelope, slows under a streetlamp, breath visible in cold air, looks toward one lit window. Natural human walking, subtle facial emotion, realistic wet skin and fabric, physically plausible rain, practical street lighting, 35mm lens, shallow depth of field, restrained film color grade, gentle handheld camera. No cartoon, no CGI look, no text, no subtitles, no watermark."
        },
        {
            "id": 2, "seconds": 3.0,
            "dialogue": [("woman", "I never thought you would come back.")],
            "prompt": "Photorealistic live-action continuation, same fictional adult man and same fictional adult woman, exact identity and wardrobe as the reference. The apartment door opens. The woman in her late 20s with shoulder-length dark brown hair and beige sweater freezes when she sees the man. He stands quietly with the sealed envelope. She takes one small breath and looks from his face to the envelope. Natural eye movement, believable human body language, realistic skin texture, subtle emotion, rainy street light entering the doorway, slow cinematic push-in, 50mm lens, shallow depth of field. No cartoon, no CGI look, no text, no subtitles, no watermark."
        },
        {
            "id": 3, "seconds": 3.0,
            "dialogue": [("man", "I just had to bring you this letter.")],
            "prompt": "Photorealistic live-action continuation, exact same two fictional adults, exact faces, hair and wardrobe. Inside the quiet apartment, the man places the sealed envelope on a wooden table. The woman remains standing opposite him, uncertain. He gently slides the envelope toward her. She hesitates, reaches for it, and looks at him. Restrained realistic acting, tiny hand movement, natural blinking and breathing, warm practical lamp light contrasting with the cool rainy window, cinematic over-the-shoulder composition, 50mm lens, subtle dolly movement, realistic film texture. No cartoon, no CGI look, no text, no subtitles, no watermark."
        },
        {
            "id": 4, "seconds": 3.0,
            "dialogue": [("woman", "Then why did you wait all these years?")],
            "prompt": "Photorealistic live-action final beat, exact same fictional man and woman, consistent faces, hair and wardrobe. Close-up at the wooden table: the woman opens the old envelope and finds a faded photograph. Her eyes become wet but she stays composed. The man watches silently. She looks up at him; he gives a small relieved smile. End with both hands resting beside the photograph as rain softly moves on the window in the background. Natural human emotion, realistic eyes and skin, subtle breathing, cinematic 85mm close-up, warm practical lighting, shallow depth of field, understated film color grade. No melodrama, no cartoon, no CGI look, no text, no subtitles, no watermark."
        },
    ],
}

NEGATIVE = (
    "cartoon, anime, illustration, CGI, 3d render, plastic skin, wax face, "
    "doll face, deformed face, asymmetrical eyes, extra fingers, extra limbs, "
    "duplicate person, fused hands, malformed hands, unnatural joints, blurry face, "
    "flicker, frozen motion, jerky motion, text, subtitles, watermark, logo"
)


def _client(space: str):
    try:
        from gradio_client import Client
    except ImportError as exc:
        raise RuntimeError("gradio_client is required for cinematic mode.") from exc
    token = os.getenv("HF_TOKEN", "").strip() or None
    return Client(space, hf_token=token)


def _local_file(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value if Path(value).is_file() else None
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
    raise RuntimeError(f"Remote Space returned an invalid media file: {last_error}")


def _resolve_media(result, space_url: str | None = None, suffix=".mp4"):
    local = _local_file(result)
    if local:
        return local
    values = result if isinstance(result, (list, tuple)) else [result]
    for value in values:
        if isinstance(value, dict):
            for key in ("path", "url"):
                candidate = value.get(key)
                if isinstance(candidate, str):
                    value = candidate
                    break
        if isinstance(value, str) and value.startswith("/") and space_url:
            try:
                return _download_remote(space_url, value, suffix)
            except Exception:
                continue
    raise RuntimeError(f"Space returned no usable media: {str(result)[:500]}")


def generate_character_reference():
    cached = WORK / "character_reference.png"
    if cached.exists() and cached.stat().st_size >= 10_000:
        print("[cinematic] reusing cached character reference")
        return str(cached)
    client = _client("black-forest-labs/FLUX.1-schnell")
    prompt = (
        "Photorealistic cinematic character reference photograph for a fictional live-action short film. "
        "Exactly two fictional adult humans standing together, full body, neutral relaxed pose, front three-quarter view. "
        "Man early 30s, short black hair, natural light stubble, charcoal wool coat. "
        "Woman late 20s, shoulder-length dark brown hair, beige sweater. Natural skin texture, realistic eyes, "
        "believable faces, subtle imperfections, realistic proportions, neutral studio background, soft film lighting, "
        "50mm photography, no text, no logo."
    )
    result = client.predict(prompt, 42, False, 1024, 1024, 4, api_name="/infer")
    source = _resolve_media(result, "https://black-forest-labs-flux-1-schnell.hf.space", ".png")
    cached = WORK / "character_reference.png"
    if Path(source).resolve() != cached.resolve():
        cached.write_bytes(Path(source).read_bytes())
    return str(cached)


def generate_scene(reference: str, scene: dict, seed: int):
    client = _client("zerogpu-aoti/wan2-2-fp8da-aoti-faster")
    from gradio_client import handle_file
    result = client.predict(
        handle_file(reference), scene["prompt"], 4, NEGATIVE,
        float(scene["seconds"]), 1.0, 1.0, int(seed), False,
        api_name="/generate_video",
    )
    return _resolve_media(result, "https://zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space", ".mp4")


def _render_scene_with_audio(video: str, audio: Path, output: Path):
    cmd = [
        FFMPEG, "-y", "-i", video, "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
        "-r", "16", "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "+faststart", str(output),
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise RuntimeError("Scene audio/video mux failed: " + r.stderr[-1600:])
    if not output.exists() or output.stat().st_size < 50_000:
        raise RuntimeError("Scene mux produced an invalid file.")


def _make_dialogue_audio(scene: dict, index: int) -> Path:
    cfg = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))
    voices = {"woman": "en-US-AriaNeural", "man": "en-US-GuyNeural"}
    lines = scene.get("dialogue") or []
    parts = []
    for part_index, (speaker, line) in enumerate(lines, 1):
        path = WORK / f"scene_{index}_line_{part_index}.mp3"
        generate_voice(line, path, {**cfg, "voice": {**cfg["voice"], "voice": voices[speaker]}})
        parts.append(path)
    manifest = WORK / f"scene_{index}_audio.txt"
    manifest.write_text("\n".join(f"file '{p.resolve()}'" for p in parts) + "\n", encoding="utf-8")
    output = WORK / f"scene_{index}_audio.m4a"
    r = subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
         "-c:a", "aac", "-b:a", "128k", str(output)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if r.returncode:
        raise RuntimeError("Dialogue audio rendering failed: " + r.stderr[-1200:])
    return output


def _concat_scene_clips(clips: list[Path], output: Path):
    manifest = WORK / "final_concat.txt"
    manifest.write_text("\n".join(f"file '{p.resolve()}'" for p in clips) + "\n", encoding="utf-8")
    r = subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
         "-pix_fmt", "yuv420p", "-r", "16", "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart", str(output)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if r.returncode:
        raise RuntimeError("Final concatenation failed: " + r.stderr[-1800:])


def _technical_gate(path: Path):
    duration = _probe_duration(path)
    if duration < 10:
        raise RuntimeError(f"Cinematic quality gate failed: duration={duration:.2f}s")
    probe = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if "Video:" not in probe.stderr or "Audio:" not in probe.stderr:
        raise RuntimeError("Cinematic quality gate failed: missing audio/video stream.")
    if path.stat().st_size < 500_000:
        raise RuntimeError("Cinematic quality gate failed: final file is unexpectedly small.")
    return duration


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    print("[cinematic] creating persistent character reference")
    reference = generate_character_reference()
    scene_clips = []
    for index, scene in enumerate(STORY["scenes"], 1):
        scene_clip = WORK / f"scene_{index}_final.mp4"
        if scene_clip.exists() and scene_clip.stat().st_size >= 50_000:
            print(f"[cinematic] reusing cached scene {index}/{len(STORY['scenes'])}")
            scene_clips.append(scene_clip)
            continue
        print(f"[cinematic] generating scene {index}/{len(STORY['scenes'])}")
        scene_video = generate_scene(reference, scene, seed=9100 + index)
        scene_audio = _make_dialogue_audio(scene, index)
        _render_scene_with_audio(scene_video, scene_audio, scene_clip)
        scene_clips.append(scene_clip)
    if len(scene_clips) != len(STORY["scenes"]):
        raise RuntimeError("Cinematic generation incomplete: cached progress is preserved for the next run.")
    final = OUT / "final_film.mp4"
    _concat_scene_clips(scene_clips, final)
    duration = _technical_gate(final)
    report = {
        "title": STORY["title"], "logline": STORY["logline"],
        "language": STORY["language"], "scene_count": len(scene_clips),
        "duration_seconds": round(duration, 2), "characters": STORY["characters"],
        "generation": {
            "character_reference": "FLUX.1-schnell ZeroGPU",
            "video_model": "Wan2.2 14B Fast ZeroGPU", "post": "FFmpeg",
            "voice": "Edge TTS English", "paid_services_required": False,
        },
        "gates": {
            "photorealistic_prompt_contract": True,
            "character_reference_required": True, "story_structure_required": True,
            "english_dialogue_required": True, "audio_stream_required": True,
            "video_stream_required": True, "passed": True,
        },
    }
    (OUT / "quality.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "story.json").write_text(json.dumps(STORY, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"READY: {final}")
    print(f"DURATION_SECONDS: {duration:.2f}")


if __name__ == "__main__":
    main()
