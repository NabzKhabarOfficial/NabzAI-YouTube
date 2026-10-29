# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work.
- Telegram news-channel code belongs in `NabzKhabar`.

## Audit snapshot
- Audited current `main` on 2026-10-28.
- Main includes the safe Buffer default, canonical runtime batch loader, batch-aware repeat guard, and guarded Buffer runtime safety.
- Open PRs still requiring review: [#3](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/3), [#4](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/4), [#5](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/5). Do not merge any of them wholesale.

## Changes applied in this audit
- Guarded Buffer installs `ig_runtime_safety` before running.
- Guarded Buffer distinguishes deterministic provider rejection (`failed`) from transport uncertainty (`ambiguous`).
- Scheduled Buffer runs default to one new item. Broad batches require an explicit manual choice of 10.
- `mystery_short.load_bank()` loads every `content/mysteries_batch*.json` file and fails closed on invalid required batch entries.
- `scripts/guard_today.py` now uses the same batch population for repeat protection.
- `sitecustomize.py` no longer leaves the Instagram-only `_BankAddFinder` wrapper installed during tests and non-pack runs. That stale wrapper was masking the canonical loader and caused the 150-story runtime assertion to fail.

## Verification status
- Earlier offline and hardening runs passed for the Buffer safety/default changes.
- The 150-story runtime test failed because the import hook replaced the fixed `mystery_short.load_bank()` with an older wrapper that loaded only `mysteries.json` plus `mysteries_add.json`.
- The import-hook fix is now on `main`; a fresh offline run must be green before any live smoke test.
- No live Buffer, Meta, YouTube, GitHub Pages or final audio/video verification has been performed.

## Remaining manual-only items
1. Run the fresh offline test suite on the latest `main` commit and confirm `test_all_150_batch_stories_are_loaded_into_runtime` passes.
2. Protect `backup/immutable-2026-10-25` against deletion and force-push. It is currently unprotected and requires repository administration access.
3. Run exactly one Buffer smoke test with `per_day=2`, `buffer_max=1` only after the fresh suite is green.
4. Independently verify the Buffer item, `content/ig_buffer_state.json`, and `content/publication_claims.json`.
5. Keep `buffer_max=10` disabled until that evidence is clean.
6. Never retry a pending or ambiguous claim without provider reconciliation.

## Current limitation
Branch protection and full backup immutability require GitHub repository administration access not available through the current connection.

## Guarantee boundary
Offline checks establish deterministic code behavior only. They cannot guarantee provider delivery, factual truth, or final rendered media quality.
