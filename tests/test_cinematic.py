import unittest

from src.cinematic_short import STORY


class CinematicStoryTests(unittest.TestCase):
    def test_story_has_meaningful_structure(self):
        self.assertEqual(STORY["title"], "The Last Letter")
        self.assertEqual(len(STORY["scenes"]), 3)
        self.assertEqual(len(STORY["dialogue"]), 3)
        for scene in STORY["scenes"]:
            self.assertIn("prompt", scene)
            self.assertGreaterEqual(scene["seconds"], 2.0)
            self.assertIn("same", scene["prompt"].lower())

    def test_character_bible_exists(self):
        self.assertIn("man", STORY["characters"])
        self.assertIn("woman", STORY["characters"])
        self.assertGreater(len(STORY["characters"]["man"]), 30)
        self.assertGreater(len(STORY["characters"]["woman"]), 30)


if __name__ == "__main__":
    unittest.main()
