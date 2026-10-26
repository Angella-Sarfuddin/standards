"""Regression tests for batching broad identity lookups in bulk searches."""

import unittest

from app.repositories.enrichment_repository import EnrichmentRepository
from app.repositories.standards_repository import StandardsRepository


class _Query:
    def __init__(self, db):
        self.db = db

    def filter(self, *_criteria):
        return self

    def all(self):
        self.db.executed_queries += 1
        return []


class _Database:
    def __init__(self):
        self.executed_queries = 0

    def query(self, *_entities):
        return _Query(self)


def _long_core_hints(count):
    return [
        (7, "ISO", str(100000 + index))
        for index in range(count)
    ]


class SearchRepositoryBatchingTests(unittest.TestCase):
    def test_local_identity_lookup_batches_300_cores(self):
        db = _Database()

        results = StandardsRepository(db).search_by_sdo_and_identity_hints(
            _long_core_hints(300)
        )

        self.assertEqual(results, [])
        # Prefix batches plus fulltext batches. One query per core would be 300.
        self.assertEqual(db.executed_queries, 14)

    def test_master_identity_lookup_batches_300_cores(self):
        db = _Database()
        hints = [(*hint, None) for hint in _long_core_hints(300)]

        results = EnrichmentRepository(
            db
        ).search_master_by_sdo_and_identity_hints(hints)

        self.assertEqual(results, [])
        # Master has no normalized column, so its prefix batches are smaller.
        self.assertEqual(db.executed_queries, 12)


if __name__ == "__main__":
    unittest.main()
