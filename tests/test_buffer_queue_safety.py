import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src import ig_buffer
from src.ig_runtime_safety import install


class BufferQueueSafetyTests(unittest.TestCase):
    def test_queue_read_failure_preserves_overdue_local_records(self):
        with tempfile.TemporaryDirectory() as td:
            state_file = Path(td) / "ig_buffer_state.json"
            state_file.write_text(json.dumps({"sent": {
                "old": {"post_id": "buffer-old", "due": "2020-01-01T00:00:00+00:00", "status": "scheduled"}
            }}), encoding="utf-8")
            original_state = ig_buffer.STATE_FILE
            original_scheduled = ig_buffer.scheduled_posts
            try:
                ig_buffer.STATE_FILE = state_file
                ig_buffer.scheduled_posts = lambda org, channel: (_ for _ in ()).throw(ig_buffer.BufferError("read failed"))
                install(ig_buffer)
                rows = ig_buffer.scheduled_posts("org", "channel")
                self.assertEqual(rows, [{"id": "buffer-old", "dueAt": "2020-01-01T00:00:00+00:00"}])
            finally:
                ig_buffer.STATE_FILE = original_state
                ig_buffer.scheduled_posts = original_scheduled
                ig_buffer._current_main_buffer_safety = False


if __name__ == "__main__":
    unittest.main()
