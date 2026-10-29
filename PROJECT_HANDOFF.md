# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work.
- Telegram news-channel code belongs in `NabzKhabar`.

## Latest hardening
- Buffer queue-read fallback marks queue state unknown and blocks create/replace/delete mutations until the provider queue is readable again.
- The successful smoke-test evidence was a Carousel (`car_behistun`), not a Reel; no additional test post should be created.
- 10 active scheduled Buffer records remain internally matched to succeeded claims.

## Verification
- User-reported offline tests: green, including `test_all_150_batch_stories_are_loaded_into_runtime`.
- User-reported hardening checks: green.
- Latest code hardening commit: [c8d2cb3](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/commit/c8d2cb3b5fffce69c31948efee89cef23fd12f07).
- These checks prove deterministic/offline behavior, not Instagram delivery or provider-wide truth.

## Remaining code hardening
- Require `publishAt` confirmation in YouTube before marking a scheduled claim succeeded.
- Add durable idempotency/reconciliation to direct Meta before live publishing.
- Use one effective-bank loader in review/comments/stats/mood.
- Enforce Persian length and hook rules.
- Fix CSV file overrides and clear stale `last_fail` after recovery.
- Protect `backup/immutable-2026-10-25` manually; it remains unprotected.

## Manual steps required from the owner
1. Do not run another Buffer smoke test; the queue is already full and the smoke evidence is a carousel.
2. In GitHub Settings → Branches, protect `backup/immutable-2026-10-25`: prevent deletion, prevent force-push, and require pull requests.
3. Keep `buffer_max=10` disabled.
4. Do not retry any pending or ambiguous claim without provider reconciliation.
5. For any future provider test, capture the workflow run URL and independently verify the external Buffer item before reporting success.

## Verification boundary
Offline and hardening checks establish deterministic code behavior only. They cannot guarantee provider delivery, factual truth, or final rendered media quality.
