"""AI Horde: free, crowd-sourced Stable Diffusion workers (https://aihorde.net), no paid plan.

Last-resort picture provider (Oct 12 2026): it is used only when Hugging Face, Cloudflare and
Pollinations are all out of their free daily quota. The anonymous key works without an account
(AI_HORDE_KEY can hold a free registered key for a shorter queue). It is slow (a queue of
volunteer GPUs), so one run spends at most NABZ_HORDE_SECONDS on it and second camera angles
never use it.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request

API = "https://aihorde.net/api/v2"
BUDGET = float(os.getenv("NABZ_HORDE_SECONDS", "1500"))  # whole run, seconds
PER_IMAGE = float(os.getenv("NABZ_HORDE_IMAGE_SECONDS", "600"))
WIDTH, HEIGHT = 640, 1152  # portrait 9:16 under the anonymous size limit
MODELS = [m.strip() for m in os.getenv(
    "NABZ_HORDE_MODELS", "AlbedoBase XL (SDXL),Juggernaut XL,ICBINP XL,Deliberate").split(",") if m.strip()]
NEGATIVE = "text, letters, words, watermark, logo, signature, blurry, deformed, extra limbs, cartoon"
SKIP_WORDS = ("extreme close-up detail shot", "wide establishing shot from a different angle",
              "low angle dramatic shot, different framing", "over-the-shoulder view")
_SPENT = [0.0]


def _call(path: str, body: dict | None = None, method: str = "GET") -> dict:
    key = os.getenv("AI_HORDE_KEY", "").strip() or "0000000000"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers={
        "apikey": key, "Client-Agent": "NabzAI:1.0:github.com/NabzKhabarOfficial",
        "Content-Type": "application/json", "User-Agent": "NabzAI/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"AI Horde HTTP {exc.code}: {exc.read()[:200].decode('utf-8', 'ignore')}") from None
    return json.loads(raw or b"{}")


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "NabzAI/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def generate(prompt: str, seed: int) -> bytes:
    """One portrait picture as image bytes (webp/png); raises RuntimeError on any problem."""
    if any(w in prompt for w in SKIP_WORDS):
        raise RuntimeError("AI Horde is kept for the main pictures (second angle skipped)")
    if _SPENT[0] >= BUDGET:
        raise RuntimeError("AI Horde time budget of this run is used up (quota)")
    start = time.time()
    body = {"prompt": f"{prompt[:900]} ### {NEGATIVE}",
            "params": {"width": WIDTH, "height": HEIGHT, "steps": 24, "n": 1, "cfg_scale": 6.5,
                       "sampler_name": "k_dpmpp_2m", "karras": True, "seed": str(int(seed) % 2147483647)},
            "nsfw": False, "censor_nsfw": True, "trusted_workers": False, "r2": True, "models": MODELS}
    job = _call("/generate/async", body, "POST").get("id")
    if not job:
        raise RuntimeError("AI Horde did not accept the request")
    limit = min(PER_IMAGE, max(60.0, BUDGET - _SPENT[0]))
    try:
        while True:
            time.sleep(8)
            check = _call(f"/generate/check/{job}")
            if check.get("faulted"):
                raise RuntimeError("AI Horde job faulted")
            if check.get("is_possible") is False:
                raise RuntimeError("AI Horde has no worker for this request")
            if check.get("done"):
                break
            if time.time() - start > limit:
                raise RuntimeError(f"AI Horde queue too slow ({int(time.time() - start)} s)")
        gens = (_call(f"/generate/status/{job}").get("generations") or [])
        if not gens or gens[0].get("censored"):
            raise RuntimeError("AI Horde returned no usable picture")
        img = str(gens[0].get("img") or "")
        data = _download(img) if img.startswith("http") else base64.b64decode(img)
        if len(data) < 10_000:
            raise RuntimeError("AI Horde picture is too small")
        return data
    except Exception:
        try:  # free the queue slot
            _call(f"/generate/status/{job}", method="DELETE")
        except Exception:
            pass
        raise
    finally:
        _SPENT[0] += time.time() - start
