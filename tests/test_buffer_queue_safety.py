import json
import os
import subprocess
import sys
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


    def test_provider_defaults_to_one_new_reel_per_run(self):
        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env.pop("NABZ_BUFFER_MAX_NEW", None)
        result = subprocess.run(
            [sys.executable, "-c", "from src.ig_buffer import MAX_NEW; print(MAX_NEW)"],
            cwd=root, env=env, text=True, capture_output=True, check=True,
        )
        self.assertEqual(result.stdout.strip(), "1")


    def test_provider_clamps_larger_environment_values_to_one(self):
        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["NABZ_BUFFER_MAX_NEW"] = "2"
        result = subprocess.run(
            [sys.executable, "-c", "from src.ig_buffer import MAX_NEW; print(MAX_NEW)"],
            cwd=root, env=env, text=True, capture_output=True, check=True,
        )
        self.assertEqual(result.stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main()
