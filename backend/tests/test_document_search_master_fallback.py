"""Characterize master-fallback orchestration before extraction."""

import unittest
from types import SimpleNamespace

from app.services.document_search_service import DocumentSearchService


class DocumentSearchMasterFallbackTests(unittest.TestCase):
    def test_withdrawn_bis_duplicate_master_rows_do_not_create_two_matches(self):
        first = SimpleNamespace(
            id=492833,
            Standard_id="BIS-Boss-27432",
            sdo_id=77,
            status_id=10,
            status=0,
            standardno="BIS 2099",
            display_stdNo="BIS 2099 : 1986",
            standardyear=1986,
            recent=0,
            DocumentAvailability=0,
            url="",
        )
        second = SimpleNamespace(
            id=492834,
            Standard_id="BIS-Boss-29634",
            sdo_id=77,
            status_id=10,
            status=0,
            standardno="BIS 2099",
            display_stdNo="BIS 2099 : 1986",
            standardyear=1986,
            recent=0,
            DocumentAvailability=0,
            url="",
        )
        master_rows = [first, second]
        queried_master_ids = []

        class LocalRepository:
            def __getattr__(self, name):
                if name.startswith("search_by_sdo_and_"):
                    return lambda *_args: []
                raise AttributeError(name)

        class EnrichmentRepository:
            def search_master_by_sdo_and_display_variants(self, _pairs):
                queried_master_ids.extend(row.id for row in master_rows)
                return list(master_rows)

            def search_master_by_sdo_and_standard_numbers(self, _pairs):
                return []

            def search_master_by_sdo_and_identity_hints(self, _hints):
                return list(master_rows)

            def get_standard_status_map(self, status_ids):
                if 10 in status_ids:
                    return {
                        10: {
                            "name": "WITHDRAWN",
                            "cart_show": 0,
                            "std_show": 0,
                        },
                    }
                return {}

        service = DocumentSearchService.__new__(DocumentSearchService)
        service.repository = LocalRepository()
        service.enrichment_repository = EnrichmentRepository()
        service.resolve_sdo_ids = lambda names, fallback_names=None: {
            str(name).upper(): 77 for name in names
        }

        selection_trace = []
        original_select_master_candidates = service._select_master_candidates

        def capture_master_selection(candidates, row):
            selected = original_select_master_candidates(candidates, row)
            selection_trace.append(
                (
                    {candidate.id for candidate in candidates},
                    [candidate.id for candidate in selected],
                )
            )
            return selected

        service._select_master_candidates = capture_master_selection

        results = service.search(
            [{"displaystdno": "BIS 2099 : 1986"}]
        )

        self.assertEqual(set(queried_master_ids), {492833, 492834})
        self.assertTrue(
            any(candidate_ids == {492833, 492834} and not selected_ids
                for candidate_ids, selected_ids in selection_trace)
        )
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["matched"])
        self.assertIsNone(results[0]["standard"])


if __name__ == "__main__":
    unittest.main()
