# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work.
- Telegram news-channel code belongs in `NabzKhabar`.

## Audit snapshot
- Audited current `main` on 2026-10-28.
- Main now includes the safe Buffer default, runtime batch loader, and explicit runtime batch test.
- Open PRs still requiring review: [#3](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/3), [#4](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/4), [#5](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/5). Do not merge any of them wholesale.

## Changes applied in this audit
- Guarded Buffer installs `ig_runtime_safety` before running.
- Guarded Buffer distinguishes deterministic provider rejection (`failed`) from transport uncertainty (`ambiguous`).
- Scheduled Buffer runs default to one new item. Broad batches require an explicit manual choice of 10.
- `mystery_short.load_bank()` loads every `content/mysteries_batch*.json` file and fails closed on invalid required batch entries.
- `scripts/guard_today.py` now uses the same batch population for repeat protection.

## Verification status
- Offline and hardening GitHub Actions runs reported success for the workflow-default change: [offline run](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/actions/runs/40793044886), [hardening run](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/actions/runs/40793044874).
- The runtime batch-loader verification run was still pending at the last handoff; verify its final result before any live smoke test.
- No live Buffer, Meta, YouTube, GitHub Pages or final audio/video verification has been performed.

## Remaining manual-only items
1. Protect `backup/immutable-2026-10-25` against deletion and force-push. It is currently unprotected.
2. Verify the runtime batch test and the full current-main offline suite are green.
3. Run exactly one Buffer smoke test with `per_day=2`, `buffer_max=1`.
4. Independently verify the Buffer item, `content/ig_buffer_state.json`, and `content/publication_claims.json`.
5. Keep `buffer_max=10` disabled until that evidence is clean.
6. Never retry a pending or ambiguous claim without provider reconciliation.

## Current limitation
Branch protection and full backup immutability require GitHub repository administration access not available through the current connection.

## Guarantee boundary
Offline checks establish deterministic code behavior only. They cannot guarantee provider delivery, factual truth, or final rendered media quality.
