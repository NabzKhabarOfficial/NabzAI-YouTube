# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work. Telegram belongs in `NabzKhabar`.

## Current branch
- `brain/production-hardening`
- Backup: `brain/production-hardening-backup`
- PR #5 remains open and unmerged. PR #4 remains open.

## Latest change
- Commit: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/7680a4f46723e9a549bcd33606b3c31ec15a9c75
- Corrected Meta dry-run semantics: dry runs do not consume production claims because they perform no mutation.
- Real Meta publication remains claim-guarded and records success only with a returned media id.
- Buffer confirmed snapshots remain idempotent no-ops; pending and ambiguous snapshots remain hard stops.
- Guarded YouTube publication requires a valid passed media report and Gemini voice by default.
- Regression coverage exercises these production adapters with mocked providers.

## Verification
- Fresh CI for the current head was started as `40160240378`; it was still in progress at the last observation and is not yet a pass.
- Previous completed checks for the preceding head are historical only: `40160040038` and `40160036392`.
- Live YouTube, Buffer, Meta, public-hosting, or provider-quota verification has not been performed.

## Important limitations
- Workflow-file writes remain blocked by the connected GitHub writer's missing `workflow` permission. `.github/workflows/youtube.yml` and `.github/workflows/ig-pack.yml` still call the original modules, so these adapters are not yet active in CI.
- Per-post Buffer claims inside `src/ig_buffer.py` are not yet migrated. The Buffer adapter is run-level only and is not an exactly-once guarantee.
- `ig_buffer.py` still directly writes `content/ig_stats.json` and `review/ig_weekly.md`; `ig_pack.py` still directly writes the Persian bank during merge. Safe migration needs patch-capable editing of those large files.
- Provider-side lookup after accepted-but-lost responses remains unavailable in the current configured paths. Ambiguous claims require manual review, not automatic retry.
- Voice fail-closed behavior is enforced in the guarded YouTube adapter, but the original unguarded workflow and other Reel paths still need migration.
- Buffer queue/public-hosting replacement reconciliation and clean-checkout verification remain open.
- Runtime dependency/model/font integrity hardening is incomplete.
- Live platform verification is `NOT VERIFIED`.

## Existing verified hardening
- Atomic persistence, corrupt-state quarantine, bounded history, tri-state transport outcomes, redacted AI logging, missing-credential failure, bounded YouTube tags, no blind resumable-upload retry, and one-take voice controls remain present.
- The isolated `instagram/runner.py` path validates Stories but does not publish production Stories.

## Next action
1. Wait for CI `40160240378` to complete and verify it against commit `7680a4f46723e9a549bcd33606b3c31ec15a9c75`.
2. Obtain the minimum workflow-write permission or have an authorized maintainer switch active workflows to the guarded entrypoints.
3. Add per-operation Buffer claims and provider lookup where supported.
4. Migrate remaining large-file writers with a patch-capable checkout, then run the complete offline suite and clean-checkout test.
5. Keep PRs open and do not merge automatically.
