from textwrap import dedent

STRUCTURES = [
    "Open with a sharp problem, prove why it matters, then solve it through concrete examples.",
    "Open with a test question, define the test, show the evidence, explain the failure points, then give the result.",
    "Open with the desired outcome, build the workflow visually in words, test each stage, then summarize.",
    "Open with the decision, compare real use cases and tradeoffs, then give a practical selection rule.",
    "Open with the common mistake, demonstrate it, correct it, and finish with a prevention checklist."
]

def build_script(topic, target_minutes=6):
    structure = STRUCTURES[sum(ord(c) for c in topic["id"]) % len(STRUCTURES)]
    sections = topic["sections"]
    target_words = max(750, int(target_minutes * 135))
    section_blocks = []

    for i, section in enumerate(sections, 1):
        section_blocks.append(dedent(f"""
        PART {i} — {section.upper()}

        Here is the practical point. {section.capitalize()} should be treated as a specific task, not as a vague AI promise.

        Imagine a real user facing this problem. First show the starting situation. Then show what changes when the workflow is applied. Give one concrete example with a clear input, action, and result.

        The useful question is not whether the tool sounds impressive. The useful question is what work disappears, what work becomes faster, and what still needs human judgment.

        Before moving on, check one limitation. If the output can be wrong, incomplete, outdated, or dependent on context, say exactly where that risk appears and how to catch it.
        """).strip())

    script = dedent(f"""
    {topic["hook"]}

    In this video, we are going to test the idea behind that statement instead of repeating another generic AI list. The goal is simple: show what changes in a real workflow, what does not, and where you should still be careful.

    {structure}

    WHAT WE ARE TESTING

    We will use four questions throughout the video:
    What is the starting task?
    What does AI actually change?
    What does the finished result look like?
    What can still go wrong?

    {chr(10).join(section_blocks)}

    THE REAL-WORLD TEST

    Now take the strongest idea from the examples and apply it to one small task you already do. Measure the manual version first. Then run the AI-assisted version under the same conditions. Compare time, quality, corrections, and the amount of human review required.

    If the AI version is not clearly better, do not force it into the workflow. That result is useful too. Automation is valuable when it removes friction without creating a larger verification problem.

    THE LIMITATION

    AI can produce confident mistakes, miss important context, or give an answer that looks polished but does not satisfy the actual requirement. Treat important outputs as drafts until they pass the relevant checks.

    FINAL CHECK

    Before you reuse this workflow, ask:
    Is the goal measurable?
    Is the input sufficient?
    Is the output easy to verify?
    What failure would be most expensive?
    Where does a human need to make the final decision?

    FINAL TAKEAWAY

    {topic["title"]} is not about using more AI. It is about using the right capability at the right point in a real workflow. Start with one measurable task, compare the result with your baseline, and keep only what genuinely improves the process.

    If this video helped, subscribe to NABZ AI for practical experiments, useful tools, automation workflows, and honest limitations—not generic AI hype.
    """).strip()

    filler = "\n\nOne final practical note: document the successful input, expected output, verification step, and known failure cases. That turns a one-time experiment into a workflow you can improve instead of repeating from scratch."
    while len(script.split()) < target_words:
        script += filler
    return script

def make_title(topic):
    return topic["title"]

def make_description(topic):
    tags = " ".join("#" + x.replace(" ", "") for x in topic["tags"])
    return f"{topic['title']}\n\nA practical NABZ AI video built around concrete examples, measurable workflows, and the limitations worth knowing.\n\n{tags}"

def make_short_script(topic):
    return f"{topic['hook']} The key is to test one real task: define the goal, give the AI the right context, check the result, and compare it with your manual baseline. Keep what saves time without creating extra work. Follow NABZ AI for practical AI workflows."
