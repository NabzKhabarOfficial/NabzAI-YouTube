import json
import unittest

from src.effective_bank import ids
from src import ig_pack, mystery_short


class EffectiveBankTests(unittest.TestCase):
    def _batch_ids(self):
        batch_ids = set()
        for path in sorted((mystery_short.ROOT / "content").glob("mysteries_batch*.json")):
            rows = json.loads(path.read_text(encoding="utf-8"))
            batch_ids.update(str(row["id"]) for row in rows)
        return batch_ids

    def test_effective_bank_contains_all_staged_batches(self):
        self.assertTrue(self._batch_ids().issubset(ids()))

    def test_instagram_production_loader_contains_all_staged_batches(self):
        # This is the exact loader called by run_week(), not just the adapter in isolation.
        production_bank = ig_pack.load_english_bank()
        self.assertTrue(self._batch_ids().issubset(production_bank))
        self.assertEqual(len(production_bank), len(set(production_bank)))

    def test_effective_bank_ids_are_unique(self):
        loaded = list(ids())
        self.assertEqual(len(loaded), len(set(loaded)))

    def test_new_persian_story_pairs_are_complete_and_valid(self):
        batch_path = mystery_short.ROOT / "content" / "mysteries_batch11.json"
        rows = json.loads(batch_path.read_text(encoding="utf-8"))
        fa = json.loads((mystery_short.ROOT / "content" / "mysteries_fa.json").read_text(encoding="utf-8"))["stories"]
        notes = json.loads((mystery_short.ROOT / "content" / "story_notes_fa.json").read_text(encoding="utf-8"))["stories"]
        self.assertEqual(len(rows), 25)
        for story in rows:
            mystery_short.validate_story(story)
            self.assertIn(story["id"], fa)
            self.assertIn(story["id"], notes)


if __name__ == "__main__":
    unittest.main()
