from textwrap import dedent

STRUCTURES = [
    ("problem", "Start with the pain point, then show the fix, an example, a warning, and a practical checklist."),
    ("experiment", "Start with a test question, define the test, show observations, explain failures, then give the result."),
    ("workflow", "Start with the desired outcome, map the workflow, walk through each stage, add quality checks, then summarize."),
    ("comparison", "Start with the decision, compare use cases rather than hype, show tradeoffs, then give a selection framework."),
    ("mistakes", "Open with the common mistake, explain why it happens, show corrections, then finish with a prevention checklist.")
]

def _structure(topic):
    idx = sum(ord(c) for c in topic["id"]) % len(STRUCTURES)
    return STRUCTURES[idx]

def build_script(topic, target_minutes=6):
    name, guidance = _structure(topic)
    sections = topic["sections"]
    beats = "\n".join(f"{i+1}. {s.title()}" for i, s in enumerate(sections))
    examples = "\n".join(f"Example {i+1}: Take a realistic case involving {s} and show what changes in practice." for i, s in enumerate(sections))
    target_words = max(650, int(target_minutes * 135))
    script = dedent(f"""
    {topic["hook"]}

    Today we are going to make this practical. The goal is not to make AI sound impressive. The goal is to get a useful result with a workflow you can actually repeat.

    Here is the plan:
    {beats}

    {guidance}

    STEP 1 — {sections[0].upper()}
    Start by defining the outcome in one sentence. If you cannot explain what a successful result looks like, an AI tool cannot reliably produce it either. Write down the input, the desired output, and what would make the output unacceptable.

    STEP 2 — {sections[1].upper() if len(sections) > 1 else "THE WORKFLOW"}
    Give the model only the context it needs, but do not remove context that changes the answer. A useful instruction usually includes the task, relevant background, constraints, and the format you want back.

    STEP 3 — {sections[2].upper() if len(sections) > 2 else "TEST THE RESULT"}
    Now test the workflow on a real example. Do not judge it because the answer sounds confident. Check whether it actually satisfies the goal and whether important claims can be verified.

    STEP 4 — {sections[3].upper() if len(sections) > 3 else "ADD A QUALITY CHECK"}
    This is where a quick experiment becomes a reliable workflow. Add a checkpoint for accuracy, missing information, privacy, and edge cases. If the result fails, change one part of the process at a time so you know what fixed it.

    REALISTIC EXAMPLES
    {examples}

    THE IMPORTANT LIMITATION
    AI is a tool, not a guarantee. It can produce plausible mistakes, misunderstand a requirement, or confidently fill gaps in its knowledge. For important decisions, verify the result against trustworthy sources and keep a human in the loop.

    QUICK CHECKLIST
    Before you reuse this workflow, ask: Is the goal clear? Is the input sufficient? Are the constraints explicit? Can the output be checked? Did the process avoid sensitive information that should not be shared?

    FINAL TAKEAWAY
    {topic["title"]} is useful when it removes friction without removing judgment. Start with one small task, measure the result, and improve the workflow based on what actually happens.

    If this was useful, subscribe for practical AI workflows, tools, experiments, and automation that focus on results instead of hype.
    """).strip()
    words = script.split()
    if len(words) < target_words:
        filler = "\n\nOne more practical point: keep the first version simple. A small workflow with a clear checkpoint is usually easier to improve than a complicated system that you cannot inspect. Once the process works, document the successful prompt, inputs, expected output, and failure cases so the next run starts from a known baseline."
        while len(script.split()) < target_words:
            script += filler
    return script

def make_title(topic):
    return topic["title"]

def make_description(topic):
    tags = " ".join("#" + x.replace(" ", "") for x in topic["tags"])
    return f"{topic['title']}\n\nA practical NABZ AI guide with examples, tradeoffs, and a workflow you can test yourself.\n\nThis video focuses on useful, original educational content rather than generic AI hype.\n\n{tags}"

def make_short_script(topic):
    return f"{topic['hook']} Here is the practical idea: define the goal, give the AI the right context, test the result, and add a quality check. Start with one small real task and measure whether it actually saves time. Follow NABZ AI for practical AI workflows."
