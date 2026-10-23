"""Characterize candidate-selection methods before extracting them."""

import unittest
import inspect
from types import SimpleNamespace
from unittest.mock import patch

from app.services.document_search_service import DocumentSearchService
from app.services.document_search.selection_context import use_candidate_status_map
from app.utils.standard_identity import parse_identity


def _candidate(record_id, designation, year=None, recent=0):
    values = {
        "id": record_id,
        "standardno": designation,
        "display_stdNo": designation,
        "recent": recent,
    }
    if year is not None:
        values["standardyear"] = year
    return SimpleNamespace(**values)


def _row(sdo_name, designation):
    return {
        "sdo_name": sdo_name,
        "search_sdo_name": sdo_name,
        "displaystdno": designation,
        "identity": parse_identity(sdo_name, designation),
    }


class CandidateSelectionCharacterizationTests(unittest.TestCase):
    def test_compatibility_selectors_keep_static_two_argument_signatures(self):
        for name in (
            "_select_candidate",
            "_select_candidates",
            "_select_master_candidates",
            "_select_master_candidate",
        ):
            with self.subTest(name=name):
                self.assertIsInstance(
                    DocumentSearchService.__dict__[name],
                    staticmethod,
                )
                self.assertEqual(
                    list(inspect.signature(getattr(DocumentSearchService, name)).parameters),
                    ["candidates", "row"],
                )

    def test_series_member_key_and_language_marker_return_exact_values(self):
        row = _row("IEC", "IEC 62305 SER (EN-FR)")
        part = _candidate(1, "IEC 62305-1:2024 (EN-FR)")
        series_root = _candidate(2, "IEC 62305 SER (EN-FR)")

        self.assertEqual(
            DocumentSearchService._series_member_key(part, row),
            ("62305", "PART:1"),
        )
        self.assertIsNone(
            DocumentSearchService._series_member_key(series_root, row)
        )
        for value, expected in (
            ("Title (EN-FR)", "EN-FR"),
            ("Title ( en _ d )", "EN-D"),
            ("Title (EN-FR) (EN-D)", "EN-FR"),
            (None, ""),
            ("Title (FR-EN)", ""),
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    DocumentSearchService._series_language_marker(value),
                    expected,
                )

    def test_series_selection_filters_language_and_keeps_latest_object_per_part(self):
        row = _row("IEC", "IEC 62305:2025 SER (EN-FR)")
        candidates = [
            _candidate(1, "IEC 62305 SER (EN-FR)", 2013),
            _candidate(2, "IEC 62305-1:2010 (EN-FR)", 2010),
            _candidate(3, "IEC 62305-1:2024 (EN-FR)", 2024),
            _candidate(5, "IEC 62305-1:2025 (EN-D)", 2025),
            _candidate(6, "IEC 62305-2:2024 (EN-FR)", 2024),
        ]

        selected = DocumentSearchService._select_series_candidates(
            candidates,
            row,
        )

        self.assertEqual(
            [candidate.id for candidate in selected],
            [3, 6],
        )
        self.assertIs(selected[0], candidates[2])
        self.assertIs(selected[1], candidates[4])
        self.assertEqual(
            DocumentSearchService._select_series_candidates([], row),
            [],
        )

    def test_local_and_master_selectors_keep_their_distinct_duplicate_rules(self):
        row = _row("ISO", "ISO 100")
        first = _candidate(7, "ISO 100:2020", 2020)
        later_duplicate = _candidate(7, "ISO 100:2020", 2020)

        with (
            patch.object(
                DocumentSearchService,
                "_select_candidate",
                return_value=None,
            ),
            patch.object(
                DocumentSearchService,
                "_candidate_is_part_of_root",
                return_value=True,
            ),
            patch.object(
                DocumentSearchService,
                "_is_bare_qualifier_request",
                return_value=True,
            ),
            patch.object(
                DocumentSearchService,
                "_select_best_current_candidate",
                side_effect=lambda values, *_args: list(values),
            ),
        ):
            local = DocumentSearchService._select_candidates(
                [first, later_duplicate],
                row,
            )

        self.assertEqual(len(local), 1)
        self.assertIs(local[0], first)

        master_row = _row("ISO", "ISO 100")
        with (
            patch.object(
                DocumentSearchService,
                "_master_candidate_matches_identity",
                return_value=True,
            ),
            patch.object(
                DocumentSearchService,
                "_is_bare_qualifier_request",
                return_value=True,
            ),
        ):
            master = DocumentSearchService._select_master_candidates(
                [first, later_duplicate],
                master_row,
            )

        self.assertEqual(len(master), 1)
        self.assertIs(master[0], later_duplicate)

    def test_master_candidate_selection_uses_latest_year_and_returns_original(self):
        row = _row("AS", "AS 2885")
        older = _candidate(1, "AS 2885:2007", 2007)
        newer = _candidate(2, "AS 2885:2016", 2016)

        selected = DocumentSearchService._select_master_candidate(
            [older, newer],
            row,
        )

        self.assertIs(selected, newer)
        self.assertIsNone(
            DocumentSearchService._select_master_candidate([], row)
        )

    def test_local_selector_dispatch_order_and_selected_candidate_short_circuit(self):
        row = _row("ISO", "ISO 100")
        candidates = [
            _candidate(1, "ISO 100:2020", 2020),
            _candidate(2, "ISO 100:2021", 2021),
        ]
        events = []

        def record(*args):
            events.append(("record", args[0]))

        def exclude(candidate):
            events.append(("exclude", candidate.id))
            return False

        def prefer(candidates_arg, *_args):
            events.append(("prefer-visible", [c.id for c in candidates_arg]))
            return candidates_arg

        def select(candidates_arg, _row):
            events.append(("select", [c.id for c in candidates_arg]))
            return candidates_arg[0]

        with (
            patch.object(DocumentSearchService, "_record_requested_edition_status", side_effect=record),
            patch.object(DocumentSearchService, "_candidate_should_be_excluded", side_effect=exclude),
            patch.object(DocumentSearchService, "_is_api_request", return_value=False),
            patch.object(DocumentSearchService, "_prefer_catalog_visible_candidates", side_effect=prefer),
            patch.object(DocumentSearchService, "_select_candidate", side_effect=select),
            patch.object(DocumentSearchService, "_is_bare_qualifier_request", return_value=False),
            patch.object(
                DocumentSearchService,
                "_candidate_is_part_of_root",
                side_effect=AssertionError("selected root must short-circuit part fallback"),
            ),
        ):
            with use_candidate_status_map({}):
                selected = DocumentSearchService._select_candidates(
                    candidates,
                    row,
                )

        self.assertEqual(len(selected), 1)
        self.assertIs(selected[0], candidates[0])
        self.assertEqual(
            events,
            [
                ("record", candidates),
                ("exclude", 1),
                ("exclude", 2),
                ("prefer-visible", [1, 2]),
                ("select", [1, 2]),
            ],
        )

    def test_master_selector_dispatches_class_helpers_and_empty_inputs(self):
        row = _row("ISO", "ISO 100")
        candidate = _candidate(1, "ISO 100:2020", 2020)
        events = []

        def record(*args):
            events.append("record")

        with (
            patch.object(DocumentSearchService, "_record_requested_edition_status", side_effect=record),
            patch.object(DocumentSearchService, "_candidate_should_be_excluded", return_value=False),
            patch.object(DocumentSearchService, "_is_api_request", return_value=False),
            patch.object(DocumentSearchService, "_prefer_catalog_visible_candidates", side_effect=lambda values, *_: values),
            patch.object(DocumentSearchService, "_current_edition_request_requires_active_status", return_value=False),
            patch.object(DocumentSearchService, "_is_bare_qualifier_request", return_value=False),
            patch.object(DocumentSearchService, "_master_candidate_matches_identity", side_effect=lambda _candidate, _row: events.append("identity") or True),
            patch.object(DocumentSearchService, "_is_tema_edition_family_candidate", return_value=False),
            patch.object(DocumentSearchService, "_select_master_candidate", side_effect=lambda values, _row: events.append("select-master") or values[0]),
        ):
            with use_candidate_status_map({}):
                selected = DocumentSearchService._select_master_candidates(
                    [candidate],
                    row,
                )

        self.assertEqual(len(selected), 1)
        self.assertIs(selected[0], candidate)
        self.assertEqual(events, ["record", "identity", "select-master"])
        self.assertEqual(
            DocumentSearchService._select_candidates([], row),
            [],
        )
        self.assertEqual(
            DocumentSearchService._select_master_candidates([], row),
            [],
        )


if __name__ == "__main__":
    unittest.main()
