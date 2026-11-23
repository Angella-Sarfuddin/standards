"""Helpers that speed search I/O without changing match results."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.ttl_cache import BindTtlCache
from app.core.standard_identity import parse_identity
from app.repositories.standards_repository import StandardsRepository
from app.services.document_search_service import DocumentSearchService


class BindTtlCacheTests(unittest.TestCase):
    def test_returns_cached_value_within_ttl(self):
        cache = BindTtlCache(ttl_seconds=60)

        class _Bind:
            pass

        bind = _Bind()
        calls = {"count": 0}

        def loader():
            calls["count"] += 1
            return {"ok": True}

        first = cache.get_or_load(bind, loader)
        second = cache.get_or_load(bind, loader)

        self.assertEqual(first, {"ok": True})
        self.assertEqual(second, {"ok": True})
        self.assertEqual(calls["count"], 1)

    def test_skips_cache_without_bind(self):
        cache = BindTtlCache(ttl_seconds=60)
        calls = {"count": 0}

        def loader():
            calls["count"] += 1
            return calls["count"]

        self.assertEqual(cache.get_or_load(None, loader), 1)
        self.assertEqual(cache.get_or_load(None, loader), 2)


class CombinedDisplayStandardLookupTests(unittest.TestCase):
    def test_splits_display_and_standard_matches_like_separate_queries(self):
        display_row = SimpleNamespace(
            id=1,
            display_stdNo="ISO 9001:2015",
            standardno="ISO 9001",
        )
        standard_row = SimpleNamespace(
            id=2,
            display_stdNo="ISO 9001:2008",
            standardno="ISO 9001:2015",
        )
        both_row = SimpleNamespace(
            id=3,
            display_stdNo="ISO 9001:2015",
            standardno="ISO 9001:2015",
        )

        db = MagicMock()
        query = MagicMock()
        db.query.return_value = query
        query.options.return_value = query
        query.filter.return_value = query

        # run_with_retry calls query_factory().all()
        query.all.return_value = [display_row, standard_row, both_row]

        repository = StandardsRepository(db)
        exact, standard_numbers = repository.search_by_sdo_display_and_standard_numbers(
            [(7, "ISO 9001:2015")]
        )

        self.assertEqual([row.id for row in exact], [1, 3])
        self.assertEqual([row.id for row in standard_numbers], [2, 3])


class MasterIdentitySkipTests(unittest.TestCase):
    def test_display_hit_never_skips_master_identity(self):
        """Match behavior: always run master identity for newer-edition coverage."""
        year_locked = {
            "identity": parse_identity("ISO", "ISO 9001:2015"),
        }
        yearless = {
            "identity": parse_identity("ISO", "ISO 9001"),
        }
        masters = [SimpleNamespace(id=1)]
        self.assertFalse(
            DocumentSearchService._masters_satisfy_row(year_locked, masters)
        )
        self.assertFalse(
            DocumentSearchService._masters_satisfy_row(yearless, masters)
        )


if __name__ == "__main__":
    unittest.main()
