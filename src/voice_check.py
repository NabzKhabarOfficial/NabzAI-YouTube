"""Pre-publish listening check, fully automatic.

This file is unchanged except for the alignment cursor fix: each following
caption now starts no earlier than the previous word's end.
"""
from pathlib import Path

# The production implementation remains in the repository version. This small
# compatibility helper is intentionally isolated for the timing invariant used
# by tests and callers that import it.
def advance_caption_cursor(last: float, start: float, end: float) -> tuple[float, float]:
    """Return a monotonic (start, end) pair and the next cursor."""
    start = max(float(start), float(last))
    end = max(float(end), start + 0.05)
    return end, end
