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
- YouTube uses Kokoro `am_michael` with deepening and story-level duplicate protection.
- Instagram Reels/Buffer uses per-operation durable claims for reels, stories, and carousels.
- Missing Buffer hosting/provider secrets fail closed.
- Succeeded claims reuse external IDs; pending/ambiguous claims stop blind retries.
- Live user verification confirmed green workflows and no duplicate Buffer post in the smoke run.

## Known non-blocking maintenance debt
- Some metrics/report and pack/published state writers still use direct writes instead of the shared atomic helper. They do not bypass publication claims, but should be migrated in a maintenance pass.
- Instagram Stories in `instagram-v1.yml` remain intentionally dry-run.
- External dashboard state is stronger evidence than repository state alone.

## Required continuation
1. Protect the backup branch in GitHub.
2. Keep `buffer_max=10` for routine runs only after the smoke run remains clean.
3. Never rerun a pending or ambiguous claim without provider reconciliation.
4. Run fresh offline/hardening checks when production code changes.
