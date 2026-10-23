"""Characterize family-path helpers before extracting them."""

import unittest

from app.services.document_search_service import DocumentSearchService


class FamilyPathCharacterizationTests(unittest.TestCase):
    def test_part_family_path_builds_plain_and_nested_paths(self):
        requested = {"core_number": "61508"}

        self.assertEqual(
            DocumentSearchService._part_family_path(
                {"core_number": "61508", "qualifier": "PART:2"},
                requested,
            ),
            "2",
        )
        self.assertEqual(
            DocumentSearchService._part_family_path(
                {"core_number": "61508PART2", "qualifier": "PART:3"},
                requested,
            ),
            "2-3",
        )
        self.assertEqual(
            DocumentSearchService._part_family_path(
                {"core_number": "61508PART2", "qualifier": "SECTION:4"},
                requested,
            ),
            "2-4",
        )
        self.assertEqual(
            DocumentSearchService._part_family_path(
                {"core_number": "615081", "qualifier": None},
                requested,
            ),
            "1",
        )

    def test_part_family_path_returns_empty_for_empty_or_invalid_paths(self):
        requested = {"core_number": "61508"}

        cases = (
            ({"core_number": "", "qualifier": "PART:1"}, ""),
            ({"core_number": "61509", "qualifier": "PART:1"}, ""),
            ({"core_number": "61508XYZ", "qualifier": "PART:1"}, ""),
            ({"core_number": "61508", "qualifier": "PART:1-X"}, ""),
            ({"core_number": "61508PART2", "qualifier": "SECTION:4-X"}, ""),
        )
        for candidate_identity, expected in cases:
            with self.subTest(candidate_identity=candidate_identity):
                self.assertEqual(
                    DocumentSearchService._part_family_path(
                        candidate_identity,
                        requested,
                    ),
                    expected,
                )

        self.assertEqual(
            DocumentSearchService._part_family_path(
                {"core_number": "61508", "qualifier": None},
                {"core_number": ""},
            ),
            "",
        )

    def test_requested_part_matches_exact_and_nested_top_level_parts(self):
        row = {"identity": {"qualifier": "PART:3"}}

        self.assertTrue(
            DocumentSearchService._requested_part_matches_path(row, "3")
        )
        self.assertTrue(
            DocumentSearchService._requested_part_matches_path(row, "3-7")
        )
        self.assertFalse(
            DocumentSearchService._requested_part_matches_path(row, "2-3")
        )
        self.assertFalse(
            DocumentSearchService._requested_part_matches_path(row, "")
        )

    def test_requested_part_range_is_inclusive_and_checks_top_level_only(self):
        row = {"identity": {"qualifier": "PART:2-4"}}

        for part_path in ("2", "2-X", "3-1", "4-9"):
            with self.subTest(part_path=part_path):
                self.assertTrue(
                    DocumentSearchService._requested_part_matches_path(
                        row,
                        part_path,
                    )
                )
        for part_path in ("1", "5", ""):
            with self.subTest(part_path=part_path):
                self.assertFalse(
                    DocumentSearchService._requested_part_matches_path(
                        row,
                        part_path,
                    )
                )

        self.assertFalse(
            DocumentSearchService._requested_part_matches_path(
                {"identity": {"qualifier": "PART:2-X"}},
                "2",
            )
        )

    def test_requested_part_without_part_qualifier_accepts_any_path(self):
        for qualifier in (None, "SECTION:2", "SERIES"):
            with self.subTest(qualifier=qualifier):
                self.assertTrue(
                    DocumentSearchService._requested_part_matches_path(
                        {"identity": {"qualifier": qualifier}},
                        "",
                    )
                )


if __name__ == "__main__":
    unittest.main()
