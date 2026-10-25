# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work.
- Telegram news-channel code belongs in the public `NabzKhabar` repository.

## Current branch
- `brain/production-hardening`
- Backup branch: `brain/production-hardening-backup`

## Production hardening status
- PR: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/5
- Previous helper PR: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/4
- PRs remain open and unmerged by design.
- Latest claim-state commit: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/365c167815ade51a3793e8ea08ebffb552edde55
- Latest claim regression tests: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/37c410dca2fce90f8306647bc12b0c5bde99750f
- Latest evidence commit: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/cfc63f7ea30244f18f05e69e08ee920d55450a4a

## Repository layout
- `src/`: production Reels, Stories/Buffer, YouTube, voice, and media code.
- `instagram/`: isolated Story validation/publisher package and 60-day calendar.
- `.github/workflows/ig-pack.yml`: production-like Instagram Reel pack and Buffer path.
- `.github/workflows/instagram-v1.yml`: isolated Story validation/dry-run workflow; it does not publish by itself.
- `.github/workflows/youtube.yml`: YouTube build/test/upload workflow.
- `tests/`: offline unit/regression tests.

## Completed and verified
- Story rotation happens only after a confirmed YouTube video ID.
- Missing YouTube credentials fail the upload workflow instead of silently succeeding.
- Ambiguous resumable upload errors are not blindly retried; schedule fallback is limited to structured publishAt validation errors.
- YouTube tag totals are bounded.
- Atomic persistence added across story, Buffer, pack, comment, and voice state paths covered by the hardening batch.
- Buffer and Meta mutation transport outcomes are not blindly retried.
- PAT is not embedded in the Git remote URL or process arguments.
- Voice report counters reset after durable persistence.
- Durable claim helper now supports `pending`, `succeeded`, `ambiguous`, and `failed`, with `get()` and `reconcile()` plus regression tests.
- Latest full offline workflow and Instagram/YouTube offline checks observed as passing before the handoff-only update.

## Latest CI observation
- Latest observed full workflow: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/actions/runs/40158118834
- Full offline check: passed.
- Instagram and YouTube offline tests: passed.
- No live YouTube, Buffer, Meta, public-hosting, or provider-quota verification has been performed.

## Critical architecture note
- The actual current production Instagram Reel path is `ig-pack.yml` -> `src.ig_pack` -> release assets/Buffer.
- The isolated `instagram/runner.py` path validates and selects Stories but does not publish or persist production publish state.
- Do not claim Instagram Story publishing is live unless a workflow explicitly calls `instagram.publisher.publish_story` with a public media URL and persistent idempotency state.

## Known remaining risks and blockers
- Claim/reconciliation is not yet wired into every real YouTube, Buffer, and Meta call site; the helper alone is not a complete idempotency guarantee.
- Provider-side lookup after accepted-but-lost responses remains required before any later retry.
- Buffer queue/public-site force-push ordering still needs full reconciliation against the remote queue before destructive replacement.
- Voice fail-closed behavior is not uniform across every YouTube and Reel generation path; English Short and standalone Reel fallbacks require a final policy decision and shared gate.
- Some state/report writers still need a complete atomic-writer audit, including Buffer stats/weekly report and pack-bank merge paths.
- Runtime dependency/model/font downloads still require pin/checksum hardening where practical.
- Live platform behavior remains unverified.

## Required continuation procedure
1. Inspect `main`, latest commits, workflows, and state schemas before changing anything.
2. Run offline CI before changing behavior; never repeat completed fixes blindly.
3. Preserve one-continuous-take voice policy and fail closed when the required voice check cannot run.
4. Keep Tehran timezone handling explicit.
5. Keep Telegram code in `NabzKhabar`; do not copy it here.
6. Treat YouTube/Buffer/Meta state transitions as idempotency-sensitive.
7. After every code, workflow, dependency, state, or documentation change, update this handoff with latest commit, changed files, verification, blockers, and next action.
8. Separate static/offline verification from live-platform verification.

## Handoff update format
- Last change: `<commit URL>`
- Changed files: `<paths>`
- Verification: `<CI/test/static status>`
- Blockers: `<none or exact blocker>`
- Next action: `<concrete continuation step>`

## Next action
- Re-check the latest CI after this documentation-only commit.
- Wire the durable claim/reconcile state into every real YouTube, Buffer, and Meta mutation call site.
- Add mocked provider lookup tests for accepted-but-lost responses.
- Complete the public-site queue reconciliation guard before any destructive replacement.
- Unify the voice fail-closed policy across English Short, Persian Reel, and pack paths.
- Audit remaining state writers and dependency/model/font integrity, then rerun full offline CI.
- Do not merge PRs automatically.
