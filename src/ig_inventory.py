"""Read-only inventory calculation for unused, approved Instagram stories."""
from __future__ import annotations

import json
from pathlib import Path

# These Persian entries duplicate stories already published under their canonical IDs.
KNOWN_DUPLICATE_STORY_IDS = {"eilean-mor", "wow-signal-duplicate"}


def _json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"cannot read {path.name}: {exc}") from exc


def _mapping(path: Path) -> dict:
    data = _json(path, {})
    if not isinstance(data, dict):
        raise RuntimeError(f"{path.name} must contain a JSON object")
    rows = data.get("stories") or {}
    if not isinstance(rows, dict):
        raise RuntimeError(f"{path.name}: stories must be an object")
    return rows


def _english_ids(content: Path) -> set[str]:
    paths = [content / "mysteries.json"]
    add_path = content / "mysteries_add.json"
    if add_path.exists():
        paths.append(add_path)
    paths.extend(sorted(content.glob("mysteries_batch*.json")))
    found: set[str] = set()
    for path in paths:
        data = _json(path, None)
        rows = data if isinstance(data, list) else data.get("stories") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError(f"{path.name} must contain a story list")
        for row in rows:
            sid = str(row.get("id") or "").strip() if isinstance(row, dict) else ""
            if not sid:
                raise RuntimeError(f"{path.name} contains a story without an id")
            if sid in found:
                raise RuntimeError(f"duplicate English story id: {sid}")
            found.add(sid)
    return found


def available_story_ids(root: Path) -> list[str]:
    """Return stories with Persian text, approved notes, English scripts, and no prior reservation."""
    root = Path(root)
    content = root / "content"
    fa = _mapping(content / "mysteries_fa.json")
    fa.update(_mapping(content / "mysteries_fa_add.json"))
    approved = _mapping(content / "story_notes_fa.json")
    english = _english_ids(content)

    ig_state = _json(content / "ig_state.json", {})
    pack_state = _json(content / "ig_pack_state.json", {})
    used = set(ig_state.get("posted") or [])
    used.update(pack_state.get("retired") or [])
    for info in (pack_state.get("weeks") or {}).values():
        for item in info.get("plan") or []:
            if item.get("id"):
                used.add(item["id"])

    return sorted((set(fa) & set(approved) & english) - used - KNOWN_DUPLICATE_STORY_IDS)


def inventory_status(root: Path, reserve: int = 14) -> dict:
    ids = available_story_ids(root)
    return {"available": len(ids), "reserve": reserve, "low": len(ids) < reserve, "ids": ids}
