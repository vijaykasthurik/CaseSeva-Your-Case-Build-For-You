from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from backend.adapters.mock.database import MockDatabaseAdapter


class PersistenceTests(unittest.TestCase):
    def test_parallel_reservations_do_not_lose_or_reuse_evidence_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            db = MockDatabaseAdapter(Path(directory) / "database.json")
            db.create("cases", {"id": "case", "next_evidence_number": 1})
            def reserve(_):
                return db.mutate("cases", "case", lambda case: {"next_evidence_number": case["next_evidence_number"] + 1})["next_evidence_number"] - 1
            with ThreadPoolExecutor(max_workers=6) as workers:
                numbers = list(workers.map(reserve, range(24)))
            self.assertEqual(sorted(numbers), list(range(1, 25)))
            self.assertEqual(db.get("cases", "case")["next_evidence_number"], 25)
