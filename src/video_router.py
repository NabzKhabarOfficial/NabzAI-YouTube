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
    ("ltx2", "Lightricks/ltx-2"),
    ("wan22", "zerogpu-aoti/wan2-2-fp8da-aoti-faster"),
]


def _provider_order():
    raw = os.getenv("NABZ_VIDEO_PROVIDERS", "ltx2,wan22")
    wanted = [x.strip().lower() for x in raw.split(",") if x.strip()]
    valid = {name for name, _ in PROVIDERS}
    return [x for x in wanted if x in valid] or ["ltx2", "wan22"]


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
    generators = {"ltx2": _generate_ltx, "wan22": _generate_wan}

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
