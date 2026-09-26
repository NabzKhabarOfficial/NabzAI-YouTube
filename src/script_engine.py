from textwrap import dedent

STRUCTURES = [
    "Start with the pain point, then show the fix, an example, a warning, and a practical checklist.",
    "Start with a test question, define the test, show observations, explain failures, then give the result.",
    "Start with the desired outcome, map the workflow, walk through each stage, add quality checks, then summarize.",
    "Start with the decision, compare use cases rather than hype, show tradeoffs, then give a selection framework.",
    "Open with the common mistake, explain why it happens, show corrections, then finish with a prevention checklist."
]

def build_script(topic, target_minutes=6):
    structure = STRUCTURES[sum(ord(c) for c in topic["id"]) % len(STRUCTURES)]
    sections = topic["sections"]
    plan = "\n".join(f"- {s.title()}" for s in sections)
    examples = "\n".join(
        f"Example {i}: take a realistic case involving {s} and show what changes in practice."
        for i, s in enumerate(sections, 1)
    )
    target_words = max(700, int(target_minutes * 140))
    script = dedent(f"""
    {topic["hook"]}

    Today we are going to make this practical. The goal is not to make AI sound impressive. The goal is to get a useful result with a workflow you can actually repeat.

    Here is the plan:
    {plan}

    {structure}

    STEP 1 — {sections[0].upper()}
    Start by defining the outcome in one sentence. If you cannot explain what success looks like, an AI tool cannot reliably produce it either. Write down the input, the desired output, and what would make the output unacceptable.

    STEP 2 — {sections[1].upper() if len(sections) > 1 else "THE WORKFLOW"}
    Give the model the context that changes the answer, while removing irrelevant noise. A useful instruction usually contains the task, relevant background, constraints, and the format you want back.

    STEP 3 — {sections[2].upper() if len(sections) > 2 else "TEST THE RESULT"}
    Test the workflow on a real example. Do not judge it because the answer sounds confident. Check whether it satisfies the goal and whether important claims can be verified.

    STEP 4 — {sections[3].upper() if len(sections) > 3 else "ADD A QUALITY CHECK"}
    Add a checkpoint for accuracy, missing information, privacy, and edge cases. If the result fails, change one part of the process at a time so you know what fixed it.

    REALISTIC EXAMPLES
    {examples}

    THE IMPORTANT LIMITATION
    AI is a tool, not a guarantee. It can produce plausible mistakes, misunderstand a requirement, or confidently fill gaps in its knowledge. For important decisions, verify the result against trustworthy sources and keep a human in the loop.

    QUICK CHECKLIST
    Before reusing this workflow, ask: Is the goal clear? Is the input sufficient? Are the constraints explicit? Can the output be checked? Did the process avoid sensitive information that should not be shared?

    FINAL TAKEAWAY
    {topic["title"]} is useful when it removes friction without removing judgment. Start with one small real task, measure the result, and improve the workflow based on what actually happens.

    If this was useful, subscribe for practical AI workflows, tools, experiments, and automation that focus on results instead of hype.
    """).strip()
    filler = ("\n\nOne more practical point: keep the first version simple. A small workflow with a clear checkpoint is easier to improve than a complicated system you cannot inspect. "
              "Once it works, document the successful instructions, inputs, expected output, and failure cases so the next run starts from a known baseline.")
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
