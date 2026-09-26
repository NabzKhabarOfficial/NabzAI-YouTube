import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "content/published.json"


def load_topics():
    data = json.loads((ROOT / "content/topics.json").read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise RuntimeError("Topic gate: topic bank is empty or invalid.")
    return data


def load_state():
    if not STATE_PATH.exists():
        return {"published": [], "reserved": []}
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Topic gate: published state is invalid.")
    return {
        "published": list(data.get("published", [])),
        "reserved": list(data.get("reserved", [])),
    }


def choose_topic():
    state = load_state()
    used = set(state["published"]) | set(state["reserved"])
    topics = load_topics()
    for topic in topics:
        topic_id = str(topic.get("id", "")).strip()
        if topic_id and topic_id not in used:
            return topic
    raise RuntimeError(
        "No unused topics remain. Add more topics before the next scheduled run."
    )


def mark_published(topic_id):
    topic_id = str(topic_id).strip()
    if not topic_id:
        raise RuntimeError("Topic gate: cannot mark an empty topic id.")

    state = load_state()
    published = list(dict.fromkeys(state["published"]))
    reserved = [x for x in state["reserved"] if x != topic_id]

    if topic_id not in published:
        published.append(topic_id)

    STATE_PATH.write_text(
        json.dumps(
            {"published": published, "reserved": reserved},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
