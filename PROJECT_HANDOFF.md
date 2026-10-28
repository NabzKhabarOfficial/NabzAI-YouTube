# NabzAI-YouTube Project Handoff

## Scope
- This private repository owns Instagram and YouTube work.
- Telegram news-channel code belongs in `NabzKhabar`.

## Backup and change control
- Immutable-backup candidate branch: `backup/immutable-2026-10-25`
- Backup source snapshot: `caf8729b81447eff280595ed9016b174a6d9a748`
- Backup policy: `CHANGE_CONTROL_POLICY.md`
- The backup branch must be protected in GitHub against force-push and deletion. A branch name alone is not technically immutable.

## Production status
- The 150 staged English/Persian mystery stories are merged on `main`; validation and post-merge checks are green.
- YouTube uses Kokoro `am_michael` with deepening and story-level duplicate protection.
- Instagram Reels/Buffer uses per-operation durable claims for reels, stories, and carousels.
- Missing Buffer hosting/provider secrets fail closed.
- Succeeded claims reuse external IDs; pending/ambiguous claims stop blind retries.
- PR #8 was recreated from current `main`, passed offline CI, and merged. It preserves locally scheduled Buffer records, including overdue records, when the Buffer queue cannot be read, and routes Buffer state writes through atomic JSON persistence.
- Live provider verification is not proven by the current repository checks.

## PR audit: 2026-10-28
- [PR #3](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/3), Buffer safety: remains open and stale. Its highest-confidence queue-safety fix was recreated as [PR #8](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/8) and merged on current `main`.
- [PR #5](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/5), production hardening: remains open and diverged. Do not merge wholesale; current `main` already contains newer guarded paths.

## Instagram smoke-test boundary
- No live Buffer smoke test has been executed or independently verified.
- Keep `buffer_max=10` disabled for broad rollout. The first real test remains `per_day=2`, `buffer_max=1`, empty-week input, after current-main safety checks are green.
- Do not claim a successful Instagram publication until Buffer state and the resulting external item are independently verified.

## Known non-blocking maintenance debt
- Some metrics/report and pack/published state writers still use direct writes instead of the shared atomic helper. They do not bypass publication claims, but should be migrated in a maintenance pass.
- Instagram Stories in `instagram-v1.yml` remain intentionally dry-run.
- External dashboard state is stronger evidence than repository state alone.

## Required continuation
1. Protect the backup branch in GitHub.
2. Recreate only selected PR #5 fixes on current `main`, with fresh tests.
3. Run only the one-item `buffer_max=1` smoke test and verify provider state.
4. Keep `buffer_max=10` blocked until that evidence is clean.
5. Never rerun a pending or ambiguous claim without provider reconciliation.
