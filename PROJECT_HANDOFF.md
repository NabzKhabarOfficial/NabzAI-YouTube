# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work.
- Telegram news-channel code belongs in `NabzKhabar`.

## Current branch
- `main`

## Production hardening applied
- `src/atomic_state.py`: crash-safe JSON and UTF-8 text persistence with fsync and corrupt-state quarantine.
- `src/idempotency.py`: durable publication claims with explicit reconciliation.
- `src/production_state.py`: pending, succeeded, failed, and ambiguous contracts.
- `src/guarded_youtube_upload.py`: quality gate and durable claim before YouTube mutation.
- `src/guarded_buffer.py`: Buffer aggregate claim and fail-closed handling when the legacy runner swallows failures.
- `scripts/record_story_after_upload.py`: post-upload story recording hook.
- The deterministic broken newline syntax in `src/atomic_state.py` was repaired.

## Active integration boundary
- The active workflow files still invoke the legacy entrypoints `src.youtube_uploader` and `src.ig_buffer`.
- Updating `.github/workflows/*.yml` is blocked by the connected GitHub credential lacking the repository `workflow` permission.
- Therefore the guarded adapters exist on `main`, but scheduled production will not use them until an authorized maintainer updates the workflow commands or grants the minimum workflow scope.
- Instagram Stories remain intentionally dry-run in `instagram-v1.yml`.

## Required next action
1. An authorized maintainer must change `youtube.yml` to run `python -m src.guarded_youtube_upload output/mystery-short`, set `NABZ_RECORD_STORY=0` during build, then run `scripts/record_story_after_upload.py` after confirmed upload.
2. Change `ig-pack.yml` to run `python -m src.guarded_buffer` and persist `content/publication_claims.json`.
3. Run the exact main-branch offline suite and inspect fresh GitHub Actions results.
4. Perform live provider verification separately. Do not infer it from offline green checks.

## Verification boundary
- Static source review completed for the files above.
- Offline and live workflow results for the final main-branch integration are not yet independently verified.
- No automatic retry is allowed for pending or ambiguous external publication claims.
