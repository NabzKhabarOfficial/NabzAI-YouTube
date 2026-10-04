"""Decide whether a run still has to build today's Short.

GitHub sometimes drops scheduled runs, so the workflow is started from several
places: its own backup crons, an external daily trigger (cron-job.org calling
workflow_dispatch) and manual rescue runs. Only the first one builds; any later
run sees today's date in content/published.json and skips.
A manual run with an explicit story_id always builds (deliberate override).
Writes skip=true|false to $GITHUB_OUTPUT and never fails.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEHRAN = timezone(timedelta(hours=3, minutes=30))


def decide(event, state, now=None, forced=False):
    if forced:
        return False
    if event not in ("schedule", "workflow_dispatch"):
        return False
    today = (now or datetime.now(timezone.utc)).astimezone(TEHRAN).date().isoformat()
    return state.get("last_built_date") == today


def forced_story():
    try:
        payload = json.loads(Path(os.getenv("GITHUB_EVENT_PATH", "")).read_text(encoding="utf-8"))
        return str((payload.get("inputs") or {}).get("story_id") or "").strip()
    except Exception:
        return ""


def main():
    try:
        state = json.loads(Path("content/published.json").read_text(encoding="utf-8"))
    except Exception:
        state = {}
    try:
        skip = decide(os.getenv("GITHUB_EVENT_NAME", ""), state, forced=bool(forced_story()))
    except Exception as exc:
        print(f"guard error, building anyway: {exc}")
        skip = False
    print("Today's Short already built, skipping this run." if skip else "Building today's Short.")
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"skip={'true' if skip else 'false'}\n")


if __name__ == "__main__":
    main()
