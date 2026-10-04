"""Decide whether a scheduled run still has to build today's Short.

GitHub sometimes drops scheduled runs, so the workflow has several daily
crons. Only the first one that fires builds; the others see today's date in
content/published.json and skip. Manual runs always build.
Writes skip=true|false to $GITHUB_OUTPUT and never fails.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEHRAN = timezone(timedelta(hours=3, minutes=30))


def decide(event, state, now=None):
    if event != "schedule":
        return False
    today = (now or datetime.now(timezone.utc)).astimezone(TEHRAN).date().isoformat()
    return state.get("last_built_date") == today


def main():
    try:
        state = json.loads(Path("content/published.json").read_text(encoding="utf-8"))
    except Exception:
        state = {}
    try:
        skip = decide(os.getenv("GITHUB_EVENT_NAME", ""), state)
    except Exception as exc:
        print(f"guard error, building anyway: {exc}")
        skip = False
    print("Today's Short already built, skipping this backup run." if skip else "Building today's Short.")
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"skip={'true' if skip else 'false'}\n")


if __name__ == "__main__":
    main()
