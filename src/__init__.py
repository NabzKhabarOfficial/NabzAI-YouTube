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

Sharp reel pictures (Oct 14 2026, owner: "the reels use low-quality pictures"): the Cloudflare
model of the normal chain (FLUX.1-schnell) only makes 1024x1024 squares; cut to 9:16 that is
576x1024, blown up ~1.9x to 1080x1920, which is the blur. Instagram pack pictures (the "pics"
folder of src.ig_pack) are now first asked from FLUX.2 [klein] 4B on the same Cloudflare account
and free daily neurons, drawn natively in portrait (768x1344, NABZ_KLEIN_W/H): newer model, no
crop, only a 1.4x scale. About 100-160 neurons a picture: 6 reels x 6 pictures a day plus the
daily Short stay under the free 10k. Any quota error or refusal switches it off for the run and
the normal chain takes over (never a lost reel). NABZ_KLEIN=0 switches it off.
"""
import base64
import importlib.abc
import importlib.machinery
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ADD = _ROOT / "content" / "mysteries_add.json"


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
_KLEIN = {"off": ""}
_KLEIN_OFF_WORDS = ("http 4", "429", "neuron", "quota", "no image", "not configured", "too small", "blank")


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


def _klein_image(m, prompt: str, seed: int):
    """One native portrait picture from FLUX.2 [klein] on Cloudflare Workers AI, or raises."""
    import hashlib
    import urllib.error
    account = os.getenv("CF_ACCOUNT_ID", "").strip()
    token = os.getenv("CF_API_TOKEN", "").strip()
    if not account or not token:
        raise RuntimeError("CF_ACCOUNT_ID / CF_API_TOKEN not configured")
    model = os.getenv("NABZ_CF_KLEIN_MODEL", "@cf/black-forest-labs/flux-2-klein-4b")
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
    raise RuntimeError(last or "FLUX.2 klein gave no picture")


def _patch_images(m) -> None:
    """Instagram reel pictures: hook picture (img_0.jpg) from Nano Banana first, every pack picture
    from FLUX.2 klein (native portrait) next, then the normal free chain (see module notes)."""
    import hashlib
    plain = m.generate_image

    def generate_image(prompt, seed, target):
        target = Path(target)
        nano = (target.name == "img_0.jpg" and not _NANO["dead"] and os.getenv("NABZ_NANO_BANANA", "1") != "0"
                and bool(_nano_keys()))
        klein = (target.parent.name == "pics" and not _KLEIN["off"] and os.getenv("NABZ_KLEIN", "1") != "0"
                 and bool(os.getenv("CF_API_TOKEN", "").strip()))
        if not nano and not klein:
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
                img = _klein_image(m, prompt, seed)
                m.cover(img).save(target, quality=95)
                marker.write_text(key)
                return f"cf-klein {img.size[0]}x{img.size[1]}"
            except Exception as exc:
                text = f"{type(exc).__name__}: {str(exc)[:220]}"
                if any(w in text.lower() for w in _KLEIN_OFF_WORDS):
                    _KLEIN["off"] = text  # quota or refusal: the normal chain for the rest of this run
                print(f"::warning title=Sharp reel pictures off::FLUX.2 klein not used ({text}); normal pictures",
                      flush=True)
        return plain(prompt, seed, target)

    m.generate_image = generate_image


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
            for patch in (_patch_bank, _patch_images):
                try:
                    patch(module)
                except Exception as exc:  # never break the import over an extra
                    print(f"::warning title=Extra not added::{patch.__name__}: {type(exc).__name__}: {exc}", flush=True)

        spec.loader.exec_module = exec_module
        return spec


if not any(isinstance(f, _BankAddFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _BankAddFinder())
