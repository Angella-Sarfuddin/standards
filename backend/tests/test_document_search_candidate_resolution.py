"""Characterize candidate identity and selection before extraction."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.document_search_service import DocumentSearchService
from app.utils.standard_identity import parse_identity


def _candidate(
    record_id,
    designation,
    *,
    standardyear=None,
    status_id=None,
    title="",
    recent=0,
):
    return SimpleNamespace(
        id=record_id,
        standardno=designation,
        display_stdNo=designation,
        standardyear=standardyear,
        status_id=status_id,
        title=title,
        recent=recent,
    )


def _row(sdo_name, designation, **values):
    result = {
        "sdo_name": sdo_name,
        "search_sdo_name": sdo_name,
        "identity": parse_identity(sdo_name, designation),
    }
    result.update(values)
    return result


class CandidateResolutionCharacterizationTests(unittest.TestCase):
    def test_identity_matching_accepts_separator_alias_and_rejects_other_core(self):
        row = _row("API", "API STD/610")
        matching = _candidate(1, "API RP-610:2022")
        different = _candidate(2, "API RP-611:2022")

        self.assertTrue(
            DocumentSearchService._candidate_matches_identity(matching, row)
        )
        self.assertFalse(
            DocumentSearchService._candidate_matches_identity(different, row)
        )

    def test_candidate_year_prefers_column_then_display_and_number_fallbacks(self):
        column_year = _candidate(
            1, "ISO 50001:2024", standardyear=2020
        )
        display_year = _candidate(2, "ISO 50001:2018")
        number_year = _candidate(3, "ISO 50001")

        self.assertEqual(
            DocumentSearchService._candidate_year(column_year, "ISO"), 2020
        )
        self.assertEqual(
            DocumentSearchService._candidate_year(display_year, "ISO"), 2018
        )
        # The display string has no year; the standard-number parser supplies it.
        number_year.standardno = "ISO 50001:2015"
        self.assertEqual(
            DocumentSearchService._candidate_year(number_year, "ISO"), 2015
        )

    def test_identifier_prefix_normalization_is_case_and_separator_insensitive(self):
        self.assertEqual(
            DocumentSearchService._normalized_identifier_prefix("ansi / api"),
            "ANSIAPI",
        )
        self.assertEqual(
            DocumentSearchService._normalized_identifier_prefix(None), ""
        )

    def test_api_filter_keeps_unavailable_and_dated_records_in_input_order(self):
        withdrawn = _candidate(
            1, "API 610:2018", standardyear=2018, status_id=10
        )
        yearless = _candidate(2, "API 610", status_id=20)
        active = _candidate(
            3, "API 610:2022", standardyear=2022, status_id=20
        )
        active_duplicate = _candidate(
            3, "API 610:2022", standardyear=2022, status_id=20
        )
        legacy_placeholder = _candidate(
            4,
            "API 610",
            standardyear=0,
            status_id=20,
            title="2nd Edition",
        )
        status_map = {
            10: {"name": "WITHDRAWN", "cart_show": 0, "std_show": 0},
            20: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
        }
        candidates = [withdrawn, yearless, active, legacy_placeholder, active_duplicate]

        filtered = DocumentSearchService._filter_api_unavailable_candidates(
            candidates, status_map, _row("API", "API 610")
        )

        self.assertEqual(filtered, [withdrawn, active, active_duplicate])
        self.assertIs(filtered[0], withdrawn)
        self.assertIs(filtered[1], active)
        self.assertIs(filtered[2], active_duplicate)

    def test_api_filter_without_status_map_returns_a_new_order_preserving_list(self):
        first = _candidate(1, "API 610:2022", standardyear=2022)
        second = _candidate(2, "API 610", standardyear=0, title="2nd Edition")
        candidates = [first, second]

        filtered = DocumentSearchService._filter_api_unavailable_candidates(
            candidates, {}, _row("API", "API 610")
        )

        self.assertEqual(filtered, candidates)
        self.assertIsNot(filtered, candidates)

    def test_api_filter_dispatches_helpers_in_candidate_order(self):
        first = _candidate(1, "API 610:2018", standardyear=2018, status_id=10)
        second = _candidate(2, "API 610:2022", standardyear=2022, status_id=20)
        status_map = {
            10: {"name": "ACTIVE"},
            20: {"name": "ACTIVE"},
        }
        events = []
        original_year = DocumentSearchService._candidate_year
        original_embedded_status = (
            DocumentSearchService._candidate_embedded_lifecycle_status
        )
        original_unavailable = DocumentSearchService._status_label_is_unavailable

        def candidate_year(candidate, sdo_name):
            result = original_year(candidate, sdo_name)
            events.append(("year", candidate.id, sdo_name, result))
            return result

        def embedded_status(candidate):
            result = original_embedded_status(candidate)
            events.append(("embedded_status", candidate.id, result))
            return result

        def unavailable(status_name):
            result = original_unavailable(status_name)
            events.append(("unavailable", status_name, result))
            return result

        with (
            patch.object(
                DocumentSearchService,
                "_candidate_year",
                staticmethod(candidate_year),
            ),
            patch.object(
                DocumentSearchService,
                "_candidate_embedded_lifecycle_status",
                staticmethod(embedded_status),
            ),
            patch.object(
                DocumentSearchService,
                "_status_label_is_unavailable",
                staticmethod(unavailable),
            ),
        ):
            filtered = DocumentSearchService._filter_api_unavailable_candidates(
                [first, second], status_map, _row("API", "API 610")
            )

        self.assertEqual(filtered, [first, second])
        self.assertEqual(
            events,
            [
                ("year", 1, "API", 2018),
                ("embedded_status", 1, None),
                ("unavailable", "ACTIVE", False),
                ("year", 2, "API", 2022),
                ("embedded_status", 2, None),
                ("unavailable", "ACTIVE", False),
            ],
        )

    def test_best_current_candidate_deduplicates_and_records_requested_status(self):
        requested_edition = _candidate(
            1, "ISO 50001:2018", standardyear=2018, status_id=10
        )
        requested_duplicate = _candidate(
            1, "ISO 50001:2018", standardyear=2018, status_id=10
        )
        current = _candidate(
            2, "ISO 50001:2022", standardyear=2022, status_id=20
        )
        row = _row("ISO", "ISO 50001:2018")
        status_map = {
            10: {"name": "WITHDRAWN", "cart_show": 0, "std_show": 0},
            20: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
        }
        events = []
        original_record_status = DocumentSearchService._record_requested_edition_status

        def record_status(candidates, passed_row, passed_status_map=None):
            events.append(
                ("record", [item.id for item in candidates], passed_row is row, passed_status_map is status_map)
            )
            return original_record_status(candidates, passed_row, passed_status_map)

        with patch.object(
            DocumentSearchService,
            "_record_requested_edition_status",
            staticmethod(record_status),
        ):
            selected = DocumentSearchService._select_best_current_candidate(
                [requested_edition, requested_duplicate, current], row, status_map
            )

        self.assertEqual(events, [("record", [1, 1, 2], True, True)])
        self.assertEqual(row["requested_edition_status"], "WITHDRAWN")
        self.assertEqual(selected, [current])
        self.assertIs(selected[0], current)

    def test_current_candidate_selection_preserves_first_item_on_a_full_tie(self):
        row = _row("ISO", "ISO 50001")
        first = _candidate(1, "ISO 50001:2022", standardyear=2022)
        tied = _candidate(2, "ISO 50001:2022", standardyear=2022)

        selected = DocumentSearchService._select_best_current_candidate(
            [first, tied], row
        )

        self.assertEqual(selected, [first])
        self.assertIs(selected[0], first)

    def test_select_candidate_dispatches_class_helper_and_uses_latest_year(self):
        row = _row("ISO", "ISO 50001")
        older = _candidate(1, "ISO 50001:2018", standardyear=2018)
        newer = _candidate(2, "ISO 50001:2022", standardyear=2022)
        events = []
        original = DocumentSearchService._prefer_exact_designation
        original_match = DocumentSearchService._candidate_matches_identity
        original_year = DocumentSearchService._candidate_year

        def matches(candidate, passed_row):
            result = original_match(candidate, passed_row)
            events.append(("matches", candidate.id, passed_row is row, result))
            return result

        def prefer_exact(candidates, passed_row):
            events.append(
                ("prefer_exact", [item.id for item in candidates], passed_row is row)
            )
            return original(candidates, passed_row)

        def candidate_year(candidate, sdo_name):
            result = original_year(candidate, sdo_name)
            events.append(("year", candidate.id, sdo_name, result))
            return result

        with patch.object(
            DocumentSearchService,
            "_prefer_exact_designation",
            staticmethod(prefer_exact),
        ), patch.object(
            DocumentSearchService,
            "_candidate_matches_identity",
            staticmethod(matches),
        ), patch.object(
            DocumentSearchService,
            "_candidate_year",
            staticmethod(candidate_year),
        ):
            selected = DocumentSearchService._select_candidate(
                [older, newer], row
            )

        self.assertEqual(
            events,
            [
                ("matches", 1, True, True),
                ("matches", 2, True, True),
                ("prefer_exact", [1, 2], True),
                ("year", 1, "ISO", 2018),
                ("year", 2, "ISO", 2022),
            ],
        )
        self.assertIs(selected, newer)

    def test_select_candidate_returns_none_when_identity_validation_fails(self):
        row = _row("ISO", "ISO 50001")
        other = _candidate(1, "ISO 50002:2022", standardyear=2022)

        self.assertIsNone(
            DocumentSearchService._select_candidate([other], row)
        )


if __name__ == "__main__":
    unittest.main()
