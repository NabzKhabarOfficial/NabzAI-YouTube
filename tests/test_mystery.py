import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from src import mystery_short as m


class MysteryShortTests(unittest.TestCase):
    def test_bank_is_valid_and_shorts_sized(self):
        stories = m.load_bank()
        self.assertGreaterEqual(len(stories), 14)
        for s in stories:
            words = sum(len(b["text"].split()) for b in s["beats"])
            self.assertLessEqual(words / 2.7, 59, s["id"])  # ~2.7 words/s narration

    def test_pick_cycles_without_repeats(self):
        stories = m.load_bank()
        with TemporaryDirectory() as tmp:
            state = Path(tmp) / "published.json"
            state.write_text(json.dumps({"published": ["x"]}))
            seen = []
            for _ in range(len(stories)):
                s = m.pick_story(stories, m.load_state(state))
                seen.append(s["id"])
                m.record_story(s["id"], state)
            self.assertEqual(len(set(seen)), len(stories))
            again = m.pick_story(stories, m.load_state(state))
            self.assertEqual(again["id"], seen[0])
            self.assertEqual(json.loads(state.read_text())["published"], ["x"])

    def test_punctuation_and_chunks(self):
        words = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.25, "beat": 0}
                 for i, t in enumerate("It was the Mary Celeste Her captain his two year old daughter".split())]
        m.mark_punctuation("It was the Mary Celeste. Her captain, his two-year-old daughter.", words)
        chunks = [[w["text"] for w in c] for c in m.chunk_words(words)]
        self.assertIn(["Mary", "Celeste"], chunks)
        self.assertTrue(all(len(c) <= 3 for c in chunks))

    def test_segments_keep_audio_sync(self):
        d = [6.0, 5.5, 7.0]
        lengths = m.segment_lengths(d)
        total = sum(lengths) - m.XFADE * (len(d) - 1)
        self.assertAlmostEqual(total, sum(d), places=6)

    def test_music_and_mix(self):
        music = m.make_music(3.0, 7)
        self.assertEqual(music.shape, (int(3.0 * m.SR), 2))
        voice = np.zeros(int(2.5 * m.SR), dtype=np.float32)
        out = m.mix(voice, music)
        self.assertEqual(out.shape[0], len(voice))
        self.assertLessEqual(float(np.max(np.abs(out))), 1.0)


class UploaderCredentialTests(unittest.TestCase):
    def test_separate_secrets_and_curly_quotes(self):
        try:
            from src.youtube_uploader import load_credential_info
        except ImportError:
            self.skipTest("google client libraries not installed")
        env = {"YOUTUBE_CLIENT_ID": " 1-a.apps.googleusercontent.com ", "YOUTUBE_CLIENT_SECRET": "GOCSPX-x",
               "YOUTUBE_REFRESH_TOKEN": "1//abc"}
        self.assertEqual(load_credential_info(env=env)["client_id"], "1-a.apps.googleusercontent.com")
        curly = "{\u201cclient_id\u201d:\u201c1-a.apps.googleusercontent.com\u201d,\u201cclient_secret\u201d:\u201cs\u201d,\u201crefresh_token\u201d:\u201c1//r\u201d}"
        info = load_credential_info(env={"YOUTUBE_TOKEN": curly})
        self.assertEqual(info["refresh_token"], "1//r")
        self.assertEqual(info["token_uri"], "https://oauth2.googleapis.com/token")


if __name__ == "__main__":
    unittest.main()
