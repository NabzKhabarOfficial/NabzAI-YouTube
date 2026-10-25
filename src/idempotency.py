"""Durable claim registry for external publication calls."""
from __future__ import annotations
import hashlib
from .atomic_state import load_json, save_json


def fingerprint(kind: str, *parts: str) -> str:
    raw = "\x1f".join([kind, *(str(x or "").strip() for x in parts)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def claim(path, key: str, metadata=None) -> bool:
    state = load_json(path, {})
    claims = state.setdefault("claims", {})
    if key in claims:
        return False
    claims[key] = {"status": "pending", "metadata": metadata or {}}
    save_json(path, state)
    return True


def finish(path, key: str, external_id: str, status="succeeded") -> None:
    state = load_json(path, {})
    claims = state.setdefault("claims", {})
    claims[key] = {**claims.get(key, {}), "status": status, "external_id": external_id}
    save_json(path, state)
