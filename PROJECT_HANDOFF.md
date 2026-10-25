# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work. Telegram belongs in `NabzKhabar`.

## Current branch
- `brain/production-hardening`
- Backup: `brain/production-hardening-backup`
- PR #5 remains open and unmerged. PR #4 remains open.

## Current head and evidence
- Current PR head before this documentation commit: `88f679075c534de7120de7739687e282d64d2382`.
- Current-head CI:
  - offline: **success**, https://github.com/NabzKhabarOfficial/NabzAI-YouTube/actions/runs/40160638817/job/121071254766
  - hardening/offline: **success**, https://github.com/NabzKhabarOfficial/NabzAI-YouTube/actions/runs/40160634055/job/121071240434
  - Instagram and YouTube offline tests: **failure**, https://github.com/NabzKhabarOfficial/NabzAI-YouTube/actions/runs/40160638821/job/121071255099
- The failing check is attached to the current PR head. The available connection exposes the failed job URL but not step logs, so no root cause is being guessed.
- Live YouTube, Buffer, Meta, public-hosting, or provider-quota verification: `NOT VERIFIED`.

## Verified code additions
- Claim-guarded YouTube adapter with a durable claim before upload, media/quality gate, Gemini voice gate, confirmed success only after a video id, and no blind retry.
- Claim-guarded Buffer adapter with confirmed-snapshot no-op reuse and hard stops for pending/ambiguous snapshots.
- Claim-guarded Meta Story adapter. Dry runs perform no mutation and do not consume production claims; real publication requires a returned media id.
- Mocked regressions cover duplicate claims, ambiguous outcomes, confirmed Buffer reuse, Meta dry-run safety, and quality/voice rejection.

## Active integration gaps
- `.github/workflows/youtube.yml` still invokes `src.youtube_uploader`.
- `.github/workflows/ig-pack.yml` still invokes `src.ig_buffer`.
- Workflow-file editing was attempted and rejected with `Insufficient scope: required workflow`; no further unauthorized attempts are being made.
- Per-operation Buffer claims are not yet inside the real `ig_buffer.py` mutation call sites.
- Remaining direct writers in `ig_buffer.py` and `ig_pack.py` are not migrated.
- Voice fail-closed enforcement is not yet applied uniformly to every active Reel path.
- Buffer queue/public-hosting replacement reconciliation and clean-checkout verification remain open.

## Next action
1. Obtain the failed job step log or rerun after the root cause is known; current CI is not green.
2. Grant the minimum GitHub `workflow` write permission or have an authorized maintainer switch active workflows to the guarded entrypoints.
3. Use a patch-capable writable checkout to migrate per-operation Buffer claims and remaining state writers.
4. Run the complete offline suite and verify all checks against the exact resulting head.
5. Keep PRs open and do not merge automatically.
