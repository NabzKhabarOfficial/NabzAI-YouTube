# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work.
- Telegram news-channel code belongs in `NabzKhabar`.

## Audit snapshot
- Audited current `main` on 2026-10-28.
- Open PRs still requiring review: [#3](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/3), [#4](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/4), [#5](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/5).
- Do not merge any of them wholesale. Recreate only targeted fixes against current `main`.

## Changes applied in this audit
- Guarded Buffer now installs `ig_runtime_safety` before running, so overdue local posts are preserved when the provider queue cannot be read.
- Guarded Buffer distinguishes deterministic provider rejection (`failed`) from transport uncertainty (`ambiguous`). Ambiguous claims still stop blind retries.
- The workflow file could not be changed through the connected GitHub permission because workflow-edit scope is unavailable. The manual one-line change is recorded below.
- Publication claims remain durable repository state, but a successful external mutation followed by a failed Git push can still require provider reconciliation.

## Content and runtime findings still open
- The ten validated English batch files must be included in the effective runtime bank and in `guard_today`; validation alone is not proof of runtime availability.
- Meta/Instagram publisher POST mutations still need idempotency and provider reconciliation before live publishing.
- YouTube/Buffer external success followed by state-push failure can duplicate on a fresh runner without deterministic provider lookup.
- Several metrics, reports and pack state writers still bypass the shared atomic helper.
- Persian story banks contain known language/wording defects and have no machine-verifiable source citations.
- Live Buffer, Meta, YouTube, GitHub Pages and final audio/video checks were not performed.

## Safe offline checks
```bash
python -m compileall -q src scripts instagram
PYTHONPATH=. NABZ_VOICE_CHECK=0 python -m unittest discover -s tests -v
python scripts/validate_ig_batches.py
PYTHONPATH=. NABZ_VOICE_CHECK=0 python -m instagram.runner --check
```

## Manual-only continuation
1. Run the offline suite on the exact current `main` commit.
2. Verify the effective runtime bank includes every staged batch story.
3. In `.github/workflows/ig-pack.yml`, change the Buffer environment default to `${{ inputs.buffer_max || '1' }}` and keep the manual options ordered `1`, then `10`.
4. Run one manual Buffer smoke test with `per_day=2`, `buffer_max=1` only.
5. Independently verify the resulting Buffer item and repository claim.
6. Keep `buffer_max=10` disabled until that evidence is clean.
7. Never retry a pending or ambiguous claim without provider reconciliation.

## Guarantee boundary
Offline checks can establish deterministic code behavior only. They cannot guarantee Telegram/Buffer/Meta/YouTube delivery, external provider state, factual truth of stories, or final rendered media quality.
