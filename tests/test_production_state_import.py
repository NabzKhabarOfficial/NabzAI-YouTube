import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
