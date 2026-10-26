import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.repositories import standards_repository
from app.repositories.standards_repository import StandardsRepository


class FakeEngine:
    pass


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.engine = FakeEngine()
        self.rows = rows
        self.query_count = 0

    def get_bind(self):
        return self.engine

    def query(self, *_columns):
        self.query_count += 1
        return FakeQuery(self.rows)


class StandardsRepositorySdoCacheTests(unittest.TestCase):
    def setUp(self):
        standards_repository._sdo_rows_cache.clear()

    def tearDown(self):
        standards_repository._sdo_rows_cache.clear()

    def test_active_sdo_rows_are_reused_for_repeated_lookups(self):
        session = FakeSession(
            [
                SimpleNamespace(
                    id=1,
                    sdo_title="ISO",
                    sdo_fullname="International Organization for Standardization",
                    sdo_shortdesc="ISO",
                    designation="ISO",
                ),
                SimpleNamespace(
                    id=2,
                    sdo_title="API",
                    sdo_fullname="American Petroleum Institute",
                    sdo_shortdesc="API",
                    designation="API",
                ),
            ]
        )
        repository = StandardsRepository(session)

        iso_rows = repository.find_sdo_ids_from_sdo_table({"ISO"})
        api_rows = repository.find_sdo_ids_from_sdo_table({"API"})

        self.assertEqual([row.id for row in iso_rows], [1])
        self.assertEqual([row.id for row in api_rows], [2])
        self.assertEqual(session.query_count, 1)

    def test_expired_active_sdo_snapshot_is_refreshed(self):
        old_rows = [
            SimpleNamespace(
                id=1,
                sdo_title="ISO",
                sdo_fullname="ISO",
                sdo_shortdesc="ISO",
                designation="ISO",
            )
        ]
        new_rows = [
            SimpleNamespace(
                id=2,
                sdo_title="ISO",
                sdo_fullname="ISO",
                sdo_shortdesc="ISO",
                designation="ISO",
            )
        ]
        session = FakeSession(old_rows)
        repository = StandardsRepository(session)
        fetch_results = iter([old_rows, new_rows])

        def fetch(_db, query_factory):
            query_factory()
            return next(fetch_results)

        with patch.object(
            standards_repository.time,
            "monotonic",
            side_effect=[10, 71],
        ), patch.object(standards_repository, "run_with_retry", side_effect=fetch):
            first = repository.find_sdo_ids_from_sdo_table({"ISO"})
            refreshed = repository.find_sdo_ids_from_sdo_table({"ISO"})

        self.assertEqual(first[0].id, 1)
        self.assertEqual(refreshed[0].id, 2)
        self.assertEqual(session.query_count, 2)


if __name__ == "__main__":
    unittest.main()
