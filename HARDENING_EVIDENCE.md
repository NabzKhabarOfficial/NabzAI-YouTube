# Production hardening evidence

Branch: `brain/production-hardening`
PR: #5

## Latest verified CI before this commit
- Full offline workflow: PASS.
- Instagram and YouTube offline tests: PASS.
- Latest completed run before this commit: `https://github.com/NabzKhabarOfficial/NabzAI-YouTube/actions/runs/40159063377`

## This commit
- Adds `src/production_state.py`, a small tested contract for atomic state writes and terminal claim handling.
- Ambiguous mutations are persisted for manual review and are never automatically retryable.
- This is a contract layer, not a claim that every provider call site has already been migrated.

## Remaining blockers
- Wire the contract into YouTube, Buffer, and Meta call sites without blind full-file rewrites.
- Migrate direct stats/report/bank writers.
- Unify voice fail-closed behavior.
- Live provider verification remains NOT VERIFIED.
