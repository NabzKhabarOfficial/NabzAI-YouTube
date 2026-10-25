# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work.
- Telegram news-channel code belongs in the public `NabzKhabar` repository.

## Current branch
- `brain/production-hardening`

## Repository layout
- `src/`: production Reels, Stories/Buffer, YouTube, voice, and media code.
- `instagram/`: isolated Story validation/publisher package and 60-day calendar.
- `.github/workflows/ig-pack.yml`: production-like Instagram Reel pack and Buffer path.
- `.github/workflows/instagram-v1.yml`: isolated Story package validation/dry-run workflow; it does not publish by itself.
- `.github/workflows/youtube.yml`: YouTube build/test/upload workflow.
- `tests/`: offline unit/regression tests.

## Completed fixes
- Added and validated the 60-day Tehran-time Story calendar and calendar-rule checks.
- Restored functional `src/voice_check.py` ASR behavior, candidate generation, repair loop, learned pronunciation persistence, bundled-FFmpeg lookup, and monotonic caption timing.
- Added `faster-whisper` to `requirements-cinematic.txt`.
- Added `requests` to `requirements.txt` for the Instagram publisher.
- Added the isolated `instagram/` package and dry-run validation path.

## Critical architecture note
- The actual current production Instagram Reel path is `ig-pack.yml` -> `src.ig_pack` -> release assets/Buffer.
- The isolated `instagram/runner.py` path validates and selects Stories but does not publish or persist production publish state.
- Do not claim Instagram Story publishing is live unless a workflow explicitly calls `instagram.publisher.publish_story` with a public media URL and persistent idempotency state.

## Required continuation procedure
1. Inspect `main`, latest commits, current workflow files, and state schemas first.
2. Run offline CI before changing behavior; never repeat completed work.
3. Preserve the one-continuous-take voice policy and fail closed when the required voice check cannot run.
4. Keep Tehran timezone handling explicit.
5. Keep Telegram code in `NabzKhabar`; do not copy its modules here.
6. Treat Buffer/Meta/YouTube state transitions as idempotency-sensitive.
7. After every code, workflow, dependency, state, or documentation change, update this handoff with the latest commit, changed files, current status, blockers, and next action.
8. Verify exact changed files and separate static verification from live API verification.

## Handoff update format
- Last change: `<commit URL>`
- Changed files: `<paths>`
- Verification: `<CI/test/static status>`
- Blockers: `<none or exact blocker>`
- Next action: `<concrete continuation step>`

## Secrets
- YouTube and media/provider secrets are GitHub Actions secrets in this repository.
- The isolated Meta Story publisher expects `INSTAGRAM_USER_ID`, `INSTAGRAM_ACCESS_TOKEN`, and optional `INSTAGRAM_API_VERSION`, but its workflow remains dry-run until explicitly wired and enabled.

## Known verification boundary
- Static code and workflow wiring have been reviewed.
- Live GitHub Actions, Buffer, Meta, YouTube, public hosting, and provider quota behavior still require actual workflow runs.


## Production hardening — 2026-10-25
- Current branch: `brain/production-hardening`; safety snapshot: `brain/production-hardening-backup` (both branched from `main`).
- Last change: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/3cad61e715b009096c35c07b125a0df8b04f356c
- Changed files: `src/mystery_short.py`, `src/youtube_uploader.py`, `.github/workflows/youtube.yml`, `tests/test_youtube_story_transaction.py`.
- Verified by static inspection: story rotation is no longer recorded by default during video build; `src.mystery_short` uses atomic state read/write; the uploader records the story only after `upload_video` returns a confirmed video ID; missing YouTube credentials now fail the workflow instead of silently exiting zero.
- Verification: GitHub file reads/writes succeeded. Offline unit tests and compile checks have **not yet been run** against this branch; do not treat this batch as green until branch CI completes.
- CI follow-up: first PR CI caught an unterminated string in the existing `src/atomic_state.py`; corrected the newline literal in commit https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/47274c232ce2c108b87e09b75134ebc839b64502. CI rerun pending.
- Blockers/remaining: durable YouTube/Buffer/Meta claim and reconciliation still need full production integration; ambiguous resumable upload recovery, Buffer/Meta retries, voice fail-closed policy, dependency pinning/removal of runtime installs, and complete state-writer migration remain open. No live external APIs were called during this pass.
- Next action: run the full offline unit suite and compile checks on this branch, fix failures, then integrate durable upload idempotency and the Buffer/Meta state transitions in small batches. Do not merge PRs automatically.

- Verification update: the full offline workflow passed on commit `c45b48e55b7d9e67270eebb59df520446c4dcc8f`: compile source/Instagram packages, validate the Story calendar, run due-slot check, and `python -m unittest discover -s tests -v` all succeeded. Workflow-YAML syntax validation has now been added to the offline workflow and must pass on the latest commit before this batch is considered green.
- Additional changed file: `.github/workflows/offline-tests.yml`.
- Latest uploader hardening: resumable upload errors are no longer retried as a plain upload unless a structured HTTP 400 explicitly identifies a `publishAt` validation error. Combined YouTube tags are bounded by a 500-character budget. Added offline tests for ambiguous timeout no-retry, known schedule-validation fallback, and tag budget.
- Latest code commit: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/77bb35afc52e769906f0309c2f9e49e3ad58c495; test commit: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/543c5e854e777cc6a40853f5b5d37ca233564fa0.
- Verification: the prior full offline workflow passed; the latest run including workflow-YAML validation and uploader retry tests is pending. No live YouTube/Buffer/Meta API calls were made.