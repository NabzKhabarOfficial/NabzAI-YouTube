"""Small runtime-only safety patches for the official Buffer path."""
from __future__ import annotations

import json
from datetime import datetime
from functools import wraps


def install(module) -> None:
    if getattr(module, "_current_main_buffer_safety", False):
        return

    original_save_state = module.save_state
    original_scheduled_posts = module.scheduled_posts

    def save_state(state):
        try:
            from src.atomic_state import save_json
            save_json(module.STATE_FILE, state)
        except Exception:
            original_save_state(state)

    @wraps(original_scheduled_posts)
    def scheduled_posts(org, channel):
        try:
            return original_scheduled_posts(org, channel)
        except module.BufferError:
            # A failed queue read is not proof that overdue posts were published.
            # Return every locally scheduled record, including overdue ones, so
            # run() keeps them scheduled until Buffer can be reconciled.
            state = module.load_json(module.STATE_FILE, {})
            fallback = []
            for rec in (state.get("sent") or {}).values():
                if rec.get("status") == "scheduled" and rec.get("post_id"):
                    fallback.append({"id": rec["post_id"], "dueAt": rec.get("due", "")})
            module.log("queue read failed; preserving local scheduled records pending reconciliation")
            return fallback

    module.save_state = save_state
    module.scheduled_posts = scheduled_posts
    module._current_main_buffer_safety = True
