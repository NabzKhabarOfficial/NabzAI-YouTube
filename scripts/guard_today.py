"""Decide whether a run still has to build today's Short.

GitHub sometimes drops scheduled runs, so the workflow is started from several
places: its own backup crons, an external daily trigger (cron-job.org calling
workflow_dispatch) and manual rescue runs. Only the first one builds; any later
run sees today's date in content/published.json and skips.
A manual run with an explicit story_id builds even if today's Short is done.

No-repeat rule: a story that was already published (YouTube Short + Persian
reel) is never built again. A forced story_id that was already used is refused,
and when every story in the effective bank is used the run stops with an error
instead of recycling an old story.
Writes skip=true|false to $GITHUB_OUTPUT and never fails.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEHRAN = timezone(timedelta(hours=3, minutes=30))
ROOT = Path(__file__).resolve().parents[1]


def decide(event, state, now=None, forced=False):
    if forced:
        return False
    if event not in ("schedule", "workflow_dispatch"):
        return False
    today = (now or datetime.now(timezone.utc)).astimezone(TEHRAN).date().isoformat()
    return state.get("last_built_date") == today


def repeat_check(bank_ids, state, forced=""):
    """-> problem text, or "" when the next story is new."""
    used = set(state.get("mysteries", []))
    if forced:
        if forced in used:
            return f"story '{forced}' was already published; not repeating it"
        return ""
    if bank_ids and not [s for s in bank_ids if s not in used]:
        return "every story in the effective bank is already published; add new stories (no repeats)"
    return ""


def forced_story():
    try:
        payload = json.loads(Path(os.getenv("GITHUB_EVENT_PATH", "")).read_text(encoding="utf-8"))
        return str((payload.get("inputs") or {}).get("story_id") or "").strip()
    except Exception:
        return ""


def _rows(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data if isinstance(data, list) else data.get("stories", []) if isinstance(data, dict) else []
    return rows if isinstance(rows, list) else []


def bank_ids():
    """Return IDs from the exact effective English bank population.

    mystery_short.load_bank() loads mysteries.json plus mysteries_batch*.json.
    The guard must use the same population or it can stop/recycle while unused
    batch stories remain available.
    """
    paths = [ROOT / "content" / "mysteries.json"]
    paths.extend(sorted((ROOT / "content").glob("mysteries_batch*.json")))
    ids = []
    for path in paths:
        for story in _rows(path):
            if isinstance(story, dict) and story.get("id"):
                ids.append(str(story["id"]))
    return list(dict.fromkeys(ids))


def main():
    try:
        state = json.loads((ROOT / "content" / "published.json").read_text(encoding="utf-8"))
    except Exception:
        state = {}
    forced = forced_story()
    try:
        skip = decide(os.getenv("GITHUB_EVENT_NAME", ""), state, forced=bool(forced))
    except Exception as exc:
        print(f"guard error, building anyway: {exc}")
        skip = False
    if skip:
        print("Today's Short already built, skipping this run.")
    else:
        problem = repeat_check(bank_ids(), state, forced)
        if problem:
            skip = True
            print(f"::error title=No repeat::{problem}")
        else:
            print("Building today's Short.")
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"skip={'true' if skip else 'false'}\n")


if __name__ == "__main__":
    main()
