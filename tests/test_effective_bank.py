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


if __name__ == "__main__":
    unittest.main()
