import unittest

from src.cinematic_short import STORY


class CinematicStoryTests(unittest.TestCase):
    def test_story_has_short_film_structure(self):
        self.assertEqual(STORY["language"], "en-US")
        self.assertEqual(len(STORY["scenes"]), 4)
        self.assertEqual(len(STORY["dialogue"]), 4)
        self.assertGreaterEqual(sum(s["seconds"] for s in STORY["scenes"]), 10.0)
        for scene in STORY["scenes"]:
            self.assertIn("prompt", scene)
            self.assertGreaterEqual(scene["seconds"], 2.5)
            self.assertIn("same", scene["prompt"].lower())
            self.assertIn("photorealistic", scene["prompt"].lower())
            self.assertTrue(scene["dialogue"])

    def test_character_bible_exists(self):
        self.assertIn("man", STORY["characters"])
        self.assertIn("woman", STORY["characters"])
        self.assertGreater(len(STORY["characters"]["man"]), 30)
        self.assertGreater(len(STORY["characters"]["woman"]), 30)

    def test_story_is_english(self):
        lines = [line for _, line in STORY["dialogue"]]
        self.assertTrue(any("letter" in line.lower() for line in lines))
        self.assertTrue(all(any(ch.isascii() for ch in line) for line in lines))

    def test_video_provider_router_is_configurable(self):
        from src.video_router import PROVIDERS, _provider_order
        self.assertEqual([name for name, _ in PROVIDERS], ["ltx2", "wan22"])
        self.assertEqual(_provider_order(), ["ltx2", "wan22"])


if __name__ == "__main__":
    unittest.main()
