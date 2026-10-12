"""Package setup.

Reel-only rescue: running the daily workflow with story_id "reel:<id>" rebuilds the
Persian Instagram reel of a Short that is ALREADY on YouTube, without uploading it
again and without touching the story state. Only allowed for the latest built story.

Extra English stories (Oct 12 2026): content/mysteries_add.json holds stories that are added to
the English bank (content/mysteries.json) without rewriting that big file. Whenever
src.mystery_short is imported (the Instagram pack does `from src import mystery_short`), its
load_bank() also returns these stories (same overrides and validation; an id already in the
bank wins). The daily Short, run as `python -m src.mystery_short`, keeps the plain bank.
"""
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
            try:
                _patch_bank(module)
            except Exception as exc:  # never break the import over the extra stories
                print(f"::warning title=Extra stories not added::{type(exc).__name__}: {exc}", flush=True)

        spec.loader.exec_module = exec_module
        return spec


if not any(isinstance(f, _BankAddFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _BankAddFinder())
