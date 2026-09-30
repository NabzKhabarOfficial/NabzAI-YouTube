from __future__ import annotations

import os
from pathlib import Path

from gradio_client import Client, handle_file
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "output" / "cinematic-short" / "work"

def _client(space: str):
    token = os.getenv("HF_TOKEN", "").strip() or None
    return Client(space, hf_token=token)

def _resolve_media(result, space_url: str, suffix=".mp4"):
    values = result if isinstance(result, (list, tuple)) else [result]
    for value in values:
        if isinstance(value, dict):
            value = value.get("path") or value.get("url")
        if isinstance(value, str):
            p = Path(value)
            if p.is_file():
                return str(p)
            if value.startswith("/"):
                target = WORK / ("router_remote_" + next(tempfile._get_candidate_names()) + suffix)
                for url in (f"{space_url}/file={value.lstrip('/')}", f"{space_url}/gradio_api/file={value.lstrip('/')}"):
                    try:
                        urllib.request.urlretrieve(url, target)
                        if target.exists() and target.stat().st_size >= 10_000:
                            return str(target)
                    except Exception:
                        pass
    raise RuntimeError("Space returned no usable video media")

NEGATIVE = (
    "cartoon, anime, illustration, CGI, 3d render, plastic skin, wax face, "
    "doll face, deformed face, asymmetrical eyes, extra fingers, extra limbs, "
    "duplicate person, fused hands, malformed hands, unnatural joints, blurry face, "
    "flicker, frozen motion, jerky motion, text, subtitles, watermark, logo"
)

PROVIDERS = [
    ("agnes", "https://apihub.agnes-ai.com"),
    ("ltx2", "Lightricks/ltx-2"),
    ("wan22", "zerogpu-aoti/wan2-2-fp8da-aoti-faster"),
]


def _provider_order():
    raw = os.getenv("NABZ_VIDEO_PROVIDERS", "").strip()
    if raw:
        wanted = [x.strip().lower() for x in raw.split(",") if x.strip()]
    else:
        wanted = ["agnes", "ltx2", "wan22"] if os.getenv("AGNES_API_KEY", "").strip() else ["ltx2", "wan22"]
    valid = {name for name, _ in PROVIDERS}
    return [x for x in wanted if x in valid and (x != "agnes" or os.getenv("AGNES_API_KEY", "").strip())] or ["ltx2", "wan22"]


def _generate_agnes(reference: str, scene: dict, seed: int):
    import json
    import time
    import urllib.parse
    import urllib.request

    key = os.getenv("AGNES_API_KEY", "").strip()
    if not key:
        raise RuntimeError("AGNES_API_KEY is not configured")

    base = "https://apihub.agnes-ai.com"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    # Agnes is the no-GPU production path. The reference image is represented
    # by the same fixed character bible in every scene prompt.
    prompt = (
        "Photorealistic live-action cinematic short film, real human actors, "
        "natural skin and eyes, realistic hands, physical camera movement, "
        "35mm/50mm lens, shallow depth of field, consistent adult characters, "
        "restrained film lighting and color grade. "
        + scene["prompt"]
        + " No CGI, cartoon, anime, illustration, text, subtitles, watermark or logo."
    )
    seconds = max(3.0, min(float(scene["seconds"]), 5.0))
    # Agnes requires num_frames = 8n + 1. Round to the closest legal frame count.
    frames = max(9, min(441, 8 * round((seconds * 24 - 1) / 8) + 1))
    payload = json.dumps({
        "model": "agnes-video-v2.0",
        "prompt": prompt,
        "negative_prompt": NEGATIVE,
        "width": 1152,
        "height": 768,
        "num_frames": frames,
        "frame_rate": 24,
        "seed": int(seed),
    }).encode("utf-8")
    data = None
    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(base + "/v1/videos", data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
    if data is None:
        raise RuntimeError(f"Agnes create request failed after retries: {last_error}")
    video_id = data.get("video_id") or data.get("task_id")
    if not video_id:
        raise RuntimeError(f"Agnes did not return a video id: {data}")

    deadline = time.time() + 900
    while time.time() < deadline:
        query = urllib.parse.urlencode({"video_id": video_id, "model_name": "agnes-video-v2.0"})
        poll = urllib.request.Request(base + "/agnesapi?" + query, headers={"Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(poll, timeout=90) as resp:
                status = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            print(f"[video-router] Agnes poll transient error: {type(exc).__name__}: {exc}")
            time.sleep(15)
            continue
        state = str(status.get("status", "")).lower()
        result_url = status.get("url") or status.get("video_url")
        if state == "completed" and result_url:
            if not str(result_url).startswith("https://"):
                raise RuntimeError("Agnes returned a non-HTTPS video URL")
            target = WORK / ("agnes_" + next(tempfile._get_candidate_names()) + ".mp4")
            urllib.request.urlretrieve(result_url, target)
            if target.exists() and target.stat().st_size >= 50_000:
                return str(target)
            raise RuntimeError("Agnes returned an invalid video file")
        if state == "failed":
            raise RuntimeError(str(status.get("error", "Agnes generation failed")))
        time.sleep(30)
    raise TimeoutError("Agnes video generation timed out after 15 minutes")


def _generate_ltx(reference: str, scene: dict, seed: int):
    client = _client("Lightricks/ltx-2")
    result = client.predict(
        handle_file(reference),
        scene["prompt"],
        float(scene["seconds"]),
        NEGATIVE,
        int(seed),
        False,
        25,
        3.0,
        704,
        1216,
        api_name="/generate_video",
    )
    return _resolve_media(result, "https://lightricks-ltx-2.hf.space", ".mp4")


def _generate_wan(reference: str, scene: dict, seed: int):
    client = _client("zerogpu-aoti/wan2-2-fp8da-aoti-faster")
    result = client.predict(
        handle_file(reference), scene["prompt"], 4, NEGATIVE,
        float(scene["seconds"]), 1.0, 1.0, int(seed), False,
        api_name="/generate_video",
    )
    return _resolve_media(
        result,
        "https://zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space",
        ".mp4",
    )


def generate_scene_with_fallback(reference: str, scene: dict, seed: int):
    errors = []
    generators = {"agnes": _generate_agnes, "ltx2": _generate_ltx, "wan22": _generate_wan}

    for name in _provider_order():
        print(f"[video-router] trying provider={name}")
        try:
            media = generators[name](reference, scene, seed)
            if Path(media).exists() and Path(media).stat().st_size >= 50_000:
                print(f"[video-router] provider={name} succeeded")
                return media, name
            raise RuntimeError("provider returned an invalid media file")
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            errors.append(f"{name}: {message}")
            print(f"[video-router] provider={name} failed: {message}")

    raise RuntimeError("All video providers failed: " + " | ".join(errors))
