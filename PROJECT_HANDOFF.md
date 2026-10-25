# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work. Telegram belongs in `NabzKhabar`.

## Current branch
- `brain/production-hardening`
- Backup: `brain/production-hardening-backup`
- PR #5 remains open and unmerged. PR #4 remains open.

## Latest change
- Commit: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/34aeea5275996fd3f076efdf0a4d6b6b68d23aa0
- Added `src/guarded_meta.py` for claim-guarded Meta Story publication.
- Hardened `src/guarded_buffer.py`: completed snapshots are idempotent no-ops; pending/ambiguous snapshots remain hard stops.
- Hardened `src/guarded_youtube_upload.py`: publication now requires a valid passed media report and Gemini voice by default.
- Expanded offline tests for Meta claims, Buffer success reuse, ambiguous outcomes, duplicate claims, and non-Gemini voice rejection.

## Verification
- The previous head checks passed, but this new code head requires fresh CI. No check for `34aeea5275996fd3f076efdf0a4d6b6b68d23aa0` is being inferred from an older run.
- Live YouTube, Buffer, Meta, public-hosting, or provider-quota verification has not been performed.

## Important limitations
- Workflow-file writes remain blocked by the connected GitHub writer's missing `workflow` permission. `.github/workflows/youtube.yml` and `.github/workflows/ig-pack.yml` still call the original modules, so these adapters are not yet active in CI.
- Per-post Buffer claims inside `src/ig_buffer.py` are not yet migrated. The Buffer adapter is run-level only and is not an exactly-once guarantee.
- `ig_buffer.py` still directly writes `content/ig_stats.json` and `review/ig_weekly.md`; `ig_pack.py` still directly writes the Persian bank during merge. Safe migration needs patch-capable editing of those large files.
- Provider-side lookup after accepted-but-lost responses remains unavailable in the current configured paths. Ambiguous claims require manual review, not automatic retry.
- Voice fail-closed behavior is now enforced at the guarded YouTube entrypoint, but the original unguarded YouTube workflow and other Reel generation paths still need the workflow/entrypoint migration.
- Buffer queue/public-site replacement still needs remote-state reconciliation before destructive replacement.
- Runtime dependency/model/font integrity hardening is incomplete.
- Live platform verification is `NOT VERIFIED`.

## Existing verified hardening
- Atomic persistence, corrupt-state quarantine, bounded history, tri-state transport outcomes, redacted AI logging, missing-credential failure, bounded YouTube tags, no blind resumable-upload retry, and one-take voice controls remain present.
- The isolated `instagram/runner.py` path validates Stories but does not publish production Stories.

## Next action
1. Verify fresh CI for commit `34aeea5275996fd3f076efdf0a4d6b6b68d23aa0` and fix any failures.
2. Obtain the minimum workflow-write permission or have an authorized maintainer switch active workflows to the guarded entrypoints.
3. Add per-operation Buffer claims and provider lookup where supported.
4. Migrate remaining large-file writers with a patch-capable checkout, then run the complete offline suite and clean-checkout test.
5. Keep PRs open and do not merge automatically.
