"""Characterize lifecycle status helpers before extraction."""

import unittest
from types import SimpleNamespace

from app.services.document_search_service import DocumentSearchService


class LifecycleStatusCharacterizationTests(unittest.TestCase):
    def test_unavailable_status_labels_match_every_existing_alternative(self):
        for label in (
            "WITHDRAWN",
            "WTHDRAWN",
            "DO NOT USE",
            "OBSOLETE",
            "SUPERSEDED",
            "INACTIVE",
            "DISCONTINUED",
            "HISTORIC",
            "HISTORICAL",
            "ARCHIVED",
        ):
            with self.subTest(label=label):
                self.assertTrue(
                    DocumentSearchService._status_label_is_unavailable(
                        f"Catalogue status: {label}."
                    )
                )

    def test_unavailable_status_matching_preserves_case_and_word_boundaries(self):
        self.assertTrue(
            DocumentSearchService._status_label_is_unavailable("withdrawn")
        )
        for status in (
            None,
            "",
            "ACTIVE",
            "WITHDRAWNISH",
            "UNWITHDRAWN",
            "DO NOT USEFUL",
            "HISTORICALLY",
        ):
            with self.subTest(status=status):
                self.assertFalse(
                    DocumentSearchService._status_label_is_unavailable(
                        status
                    )
                )

    def test_embedded_status_uses_standardno_before_display_stdno(self):
        candidate = SimpleNamespace(
            standardno="ISO 100 (OBSOLETE)",
            display_stdNo="ISO 100 (WITHDRAWN): 2020",
        )
        self.assertEqual(
            DocumentSearchService._candidate_embedded_lifecycle_status(
                candidate
            ),
            "OBSOLETE",
        )

    def test_embedded_status_uses_first_marker_and_normalizes_historic(self):
        cases = (
            ("ISO 100 (HISTORIC) (WITHDRAWN)", "", "HISTORICAL"),
            ("ISO 100 (HISTORICAL)", "", "HISTORICAL"),
            ("ISO 100", "ISO 100 (DO NOT USE)", "DO NOT USE"),
        )
        for standardno, display_stdNo, expected in cases:
            with self.subTest(standardno=standardno, display_stdNo=display_stdNo):
                self.assertEqual(
                    DocumentSearchService._candidate_embedded_lifecycle_status(
                        SimpleNamespace(
                            standardno=standardno,
                            display_stdNo=display_stdNo,
                        )
                    ),
                    expected,
                )

    def test_embedded_status_returns_none_for_missing_empty_or_unmarked_fields(self):
        for candidate in (
            SimpleNamespace(),
            SimpleNamespace(standardno="", display_stdNo=""),
            SimpleNamespace(
                standardno="ISO 100 WITHDRAWNISH",
                display_stdNo="ISO 100 ACTIVE",
            ),
        ):
            with self.subTest(candidate=candidate):
                self.assertIsNone(
                    DocumentSearchService._candidate_embedded_lifecycle_status(
                        candidate
                    )
                )


if __name__ == "__main__":
    unittest.main()
