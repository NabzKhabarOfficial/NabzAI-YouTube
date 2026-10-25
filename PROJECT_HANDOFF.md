# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work. Telegram belongs in `NabzKhabar`.

## Current branch
- `brain/production-hardening`
- Backup: `brain/production-hardening-backup`
- PR #5 remains open and unmerged. PR #4 remains open.

## Latest change
- Commit: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/f7a353716731c5d44a9c3f920475c241743947d6
- Added `src/guarded_youtube_upload.py` and `src/guarded_buffer.py`.
- Added `tests/test_guarded_publication_entrypoints.py`.
- The guarded YouTube entrypoint now creates a durable claim before upload, confirms only after a video ID, and blocks reruns for pending/ambiguous claims.
- The guarded Buffer entrypoint adds a run-level claim for an identical pack-state snapshot and blocks uncertain reruns.

## Verification
- The new commit triggered CI runs `40159549815`, `40159552563`, and `40159553039`.
- At handoff update time, `40159549815` was in progress and the other two were queued. They are not yet a pass.
- Prior completed checks `40159191245` passed; `40159191248` failed before this change and is not evidence for the current head.
- No live YouTube, Buffer, Meta, public-hosting, or provider-quota verification has been performed.

## Important limitations
- The existing GitHub connection rejected workflow-file writes because the required workflow permission is unavailable. Therefore `.github/workflows/youtube.yml` and `.github/workflows/ig-pack.yml` have not yet been switched to the new guarded entrypoints. The new entrypoints are real, tested production adapters, but they are not wired into CI until that permission is granted or the workflow command is changed by an authorized maintainer.
- Per-post Buffer claims inside `src/ig_buffer.py` are not yet migrated. The current adapter is run-level only and must not be described as exactly-once Buffer publication.
- `ig_buffer.py` still directly writes `content/ig_stats.json` and `review/ig_weekly.md`; `ig_pack.py` still directly writes the Persian bank during merge. These remain open migration items because the available GitHub editor cannot safely patch those large files without whole-file replacement.
- Provider-side lookup after accepted-but-lost responses remains unavailable in the current configured paths. Ambiguous claims therefore require manual review, not automatic retry.
- Voice fail-closed policy still needs one shared gate across English Shorts, Persian Reels, and one-take packs.
- Buffer queue/public-site replacement still needs remote-state reconciliation before destructive replacement.
- Runtime dependency/model/font integrity hardening is incomplete.
- Live platform verification is `NOT VERIFIED`.

## Existing verified hardening
- Atomic persistence, corrupt-state quarantine, bounded history, tri-state transport outcomes, redacted AI logging, missing-credential failure, bounded YouTube tags, no blind resumable-upload retry, and one-take voice controls remain present.
- The isolated `instagram/runner.py` path validates Stories but does not publish production Stories.

## Next action
1. Wait for every check on the actual PR head and inspect failures, never treating queued/running as pass.
2. Obtain the minimum workflow-write permission or have an authorized maintainer change the two workflow commands to `python -m src.guarded_youtube_upload` and `python -m src.guarded_buffer`.
3. Then add per-operation Buffer/Meta claims, provider lookup where supported, and manual-review states.
4. Migrate the remaining large-file writers with a patch-capable checkout, then run the complete offline suite and clean-checkout test.
5. Keep PRs open and do not merge automatically.
