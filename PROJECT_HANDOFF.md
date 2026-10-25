# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work. Telegram belongs in `NabzKhabar`.

## Current branch
- `brain/production-hardening`
- Backup: `brain/production-hardening-backup`
- PR #5 remains open and unmerged. PR #4 remains open.

## Latest code changes
- Current code head before this documentation commit: `e95fbbf8e518b829feb6d57fdaff51b232da6786`.
- Fixed the deterministic CI import defect: `src.production_state` imported `save_text`, but `src.atomic_state` did not define it.
- Added crash-safe atomic UTF-8 `save_text()` using flush, fsync, same-directory replacement, and directory fsync.
- Added import/atomic-text regression coverage for all guarded modules.
- Hardened `guarded_buffer`: because `ig_buffer.main()` can swallow failures and return 0, a recorded Buffer failure streak now leaves the aggregate claim ambiguous instead of falsely succeeding.
- Added regression coverage for the swallowed-failure case.

## CI evidence
- Fresh checks are required for `e95fbbf8e518b829feb6d57fdaff51b232da6786` and are not yet inferred from older heads.
- Prior failure root cause is now high-confidence from source inspection: the full offline suite imports `production_state`, which failed on missing `atomic_state.save_text`; the narrower hardening workflow did not import that module.
- Prior failed job: https://github.com/NabzKhabarOfficial/NabzAI-YouTube/actions/runs/40160638821/job/121071255099
- Live YouTube, Buffer, Meta, public-hosting, or provider-quota verification: `NOT VERIFIED`.

## Active integration gaps
- `.github/workflows/youtube.yml` still invokes `src.youtube_uploader`.
- `.github/workflows/ig-pack.yml` still invokes `src.ig_buffer`.
- Workflow-file editing was rejected with `Insufficient scope: required workflow`.
- Per-operation Buffer claims are not yet inside real `ig_buffer.py` mutation call sites; the current adapter remains aggregate/run-level.
- Remaining direct writers in `ig_buffer.py` and `ig_pack.py` are not migrated.
- Voice fail-closed enforcement is not uniform across every active Reel path.
- Buffer queue/public-hosting replacement reconciliation and clean-checkout verification remain open.

## Next action
1. Verify all fresh checks for the exact current head and inspect any new failures.
2. Obtain the minimum GitHub `workflow` permission or have an authorized maintainer switch active workflows to guarded entrypoints and persist `content/publication_claims.json`.
3. Use a patch-capable writable checkout to migrate per-operation Buffer claims and remaining state writers.
4. Run the complete offline suite and verify every check against the exact resulting head.
5. Keep PRs open and do not merge automatically.
