"""Runtime safety patches for the official Buffer path."""
from __future__ import annotations
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
            rows = original_scheduled_posts(org, channel)
            module._buffer_queue_known = True
            return rows
        except module.BufferError as exc:
            # Local state is useful for preserving records, but it is not proof
            # of the provider queue. The caller must not mutate Buffer while
            # the provider-side queue is unknown.
            state = module.load_json(module.STATE_FILE, {})
            fallback = []
            for rec in (state.get("sent") or {}).values():
                if rec.get("status") == "scheduled" and rec.get("post_id"):
                    fallback.append({"id": rec["post_id"], "dueAt": rec.get("due", "")})
            module._buffer_queue_known = False
            module.log("queue read failed; preserving local scheduled records; mutations blocked pending reconciliation")
            return fallback

    module.save_state = save_state
    module.scheduled_posts = scheduled_posts
    module._buffer_queue_known = True
    module._current_main_buffer_safety = True
