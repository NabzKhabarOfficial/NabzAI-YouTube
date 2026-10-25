# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work.
- Telegram news-channel code belongs in `NabzKhabar`.

## Current branch
- `main`

## Root-cause findings
- The previous hardening added an aggregate Buffer claim, but the real `ig_buffer` mutation functions were still unguarded.
- That left a partial-run window where a Reel could be created remotely and the local state commit could fail, allowing a later run to create a duplicate.
- The YouTube duplicate came from the same story being rebuilt with a different audio hash. A hash-only claim treats the second voice build as a new publication.

## Production hardening now applied
- `src/atomic_state.py`: crash-safe JSON and UTF-8 text persistence with fsync and corrupt-state quarantine.
- `src/idempotency.py`: durable publication claims with explicit reconciliation.
- `src/production_state.py`: pending, succeeded, failed, and ambiguous contracts.
- `src/guarded_youtube_upload.py`: quality gate, story-level duplicate check, and durable claim before YouTube mutation.
- `scripts/record_story_after_upload.py`: runnable from repository root and records state only after confirmed upload.
- `src/guarded_buffer.py`: wraps the actual `ig_buffer.create_post`, `create_story`, and `create_carousel` mutations with a separate durable claim per operation.
- A successful claim reuses the confirmed external post id and never calls Buffer again.
- An ambiguous claim is a hard stop and requires reconciliation. No blind retry.

## Active production workflow
- The intended YouTube workflow must set `NABZ_EN_TTS=kokoro`, `NABZ_KOKORO_VOICE=am_michael`, `NABZ_KOKORO_DEEPEN=1.5`, `NABZ_RECORD_STORY=0`, and `NABZ_REQUIRE_VOICE=kokoro`.
- It must call `src.guarded_youtube_upload`, then `scripts/record_story_after_upload.py` only after a confirmed video id.
- The intended Instagram workflow must call `src.guarded_buffer` and persist `content/publication_claims.json` together with Buffer state.
- Instagram Stories remain intentionally dry-run in `instagram-v1.yml`.

## Verification plan
1. Run offline and hardening workflows on `main`.
2. Run Instagram pack manually with `buffer_max=1` only.
3. Confirm exactly one Reel mutation in Buffer and one `succeeded` per-operation claim.
4. Do not run the same pack again if a claim is `pending` or `ambiguous`.
5. Increase to `buffer_max=10` only after the single-Reel run is confirmed.

## Verification boundary
- Static source changes are complete through commit `2983699ca3abac439dfc7ab73439edacf3843e2e`.
- Fresh offline, hardening, and live Buffer results for this exact commit are not yet independently verified.
- No automatic retry is allowed for pending or ambiguous external publication claims.
