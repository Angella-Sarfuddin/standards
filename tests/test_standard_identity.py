import unittest
from types import SimpleNamespace

from app.services.document_search_service import DocumentSearchService
from app.services.extractors.excel_extractor import ExcelExtractor
from app.utils.standard_formatter import build_full_display_number
from app.utils.standard_identity import (
    identity_bound_like_patterns,
    identity_core_appears,
    identity_core_sql_pattern,
    identity_matches,
    identity_unprefixed_like_patterns,
    parse_identity,
)


class StandardIdentityTests(unittest.TestCase):
    def matches(self, sdo, requested, candidate):
        return identity_matches(
            parse_identity(sdo, requested),
            parse_identity(sdo, candidate),
        )

    def test_designation_change_with_separator_variants_matches(self):
        self.assertTrue(
            self.matches("API", "API STD/610", "API RP-610")
        )

    def test_api_bulletin_alias_matches_bare_number(self):
        self.assertTrue(
            self.matches("API", "API 1178", "API BULL 1178:2024")
        )

    def test_asme_optional_b_prefix_keeps_decimal_identifier(self):
        self.assertTrue(
            self.matches("ASME", "ASME 36.10", "ASME B36.10:2022")
        )

    def test_repeated_separator_in_chapter_number_matches(self):
        self.assertTrue(
            self.matches(
                "API",
                "API MPMS CHAPTER 11/.1",
                "API MPMS CHAPTER 11.1:2004",
            )
        )

    def test_compound_section_punctuation_matches(self):
        self.assertTrue(
            self.matches("BSI", "BS 1139 SEC 1/.2", "BS 1139-1.2")
        )

    def test_withdrawn_status_is_not_part_of_identity(self):
        self.assertTrue(
            self.matches("BS", "BS 1501 PT 1/WITHDRAWN", "BS 1501 PART 1:2000")
        )

    def test_language_suffix_does_not_hide_edition_year(self):
        identity = parse_identity("IEC", "IEC 60909-0:2016 (EN-FR)")
        self.assertEqual(identity["year"], 2016)
        self.assertTrue(
            self.matches(
                "IEC",
                "IEC 60909-0:2016",
                "IEC 60909-0:2016 (EN-FR)",
            )
        )

    def test_search_can_fall_back_to_latest_stored_edition(self):
        row = {
            "sdo_name": "IEC",
            "identity": parse_identity("IEC", "IEC 60909-0:2026"),
        }
        stored_edition = SimpleNamespace(
            id=1,
            standardno="IEC 60909-0 (EN-FR)",
            display_stdNo="IEC 60909-0:2016 (EN-FR)",
        )

        self.assertTrue(
            DocumentSearchService._candidate_matches_identity(
                stored_edition,
                row,
            )
        )
        self.assertIs(
            DocumentSearchService._select_candidate(
                [stored_edition],
                row,
            ),
            stored_edition,
        )

    def test_series_suffix_is_a_family_marker(self):
        identity = parse_identity("IEC", "IEC 60332:2026 SERIES/EN-FR")
        self.assertEqual(identity["year"], 2026)
        self.assertEqual(identity["qualifier"], "SERIES")

    def test_punctuation_variants_match(self):
        forms = ("ISO 1234/5", "ISO 1234-5", "ISO 1234.5", "ISO 1234 PART 5")
        for requested in forms:
            for candidate in forms:
                with self.subTest(requested=requested, candidate=candidate):
                    self.assertTrue(self.matches("ISO", requested, candidate))

        self.assertFalse(
            self.matches("ISO", "ISO 1234-5", "ISO 12345")
        )

    def test_sql_pattern_wildcards_only_original_separators(self):
        self.assertEqual(
            identity_core_sql_pattern("60909-0"),
            "60909%0",
        )

    def test_bound_like_patterns_are_prefix_anchored_and_digit_safe(self):
        patterns = identity_bound_like_patterns("API", "610")

        self.assertIn("API 610", patterns)
        self.assertIn("API % 610", patterns)
        self.assertIn("API 610:%", patterns)
        self.assertIn("API610", patterns)
        self.assertNotIn("610%", patterns)
        self.assertNotIn("API %610%", patterns)
        self.assertTrue(
            all(
                pattern.startswith("API")
                for pattern in patterns
            )
        )

    def test_identity_like_patterns_helper_matches_bound_and_unprefixed(self):
        from app.utils.standard_identity import (
            identity_like_patterns_for_hint,
            like_pattern_is_prefix_indexable,
        )

        core, patterns = identity_like_patterns_for_hint("API", "610")
        self.assertEqual(core, "610")
        self.assertIn("API 610", patterns)
        self.assertIn("API % 610", patterns)
        self.assertTrue(like_pattern_is_prefix_indexable("API 610"))
        self.assertTrue(like_pattern_is_prefix_indexable("API 610:%"))
        self.assertFalse(like_pattern_is_prefix_indexable("API % 610"))
        self.assertFalse(like_pattern_is_prefix_indexable("60909%0"))

    def test_identity_discovery_terms_uses_containment_for_long_cores(self):
        from app.utils.standard_identity import identity_discovery_terms

        core, containment, bound = identity_discovery_terms("API", "610")
        self.assertEqual(core, "610")
        self.assertEqual(containment, "610")
        self.assertEqual(bound, [])

        short_core, short_containment, short_bound = identity_discovery_terms(
            "API",
            "12",
        )
        self.assertEqual(short_core, "12")
        self.assertIsNone(short_containment)
        self.assertTrue(any(p.startswith("API") for p in short_bound))
        self.assertIn("API 12", short_bound)

    def test_skip_master_identity_keeps_display_lookups_only(self):
        service = DocumentSearchService.__new__(DocumentSearchService)

        class FakeEnrichment:
            def __init__(self):
                self.identity_calls = 0
                self.display_calls = 0
                self.standard_calls = 0

            def search_master_by_sdo_and_display_variants(self, pairs):
                self.display_calls += 1
                return [
                    SimpleNamespace(
                        id=10,
                        sdo_id=1,
                        display_stdNo="API RP 560 PART 1",
                        standardno="API RP 560 PART 1",
                        standardyear=2020,
                    )
                ]

            def search_master_by_sdo_and_standard_numbers(self, pairs):
                self.standard_calls += 1
                return []

            def search_master_by_sdo_and_identity_hints(self, hints):
                self.identity_calls += 1
                return [
                    SimpleNamespace(
                        id=99,
                        sdo_id=1,
                        display_stdNo="API STD 560 PART 9",
                        standardno="API STD 560 PART 9",
                        standardyear=2019,
                    )
                ]

        enrichment = FakeEnrichment()
        service.enrichment_repository = enrichment

        row = {
            "sdo_id": 1,
            "sdo_name": "API",
            "full_display_number": "API 560 PT",
            "request_key": ("k",),
            "identity": parse_identity("API", "API 560 PT"),
            "skip_master_identity": True,
        }

        matches = service.find_master_matches([row])

        self.assertEqual(enrichment.display_calls, 1)
        self.assertEqual(enrichment.standard_calls, 1)
        self.assertEqual(enrichment.identity_calls, 0)
        # Display masters may still be selected; identity-only PART 9 must not appear.
        selected_ids = [
            candidate.id
            for selected in matches.values()
            for candidate in selected
        ]
        self.assertNotIn(99, selected_ids)

    def test_unprefixed_like_patterns_skip_short_cores(self):
        self.assertEqual(
            identity_unprefixed_like_patterns("610", "610"),
            [],
        )
        patterns = identity_unprefixed_like_patterns("60909%0", "609090")
        self.assertIn("60909%0", patterns)
        self.assertIn("STD 60909%0", patterns)
        self.assertNotIn("60909%0%", patterns)

    def test_identity_core_appears_rejects_digit_supersets(self):
        self.assertTrue(identity_core_appears("API STD 610:2020", "610"))
        self.assertTrue(identity_core_appears("API610", "610"))
        self.assertTrue(identity_core_appears("IS 875-1", "875"))
        self.assertFalse(identity_core_appears("API 1610", "610"))

    def test_row_needs_identity_discovery_skips_strong_local_matches(self):
        row = {
            "identity": parse_identity("API", "API STD 610:2020"),
        }
        selected = SimpleNamespace(id=1, standardno="API STD 610 : 2020")

        self.assertFalse(
            DocumentSearchService._row_needs_identity_discovery(
                row,
                selected,
            )
        )
        self.assertTrue(
            DocumentSearchService._row_needs_identity_discovery(
                row,
                None,
            )
        )

        bare_part_row = {
            "identity": parse_identity("API", "API 560 PT"),
        }
        self.assertTrue(
            DocumentSearchService._row_needs_identity_discovery(
                bare_part_row,
                selected,
            )
        )

    def test_slash_zero_uses_root_identity(self):
        self.assertTrue(
            self.matches("IS", "IS 875/0", "IS 875")
        )

    def test_compact_part_and_implicit_hyphen_match(self):
        self.assertTrue(
            self.matches("IS", "IS875 PT1", "IS 875 : Part 1")
        )
        self.assertTrue(
            self.matches("API", "API 56-2", "API 56 PART 2")
        )

    def test_bare_part_matches_members_and_allows_base_fallback(self):
        requested = parse_identity("API", "API 560 PT")
        part_one = parse_identity("API", "API RP 560 PART 1")
        part_two = parse_identity("API", "API STD 560 PART 2")
        base = parse_identity("API", "API STD 560")

        self.assertTrue(identity_matches(requested, part_one))
        self.assertTrue(identity_matches(requested, part_two))
        self.assertTrue(identity_matches(requested, base))

    def test_bare_part_selection_returns_latest_per_part(self):
        row = {
            "sdo_name": "API",
            "identity": parse_identity("API", "API 560 PT"),
        }
        candidates = [
            SimpleNamespace(
                id=1,
                standardno="API RP 560 PART 1 : 2018",
                display_stdNo="API RP 560 : Part 1 : 2018",
            ),
            SimpleNamespace(
                id=2,
                standardno="API STD 560 PART 1 : 2024",
                display_stdNo="API STD 560 : Part 1 : 2024",
            ),
            SimpleNamespace(
                id=3,
                standardno="API STD 560 PART 2 : 2020",
                display_stdNo="API STD 560 : Part 2 : 2020",
            ),
            SimpleNamespace(
                id=4,
                standardno="API STD 560 : 2025",
                display_stdNo="API STD 560 : 2025",
            ),
        ]

        matches = DocumentSearchService._select_candidates(
            candidates,
            row,
        )

        self.assertEqual([candidate.id for candidate in matches], [2, 3])

    def test_unqualified_root_falls_back_to_latest_parts_when_root_missing(self):
        row = {
            "sdo_name": "AS",
            "identity": parse_identity("AS", "AS 2885"),
        }
        candidates = [
            SimpleNamespace(
                id=1,
                standardno="AS 2885-1:2018",
                display_stdNo="AS 2885-1:2018",
            ),
            SimpleNamespace(
                id=2,
                standardno="AS 2885-2:2007",
                display_stdNo="AS 2885-2:2007",
            ),
            SimpleNamespace(
                id=3,
                standardno="AS 2885-2:2016",
                display_stdNo="AS 2885-2:2016",
            ),
        ]

        matches = DocumentSearchService._select_candidates(candidates, row)

        self.assertEqual([candidate.id for candidate in matches], [1, 3])

    def test_master_root_falls_back_to_parts_when_root_missing(self):
        row = {
            "sdo_name": "AS",
            "identity": parse_identity("AS", "AS 2885"),
        }
        candidates = [
            SimpleNamespace(
                id=1,
                standardyear=2007,
                recent=0,
                standardno="AS 2885-1",
                display_stdNo="AS 2885-1:2007",
            ),
            SimpleNamespace(
                id=2,
                standardyear=2007,
                recent=0,
                standardno="AS 2885-2",
                display_stdNo="AS 2885-2:2007",
            ),
            SimpleNamespace(
                id=3,
                standardyear=2016,
                recent=1,
                standardno="AS 2885-2",
                display_stdNo="AS 2885-2:2016",
            ),
        ]

        matches = DocumentSearchService._select_master_candidates(
            candidates,
            row,
        )

        self.assertEqual([candidate.id for candidate in matches], [1, 3])

    def test_compact_is_sdo_is_extracted(self):
        parsed = ExcelExtractor()._parse_standard_value("IS875 PT 1")

        self.assertEqual(
            parsed,
            {"sdo_name": "IS", "displaystdno": "875 PT 1"},
        )

    def test_bsi_prefix_aliases_are_preserved_and_generated(self):
        parsed = parse_identity("BSI", "BS EN ISO 10434:2020")

        self.assertEqual(parsed["identifier_prefix"], "BS EN ISO")
        self.assertEqual(parsed["core_number"], "10434")
        self.assertIn("BS EN ISO 10434", parsed["variants"])
        self.assertEqual(
            build_full_display_number("BSI", "BS EN 12101-3:2015"),
            "BS EN 12101-3:2015",
        )
        self.assertEqual(
            build_full_display_number("BSI", "4211"),
            "BS 4211",
        )

    def test_duplicate_key_ignores_punctuation_and_designation(self):
        first_identity = parse_identity("API", "API RP 56-2")
        second_identity = parse_identity("API", "API STD 56 PART 2")
        different_part = parse_identity("API", "API STD 56 PART 1")

        first_key = DocumentSearchService._request_identity_key(
            4,
            "API",
            first_identity,
        )
        equivalent_key = DocumentSearchService._request_identity_key(
            4,
            "API",
            second_identity,
        )
        different_key = DocumentSearchService._request_identity_key(
            4,
            "API",
            different_part,
        )

        self.assertEqual(first_key, equivalent_key)
        self.assertNotEqual(first_key, different_key)

    def test_part_aliases_match_but_different_parts_do_not(self):
        self.assertTrue(
            self.matches("ISO", "ISO 1234 PT.1", "ISO 1234 PART-1")
        )
        self.assertFalse(
            self.matches("ISO", "ISO 1234 PART 1", "ISO 1234 PART 2")
        )

    def test_chapter_and_section_abbreviations_match(self):
        self.assertTrue(
            self.matches("API", "API 560 CH3", "API 560 CHAPTER 3")
        )
        self.assertTrue(
            self.matches("API", "API 560 SEC.2", "API 560 SECTION 2")
        )

    def test_different_editions_do_not_match(self):
        self.assertFalse(
            self.matches("ISO", "ISO 1234:2020", "ISO 1234:2021")
        )

    def test_reaffirmation_suffix_preserves_base_edition(self):
        reaffirmed = parse_identity(
            "API",
            "API RP 1626:2010 (R2020)",
        )
        base_edition = parse_identity("API", "API STD 1626:2010")
        wrong_edition = parse_identity("API", "API RP 1626:2020")

        self.assertEqual(reaffirmed["year"], 2010)
        self.assertTrue(identity_matches(reaffirmed, base_edition))
        self.assertFalse(identity_matches(reaffirmed, wrong_edition))

    def test_qualifier_only_identity_matches_separator_variants(self):
        self.assertTrue(
            self.matches(
                "API",
                "API MPMS Chapter 9.3",
                "API MPMS Chapter 9/3",
            )
        )

    def test_year_like_catalogue_numbers_keep_identity_core(self):
        for sdo, requested, candidate in (
            ("API", "2003", "API RP 2003 : 2015 (R2020)"),
            ("API", "API 2009", "API RP 2009 : 2022"),
            ("IS", "1905", "IS 1905 : 1987"),
        ):
            with self.subTest(requested=requested):
                parsed = parse_identity(sdo, requested)
                self.assertTrue(parsed["core_number"])
                self.assertIsNone(parsed["year"])
                self.assertTrue(self.matches(sdo, requested, candidate))

    def test_asme_b_prefix_allows_spaced_form(self):
        self.assertTrue(
            self.matches("ASME", "B 31.11", "ASME B31.11:2002")
        )

    def test_parenthetical_withdrawal_is_stripped(self):
        self.assertTrue(
            self.matches(
                "BS",
                "1501 PT 1 (WITHDRAWN)",
                "BS 1501-1:1980",
            )
        )

    def test_corrigendum_suffix_is_not_part_of_identity(self):
        parsed = parse_identity("ISO", "6974-1 CORR. 1")
        self.assertEqual(parsed["core_number"], "6974")
        self.assertEqual(parsed["qualifier"], "PART:1")
        self.assertTrue(
            self.matches(
                "ISO",
                "6974-1 CORR. 1",
                "ISO 6974-1:2012/Cor 1:2012",
            )
        )

    def test_jis_optional_department_letter_matches(self):
        self.assertTrue(
            self.matches("JIS", "0555:1995", "JIS K 0555:1995")
        )
        self.assertFalse(
            self.matches("JIS", "0555:1995", "JIS G 0555:2023")
        )

    def test_bsi_en_prefix_strips_to_root_number(self):
        parsed = parse_identity("BSI", "EN 1090")
        self.assertEqual(parsed["core_number"], "1090")
        self.assertIn("BS EN 1090", parsed["variants"])
        self.assertNotIn("BS EN EN 1090", parsed["variants"])

    def test_unprefixed_and_spaced_display_variants(self):
        api = parse_identity("IS", "SP 72")
        self.assertIn("SP 72", api["variants"])

        astm = parse_identity(
            "ASTM",
            "D1250 VOL VIII TAB 53B & 54B",
        )
        self.assertIn(
            "ASTM D 1250 VOL VIII TAB 53B & 54B",
            astm["variants"],
        )

    def test_letter_digit_sql_pattern_allows_optional_space(self):
        self.assertEqual(
            identity_core_sql_pattern("D1250"),
            "D%1250",
        )


if __name__ == "__main__":
    unittest.main()