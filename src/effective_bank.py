"""Canonical effective English story bank for every read-only consumer.

This adapter owns the batch-aware loader instead of trusting startup import hooks.
The old Instagram-only hook can therefore never hide mysteries_batch*.json from
YouTube, Instagram, or the regression suite.
"""
from __future__ import annotations

import json
from pathlib import Path
from src import mystery_short

ROOT = mystery_short.ROOT
BANK = mystery_short.BANK


def _read_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("stories") if isinstance(data, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError(f"story bank {path} must contain story objects")
    return rows


def load_bank(path: Path | None = None, strict: bool = False) -> list[dict]:
    chosen = BANK if path is None else Path(path)
    default = chosen.resolve() == BANK.resolve()
    rows = _read_rows(chosen)
    required: set[str] = set()
    if default:
        for batch in sorted((ROOT / "content").glob("mysteries_batch*.json")):
            batch_rows = _read_rows(batch)
            if not batch_rows:
                raise RuntimeError(f"empty story batch: {batch}")
            for row in batch_rows:
                sid = str(row.get("id") or "").strip()
                if not sid:
                    raise RuntimeError(f"story batch has missing id: {batch}")
                required.add(sid)
            rows.extend(batch_rows)
        rows = mystery_short.apply_overrides(rows)
    ids_seen = [str(row.get("id") or "").strip() for row in rows]
    if any(not sid for sid in ids_seen):
        raise RuntimeError("story bank contains a missing id")
    if len(ids_seen) != len(set(ids_seen)):
        raise RuntimeError("duplicate story ids across effective bank")
    good = []
    for row in rows:
        try:
            mystery_short.validate_story(row)
            good.append(row)
        except RuntimeError as exc:
            sid = str(row.get("id") or "")
            if strict or sid in required:
                raise RuntimeError(f"invalid required story {sid}: {exc}") from exc
            print(f"::warning title=Story skipped::{exc}", flush=True)
    missing = required - {str(row.get("id")) for row in good}
    if default and missing:
        raise RuntimeError(f"effective bank missing {len(missing)} batch stories: {', '.join(sorted(missing)[:20])}")
    if not good:
        raise RuntimeError("no valid stories in effective bank")
    return good


# Bind the production module to this implementation. This is intentionally done
# at import time so old src.__init__ wrappers and finder order cannot replace it.
mystery_short.load_bank = load_bank


def stories(strict: bool = False) -> list[dict]:
    return load_bank(strict=strict)


def by_id(strict: bool = False) -> dict[str, dict]:
    return {str(story["id"]): story for story in stories(strict=strict)}


def ids(strict: bool = False) -> set[str]:
    return set(by_id(strict=strict))
