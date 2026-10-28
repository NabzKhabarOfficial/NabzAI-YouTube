"""Keep scheduling inputs valid and approved before any producer imports them."""
from __future__ import annotations

from scripts.repair_story_notes import main as _repair_story_notes
from scripts.merge_story_notes import main as _merge_story_notes

_repair_story_notes()
_merge_story_notes()
