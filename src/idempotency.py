"""Durable claim registry for external publication calls.

A pending or ambiguous claim is a hard stop for blind retries. Callers must
look up the provider before creating another remote object, then call finish
with the confirmed external id or mark the claim failed explicitly.
"""
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
    raw = "\x1f".join([kind, *(str(part or "").strip() for part in parts)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get(path, key: str) -> Claim | None:
    state = load_json(path, {})
    value = (state.get("claims") or {}).get(key)
    if not isinstance(value, dict):
        return None
    return Claim(
        key=key,
        status=str(value.get("status", "pending")),
        external_id=str(value.get("external_id", "")),
        metadata=value.get("metadata") if isinstance(value.get("metadata"), dict) else {},
    )


def claim(path, key: str, metadata=None) -> bool:
    """Reserve a key exactly once. Existing keys must be reconciled, never retried blindly."""
    state = load_json(path, {})
    claims = state.setdefault("claims", {})
    if key in claims:
        return False
    claims[key] = {"status": "pending", "metadata": metadata or {}}
    save_json(path, state)
    return True


def finish(path, key: str, external_id: str, status="succeeded") -> None:
    if status not in {"succeeded", "ambiguous", "failed"}:
        raise ValueError(f"invalid claim status: {status}")
    state = load_json(path, {})
    claims = state.setdefault("claims", {})
    previous = claims.get(key) or {}
    claims[key] = {
        **previous,
        "status": status,
        "external_id": str(external_id or ""),
    }
    save_json(path, state)


def reconcile(path, key: str, external_id: str) -> None:
    """Close a pending/ambiguous claim after the provider lookup finds its object."""
    finish(path, key, external_id, status="succeeded")
