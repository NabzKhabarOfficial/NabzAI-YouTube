import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.ig_runtime_safety import install


class BufferQueueSafetyTests(unittest.TestCase):
    def test_queue_read_failure_preserves_overdue_local_records(self):
        with tempfile.TemporaryDirectory() as td:
            state_file = Path(td) / "ig_buffer_state.json"
            state_file.write_text(json.dumps({"sent": {
                "old": {"post_id": "buffer-old", "due": "2020-01-01T00:00:00+00:00", "status": "scheduled"}
            }}), encoding="utf-8")

            class BufferError(RuntimeError):
                pass

            def original_scheduled(_org, _channel):
                raise BufferError("read failed")

            module = SimpleNamespace(
                BufferError=BufferError,
                STATE_FILE=state_file,
                load_json=lambda path, default: json.loads(Path(path).read_text(encoding="utf-8")),
                scheduled_posts=original_scheduled,
                save_state=lambda state: None,
                log=lambda message: None,
            )
            install(module)
            rows = module.scheduled_posts("org", "channel")
            self.assertEqual(rows, [{"id": "buffer-old", "dueAt": "2020-01-01T00:00:00+00:00"}])


if __name__ == "__main__":
    unittest.main()
