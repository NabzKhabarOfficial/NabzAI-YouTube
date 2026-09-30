from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.parse
import urllib.request

from gradio_client import Client, handle_file

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "output" / "cinematic-short" / "work"
WORK.mkdir(parents=True, exist_ok=True)

NEGATIVE = (
    "cartoon, anime, illustration, CGI, 3d render, plastic skin, wax face, "
    "doll face, deformed face, asymmetrical eyes, extra fingers, extra limbs, "
    "duplicate person, fused hands, malformed hands, unnatural joints, blurry face, identity drift, "
    "identity change, different person, different hair, different clothing, "
    "face drift, age change, flicker, frozen motion, jerky motion, "
    "text, subtitles, watermark, logo"
)

PROVIDERS = [
    ("agnes", "https://apihub.agnes-ai.com"),
    ("ltx2", "Lightricks/ltx-2"),
    ("wan22", "zerogpu-aoti/wan2-2-fp8da-aoti-faster"),
]


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
                for url in (
                    f"{space_url}/file={value.lstrip('/')}",
                    f"{space_url}/gradio_api/file={value.lstrip('/')}",
                ):
                    try:
                        urllib.request.urlretrieve(url, target)
                        if target.exists() and target.stat().st_size >= 10_000:
                            return str(target)
                    except Exception:
                        pass
    raise RuntimeError("Space returned no usable video media")


def _reference_data_uri(reference: str) -> str:
    if not reference:
        raise RuntimeError("A character reference image is mandatory for cinematic generation")
    path = Path(reference)
    if not path.is_file() or path.stat().st_size < 10_000:
        raise RuntimeError("Character reference image is missing or invalid")
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _provider_order():
    raw = os.getenv("NABZ_VIDEO_PROVIDERS", "").strip()
    if raw:
        wanted = [x.strip().lower() for x in raw.split(",") if x.strip()]
    else:
        wanted = (
            ["agnes", "ltx2", "wan22"]
            if os.getenv("AGNES_API_KEY", "").strip()
            else ["ltx2", "wan22"]
        )
    valid = {name for name, _ in PROVIDERS}
    return [
        x for x in wanted
        if x in valid and (x != "agnes" or os.getenv("AGNES_API_KEY", "").strip())
    ] or ["ltx2", "wan22"]


def _poll_agnes(key: str, video_id: str, model: str, deadline: float):
    headers = {"Authorization": f"Bearer {key}"}
    while time.time() < deadline:
        query = urllib.parse.urlencode({"video_id": video_id, "model_name": model})
        request = urllib.request.Request(
            "https://apihub.agnes-ai.com/agnesapi?" + query,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                status = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            print(f"[video-router] Agnes poll transient error: {type(exc).__name__}: {exc}")
            time.sleep(15)
            continue

        state = str(status.get("status", "")).lower()
        metadata = status.get("metadata") or {}
        result_url = status.get("url") or status.get("video_url") or metadata.get("url")
        if state == "completed" and result_url:
            if not str(result_url).startswith("https://"):
                raise RuntimeError("Agnes returned a non-HTTPS video URL")
            target = WORK / ("agnes_" + next(tempfile._get_candidate_names()) + ".mp4")
            urllib.request.urlretrieve(result_url, target)
            if target.exists() and target.stat().st_size >= 50_000:
                return str(target)
            raise RuntimeError("Agnes returned an invalid video file")
        if state == "failed":
            raise RuntimeError(str(status.get("error") or metadata.get("error") or "Agnes generation failed"))
        time.sleep(20)
    raise TimeoutError(f"Agnes {model} video generation timed out")


def _create_agnes_job(key: str, payload: dict):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    encoded = json.dumps(payload).encode("utf-8")
    last_error = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                "https://apihub.agnes-ai.com/v1/videos",
                data=encoded,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
            video_id = data.get("video_id") or data.get("task_id") or data.get("id")
            if video_id:
                return video_id
            raise RuntimeError(f"Agnes did not return a video id: {data}")
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Agnes create request failed after retries: {last_error}")


def _generate_agnes(reference: str, scene: dict, seed: int):
    key = os.getenv("AGNES_API_KEY", "").strip()
    if not key:
        raise RuntimeError("AGNES_API_KEY is not configured")

    reference_image = _reference_data_uri(reference)
    prompt = (
        "Use <Picture 1> as the identity anchor for the two fictional adult actors. "
        "The exact same man and woman must remain recognizable throughout the shot and across the film. "
        "Preserve their facial identity, hair, age, body proportions and wardrobe from the reference. "
        "Photorealistic live-action short film, natural skin pores, realistic eyes and hands, "
        "subtle breathing and blinking, believable human acting, physical camera movement, "
        "35mm or 50mm lens, shallow depth of field, cinematic practical lighting, restrained film grade. "
        "Do not redesign or reinterpret the people. "
        + scene["prompt"]
    )

    # Current Agnes 2.5 Flash supports reference mode with image references.
    # It is the preferred free-first route; legacy v2.0 remains a reference-aware fallback.
    modern_payload = {
        "model": "agnes-video-2.5-flash",
        "prompt": prompt,
        "mode": "reference",
        "images": [reference_image],
        "seconds": str(max(4, min(12, round(float(scene["seconds"]))))),
        "size": "720P",
        "aspect_ratio": "16:9",
        "seed": int(seed),
        "n": 1,
    }
    try:
        video_id = _create_agnes_job(key, modern_payload)
        return _poll_agnes(
            key, video_id, "agnes-video-2.5-flash", time.time() + 900
        )
    except Exception as modern_error:
        print(f"[video-router] Agnes 2.5 reference path failed: {modern_error}")

    legacy_payload = {
        "model": "agnes-video-v2.0",
        "prompt": prompt,
        "image": reference_image,
        "negative_prompt": NEGATIVE,
        "width": 1152,
        "height": 648,
        "num_frames": 97,
        "frame_rate": 24,
        "seed": int(seed),
    }
    video_id = _create_agnes_job(key, legacy_payload)
    return _poll_agnes(
        key, video_id, "agnes-video-v2.0", time.time() + 900
    )


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


def generate_scene_with_fallback(reference: str, scene: dict, seed: int):
    if not reference:
        raise RuntimeError(
            "Cinematic identity protection is enabled: a character reference is required"
        )

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
