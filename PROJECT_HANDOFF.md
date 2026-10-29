# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work.
- Telegram news-channel code belongs in `NabzKhabar`.

## Verified state
- Offline tests and hardening checks are green on the current hardening line.
- The 150 staged English stories load into runtime.
- Buffer queue safety blocks mutations when the provider queue is unknown.
- YouTube scheduled claims require provider `publishAt` confirmation; a private fallback is not marked succeeded.
- The successful smoke-test evidence was a Carousel (`car_behistun`), not a Reel.
- 10 active scheduled Buffer records remain internally matched to succeeded claims.

## Latest code work
- Added `src/effective_bank.py` as the canonical read-only bank API.
- Added regression coverage proving the effective API contains all staged batch stories and unique IDs.

## Remaining hardening
- Route `scripts/review_short.py`, `src/yt_comment.py`, and `src/yt_stats.py` through `src.effective_bank` instead of reading `mysteries.json` directly.
- Enforce Persian 50–95 word and hook-length rules.
- Use `file_stem()` in schedule CSV generation for overridden plan items.
- Clear stale Buffer `last_fail` after a successful run or preserve it only as historical data.
- Add durable idempotency/reconciliation to direct Meta before live publishing.
- Protect `backup/immutable-2026-10-25` manually if the repository plan permits it; current integration reports it unprotected.

## Operational boundary
- Do not run another Buffer smoke test: the queue is full and the smoke evidence is a carousel.
- Keep `buffer_max=10` disabled.
- Never retry pending or ambiguous claims without provider reconciliation.
- Offline checks do not prove Instagram, Meta, YouTube or Telegram delivery.
