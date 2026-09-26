from .story_engine import build_episode


def build_script(topic, target_minutes=6):
    return build_episode(topic, target_minutes)["script"]


def make_title(topic):
    return topic["title"]


def make_description(topic):
    tags = " ".join("#" + str(x).replace(" ", "") for x in topic.get("tags", []))
    return f"{topic['title']}\n\nA practical NABZ AI experiment built around real workflows, visible proof, measurable tradeoffs, and honest limitations.\n\n{tags}"


def make_short_script(topic):
    episode = build_episode(topic, 1)
    return (
        episode["hook"]
        + " Test one real task, compare the baseline, verify the output, and keep only what actually helps."
    )
