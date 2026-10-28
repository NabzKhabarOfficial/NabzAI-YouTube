"""Durable, transaction-safe claim registry for external publication calls."""
from __future__ import annotations
import fcntl
import hashlib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from .atomic_state import load_json, save_json

@dataclass(frozen=True)
class Claim:
    key: str
    status: str
    external_id: str = ""
    metadata: dict | None = None

def fingerprint(kind: str, *parts: str) -> str:
    return hashlib.sha256("\x1f".join([kind, *(str(p or "").strip() for p in parts)]).encode("utf-8")).hexdigest()

@contextmanager
def _locked(path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(str(target) + ".lock", "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

def _claims(state):
    claims = state.get("claims")
    if claims is None:
        claims = {}; state["claims"] = claims
    if not isinstance(claims, dict):
        raise RuntimeError("publication claims registry is corrupt; refusing to continue")
    return claims

def get(path, key):
    value = (load_json(path, {}).get("claims") or {}).get(key)
    if not isinstance(value, dict): return None
    return Claim(key, str(value.get("status", "pending")), str(value.get("external_id", "")), value.get("metadata") or {})

def claim(path, key, metadata=None):
    with _locked(path):
        state = load_json(path, {})
        claims = _claims(state)
        existing = claims.get(key)
        if key in claims:
            # A deterministic provider rejection is safe to retry. Unknown or successful
            # outcomes remain immutable until a human/provider reconciliation confirms them.
            if isinstance(existing, dict) and existing.get("status") == "failed":
                claims[key] = {"status": "pending", "metadata": metadata or existing.get("metadata") or {}}
                save_json(path, state)
                return True
            return False
        claims[key] = {"status": "pending", "metadata": metadata or {}}
        save_json(path, state)
        return True

def finish(path, key, external_id, status="succeeded"):
    if status not in {"succeeded", "ambiguous", "failed"}: raise ValueError(f"invalid claim status: {status}")
    with _locked(path):
        state = load_json(path, {})
        claims = _claims(state)
        claims[key] = {**(claims.get(key) or {}), "status": status, "external_id": str(external_id or "")}
        save_json(path, state)

def reconcile(path, key, external_id):
    finish(path, key, external_id, "succeeded")
