"""Claim-guarded Buffer workflow entry point.

Buffer has no reliable idempotency key in the current GraphQL mutation path.
A completed sync is an idempotent no-op; pending or ambiguous syncs are hard
stops and require manual reconciliation before another mutation attempt.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from src import ig_buffer
from src.production_state import begin_claim, get, mark_ambiguous, mark_succeeded

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "content" / "publication_claims.json"
PACK = ROOT / "content" / "ig_pack_state.json"


def _state_digest() -> str:
    raw = PACK.read_bytes() if PACK.exists() else b"{}"
    return hashlib.sha256(raw).hexdigest()[:24]


def run() -> int:
    digest = _state_digest()
    key, fresh = begin_claim(CLAIMS, "buffer_sync", digest,
                              metadata={"provider": "buffer", "pack_state_sha256_24": digest})
    if not fresh:
        current = get(CLAIMS, key)
        if current and current.status == "succeeded":
            print(f"BUFFER_CLAIM_ALREADY_CONFIRMED: {key}")
            return 0
        raise RuntimeError("Buffer sync claim already exists; reconcile content/publication_claims.json before rerun")
    try:
        result = ig_buffer.main()
    except Exception as exc:
        mark_ambiguous(CLAIMS, key, f"Buffer run outcome unknown: {type(exc).__name__}: {exc}")
        raise
    mark_succeeded(CLAIMS, key, f"buffer-run:{digest}")
    print(f"BUFFER_CLAIM_CONFIRMED: {key}")
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(run())
