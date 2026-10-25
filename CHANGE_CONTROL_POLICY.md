# NabzAI-YouTube Change-Control and Publication Safety Policy

## Immutable backup
- Backup branch: `backup/immutable-2026-10-25`
- Backup source commit: `caf8729b81447eff280595ed9016b174a6d9a748`
- Treat the backup branch as read-only. Never force-push, rebase, delete, or amend it.
- GitHub branch protection must require pull requests, prevent force-pushes, and restrict deletion for backup branches. A branch name alone is not technically immutable.

## High-risk changes requiring review
- YouTube upload, Buffer mutations, claims, external IDs, workflow files, voice selection, schedule logic, public hosting, secrets, or state schemas.
- Never rerun a workflow when a claim is `pending` or `ambiguous` without reconciling the external provider first.

## Required checks before production
1. Offline and hardening workflows on the exact target SHA.
2. Static diff review against the backup branch.
3. YouTube: private visibility and story-level duplicate guard.
4. Instagram: one-Reel `buffer_max=1` smoke run before `buffer_max=10`.
5. Confirm one external post per succeeded claim and no duplicate Buffer mutation.

## Publication invariants
- Build state is not recorded as published before confirmed external success.
- A succeeded claim reuses its external ID and never mutates the provider again.
- Unknown provider outcomes become `ambiguous` and stop automatic retry.
- Missing `BUFFER_API_KEY`, `REELS_PAT`, or YouTube credentials must fail the job, never produce a green no-op.
- Instagram Stories in `instagram-v1.yml` remain dry-run unless a separately reviewed workflow enables live publishing.
