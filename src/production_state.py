"""Explicit persistence contracts for production call sites."""
from __future__ import annotations
from pathlib import Path
from .atomic_state import load_json, save_json, save_text
from .idempotency import claim, finish, get, fingerprint, reconcile


def save_json_state(path, value):
    save_json(Path(path), value)


def save_text_state(path, value):
    save_text(Path(path), value)


def begin_claim(path, operation, *identity, metadata=None):
    key = fingerprint(operation, *identity)
    return key, claim(Path(path), key, metadata or {"operation": operation, "identity": list(identity)})


def mark_ambiguous(path, key, reason):
    finish(Path(path), key, "", status="ambiguous")
    state = load_json(Path(path), {})
    state.setdefault("manual_review", {})[key] = {"reason": str(reason)[:500]}
    save_json(Path(path), state)


def mark_failed(path, key, reason):
    finish(Path(path), key, "", status="failed")
    state = load_json(Path(path), {})
    state.setdefault("failures", {})[key] = {"reason": str(reason)[:500]}
    save_json(Path(path), state)


def mark_succeeded(path, key, external_id):
    reconcile(Path(path), key, external_id)


def retry_allowed(path, key):
    return get(Path(path), key) is None
