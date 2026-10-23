"""Characterize family revision helpers before extracting them."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.document_search_service import DocumentSearchService


def _candidate(designation):
    return SimpleNamespace(
        display_stdNo=designation,
        standardno=designation,
    )


class FamilyRevisionCharacterizationTests(unittest.TestCase):
    def test_base_edition_year_trims_supported_revision_suffixes(self):
        cases = (
            ("ISO 100:2018/CORR1:2020", 2018),
            ("ISO 100:2018/CORRIGENDUM 2:2021", 2018),
            ("ISO 100:2017 COR 3:2020", 2017),
            ("ISO 100:2016+AMD 4A:2021", 2016),
            ("ISO 100:2015 AMENDMENT 5:2022", 2015),
        )
        for designation, expected_year in cases:
            with self.subTest(designation=designation):
                candidate = SimpleNamespace(
                    display_stdNo=designation,
                    standardno="ISO 100:1900",
                )
                self.assertEqual(
                    DocumentSearchService._candidate_base_edition_year(
                        candidate
                    ),
                    expected_year,
                )

    def test_base_edition_year_falls_back_to_standard_number_and_can_be_unknown(self):
        self.assertEqual(
            DocumentSearchService._candidate_base_edition_year(
                SimpleNamespace(
                    display_stdNo="",
                    standardno="ISO 100:2014+AMD 1:2018",
                )
            ),
            2014,
        )
        self.assertIsNone(
            DocumentSearchService._candidate_base_edition_year(
                SimpleNamespace(display_stdNo="ISO 100", standardno="")
            )
        )
        self.assertIsNone(
            DocumentSearchService._candidate_base_edition_year(
                SimpleNamespace()
            )
        )

    def test_tuple_keys_preserve_path_order_and_filter_only_known_year_mismatches(self):
        base_one = _candidate("ISO 100-1:2010")
        same_year_revision = _candidate("ISO 100-1:2010/CORR1:2010")
        different_year_revision = _candidate("ISO 100-1:2011/CORR2:2020")
        revision_without_base = _candidate("ISO 100-2:2012/CORR1:2012")
        base_unknown_year = _candidate("ISO 100-3")
        revision_unknown_year = _candidate("ISO 100-3/CORR1")
        latest_by_part = {
            ("1", ""): ((2010,), base_one),
            ("1", "CORR1"): ((2010,), same_year_revision),
            ("1", "CORR2"): ((2011,), different_year_revision),
            ("2", "CORR1"): ((2012,), revision_without_base),
            ("3", ""): ((0,), base_unknown_year),
            ("3", "CORR1"): ((0,), revision_unknown_year),
        }
        original_items = list(latest_by_part.items())

        selected = DocumentSearchService._select_current_family_revisions(
            latest_by_part,
            "PART",
        )

        self.assertEqual(
            len(selected),
            5,
        )
        for actual, expected in zip(
            selected,
            (
                base_one,
                same_year_revision,
                revision_without_base,
                base_unknown_year,
                revision_unknown_year,
            ),
        ):
            self.assertIs(actual, expected)
        self.assertEqual(list(latest_by_part.items()), original_items)

    def test_legacy_string_keys_group_revisions_and_keep_mapping_order(self):
        base = _candidate("ISO 200-1:2020")
        revision = _candidate("ISO 200-1:2020/CORR1:2020")
        no_base_revision = _candidate("ISO 200-2:2019/CORR2:2019")
        latest_by_part = {
            "PART:1:": ((2020,), base),
            "PART:1:CORR1": ((2020,), revision),
            "PART:2:CORR2": ((2019,), no_base_revision),
        }

        selected = DocumentSearchService._select_current_family_revisions(
            latest_by_part,
            "PART",
        )

        self.assertEqual(len(selected), 3)
        self.assertIs(selected[0], base)
        self.assertIs(selected[1], revision)
        self.assertIs(selected[2], no_base_revision)

    def test_base_year_helper_dispatch_order_and_no_base_short_circuit(self):
        base = _candidate("ISO 300-1:2020")
        same_year = _candidate("ISO 300-1:2020/CORR1:2020")
        different_year = _candidate("ISO 300-1:2020/CORR2:2021")
        calls = []
        years = {id(base): 2020, id(same_year): 2020, id(different_year): 2021}

        def base_year(candidate):
            calls.append(candidate)
            return years[id(candidate)]

        latest_by_part = {
            ("1", ""): ((2020,), base),
            ("1", "CORR1"): ((2020,), same_year),
            ("1", "CORR2"): ((2021,), different_year),
        }
        with patch.object(
            DocumentSearchService,
            "_candidate_base_edition_year",
            side_effect=base_year,
        ):
            selected = DocumentSearchService._select_current_family_revisions(
                latest_by_part,
                "PART",
            )

        self.assertEqual(calls, [base, same_year, different_year])
        self.assertEqual(len(selected), 2)
        self.assertIs(selected[0], base)
        self.assertIs(selected[1], same_year)

        calls.clear()
        without_base = {("2", "CORR1"): ((2019,), same_year)}
        with patch.object(
            DocumentSearchService,
            "_candidate_base_edition_year",
            side_effect=AssertionError("base-year helper should not be called"),
        ):
            selected = DocumentSearchService._select_current_family_revisions(
                without_base,
                "PART",
            )
        self.assertEqual(len(selected), 1)
        self.assertIs(selected[0], same_year)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
