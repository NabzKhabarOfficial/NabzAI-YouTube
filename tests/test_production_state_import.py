import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import guarded_buffer, guarded_meta, guarded_youtube_upload, production_state


class ProductionStateImportTests(unittest.TestCase):
    def test_guarded_modules_import_and_text_writer_is_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.txt"
            production_state.save_text_state(path, "ok\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "ok\n")
            self.assertEqual(list(path.parent.glob("*.tmp")), [])
        self.assertTrue(guarded_buffer.run)
        self.assertTrue(guarded_meta.publish_story)
        self.assertTrue(guarded_youtube_upload.run)

    def test_buffer_failure_stays_ambiguous_when_main_swallows_exception(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pack = root / "pack.json"
            state = root / "buffer.json"
            pack.write_text('{"weeks": {}}', encoding="utf-8")
            state.write_text('{"fail_streak": 1, "last_fail": "provider timeout"}', encoding="utf-8")
            old_claims, old_pack, old_state = guarded_buffer.CLAIMS, guarded_buffer.PACK, guarded_buffer.BUFFER_STATE
            guarded_buffer.CLAIMS, guarded_buffer.PACK, guarded_buffer.BUFFER_STATE = root / "claims.json", pack, state
            try:
                with patch.object(guarded_buffer.ig_buffer, "main", return_value=0):
                    with self.assertRaisesRegex(RuntimeError, "ambiguous"):
                        guarded_buffer.run()
            finally:
                guarded_buffer.CLAIMS, guarded_buffer.PACK, guarded_buffer.BUFFER_STATE = old_claims, old_pack, old_state


if __name__ == "__main__":
    unittest.main()
