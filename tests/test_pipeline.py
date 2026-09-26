import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.story_engine import validate_topic, build_episode
from src.quality_gate import validate_scene_set


class PipelineTests(unittest.TestCase):
    def test_topic_requires_content(self):
        with self.assertRaises(RuntimeError):
            validate_topic({"title": "", "sections": []})

    def test_episode_has_real_story_structure(self):
        topic = {
            "id": "test-topic",
            "title": "Test Workflow",
            "hook": "Can this workflow actually save time?",
            "angle": "measured experiment",
            "sections": ["input", "output"],
            "subjects": ["input", "output"],
            "tags": ["AI"],
        }
        episode = build_episode(topic, 6)
        self.assertGreaterEqual(episode["word_count"], 780)
        self.assertIn("hook", episode["scene_plan"][0]["kind"])
        self.assertEqual(episode["scene_plan"][0]["kind"], "hook")
        self.assertEqual(episode["scene_plan"][-1]["kind"], "cliffhanger")

    def test_scene_gate_rejects_too_few_shots(self):
        with TemporaryDirectory() as tmp:
            paths = []
            for i in range(3):
                p = Path(tmp) / f"{i}.png"
                p.write_bytes(b"x" * 6000)
                paths.append(p)
            with self.assertRaises(RuntimeError):
                validate_scene_set(paths)


if __name__ == "__main__":
    unittest.main()
