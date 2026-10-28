"""Keep scheduling inputs valid and approved before any producer imports them."""
from __future__ import annotations

import atexit
import sys

from scripts.repair_story_notes import main as _repair_story_notes
from scripts.merge_story_notes import main as _merge_story_notes

_repair_story_notes()
_merge_story_notes()

# The Instagram planner owns content/mysteries_add.json, but the YouTube Short
# producer must not see those stories before their Persian package is ready.
# Merge only for the ig-pack process, then restore the checked-in bank when it
# exits. This keeps the existing YouTube path and its source bank untouched.
if "src.ig_pack" in sys.argv:
    from scripts.prepare_ig_english_bank import ADD as _IG_ADD
    from scripts.prepare_ig_english_bank import BANK as _IG_BANK
    from scripts.prepare_ig_english_bank import main as _prepare_ig_bank

    _ig_original_bank = _IG_BANK.read_bytes()
    if _IG_ADD.exists():
        _prepare_ig_bank()
        atexit.register(lambda: _IG_BANK.write_bytes(_ig_original_bank))
