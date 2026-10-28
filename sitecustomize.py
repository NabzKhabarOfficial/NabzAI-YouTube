"""Keep scheduling inputs valid and approved before any producer imports them."""
from __future__ import annotations

import atexit
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
        print(f"IG BUFFER SAFETY: install skipped ({type(exc).__name__})", flush=True)


_install_buffer_safety()


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
