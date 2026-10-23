"""Characterize repository lookup ordering in document search."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.document_search import input_preparation
from app.services.document_search_service import DocumentSearchService


class StopAfterLookupMaps(Exception):
    """Stop at the first local candidate-list consumer."""


def _standard(record_id, sdo_id, standardno, display_stdno, normalized=None):
    return SimpleNamespace(
        id=record_id,
        Standard_id=f"STD-{record_id}",
        sdo_id=sdo_id,
        status_id=None,
        standardno=standardno,
        display_stdNo=display_stdno,
        stdNo_normalized=normalized or standardno,
    )


def _prepared_rows(include_api=True):
    rows = [
        {
            "sdo_name": "ISO",
            "search_sdo_name": "ISO",
            "sdo_id": 1,
            "identity": {"variants": ["ISO 1", "1", "ONE", "1"]},
            "full_display_number": "ISO 1",
            "request_key": (1, "1"),
        },
        {
            "sdo_name": "ISO",
            "search_sdo_name": "ISO",
            "sdo_id": 1,
            "identity": {"variants": ["ISO 1", "1", "ONE"]},
            "full_display_number": "ISO 1",
            "request_key": (1, "1"),
        },
        {
            "sdo_name": "ASTM",
            "search_sdo_name": "ASTM",
            "sdo_id": 2,
            "identity": {"variants": ["ASTM 2", "2"]},
            "full_display_number": "ASTM 2",
            "request_key": (2, "2"),
        },
        {
            "sdo_name": "ASTM",
            "search_sdo_name": "ASTM",
            "sdo_id": 2,
            "identity": {"variants": ["ASTM 2", "2"]},
            "full_display_number": "ASTM 2",
            "request_key": (2, "2"),
        },
        {
            "sdo_name": "SP",
            "search_sdo_name": "SP",
            "sdo_id": None,
            "identity": {"variants": ["SP 75"]},
            "full_display_number": "SP 75",
            "request_key": ("SP", "75"),
        },
    ]
    if include_api:
        rows.append(
            {
                "sdo_name": "API",
                "search_sdo_name": "API",
                "sdo_id": 3,
                "identity": {"variants": ["API 3", "3", "API 3"]},
                "full_display_number": "API 3",
                "request_key": (3, "3"),
            }
        )
    return rows


def _capture_lookup_behavior(include_api=True):
    rows = _prepared_rows(include_api=include_api)
    display_records = [
        _standard("display-first", 1, "ISO 1", "1"),
        _standard("display-second", 1, "ISO 1", "1"),
    ]
    api_display_records = [
        _standard("api-first", 3, "API 3", "API 3"),
        _standard("api-second", 3, "API 3", "API 3"),
    ]
    exact_records = [
        _standard("exact-first", 2, "ASTM 2", "ASTM 2"),
        _standard("exact-second", 2, "ASTM 2", "ASTM 2"),
    ]
    normalized_records = [
        _standard("normalized-first", 2, "ASTM 2", "ASTM 2", "ASTM2"),
        _standard("normalized-second", 2, "ASTM 2", "ASTM 2", "ASTM2"),
    ]
    standard_number_records = [
        _standard("number-first", 2, "ASTM 2", "ASTM 2"),
        _standard("number-second", 2, "ASTM 2", "ASTM 2"),
    ]

    call_trace = []

    class FakeRepository:
        def search_by_sdo_and_display_variants(self, pairs):
            call_trace.append(("repository", "search_by_sdo_and_display_variants", pairs))
            return list(display_records)

        def search_by_sdo_and_display_numbers(self, pairs):
            call_trace.append(("repository", "search_by_sdo_and_display_numbers", pairs))
            return list(exact_records)

        def search_by_sdo_and_normalized_numbers(self, pairs):
            call_trace.append(("repository", "search_by_sdo_and_normalized_numbers", pairs))
            return list(normalized_records)

        def search_by_sdo_and_standard_numbers(self, pairs):
            call_trace.append(("repository", "search_by_sdo_and_standard_numbers", pairs))
            return list(standard_number_records)

        def search_by_sdo_and_identity_hints(self, _hints):
            return []

    class FakeEnrichmentRepository:
        def search_master_by_sdo_and_display_variants(self, pairs):
            call_trace.append(
                (
                    "enrichment_repository",
                    "search_master_by_sdo_and_display_variants",
                    pairs,
                )
            )
            return list(api_display_records)

        def get_standard_status_map(self, _status_ids):
            return {}

    service = DocumentSearchService.__new__(DocumentSearchService)
    service.repository = FakeRepository()
    service.enrichment_repository = FakeEnrichmentRepository()
    service.resolve_sdo_ids = lambda _names: {"ISO": 1, "ASTM": 2, "API": 3}

    api_predicate_trace = []
    row_display_predicate_trace = []
    original_is_api_request = DocumentSearchService._is_api_request
    original_has_display_candidates = (
        DocumentSearchService._row_has_display_candidates
    )

    def is_api_request(row):
        result = original_is_api_request(row)
        api_predicate_trace.append((row["sdo_name"], row["sdo_id"], result))
        return result

    def row_has_display_candidates(row, candidate_map):
        result = original_has_display_candidates(row, candidate_map)
        row_display_predicate_trace.append((row["sdo_name"], row["sdo_id"], result))
        return result

    service._is_api_request = is_api_request
    service._row_has_display_candidates = row_has_display_candidates

    captured_maps = {}

    def intercept_direct_candidate_lists(
        _row,
        candidate_map,
        exact_result_map,
        normalized_result_map,
        standard_number_map,
    ):
        captured_maps.update(
            candidate_map=candidate_map,
            exact_result_map=exact_result_map,
            normalized_result_map=normalized_result_map,
            standard_number_map=standard_number_map,
        )
        raise StopAfterLookupMaps

    service._direct_candidate_lists = intercept_direct_candidate_lists

    with patch.object(
        input_preparation,
        "prepare_input_rows",
        return_value=rows,
    ):
        try:
            service.search(
                [
                    {"sdo_name": "ISO", "displaystdno": "ISO 1"},
                    {"sdo_name": "ASTM", "displaystdno": "ASTM 2"},
                ]
            )
        except StopAfterLookupMaps:
            pass
        else:
            raise AssertionError("search did not reach the lookup-map hook")

    return {
        "call_trace": call_trace,
        "candidate_maps": {
            name: {
                key: [record.id for record in records]
                for key, records in mapping.items()
            }
            for name, mapping in captured_maps.items()
        },
        "api_predicate_trace": api_predicate_trace,
        "row_display_predicate_trace": row_display_predicate_trace,
    }


class DocumentSearchRepositoryLookupTests(unittest.TestCase):
    def test_query_trace_arguments_and_result_order_are_preserved(self):
        captured = _capture_lookup_behavior()
        self.assertEqual(
            captured["call_trace"],
            [
                (
                    "repository",
                    "search_by_sdo_and_display_variants",
                    [
                        (1, "ISO 1"),
                        (1, "1"),
                        (1, "ONE"),
                        (2, "ASTM 2"),
                        (2, "2"),
                        (3, "API 3"),
                        (3, "3"),
                    ],
                ),
                (
                    "enrichment_repository",
                    "search_master_by_sdo_and_display_variants",
                    [(3, "API 3"), (3, "3"), (3, "API 3")],
                ),
                (
                    "repository",
                    "search_by_sdo_and_display_numbers",
                    [(2, "ASTM 2")],
                ),
                (
                    "repository",
                    "search_by_sdo_and_normalized_numbers",
                    [(2, "ASTM2")],
                ),
                (
                    "repository",
                    "search_by_sdo_and_standard_numbers",
                    [(2, "ASTM 2")],
                ),
            ],
        )
        self.assertEqual(
            captured["candidate_maps"],
            {
                "candidate_map": {
                    (1, "1"): ["display-first", "display-second"],
                    (3, "API 3"): ["api-first", "api-second"],
                },
                "exact_result_map": {
                    (2, "ASTM 2"): ["exact-first", "exact-second"],
                },
                "normalized_result_map": {
                    (2, "ASTM2"): ["normalized-first", "normalized-second"],
                },
                "standard_number_map": {
                    (2, "ASTM 2"): ["number-first", "number-second"],
                },
            },
        )

    def test_api_and_display_predicates_are_dynamically_dispatched(self):
        captured = _capture_lookup_behavior()
        self.assertEqual(
            captured["api_predicate_trace"],
            [
                ("ISO", 1, False),
                ("ISO", 1, False),
                ("ASTM", 2, False),
                ("ASTM", 2, False),
                ("SP", None, False),
                ("API", 3, True),
            ],
        )
        self.assertEqual(
            captured["row_display_predicate_trace"],
            [
                ("ISO", 1, True),
                ("ISO", 1, True),
                ("ASTM", 2, False),
                ("ASTM", 2, False),
                ("API", 3, True),
            ],
        )

    def test_api_master_query_is_skipped_when_no_api_rows_have_an_sdo(self):
        captured = _capture_lookup_behavior(include_api=False)
        method_names = [method for _repository, method, _args in captured["call_trace"]]
        self.assertEqual(
            method_names,
            [
                "search_by_sdo_and_display_variants",
                "search_by_sdo_and_display_numbers",
                "search_by_sdo_and_normalized_numbers",
                "search_by_sdo_and_standard_numbers",
            ],
        )


if __name__ == "__main__":
    unittest.main()
