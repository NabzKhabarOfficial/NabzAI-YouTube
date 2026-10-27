# AI Team Protocol

## Mission
Complete the requested project task end-to-end, not merely suggest steps. Inspect the current repository, recent CI/workflow runs, tests, and existing architecture before editing. Do not ask the user to repeat information already present in the repository or logs.

## Roles and coordination
When subagents or parallel agent tools are actually available, use separate focused roles:
1. **Lead / planner:** define acceptance criteria and identify the smallest safe change.
2. **Implementer:** make the code change on the current feature branch.
3. **Independent reviewer:** inspect the diff for bugs, regressions, security and requirement violations.
4. **Tester:** run targeted tests, then the full available test suite and CI checks.
The lead integrates results and resolves disagreements using code, logs, tests, and documented requirements. Assign disjoint files/tasks to parallel writers; never let agents edit the same file simultaneously. If subagents are unavailable, perform these roles sequentially yourself. Never claim that multiple models/agents collaborated unless they were actually invoked.

## Required workflow
1. Read this file and `CLAUDE.md` (if present), project README, dependency files, tests, and relevant workflows.
2. Inspect current branch/status and recent failed CI runs before changing code.
3. Write down concrete acceptance criteria and a short plan.
4. Reproduce the failure or add a regression test first when practical.
5. Implement the smallest root-cause fix; avoid unrelated rewrites and speculative dependencies.
6. Run targeted tests, full tests, syntax/import checks, and workflow-specific validation where feasible.
7. Review the final diff independently; check secrets, generated files, duplicate logic, API limits, and failure handling.
8. Report exactly what changed, tests and results, unresolved blockers, and any manual steps. Never say “complete” or “all green” without evidence.

## User constraints
- **No paid services, subscriptions, or APIs.** Keep the existing free-tier architecture. Warn before proposing anything that may cost money.
- Never print, commit, or expose tokens, passwords, cookies, or secret values. Do not inspect secret values to debug; report only whether a required variable is present.
- Do not disable quality gates, tests, safety checks, duplicate protection, or publication guards just to make CI green.
- Do not publish, delete production data, rotate secrets, merge a PR, or change account settings unless the user explicitly authorized that specific action.
- Prefer offline tests and mocked external calls. Do not spend API quota for tests unless necessary and explicitly approved.
- Preserve the user's language and content requirements documented in the repository.

## Completion contract
A task is done only when its acceptance criteria are met and tests are reported accurately. If blocked by missing credentials, rate limits, provider quotas, or unavailable hardware, finish all offline work and state the exact external blocker instead of repeatedly retrying.

# NabzAI-YouTube project-specific guardrails

Follow `AGENTS.md` and `CLAUDE.md`.

- The English YouTube Shorts and Persian Instagram content pipelines have separate language, formatting, and publishing requirements. Do not mix their output languages.
- Inspect `.github/workflows/youtube.yml`, the story bank, publication state, quality report and regression tests before changing build/upload behavior.
- Preserve fact-checked story-bank sourcing, story deduplication, publication claims, the guard that records a story only after confirmed upload, private-by-default manual runs, and all media quality gates.
- Test offline first with `python -m unittest discover -s tests -v`; do not upload to YouTube or schedule Buffer posts as a test.
- Do not claim a video is publish-ready without checking generated duration, voice/quality JSON, captions, and the actual output artifact when available.
- Keep the workflow compatible with free-tier constraints. Never add paid image/video/voice services or silently introduce per-generation costs. Check API quotas before suggesting live generation tests.
- Do not commit generated media, credentials, or private review artifacts unless the existing workflow explicitly requires them.