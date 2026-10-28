"""Validate Instagram story batches before they can touch runtime banks."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH_GLOB = "content/mysteries_batch*.json"
GENERIC_TITLES = {"تاریخی", "جنایی", "فولکلور", "یوفو", "ناهنجاری"}


def validate_row(row: dict, source: Path) -> None:
    sid = row.get("id", "<missing>")
    beats = row.get("beats")
    fa = row.get("fa")
    notes = row.get("notes")
    if not isinstance(beats, list) or len(beats) != 6:
        raise ValueError(f"{source}:{sid}: expected 6 English beats")
    if not isinstance(fa, dict) or not isinstance(fa.get("beats"), list) or len(fa["beats"]) != 6:
        raise ValueError(f"{source}:{sid}: expected 6 Persian beats")
    if not isinstance(fa.get("title"), str) or not fa["title"].strip() or fa["title"].strip() in GENERIC_TITLES:
        raise ValueError(f"{source}:{sid}: invalid Persian title")
    if not isinstance(fa.get("question"), str) or not fa["question"].strip():
        raise ValueError(f"{source}:{sid}: missing Persian question")
    if not isinstance(fa.get("tags"), list) or not fa["tags"]:
        raise ValueError(f"{source}:{sid}: missing Persian tags")
    if not isinstance(notes, dict) or set(notes) != {"proven", "probable", "unknown"}:
        raise ValueError(f"{source}:{sid}: notes must be proven/probable/unknown")
    words = sum(len(str(b.get("text", "")).split()) for b in beats)
    if words < 50 or words > 95:
        raise ValueError(f"{source}:{sid}: English word count {words}, expected 50-95")
    if len(str(beats[0].get("text", "")).split()) > 14:
        raise ValueError(f"{source}:{sid}: hook exceeds 14 words")
    for index, beat in enumerate(beats, 1):
        if not str(beat.get("text", "")).strip() or not str(beat.get("visual", "")).strip():
            raise ValueError(f"{source}:{sid}: empty English beat/visual {index}")
        visual = str(beat["visual"]).lower()
        if "placeholder" in visual or "illustration, beat" in visual:
            raise ValueError(f"{source}:{sid}: placeholder visual {index}")
    if any(not str(text).strip() for text in fa["beats"]):
        raise ValueError(f"{source}:{sid}: empty Persian beat")


def main() -> int:
    files = sorted(ROOT.glob(BATCH_GLOB))
    if len(files) != 10:
        raise ValueError(
            f"expected exactly 10 story batch files, found {len(files)}"
        )
    all_ids: set[str] = set()
    for path in files:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or len(rows) != 15:
            raise ValueError(f"{path}: expected exactly 15 stories")
        for row in rows:
            sid = row.get("id")
            if not sid or sid in all_ids:
                raise ValueError(f"{path}: duplicate or missing id {sid!r}")
            all_ids.add(sid)
            validate_row(row, path)
    if len(all_ids) != 150:
        raise ValueError(
            f"expected exactly 150 stories, found {len(all_ids)}"
        )
    print(f"Instagram batches valid: {len(files)} files, {len(all_ids)} stories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
