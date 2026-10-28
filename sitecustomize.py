"""Keep the scheduling input valid before any producer imports it."""
from __future__ import annotations

try:
    from scripts.repair_story_notes import main as _repair_story_notes
    _repair_story_notes()
except Exception as exc:
    # Do not hide the defect: the scheduler must fail rather than publish bad data.
    print(f"STORY NOTES INVALID: {type(exc).__name__}: {exc}", flush=True)
