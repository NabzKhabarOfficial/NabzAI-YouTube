# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work. Telegram belongs in `NabzKhabar`.

## Current branch
- `brain/production-hardening`
- Backup: `brain/production-hardening-backup`
- PR #5 remains open and unmerged. PR #4 remains open.

## Latest change
- Commit: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/852a558a21ebaf5afaf7b87413dd6dccf5f5c9f5
- Added `src/guarded_youtube_upload.py` and `src/guarded_buffer.py`.
- Added `tests/test_guarded_publication_entrypoints.py`.
- The guarded YouTube entrypoint creates a durable claim before upload, confirms only after a video ID, and blocks reruns for pending/ambiguous claims.
- The guarded Buffer entrypoint adds a run-level claim for an identical pack-state snapshot and blocks uncertain reruns.

## Verification
- Actual PR-head CI completed successfully:
  - offline: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/actions/runs/40159574161/job/121068116438
  - Instagram and YouTube offline tests: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/actions/runs/40159570883/job/121068107133
- Earlier run `40159191248` failed before this claim-guard commit and is not evidence against the current head.
- Live YouTube, Buffer, Meta, public-hosting, or provider-quota verification has not been performed.

## Important limitations
- The connected GitHub writer rejected workflow-file writes because the required `workflow` permission is unavailable. `.github/workflows/youtube.yml` and `.github/workflows/ig-pack.yml` therefore still call the original modules. The new adapters are real, tested production entry points, but they are not wired into CI until that permission is granted or an authorized maintainer changes the workflow commands.
- Per-post Buffer claims inside `src/ig_buffer.py` are not yet migrated. The current adapter is run-level only and must not be described as exactly-once Buffer publication.
- `ig_buffer.py` still directly writes `content/ig_stats.json` and `review/ig_weekly.md`; `ig_pack.py` still directly writes the Persian bank during merge. These remain open migration items because the available GitHub editor cannot safely patch those large files without whole-file replacement.
- Provider-side lookup after accepted-but-lost responses remains unavailable in the current configured paths. Ambiguous claims require manual review, not automatic retry.
- Voice fail-closed policy is not yet one shared gate across English Shorts, Persian Reels, and one-take packs.
- Buffer queue/public-site replacement still needs remote-state reconciliation before destructive replacement.
- Runtime dependency/model/font integrity hardening is incomplete.
- Live platform verification is `NOT VERIFIED`.

## Existing verified hardening
- Atomic persistence, corrupt-state quarantine, bounded history, tri-state transport outcomes, redacted AI logging, missing-credential failure, bounded YouTube tags, no blind resumable-upload retry, and one-take voice controls remain present.
- The isolated `instagram/runner.py` path validates Stories but does not publish production Stories.

## Next action
1. Obtain the minimum workflow-write permission or have an authorized maintainer change the workflow commands to `python -m src.guarded_youtube_upload` and `python -m src.guarded_buffer`.
2. Then add per-operation Buffer/Meta claims, provider lookup where supported, and manual-review states.
3. Migrate the remaining large-file writers with a patch-capable checkout, then run the complete offline suite and clean-checkout test.
4. Keep PRs open and do not merge automatically.
