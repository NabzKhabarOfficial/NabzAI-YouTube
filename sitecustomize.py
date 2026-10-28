"""Keep scheduling inputs valid and approved before any producer imports them."""
from __future__ import annotations

import atexit
import json
import sys
from pathlib import Path

from scripts.repair_story_notes import main as _repair_story_notes
from scripts.merge_story_notes import main as _merge_story_notes

_repair_story_notes()
_merge_story_notes()


def _merge_extra(base_path: Path, extra_path: Path) -> bytes:
    original = base_path.read_bytes()
    base = json.loads(original.decode("utf-8"))
    extra = json.loads(extra_path.read_text(encoding="utf-8"))
    base.setdefault("stories", {}).update(extra.get("stories") or {})
    base_path.write_text(json.dumps(base, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return original


# Instagram may stage several reviewed batches. They are visible only while the
# Instagram planner runs; YouTube never sees these temporary merges.
if sys.argv and sys.argv[0].endswith("ig_pack.py"):
    from scripts.prepare_ig_english_bank import ADD as _IG_ADD
    from scripts.prepare_ig_english_bank import BANK as _IG_BANK
    from scripts.prepare_ig_english_bank import main as _prepare_ig_bank

    _ig_original_bank = _IG_BANK.read_bytes()
    if _IG_ADD.exists():
        _prepare_ig_bank()

    _fa_bank = Path(__file__).resolve().parent / "content" / "mysteries_fa.json"
    _fa_add = Path(__file__).resolve().parent / "content" / "mysteries_fa_add_batch2.json"
    _notes = Path(__file__).resolve().parent / "content" / "story_notes_fa.json"
    _notes_add = Path(__file__).resolve().parent / "content" / "story_notes_fa_add_batch2.json"
    _fa_original = _merge_extra(_fa_bank, _fa_add) if _fa_add.exists() else None
    _notes_original = _merge_extra(_notes, _notes_add) if _notes_add.exists() else None

    def _restore_instagram_inputs() -> None:
        _IG_BANK.write_bytes(_ig_original_bank)
        if _fa_original is not None:
            _fa_bank.write_bytes(_fa_original)
        if _notes_original is not None:
            _notes.write_bytes(_notes_original)

    atexit.register(_restore_instagram_inputs)
