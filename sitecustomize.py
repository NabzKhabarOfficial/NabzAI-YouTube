"""Keep scheduling inputs valid and approved before any producer imports them."""
from __future__ import annotations

import atexit
import builtins
import importlib
import importlib.abc
import importlib.machinery
import json
import sys
from pathlib import Path

from scripts.repair_story_notes import main as _repair_story_notes
from scripts.merge_story_notes import main as _merge_story_notes
from scripts.validate_ig_batches import validate_row

_repair_story_notes()
_merge_story_notes()


def _install_buffer_safety() -> None:
    try:
        from src import ig_buffer
        from src.ig_runtime_safety import install
        install(ig_buffer)
    except Exception as exc:
        print(f"IG BUFFER SAFETY: install skipped ({type(exc).__name__}: {exc})", flush=True)


_install_buffer_safety()


def _remove_stale_bank_finder_for_tests() -> None:
    """Do not let the Instagram-only add-bank hook replace load_bank in tests."""
    if sys.argv and sys.argv[0].endswith("ig_pack.py"):
        return
    sys.meta_path[:] = [finder for finder in sys.meta_path if type(finder).__name__ != "_BankAddFinder"]


_remove_stale_bank_finder_for_tests()


def _merge_staged_batches() -> list[tuple[Path, bytes]]:
    root = Path(__file__).resolve().parent
    originals: list[tuple[Path, bytes]] = []
    batch_files = sorted((root / "content").glob("mysteries_batch*.json"))
    if not batch_files:
        return originals
    en_bank = root / "content" / "mysteries.json"
    fa_bank = root / "content" / "mysteries_fa.json"
    notes_bank = root / "content" / "story_notes_fa.json"
    en_data = json.loads(en_bank.read_text(encoding="utf-8"))
    fa_data = json.loads(fa_bank.read_text(encoding="utf-8"))
    notes_data = json.loads(notes_bank.read_text(encoding="utf-8"))
    existing = {row["id"] for row in en_data.get("stories", [])}
    seen: set[str] = set()
    staged: list[dict] = []
    for path in batch_files:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or len(rows) != 15:
            raise ValueError(f"{path}: expected exactly 15 stories")
        for row in rows:
            validate_row(row, path)
            sid = row["id"]
            if sid in seen:
                raise ValueError(f"duplicate staged story id: {sid}")
            seen.add(sid)
            if sid in existing:
                raise ValueError(f"staged story already exists in English bank: {sid}")
            staged.append(row)
    for row in staged:
        sid = row["id"]
        en_data["stories"].append({"id": sid, "title": row["title"], "tags": row["tags"], "beats": row["beats"]})
        fa_data.setdefault("stories", {})[sid] = row["fa"]
        notes_data.setdefault("stories", {})[sid] = row["notes"]
    for path in (en_bank, fa_bank, notes_bank):
        originals.append((path, path.read_bytes()))
    en_bank.write_text(json.dumps(en_data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    fa_bank.write_text(json.dumps(fa_data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    notes_bank.write_text(json.dumps(notes_data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return originals


if sys.argv and sys.argv[0].endswith("ig_pack.py"):
    _staged_originals = _merge_staged_batches()

    def _restore_staged_batches() -> None:
        for path, content in _staged_originals:
            path.write_bytes(content)

    atexit.register(_restore_staged_batches)


_original_import = builtins.__import__


def _effective_consumer_import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _original_import(name, globals, locals, fromlist, level)
    if name in {"src.yt_comment", "src.yt_stats"}:
        try:
            import src.effective_bank as _bank
            if name == "src.yt_comment":
                target = module

                def _find_story(title, bank_path=None):
                    want = target._norm(target.re.sub(r"#\w+", "", title))
                    for story in _bank.stories():
                        if target._norm(story.get("title")) == want:
                            out = dict(story)
                            try:
                                extra = _bank.mystery_short.OVERRIDE
                                overrides = _bank.mystery_short.apply_overrides([out], extra)
                                out = overrides[0] if overrides else out
                            except Exception:
                                pass
                            return out
                    return None

                target.find_story = _find_story
        except Exception as exc:
            print(f"EFFECTIVE BANK: consumer patch skipped ({type(exc).__name__}: {exc})", flush=True)
    return module


builtins.__import__ = _effective_consumer_import


class _BatchSafeFinder(importlib.abc.MetaPathFinder):
    """Load mystery_short normally, then keep only non-bank production patches."""

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
                import src as package
                for patch_name in ("_patch_images", "_patch_tts"):
                    patch = getattr(package, patch_name, None)
                    if callable(patch):
                        patch(module)
            except Exception as exc:
                print(f"::warning title=Production patch skipped::{type(exc).__name__}: {exc}", flush=True)

        spec.loader.exec_module = exec_module
        return spec


if not any(isinstance(f, _BatchSafeFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _BatchSafeFinder())


def _reload_canonical_story_loader() -> None:
    """Fix startup ordering: buffer safety may import mystery_short before this finder."""
    sys.meta_path[:] = [finder for finder in sys.meta_path if type(finder).__name__ != "_BankAddFinder"]
    module = sys.modules.get("src.mystery_short")
    if module is not None:
        try:
            importlib.reload(module)
        except Exception as exc:
            print(f"EFFECTIVE BANK: canonical loader reload skipped ({type(exc).__name__}: {exc})", flush=True)


def _bind_canonical_batch_loader() -> None:
    """Bind the real batch-aware implementation, independent of import-hook order."""
    module = sys.modules.get("src.mystery_short")
    if module is None:
        return
    canonical = module.load_bank
    root = module.ROOT
    bank = module.BANK
    read_rows = module._read_story_rows
    apply = module.apply_overrides
    validate = module.validate_story

    def load_bank(path=None, strict=False):
        chosen = bank if path is None else Path(path)
        default = chosen.resolve() == bank.resolve()
        stories = read_rows(chosen)
        batch_ids = set()
        if default:
            for batch_path in sorted((root / "content").glob("mysteries_batch*.json")):
                rows = read_rows(batch_path)
                if not rows:
                    raise RuntimeError(f"story batch is empty: {batch_path}")
                for row in rows:
                    sid = str(row.get("id") or "").strip()
                    if not sid:
                        raise RuntimeError(f"story batch has a story without id: {batch_path}")
                    batch_ids.add(sid)
                stories.extend(rows)
            stories = apply(stories)
        ids = [str(s.get("id") or "").strip() for s in stories]
        if any(not sid for sid in ids):
            raise RuntimeError("story bank contains a missing id")
        if len(ids) != len(set(ids)):
            raise RuntimeError("duplicate story ids across the effective bank")
        good = []
        for story in stories:
            try:
                validate(story)
                good.append(story)
            except RuntimeError as exc:
                sid = str(story.get("id") or "")
                if strict or sid in batch_ids:
                    raise RuntimeError(f"invalid required story {sid}: {exc}") from exc
                print(f"::warning title=Story skipped::{exc}", flush=True)
        if not good:
            raise RuntimeError("no valid stories in the bank")
        missing = batch_ids - {str(s.get("id")) for s in good}
        if default and missing:
            raise RuntimeError(f"runtime bank is missing {len(missing)} required batch stories: " + ", ".join(sorted(missing)[:20]))
        return good

    module.load_bank = load_bank


_reload_canonical_story_loader()
_bind_canonical_batch_loader()
