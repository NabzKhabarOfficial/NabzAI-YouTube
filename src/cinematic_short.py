from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .voice_engine import generate_voice
from .video_engine import FFMPEG, _probe_duration

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "cinematic-short"
WORK = OUT / "work"

STORY = {
    "title": "The Last Letter",
    "logline": "On a rainy night, a man returns to deliver a letter he promised would change everything.",
    "characters": {
        "man": "A fictional man in his early 30s, dark short hair, light stubble, charcoal wool coat, tired but calm expression.",
        "woman": "A fictional woman in her late 20s, shoulder-length dark brown hair, beige sweater, expressive eyes, restrained emotion.",
    },
    "dialogue": [
        ("woman", "I never thought you would come back."),
        ("man", "I said I would. Until you read this letter, it was never over."),
        ("woman", "Then maybe it isn't too late."),
    ],
    "scenes": [
        {
            "id": 1,
            "seconds": 3.0,
            "prompt": "Cinematic live-action short film, rainy night outside an old apartment building. The same two fictional characters from the reference must keep their exact identity. The man stands alone under a streetlamp, holding a sealed envelope, wet charcoal coat, breathing slowly, looking toward one apartment window. Natural human movement, subtle emotion, realistic rain, practical lighting, 35mm lens, shallow depth of field, restrained color grade, handheld camera, photorealistic, no text, no subtitles."
        },
        {
            "id": 2,
            "seconds": 3.0,
            "prompt": "Continue the same live-action short film with the exact same two fictional characters and wardrobe from the reference. The woman opens the apartment door and freezes when she sees the man. He raises the sealed envelope slightly. She looks shocked, then emotional. Natural facial reactions and body language, realistic skin and eyes, rainy night light spilling into the doorway, slow cinematic push-in, 50mm lens, shallow depth of field, photorealistic film look, no text, no subtitles."
        },
        {
            "id": 3,
            "seconds": 3.0,
            "prompt": "Final scene of the same live-action short film, exact same characters and wardrobe. Inside a quiet dim apartment, the man places the sealed envelope on a wooden table. The woman opens it and finds an old photograph. Her expression softens and she looks at him through tears; he gives a small relieved smile. End on a close-up of their hands beside the photograph, warm practical lamp light, subtle camera movement, cinematic 85mm close-up, natural human motion, photorealistic, emotional but understated, no text, no subtitles."
        },
    ],
}

NEGATIVE = (
    "cartoon, anime, illustration, CGI, plastic skin, wax face, distorted face, "
    "extra fingers, extra limbs, duplicate people, deformed hands, blurry face, "
    "text, subtitles, watermark, logo, frozen motion, unnatural movement"
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
        if Path(value).is_file():
            return value
        return None
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
    url = f"{space_url}/file={remote_path.lstrip('/')}"
    urllib.request.urlretrieve(url, target)
    if not target.exists() or target.stat().st_size < 10_000:
        raise RuntimeError("Remote Space returned an invalid media file.")
    return str(target)


def _resolve_media(result, space_url: str | None = None, suffix=".mp4"):
    local = _local_file(result)
    if local:
        return local
    if isinstance(result, str) and result.startswith("/") and space_url:
        return _download_remote(space_url, result, suffix)
    if isinstance(result, (list, tuple)):
        for item in result:
            if isinstance(item, str) and item.startswith("/") and space_url:
                try:
                    return _download_remote(space_url, item, suffix)
                except Exception:
                    pass
    raise RuntimeError(f"Space returned no usable media: {str(result)[:400]}")


def generate_character_reference():
    client = _client("black-forest-labs/FLUX.1-schnell")
    prompt = (
        "Photorealistic cinematic character reference photograph for a fictional short film. "
        "Exactly two fictional adult humans standing together, full body, neutral relaxed pose, "
        "front three-quarter view. Man early 30s, dark short hair, light stubble, charcoal wool coat. "
        "Woman late 20s, shoulder-length dark brown hair, beige sweater. Natural skin texture, realistic eyes, "
        "ordinary attractive faces, subtle imperfections, realistic proportions, neutral studio background, "
        "soft film lighting, 50mm photography, no text, no logo."
    )
    result = client.predict(
        prompt, 42, False, 1024, 1024, 4, api_name="/infer"
    )
    return _resolve_media(result, "https://black-forest-labs-flux-1-schnell.hf.space", ".png")


def generate_scene(reference: str, scene: dict, seed: int):
    client = _client("zerogpu-aoti/wan2-2-fp8da-aoti-faster")
    from gradio_client import handle_file

    result = client.predict(
        handle_file(reference),
        scene["prompt"],
        4,
        NEGATIVE,
        float(scene["seconds"]),
        1.0,
        1.0,
        int(seed),
        False,
        api_name="/generate_video",
    )
    return _resolve_media(
        result,
        "https://zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space",
        ".mp4",
    )


def concat_videos(scene_paths: list[str], output: Path):
    list_file = WORK / "concat.txt"
    lines = []
    for path in scene_paths:
        safe = str(Path(path).resolve()).replace("'", "'\\''")
        lines.append(f"file '{safe}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [
        FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-pix_fmt", "yuv420p", "-r", "24", "-an",
        "-movflags", "+faststart", str(output),
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise RuntimeError("Scene concatenation failed: " + r.stderr[-1800:])


def build_dialogue_audio(output: Path):
    cfg = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))
    parts = []
    voices = {
        "woman": "en-US-AriaNeural",
        "man": "en-US-GuyNeural",
    }
    for idx, (speaker, line) in enumerate(STORY["dialogue"], 1):
        path = WORK / f"dialogue_{idx}.mp3"
        generate_voice(line, path, {**cfg, "voice": {**cfg["voice"], "voice": voices[speaker]}})
        parts.append(path)

    manifest = WORK / "dialogue_concat.txt"
    manifest.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in parts) + "\n",
        encoding="utf-8",
    )
    cmd = [
        FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
        "-c:a", "aac", "-b:a", "160k", str(output),
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise RuntimeError("Dialogue audio rendering failed: " + r.stderr[-1200:])


def mux_final(video: Path, audio: Path, output: Path):
    cmd = [
        FFMPEG, "-y", "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-shortest", "-movflags", "+faststart", str(output),
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        raise RuntimeError("Final mux failed: " + r.stderr[-1500:])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    # Anonymous ZeroGPU users have a small daily quota. Three short shots are
    # deliberately used for the first fully-free proof film. A HF_TOKEN can
    # be added later to access the larger free-account quota.
    reference = generate_character_reference()
    scene_paths = []
    for i, scene in enumerate(STORY["scenes"], 1):
        print(f"[cinematic] generating scene {i}/{len(STORY['scenes'])}")
        scene_path = generate_scene(reference, scene, seed=9100 + i)
        scene_paths.append(scene_path)

    silent = WORK / "silent.mp4"
    concat_videos(scene_paths, silent)

    audio = WORK / "dialogue.m4a"
    build_dialogue_audio(audio)

    final = OUT / "final_film.mp4"
    mux_final(silent, audio, final)

    duration = _probe_duration(final)
    if duration < 7:
        raise RuntimeError(f"Cinematic quality gate failed: duration={duration:.2f}s")
    if final.stat().st_size < 500_000:
        raise RuntimeError("Cinematic quality gate failed: final file is unexpectedly small.")

    report = {
        "title": STORY["title"],
        "logline": STORY["logline"],
        "scene_count": len(scene_paths),
        "duration_seconds": round(duration, 2),
        "characters": STORY["characters"],
        "generation": {
            "character_reference": "FLUX.1-schnell ZeroGPU",
            "video_model": "Wan2.2 14B Fast ZeroGPU",
            "post": "FFmpeg",
            "voice": "Edge TTS",
            "paid_services_required": False,
        },
        "gates": {
            "realistic_video_required": True,
            "character_reference_required": True,
            "story_structure_required": True,
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
    print(f"DURATION_SECONDS: {duration:.2f}")


if __name__ == "__main__":
    main()
