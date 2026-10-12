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
the same free GEMINI_API_KEY keys). Any failure (no free quota, refusal, bad picture) silently
falls back to the normal free chain; after a quota/permission error it is not asked again in
that run. NABZ_NANO_BANANA=0 switches it off.
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


def _nano_keys() -> list:
    keys = []
    for name in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"):
        k = os.getenv(name, "").strip()
        if k and k not in keys:
            keys.append(k)
    return keys


def _nano_image(m, prompt: str):
    """One picture from Nano Banana, or raises. Tries every free key."""
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


def _patch_images(m) -> None:
    """Hook picture (img_0.jpg) of the Instagram reel from Nano Banana first (see module notes)."""
    import hashlib
    plain = m.generate_image

    def generate_image(prompt, seed, target):
        target = Path(target)
        if (target.name != "img_0.jpg" or _NANO["dead"] or os.getenv("NABZ_NANO_BANANA", "1") == "0"
                or not _nano_keys()):
            return plain(prompt, seed, target)
        key = hashlib.sha1(f"{prompt}|{seed}".encode()).hexdigest()[:12]
        marker = target.with_suffix(".key")
        if target.exists() and marker.exists() and marker.read_text() == key:
            return "cache"
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
            print(f"[nano-banana] not used ({type(exc).__name__}: {str(exc)[:220]}); normal pictures", flush=True)
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
