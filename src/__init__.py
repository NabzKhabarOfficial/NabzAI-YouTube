"""Package setup.

Reel-only rescue: running the daily workflow with story_id "reel:<id>" rebuilds the
Persian Instagram reel of a Short that is ALREADY on YouTube, without uploading it
again and without touching the story state. Only allowed for the latest built story.

Extra English stories (Oct 12 2026): content/mysteries_add.json holds stories that are added to
the English bank (content/mysteries.json) without rewriting that big file. Whenever
src.mystery_short is imported (the Instagram pack does `from src import mystery_short`), its
load_bank() also returns these stories (same overrides and validation; an id already in the
bank wins). The daily Short, run as `python -m src.mystery_short`, keeps the plain bank.

Hook picture (Oct 12 2026, owner): the FIRST picture of every Instagram reel (img_0.jpg, the
moment viewers decide to stay or swipe) is first asked from Nano Banana (Gemini image model,
the same free GEMINI_API_KEY; ONE key only, owner rule Oct 14). Any failure (no free quota,
refusal, bad picture) silently falls back to the normal free chain; after a quota/permission
error it is not asked again in that run. NABZ_NANO_BANANA=0 switches it off.

Sharp reel & Short pictures (Oct 14-15 2026, owner: "the reels use low-quality pictures" + "add
more high-quality free alternatives so the project runs nonstop"):
  1. Multi-Space HuggingFace ZeroGPU pool: NABZ_FLUX_SPACES defaults to multiple public FLUX.1
     portrait (768x1344) Spaces (`black-forest-labs/FLUX.1-schnell,multimodalart/FLUX.1-merged`)
     so if one Space's queue or ZeroGPU quota is busy, the next Space serves native 9:16 portrait.
  2. Cloudflare native portrait chain (`_cf_portrait_image`): tries FLUX.2 [klein] 4B first
     (`@cf/black-forest-labs/flux-2-klein-4b`), then FLUX.2 [klein] 9B
     (`@cf/black-forest-labs/flux-2-klein-9b`), at native 768x1344 portrait on the same free
     10,000 daily neurons.
  3. Zero-neuron Cloudflare portrait fallback (`_sdxl_lightning_image`): when daily Cloudflare
     neurons are exhausted, `@cf/bytedance/stable-diffusion-xl-lightning` (priced at $0.00/step
     in Beta) renders native 768x1344 portrait before falling back to square models or slow
     volunteer queues.
  4. Multi-model Gemini TTS failover (`_patch_tts`): when `gemini-3.8-flash-tts` hits its daily
     free-tier RPD (10/day), `src.gemini_tts.request` automatically fails over to the sibling
     free-tier TTS models (`gemini-3.8-flash-lite-tts`, `gemini-2.5-flash-preview-tts`,
     `gemini-3.1-flash-tts-preview`) on the same single `GEMINI_API_KEY`, multiplying daily
     narrator capacity ~3-4x with the exact same Algenib voice and style.
"""
import base64
import importlib.abc
import importlib.machinery
import json
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ADD = _ROOT / "content" / "mysteries_add.json"

# Default multi-Space ZeroGPU pool so native 768x1344 portrait has automatic HF failover
os.environ.setdefault("NABZ_FLUX_SPACES", "black-forest-labs/FLUX.1-schnell,multimodalart/FLUX.1-merged")


def _reel_only() -> None:
    if "pytest" in sys.modules:
        return
    raw = os.getenv("NABZ_MYSTERY_ID", "").strip()
    if not raw:
        try:
            event = json.loads(Path(os.getenv("GITHUB_EVENT_PATH", "")).read_text(encoding="utf-8"))
            raw = str((event.get("inputs") or {}).get("story_id") or "").strip()
        except Exception:
            return
    if not raw.lower().startswith("reel:"):
        return
    rid = raw.split(":", 1)[1].strip()
    try:
        state = json.loads((_ROOT / "content" / "published.json").read_text(encoding="utf-8"))
        latest = (state.get("mysteries") or [""])[-1]
    except Exception:
        latest = ""
    if not rid or rid != latest:
        print(f"::error title=Reel-only refused::{rid!r} is not the latest built story ({latest!r})", flush=True)
        return
    os.environ.update({"NABZ_REEL_ONLY": "1", "NABZ_MYSTERY_ID": rid,
                       "NABZ_PRECHECK_YOUTUBE": "0", "NABZ_RECORD_STORY": "0"})
    print(f"REEL-ONLY RUN for {rid}: Persian reel only, no YouTube upload, state unchanged.", flush=True)


_reel_only()


def _patch_bank(m) -> None:
    """Give src.mystery_short.load_bank the extra stories of content/mysteries_add.json."""
    plain = m.load_bank

    def load_bank(path=m.BANK, strict=False):
        if path != m.BANK:
            return plain(path, strict)
        try:
            extra = json.loads(_ADD.read_text(encoding="utf-8")).get("stories") or []
        except Exception:
            extra = []
        if not extra:
            return plain(path, strict)
        data = json.loads(m.BANK.read_text(encoding="utf-8"))
        stories = list(data["stories"])
        have = {s.get("id") for s in stories}
        stories += [s for s in extra if isinstance(s, dict) and s.get("id") and s["id"] not in have]
        stories = m.apply_overrides(stories)
        good = []
        for s in stories:
            try:
                m.validate_story(s)
                good.append(s)
            except RuntimeError as exc:
                if strict:
                    raise
                print(f"::warning title=Story skipped::{exc}", flush=True)
        if not good:
            raise RuntimeError("no valid stories in the bank")
        return good

    m.load_bank = load_bank


_NANO = {"dead": False}
_NANO_DEAD_WORDS = ("429", "quota", "resource_exhausted", "403", "permission", "billing", "limit: 0",
                    "not found", "404", "free tier")
_KLEIN_MODELS = (
    "@cf/black-forest-labs/flux-2-klein-4b",
    "@cf/black-forest-labs/flux-2-klein-9b",
)
_KLEIN_DEAD: set[str] = set()
_KLEIN_OFF_WORDS = ("http 4", "429", "neuron", "quota", "no image", "not configured", "too small", "blank")
_SDXL_DEAD = {"off": False}


def _nano_keys() -> list:
    """Only GEMINI_API_KEY (owner rule: one key, never extra keys to dodge the free quota)."""
    k = os.getenv("GEMINI_API_KEY", "").strip()
    return [k] if k else []


def _nano_image(m, prompt: str):
    """One picture from Nano Banana, or raises."""
    import urllib.error
    model = os.getenv("NABZ_NANO_MODEL", "gemini-2.5-flash-image")
    errors = []
    for key in _nano_keys():
        for with_ratio in (True, False):
            cfg = {"responseModalities": ["IMAGE"]}
            if with_ratio:
                cfg["imageConfig"] = {"aspectRatio": "9:16"}
            body = json.dumps({"contents": [{"parts": [{"text": prompt[:1800]}]}],
                               "generationConfig": cfg}).encode()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                raw = m._http(url, data=body, timeout=120,
                              headers={"x-goog-api-key": key, "Content-Type": "application/json"})
            except urllib.error.HTTPError as exc:
                detail = exc.read()[:300].decode("utf-8", "ignore")
                errors.append(f"HTTP {exc.code}: {detail}")
                if exc.code == 400 and with_ratio:
                    continue  # maybe the ratio option is not known: once more without it
                break
            data = json.loads(raw)
            for cand in data.get("candidates") or []:
                for part in ((cand.get("content") or {}).get("parts") or []):
                    inline = part.get("inlineData") or part.get("inline_data") or {}
                    if inline.get("data"):
                        return m._valid_image(base64.b64decode(inline["data"]))
            errors.append(f"no image in reply: {str(data)[:160]}")
            break
    raise RuntimeError(" | ".join(errors) or "no GEMINI_API_KEY")


def _klein_single(m, model: str, prompt: str, seed: int):
    """One native portrait picture from a FLUX.2 [klein] model on Cloudflare Workers AI."""
    import hashlib
    import urllib.error
    account = os.getenv("CF_ACCOUNT_ID", "").strip()
    token = os.getenv("CF_API_TOKEN", "").strip()
    if not account or not token:
        raise RuntimeError("CF_ACCOUNT_ID / CF_API_TOKEN not configured")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
    width = int(os.getenv("NABZ_KLEIN_W", "768"))
    height = int(os.getenv("NABZ_KLEIN_H", "1344"))
    last = ""
    for with_seed in (True, False):  # a refused seed field gets one more try without it
        fields = {"prompt": prompt[:2000], "width": str(width), "height": str(height)}
        if with_seed:
            fields["seed"] = str(int(seed) % 2147483647)
        boundary = "nabz" + hashlib.sha1(repr(fields).encode()).hexdigest()[:24]
        body = b""
        for name, value in fields.items():
            head = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            body += head.encode() + value.encode("utf-8") + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        try:
            raw = m._http(url, data=body, timeout=180, headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}"})
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}: {exc.read()[:300].decode('utf-8', 'ignore')}"
            if exc.code == 400 and with_seed:
                continue
            raise RuntimeError(last) from None
        if raw[:3] == b"\xff\xd8\xff" or raw[:4] == b"\x89PNG" or raw[:4] == b"RIFF":
            return m._valid_image(raw)
        data = json.loads(raw)
        result = data.get("result") if isinstance(data, dict) else None
        image = result.get("image") if isinstance(result, dict) else None
        if image:
            return m._valid_image(base64.b64decode(image))
        last = f"no image in reply: {str(data)[:160]}"
        break
    raise RuntimeError(last or f"{model} gave no picture")


def _klein_image(m, prompt: str, seed: int):
    """Try FLUX.2 klein 4B then 9B on Cloudflare Workers AI at native 768x1344 portrait."""
    custom = os.getenv("NABZ_CF_KLEIN_MODEL", "").strip()
    candidates = [custom] if custom else list(_KLEIN_MODELS)
    errors = []
    for model in candidates:
        if model in _KLEIN_DEAD:
            continue
        try:
            return _klein_single(m, model, prompt, seed), model.split("/")[-1]
        except Exception as exc:
            text = f"{model}: {type(exc).__name__}: {str(exc)[:200]}"
            errors.append(text)
            low = text.lower()
            if any(w in low for w in ("neuron", "daily", "quota", "429")):
                # Account-wide neuron limit: mark all neuron-billed Klein models off for this run
                _KLEIN_DEAD.update(candidates)
                break
            if any(w in low for w in _KLEIN_OFF_WORDS):
                _KLEIN_DEAD.add(model)
    raise RuntimeError(" | ".join(errors) or "FLUX.2 klein unavailable")


def _sdxl_lightning_image(m, prompt: str, seed: int):
    """Zero-neuron ($0.00/step Beta) native portrait fallback on Cloudflare Workers AI."""
    import urllib.error
    account = os.getenv("CF_ACCOUNT_ID", "").strip()
    token = os.getenv("CF_API_TOKEN", "").strip()
    if not account or not token:
        raise RuntimeError("CF_ACCOUNT_ID / CF_API_TOKEN not configured")
    model = "@cf/bytedance/stable-diffusion-xl-lightning"
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
    width = int(os.getenv("NABZ_KLEIN_W", "768"))
    height = int(os.getenv("NABZ_KLEIN_H", "1344"))
    body = json.dumps({
        "prompt": prompt[:1800],
        "negative_prompt": "text, letters, watermark, logo, signature, blurry, deformed, low quality, cartoon",
        "width": width,
        "height": height,
        "num_steps": 8,
        "guidance": 6.0,
        "seed": int(seed) % 2147483647,
    }).encode()
    try:
        raw = m._http(url, data=body, timeout=180, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"})
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read()[:240].decode('utf-8', 'ignore')}") from None
    if raw[:3] == b"\xff\xd8\xff" or raw[:4] == b"\x89PNG" or raw[:4] == b"RIFF":
        return m._valid_image(raw)
    data = json.loads(raw)
    image = (data.get("result") or {}).get("image") if isinstance(data, dict) else None
    if image:
        return m._valid_image(base64.b64decode(image))
    raise RuntimeError(f"SDXL-Lightning gave no picture: {str(data)[:160]}")


def _patch_images(m) -> None:
    """Instagram reel & Short pictures:
    - Hook picture (img_0.jpg) tries Nano Banana first;
    - Instagram pack pictures try FLUX.2 klein (4B -> 9B) native portrait first, then SDXL-Lightning
      portrait ($0/step), then the normal free chain (multi-Space HF ZeroGPU -> CF -> Pollinations -> HF -> Horde);
    - Daily Short uses the normal chain, upgraded so its 'cloudflare' step also tries native portrait
      FLUX.2 klein / SDXL-Lightning before square FLUX.1-schnell."""
    import hashlib
    plain = m.generate_image
    orig_cf = getattr(m, "_cloudflare", None)

    if callable(orig_cf):
        def upgraded_cf(prompt: str, seed: int):
            if len(_KLEIN_DEAD) < len(_KLEIN_MODELS) and os.getenv("NABZ_KLEIN", "1") != "0":
                try:
                    img, _ = _klein_image(m, prompt, seed)
                    return img
                except Exception:
                    pass
            try:
                return orig_cf(prompt, seed)
            except Exception as first_exc:
                if not _SDXL_DEAD["off"]:
                    try:
                        return _sdxl_lightning_image(m, prompt, seed)
                    except Exception:
                        _SDXL_DEAD["off"] = True
                raise first_exc

        m._cloudflare = upgraded_cf

    def generate_image(prompt, seed, target):
        target = Path(target)
        nano = (target.name == "img_0.jpg" and not _NANO["dead"] and os.getenv("NABZ_NANO_BANANA", "1") != "0"
                and bool(_nano_keys()))
        klein = (target.parent.name == "pics" and len(_KLEIN_DEAD) < len(_KLEIN_MODELS)
                 and os.getenv("NABZ_KLEIN", "1") != "0" and bool(os.getenv("CF_API_TOKEN", "").strip()))
        sdxl = (target.parent.name == "pics" and not _SDXL_DEAD["off"]
                and bool(os.getenv("CF_API_TOKEN", "").strip()))
        if not nano and not klein and not sdxl:
            return plain(prompt, seed, target)
        key = hashlib.sha1(f"{prompt}|{seed}".encode()).hexdigest()[:12]
        marker = target.with_suffix(".key")
        if target.exists() and marker.exists() and marker.read_text() == key:
            return "cache"
        if nano:
            try:
                img = _nano_image(m, prompt)
                m.cover(img).save(target, quality=93)
                marker.write_text(key)
                print("[nano-banana] hook picture made", flush=True)
                return "nanobanana"
            except Exception as exc:
                low = str(exc).lower()
                if any(w in low for w in _NANO_DEAD_WORDS):
                    _NANO["dead"] = True
                print(f"[nano-banana] not used ({type(exc).__name__}: {str(exc)[:220]})", flush=True)
        if klein:
            try:
                img, tag = _klein_image(m, prompt, seed)
                m.cover(img).save(target, quality=95)
                marker.write_text(key)
                return f"cf-{tag} {img.size[0]}x{img.size[1]}"
            except Exception as exc:
                text = f"{type(exc).__name__}: {str(exc)[:220]}"
                print(f"::warning title=Sharp reel pictures fallback::FLUX.2 klein not used ({text}); trying next portrait provider",
                      flush=True)
        if sdxl and len(_KLEIN_DEAD) >= len(_KLEIN_MODELS):
            try:
                img = _sdxl_lightning_image(m, prompt, seed)
                m.cover(img).save(target, quality=94)
                marker.write_text(key)
                return f"cf-sdxl-lightning {img.size[0]}x{img.size[1]}"
            except Exception as exc:
                _SDXL_DEAD["off"] = True
                print(f"[sdxl-lightning] not used ({type(exc).__name__}: {str(exc)[:200]})", flush=True)
        return plain(prompt, seed, target)

    m.generate_image = generate_image


_TTS_MODELS = (
    "gemini-3.8-flash-tts",
    "gemini-3.8-flash-lite-tts",
    "gemini-2.5-flash-preview-tts",
    "gemini-3.1-flash-tts-preview",
)
_DEAD_TTS_MODELS: set[str] = set()


def _patch_tts(_m=None) -> None:
    """Multi-model Gemini TTS failover on the same single GEMINI_API_KEY:
    Each Gemini TTS model has its own per-model daily free quota in Google AI Studio. When the
    primary model (`gemini-3.8-flash-tts`) exhausts its daily RPD, `gemini_tts.request` seamlessly
    switches to `gemini-3.8-flash-lite-tts` and `gemini-2.5-flash-preview-tts` with the exact same
    Algenib voice and style before marking the key dead."""
    from src import gemini_tts as g
    if getattr(g, "_multi_model_patched", False):
        return
    orig_request = g.request

    def multi_model_request(text: str, style: str = g.STYLE, voice: str = g.VOICE, model: str = g.MODEL):
        # 1) Check cache across all candidate TTS models first so any earlier cached take is reused free
        for cand_m in (model, *[x for x in _TTS_MODELS if x != model]):
            hit = g._cache_get(g._cache_key(text, style, voice, cand_m))
            if hit:
                g.STATS["cache_hits"] = int(g.STATS.get("cache_hits", 0)) + 1
                return hit
        # 2) Try each live TTS model in order; revive g._DEAD between models because daily RPD is per-model
        order = [model] + [x for x in _TTS_MODELS if x != model]
        last_exc = None
        for cand_m in order:
            if cand_m in _DEAD_TTS_MODELS:
                continue
            g._DEAD.clear()
            try:
                audio, mime = orig_request(text, style, voice, cand_m)
                if cand_m != model:
                    print(f"[gemini-tts] synthesized via fallback free model {cand_m} (voice {voice})", flush=True)
                return audio, mime
            except Exception as exc:
                last_exc = exc
                low = str(exc).lower()
                if "out of quota" in low or "daily" in low or "404" in low or "not found" in low or "400" in low:
                    _DEAD_TTS_MODELS.add(cand_m)
                    print(f"[gemini-tts] model {cand_m} unavailable/exhausted ({exc}); trying next free TTS model",
                          flush=True)
                    continue
                break
        if len(_DEAD_TTS_MODELS) >= len(order) and g.KEYS:
            g._DEAD.update(range(len(g.KEYS)))
        raise last_exc or RuntimeError("all free Gemini TTS models are out of quota for today")

    g.request = multi_model_request
    g._multi_model_patched = True


class _BankAddFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name != "src.mystery_short":
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
            return spec
        run = spec.loader.exec_module

        def exec_module(module, _run=run):
            _run(module)
            for patch in (_patch_bank, _patch_images, _patch_tts):
                try:
                    patch(module)
                except Exception as exc:  # never break the import over an extra
                    print(f"::warning title=Extra not added::{patch.__name__}: {type(exc).__name__}: {exc}", flush=True)

        spec.loader.exec_module = exec_module
        return spec


if not any(isinstance(f, _BankAddFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _BankAddFinder())
