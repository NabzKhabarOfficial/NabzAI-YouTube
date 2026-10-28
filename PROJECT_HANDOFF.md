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
- Live provider verification is not proven by the current repository checks.

## PR audit: 2026-10-28
- [PR #3](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/3), Buffer safety: open, stale against current `main`; no current-main CI result proves it safe to merge.
- [PR #5](https://github.com/NabzKhabarOfficial/NabzAI-YouTube/pull/5), production hardening: open and diverged from current `main`; historical offline and hardening checks passed on the old head only.
- Neither PR was merged. No production code was changed from those PRs. Rebase or recreate the fixes on current `main`, then run current CI before merging.

## Instagram smoke-test boundary
- The supplied report says no Buffer smoke test was executed and `buffer_max` was not changed.
- Treat that report as an audit result, not proof of a live provider success.
- Keep `buffer_max=10` disabled for broad rollout. The first real test remains `per_day=2`, `buffer_max=1`, empty-week input, after current-main safety checks are green.
- Do not claim a successful Instagram publication until Buffer state and the resulting external item are independently verified.

## Known non-blocking maintenance debt
- Some metrics/report and pack/published state writers still use direct writes instead of the shared atomic helper. They do not bypass publication claims, but should be migrated in a maintenance pass.
- Instagram Stories in `instagram-v1.yml` remain intentionally dry-run.
- External dashboard state is stronger evidence than repository state alone.

## Required continuation
1. Protect the backup branch in GitHub.
2. Rebase or recreate PR #3 and PR #5 on current `main`.
3. Run fresh offline/hardening checks on the rebased heads.
4. Run only the one-item `buffer_max=1` smoke test and verify provider state.
5. Keep `buffer_max=10` blocked until that evidence is clean.
6. Never rerun a pending or ambiguous claim without provider reconciliation.
