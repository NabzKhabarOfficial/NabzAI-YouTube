"""Canonical effective English story bank for every read-only consumer.

The production loader remains in mystery_short.load_bank(). This tiny adapter
keeps review, comments, stats and future tools from reading mysteries.json
alone and silently missing staged batch stories.
"""
from __future__ import annotations
from pathlib import Path
from src import mystery_short


def stories(strict: bool = False) -> list[dict]:
    return mystery_short.load_bank(strict=strict)


def by_id(strict: bool = False) -> dict[str, dict]:
    return {str(story["id"]): story for story in stories(strict=strict)}


def ids(strict: bool = False) -> set[str]:
    return set(by_id(strict=strict))
