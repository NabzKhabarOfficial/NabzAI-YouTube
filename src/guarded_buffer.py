"""Claim-guarded Buffer workflow entry point."""
from __future__ import annotations
import hashlib
from pathlib import Path
from src import ig_buffer
from src.production_state import begin_claim, get, mark_ambiguous, mark_succeeded
ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "content" / "publication_claims.json"
PACK = ROOT / "content" / "ig_pack_state.json"
BUFFER_STATE = ROOT / "content" / "ig_buffer_state.json"

def _state_digest():
    return hashlib.sha256(PACK.read_bytes() if PACK.exists() else b"{}").hexdigest()[:24]

def run():
    digest = _state_digest()
    key, fresh = begin_claim(CLAIMS, "buffer_sync", digest, metadata={"provider":"buffer","pack_state_sha256_24":digest})
    if not fresh:
        current = get(CLAIMS, key)
        if current and current.status == "succeeded":
            print(f"BUFFER_CLAIM_ALREADY_CONFIRMED: {key}"); return 0
        raise RuntimeError("Buffer sync claim already exists; reconcile content/publication_claims.json before rerun")
    try: result = ig_buffer.main()
    except Exception as exc:
        mark_ambiguous(CLAIMS, key, f"Buffer run outcome unknown: {type(exc).__name__}: {exc}"); raise
    state = ig_buffer.load_json(BUFFER_STATE, {})
    if int(state.get("fail_streak", 0) or 0) > 0:
        reason = str(state.get("last_fail") or "Buffer run recorded a failure")[:500]
        mark_ambiguous(CLAIMS, key, reason)
        raise RuntimeError("Buffer run recorded a failure; publication claim is ambiguous")
    mark_succeeded(CLAIMS, key, f"buffer-run:{digest}")
    print(f"BUFFER_CLAIM_CONFIRMED: {key}")
    return int(result or 0)

if __name__ == "__main__": raise SystemExit(run())
