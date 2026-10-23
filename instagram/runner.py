"""Validate and select the two-month Story calendar without publishing by default."""
from __future__ import annotations
import argparse, json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .content import build_caption, validate_caption
from .dedupe import content_key

ROOT = Path(__file__).parent
CALENDAR = ROOT / "story_calendar.json"
TEHRAN = ZoneInfo("Asia/Tehran")


def _fail(message: str) -> None:
    raise ValueError(f"Instagram calendar invalid: {message}")


def load_calendar():
    data = json.loads(CALENDAR.read_text(encoding="utf-8"))
    start = date.fromisoformat(data["start_date"])
    end = date.fromisoformat(data["end_date"])
    days = int(data["days"])
    if days < 1 or days > 62:
        _fail("days must be between 1 and 62")
    if start + timedelta(days=days - 1) != end:
        _fail("end_date does not match start_date and days")
    if data.get("timezone") != "Asia/Tehran":
        _fail("timezone must be Asia/Tehran")
    for field in ("pillars", "formats", "angles", "templates"):
        if not data.get(field):
            _fail(f"{field} is empty")
    rules = data.get("rules") or {}
    stories = []
    for index in range(days):
        current = start + timedelta(days=index)
        pillar = data["pillars"][index % len(data["pillars"])]
        stories.append({
            "slot_id": f"story-{current.isoformat()}",
            "publish_date": current.isoformat(),
            "pillar": pillar["name"],
            "format": data["formats"][index % len(data["formats"])],
            "angle": data["angles"][(index * 3) % len(data["angles"])],
            "template_id": data["templates"][index % len(data["templates"])],
            "event_key": f"evergreen-{pillar['name']}-{index % len(data['pillars'])}-{current.isoformat()}",
            "hook": pillar["hook"],
            "cta": pillar["cta"],
            "status": "planned",
        })
    if len(stories) != len({x["slot_id"] for x in stories}):
        _fail("duplicate slot_id")
    if len(stories) != len({x["event_key"] for x in stories}):
        _fail("duplicate event_key")
    spacing = int(rules.get("no_same_template_within_days", 0) or 0)
    if spacing:
        for i, item in enumerate(stories):
            recent = {x["template_id"] for x in stories[max(0, i - spacing + 1):i]}
            if item["template_id"] in recent:
                _fail(f"template repeated within {spacing} days at {item['slot_id']}")
    for item in stories:
        item["frames"] = [
            {"type": "hook", "text": f"{item['hook']}\nموضوع امروز: {item['pillar']}"},
            {"type": "value", "text": f"قالب: {item['format']}\nزاویه: {item['angle']}\nیک ادعای مشخص را انتخاب کن، منبع و زمان انتشارش را بررسی کن، بعد نتیجه را در یک جمله ساده بنویس."},
            {"type": "cta", "text": item["cta"]},
        ]
    keys = [content_key(x["frames"][0]["text"], event_key=x["event_key"]) for x in stories]
    if len(keys) != len(set(keys)):
        _fail("duplicate content key")
    data["stories"] = stories
    return data


def check():
    data = load_calendar()
    for item in data["stories"]:
        caption = build_caption(item["frames"][0]["text"], item["frames"][1]["text"], "NABZ")
        ok, reason = validate_caption(caption)
        if not ok:
            _fail(f"{item['slot_id']}: {reason}")
    print(f"Instagram Stories calendar: OK ({data['days']} days, {data['days'] * 3} frames)")


def due():
    data = load_calendar()
    today = datetime.now(TEHRAN).date().isoformat()
    matches = [x for x in data["stories"] if x["publish_date"] == today and x.get("status") == "planned"]
    print(json.dumps({"timezone": "Asia/Tehran", "date": today, "due": matches}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--due", action="store_true")
    args = parser.parse_args()
    if args.due:
        due()
    else:
        check()
