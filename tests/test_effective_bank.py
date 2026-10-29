import unittest

from src.effective_bank import ids
from src import mystery_short


class EffectiveBankTests(unittest.TestCase):
    def test_effective_bank_contains_all_staged_batches(self):
        batch_ids = set()
        for path in sorted((mystery_short.ROOT / "content").glob("mysteries_batch*.json")):
            import json
            rows = json.loads(path.read_text(encoding="utf-8"))
            batch_ids.update(str(row["id"]) for row in rows)
        self.assertTrue(batch_ids.issubset(ids()))

    def test_effective_bank_ids_are_unique(self):
        loaded = list(ids())
        self.assertEqual(len(loaded), len(set(loaded)))


if __name__ == "__main__":
    unittest.main()
