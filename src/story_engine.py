from __future__ import annotations

import re
from textwrap import dedent


NUMBERED_RE = re.compile(r"^(\d+)\s+")


def _number_in_title(title: str) -> int | None:
    m = NUMBERED_RE.match(title.strip())
    return int(m.group(1)) if m else None


def validate_topic(topic: dict) -> dict:
    title = str(topic.get("title", "")).strip()
    sections = [str(x).strip() for x in topic.get("sections", []) if str(x).strip()]
    if not title or not sections:
        raise RuntimeError("Story gate: topic must contain a title and at least one section.")

    claimed = _number_in_title(title)
    if claimed and not topic.get("subjects") and claimed != len(sections):
        raise RuntimeError(
            f"Story gate: title claims {claimed} items but topic contains {len(sections)} sections."
        )

    if topic.get("subjects") and claimed and len(topic["subjects"]) != claimed:
        raise RuntimeError(
            f"Story gate: title claims {claimed} items but contains {len(topic['subjects'])} subjects."
        )

    return topic


def build_episode(topic: dict, target_minutes: int = 6) -> dict:
    validate_topic(topic)
    title = topic["title"]
    hook = topic.get("hook", "").strip()
    angle = topic.get("angle", "practical test").strip()
    sections = topic["sections"]
    subjects = topic.get("subjects") or sections

    opening = dedent(f"""
    Stop scrolling for a second.

    {hook}

    But here is the part most videos skip: we are not going to repeat a list of claims.
    We are going to turn this into a small experiment. By the end, you should know what
    actually changes, where the workflow breaks, and what is worth keeping.

    The rule for this episode is simple: every idea needs a job. We will look at the
    starting problem, the action, the result, and the check that keeps the result honest.

    Today's angle is {angle}.
    """).strip()

    beats = []
    for i, section in enumerate(sections):
        subject = subjects[i] if i < len(subjects) else section
        archetypes = [
            (
                f"Start with the real bottleneck: {subject}. Show what the person does now, "
                f"then isolate the one step this idea is supposed to change.",
                f"Run {subject} on one concrete task. Compare the old path with the new path, "
                f"and measure the part that actually changed.",
                f"The trap with {subject} is invisible cleanup. If the new result needs more "
                f"correction than the old workflow, the apparent speed gain is misleading.",
            ),
            (
                f"Put {subject} under a simple test: one clear input, one expected output, "
                f"and one condition that would make the experiment fail.",
                f"Instead of describing {subject}, use it on a realistic example and capture "
                f"the exact output that a person would have to review.",
                f"Watch for the failure boundary with {subject}: impressive output is not enough "
                f"if an important detail is missing or unverifiable.",
            ),
            (
                f"Treat {subject} like a product demo with the hype removed. First define the "
                f"job, then show the smallest useful action it can perform.",
                f"Take {subject} from messy starting material to a visible result. The audience "
                f"should be able to see the transformation, not just hear a claim about it.",
                f"The limitation of {subject} matters as much as the benefit. Keep the checkpoint "
                f"that catches the most expensive mistake.",
            ),
            (
                f"Ask a sharper question about {subject}: where does it save a human a decision, "
                f"a repeated action, or a chunk of cleanup?",
                f"Use {subject} once before and once after the workflow change. Compare time, "
                f"quality, and review effort instead of relying on a vague feeling.",
                f"Do not count automation as a win if {subject} moves the work somewhere harder "
                f"to notice. The final check must expose that tradeoff.",
            ),
        ]
        setup, example, twist = archetypes[i % len(archetypes)]
        beats.append({
            "number": i + 1,
            "subject": str(subject),
            "section": str(section),
            "setup": setup,
            "example": example,
            "twist": twist,
        })

    blocks = []
    for b in beats:
        blocks.append(dedent(f"""
        CASE {b["number"]}: {b["subject"].upper()}

        {b["setup"]}

        {b["example"]}

        {b["twist"]}

        Keep one number in mind: time saved is useful only when the checking time does not
        quietly become the new bottleneck.
        """).strip())

    mid = dedent("""
    Now pause and compare the cases.

    The pattern is more important than any individual tool or technique. Good AI workflows
    have a clear input, a defined transformation, a visible output, and a verification step.
    Bad workflows usually skip one of those four pieces and hope the model will fill the gap.

    Here is the practical test. Do the task once without AI and record the time. Then repeat it
    with the workflow from this video. Compare not just speed, but corrections, missing details,
    and how much human review was required.

    If the second version is faster but creates more cleanup than the first, it did not really
    save time. That is a failed experiment, and knowing that is valuable.
    """).strip()

    ending = dedent(f"""
    So, what should you remember from {title}?

    Do not chase the biggest list of tools. Build the smallest workflow that produces a useful
    result and can be checked quickly. Start with one real task, measure the baseline, run the
    experiment, and keep the parts that genuinely improve the work.

    And there is one more rule for this channel: if a workflow looks impressive in a demo but
    fails the real-world test, we should show the failure instead of hiding it.

    Subscribe to NABZ AI for practical experiments, visual breakdowns, useful workflows, and
    the failures that teach us what the hype leaves out.
    """).strip()

    words = " ".join([opening, *blocks, mid, ending]).split()
    target_words = max(780, int(target_minutes * 145))
    if len(words) < target_words:
        extra = dedent("""
        Before you copy any workflow, write down the exact input it needs, the result you expect,
        the easiest way to verify that result, and the most expensive mistake it could make.
        This tiny checklist turns a clever demonstration into a repeatable process.

        Also remember that the best workflow is not always the most automated one. Sometimes one
        human checkpoint is the difference between useful automation and a polished mistake.
        """).strip()
        while len(words) < target_words:
            words.extend(extra.split())

    script = "\n\n".join([opening, *blocks, mid, ending])
    return {
        "title": title,
        "hook": hook,
        "beats": beats,
        "script": script,
        "word_count": len(script.split()),
        "scene_plan": _scene_plan(len(beats)),
    }


def _scene_plan(case_count: int) -> list[dict]:
    plan = [
        {"kind": "hook", "label": "COLD OPEN"},
        {"kind": "stakes", "label": "THE PROBLEM"},
        {"kind": "promise", "label": "THE TEST"},
    ]
    for i in range(case_count):
        plan.append({"kind": "case", "label": f"CASE {i + 1:02d}", "case_index": i})
        plan.append({"kind": "action", "label": "THE MOVE", "case_index": i})
        plan.append({"kind": "proof", "label": "PROOF", "case_index": i})
        plan.append({"kind": "check", "label": "VERIFY", "case_index": i})
    plan.extend([
        {"kind": "failure", "label": "THE CATCH"},
        {"kind": "workflow", "label": "THE PATTERN"},
        {"kind": "scorecard", "label": "THE TEST RESULT"},
        {"kind": "takeaway", "label": "TAKEAWAY"},
        {"kind": "cliffhanger", "label": "NEXT EXPERIMENT"},
    ])
    return plan
