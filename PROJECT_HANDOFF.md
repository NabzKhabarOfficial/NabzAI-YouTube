# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work.
- Telegram news-channel code belongs in `NabzKhabar`.

## Latest hardening
- Buffer queue-read fallback now marks queue state unknown and blocks create/replace/delete mutations until the provider queue is readable again.
- The successful smoke-test evidence was a Carousel (`car_behistun`), not a Reel; no additional test post should be created.
- 10 active scheduled Buffer records remain internally matched to succeeded claims.

## Remaining
- Require `publishAt` confirmation in YouTube before marking a scheduled claim succeeded.
- Add durable idempotency/reconciliation to direct Meta before live publishing.
- Use one effective-bank loader in review/comments/stats/mood.
- Enforce Persian length and hook rules.
- Fix CSV file overrides and clear stale `last_fail` after recovery.
- Protect `backup/immutable-2026-10-25` manually; it remains unprotected.

## Verification boundary
Run offline and hardening workflows on the latest commit before any further provider mutation. Do not run `buffer_max=10`. Never retry pending or ambiguous claims without provider reconciliation.
