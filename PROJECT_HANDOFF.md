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

## Production hardening applied
- `src/atomic_state.py`: crash-safe JSON and UTF-8 text persistence with fsync and corrupt-state quarantine.
- `src/idempotency.py`: durable publication claims with explicit reconciliation.
- `src/production_state.py`: pending, succeeded, failed, and ambiguous contracts.
- `src/guarded_youtube_upload.py`: quality gate, story-level duplicate check, and durable claim before YouTube mutation.
- `scripts/record_story_after_upload.py`: runnable from repository root and records state only after confirmed upload.
- `src/guarded_buffer.py`: wraps actual `ig_buffer.create_post`, `create_story`, and `create_carousel` mutations with separate durable claims per operation.
- Successful claims reuse the confirmed external post id and never call Buffer again.
- Ambiguous claims hard-stop and require reconciliation. No blind retry.
- `src/guarded_buffer.py` now fails closed when `BUFFER_API_KEY` or `REELS_PAT` is missing. A missing secret cannot produce a green no-op run.

## Active production workflow
- YouTube must set `NABZ_EN_TTS=kokoro`, `NABZ_KOKORO_VOICE=am_michael`, `NABZ_KOKORO_DEEPEN=1.5`, `NABZ_RECORD_STORY=0`, and `NABZ_REQUIRE_VOICE=kokoro`.
- YouTube must call `src.guarded_youtube_upload`, then `scripts/record_story_after_upload.py` only after a confirmed video id.
- Instagram Reels/Buffer must call `src.guarded_buffer` and persist `content/publication_claims.json` together with Buffer state.
- Instagram Stories in `instagram-v1.yml` remain intentionally dry-run and are not claimed live.

## Final audit status
- Latest static audit found the guarded Reels path integrated on `main` and YouTube story-level duplicate protection active.
- Repository state confirms a succeeded YouTube claim for story `carroll-deering`, external id `7spAuv-5Lic`.
- Static evidence is not live provider evidence: current Buffer queue, Instagram publication, and YouTube external state still require checking in their own dashboards.
- Remaining non-blocking hardening debt: some auxiliary writers (`ig_buffer` metrics/report, `ig_pack` state, `mystery_short` published state) still use direct writes instead of the shared atomic helper; they do not bypass per-operation publication claims, but should be migrated in the next maintenance pass.

## Verification plan
1. Run offline and hardening workflows on `main` after commit `a80231865b4eb1f773b89ae131929aceb9928b26`.
2. Run Instagram pack manually with `buffer_max=1` only.
3. Confirm exactly one Reel mutation in Buffer and one `succeeded` per-operation claim.
4. Do not run the same pack again if a claim is `pending` or `ambiguous`.
5. Increase to `buffer_max=10` only after the single-Reel run is confirmed.

## Verification boundary
- Static changes are complete through commits `2983699ca3abac439dfc7ab73439edacf3843e2e` and `a80231865b4eb1f773b89ae131929aceb9928b26`.
- Fresh offline, hardening, and live Buffer results for the latest commit must be recorded before claiming full green.
- No automatic retry is allowed for pending or ambiguous external publication claims.
