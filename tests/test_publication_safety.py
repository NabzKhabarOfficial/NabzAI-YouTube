import unittest
from pathlib import Path


class PublicationSafetyTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_youtube_guard_contains_single_insert_circuit_breaker(self):
        text = (self.ROOT / "src" / "guarded_youtube_upload.py").read_text(encoding="utf-8")
        self.assertIn("second YouTube videos.insert blocked", text)
        self.assertIn("_single_insert_only", text)
        self.assertIn("mark_ambiguous", text)

    def test_buffer_mutations_are_single_attempt_and_deletes_are_claimed(self):
        text = (self.ROOT / "src" / "guarded_buffer.py").read_text(encoding="utf-8")
        self.assertIn("_mutation_once", text)
        self.assertIn("ig_buffer.delete_post = guarded_delete", text)
        self.assertIn('status="ambiguous"', text)

    def test_workflow_runs_this_suite(self):
        text = (self.ROOT / ".github" / "workflows" / "offline-tests.yml").read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover -s tests -v", text)


if __name__ == "__main__":
    unittest.main()
