"""Durable claim registry for external publication calls."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from .atomic_state import load_json, save_json

@dataclass(frozen=True)
class Claim:
    key: str
    status: str
    external_id: str = ""
    metadata: dict | None = None

def fingerprint(kind: str, *parts: str) -> str:
    return hashlib.sha256("\x1f".join([kind, *(str(p or "").strip() for p in parts)]).encode("utf-8")).hexdigest()

def get(path, key):
    value = (load_json(path, {}).get("claims") or {}).get(key)
    if not isinstance(value, dict): return None
    return Claim(key, str(value.get("status", "pending")), str(value.get("external_id", "")), value.get("metadata") or {})

def claim(path, key, metadata=None):
    state = load_json(path, {}); claims = state.setdefault("claims", {})
    if key in claims: return False
    claims[key] = {"status": "pending", "metadata": metadata or {}}
    save_json(path, state); return True

def finish(path, key, external_id, status="succeeded"):
    if status not in {"succeeded", "ambiguous", "failed"}: raise ValueError(f"invalid claim status: {status}")
    state = load_json(path, {}); claims = state.setdefault("claims", {})
    claims[key] = {**(claims.get(key) or {}), "status": status, "external_id": str(external_id or "")}
    save_json(path, state)

def reconcile(path, key, external_id):
    finish(path, key, external_id, "succeeded")
