import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.document_search_service import DocumentSearchService
from app.services.document_search.selection_context import use_candidate_status_map
from app.services.document_service import DocumentService
from app.services.extractors.excel_extractor import ExcelExtractor
from app.utils.standard_expression_parser import StandardExpressionParser
from app.utils.standard_formatter import build_full_display_number
from app.utils.standard_identity import (
    canonicalize_search_request,
    identity_bound_like_patterns,
    identity_core_appears,
    identity_core_sql_pattern,
    identity_index_cores,
    identity_lookup_core_tokens,
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

    def test_astm_single_designation_matches_paired_current_edition(self):
        requested = parse_identity("ASTM", "ASTM E 165 : 2009")
        current = parse_identity("ASTM", "ASTM E165/E165M : 2023")
        self.assertTrue(identity_matches(requested, current, check_year=False))

    def test_aci_decimal_designation_is_not_parsed_as_part_number(self):
        requested = parse_identity("ACI", "364.9 : 2021")
        candidate = parse_identity("ACI", "ACI 364.9:2021")

        self.assertEqual(requested["core_number"], "364.9")
        self.assertIsNone(requested["qualifier"])
        self.assertTrue(identity_matches(requested, candidate))

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

    def test_master_selection_prefers_exact_designation_over_newer_alias(self):
        row = {
            "sdo_name": "API",
            "identity": parse_identity("API", "API PUBL 1149"),
        }
        exact = SimpleNamespace(
            id=1,
            standardno="API PUBL 1149",
            display_stdNo="API PUBL 1149 : 1993",
            standardyear=1993,
            recent=0,
        )
        designation_variant = SimpleNamespace(
            id=2,
            standardno="API TR 1149",
            display_stdNo="API TR 1149 : 2015",
            standardyear=2015,
            recent=1,
        )

        selected = DocumentSearchService._select_master_candidate(
            [designation_variant, exact],
            row,
        )

        self.assertIs(selected, exact)

    def test_master_selection_falls_back_when_exact_designation_is_absent(self):
        row = {
            "sdo_name": "API",
            "identity": parse_identity("API", "API RP 10F"),
        }
        available = SimpleNamespace(
            id=1,
            standardno="API SPEC 10F",
            display_stdNo="API SPEC 10F : 2018",
            standardyear=2018,
            recent=0,
        )

        selected = DocumentSearchService._select_master_candidate(
            [available],
            row,
        )

        self.assertIs(selected, available)

    def test_withdrawn_master_status_is_not_treated_as_available(self):
        self.assertEqual(
            DocumentSearchService._master_result_status(
                {"name": "WITHDRAWN", "cart_show": 0},
                SimpleNamespace(DocumentAvailability=1),
            ),
            ("WITHDRAWN", False),
        )

    def test_historical_duplicate_status_applies_only_to_requested_edition(self):
        row = {
            "identity": parse_identity("ASME", "B 18.2.3.5M : 1979"),
            "requested_edition_status": "HISTORICAL",
        }
        self.assertEqual(
            DocumentSearchService._requested_edition_lifecycle_status(
                row, 1979
            ),
            "HISTORICAL",
        )
        self.assertIsNone(
            DocumentSearchService._requested_edition_lifecycle_status(
                row, 2026
            )
        )

    def test_stale_active_duplicate_cannot_override_historical_catalog_record(self):
        row = {
            "sdo_name": "ASME",
            "search_sdo_name": "ASME",
            "requested_sdo_name": "ASME",
            "identity": parse_identity("ASME", "B 18.2.3.5M"),
        }
        historical = SimpleNamespace(
            id=1,
            sdo_id=19,
            status_id=10,
            standardno="B18.2.3.5M(Reaffirmed2016)",
            display_stdNo="ASME B18.2.3.5M : 1979 (Reaffirmed 2016)",
            standardyear=1979,
        )
        incorrectly_active = SimpleNamespace(
            id=2,
            sdo_id=19,
            status_id=11,
            standardno="ASME B 18.2.3.5M",
            display_stdNo="ASME B 18.2.3.5M : 1979",
            standardyear=1979,
        )
        filtered = DocumentSearchService._prefer_catalog_visible_candidates(
            [incorrectly_active, historical],
            {
                10: {"name": "Historical", "cart_show": 0},
                11: {"name": "ACTIVE", "cart_show": 1},
            },
            row,
        )
        self.assertEqual([candidate.id for candidate in filtered], [1])

    def test_embedded_withdrawn_label_overrides_active_catalog_flag(self):
        row = {
            "sdo_name": "ASME",
            "search_sdo_name": "ASME",
            "requested_sdo_name": "ASME",
            "identity": parse_identity("ASME", "B 18.2.3.5M"),
        }
        explicitly_withdrawn = SimpleNamespace(
            id=3,
            sdo_id=19,
            status_id=11,
            standardno="ASME B 18.2.3.5M (WITHDRAWN)",
            display_stdNo="ASME B 18.2.3.5M (WITHDRAWN) : 1979",
            standardyear=1979,
        )
        stale_duplicate = SimpleNamespace(
            id=4,
            sdo_id=19,
            status_id=11,
            standardno="ASME B 18.2.3.5M",
            display_stdNo="ASME B 18.2.3.5M : 1979",
            standardyear=1979,
        )
        filtered = DocumentSearchService._prefer_catalog_visible_candidates(
            [stale_duplicate, explicitly_withdrawn],
            {11: {"name": "ACTIVE", "cart_show": 1}},
            row,
        )
        self.assertEqual([candidate.id for candidate in filtered], [3])
        self.assertEqual(
            DocumentSearchService._candidate_embedded_lifecycle_status(
                explicitly_withdrawn
            ),
            "WITHDRAWN",
        )

    def test_active_duplicate_wins_over_withdrawn_duplicate(self):
        row = {
            "sdo_name": "BIS",
            "search_sdo_name": "BIS",
            "identity": parse_identity("BIS", "IS 3025 PT 24 : 1986"),
        }
        withdrawn = SimpleNamespace(
            id=1,
            status_id=10,
            standardno="BIS 3025 PT 24",
            display_stdNo="BIS 3025 PT 24 : 1986",
            standardyear=1986,
        )
        stale_available_duplicate = SimpleNamespace(
            id=2,
            status_id=11,
            standardno="BIS 3025 PT 24",
            display_stdNo="BIS 3025 PT 24 : 1986",
            standardyear=1986,
        )
        selected = DocumentSearchService._prefer_catalog_visible_candidates(
            [stale_available_duplicate, withdrawn],
            {
                10: {"name": "WITHDRAWN", "cart_show": 0, "std_show": 0},
                11: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
            },
            row,
        )
        self.assertEqual([candidate.id for candidate in selected], [2])

    def test_old_year_request_selects_latest_active_edition(self):
        row = {
            "sdo_name": "BIS",
            "search_sdo_name": "BIS",
            "identity": parse_identity("BIS", "IS 3025 PT 24 : 1986"),
        }
        withdrawn_edition = SimpleNamespace(
            id=1,
            status_id=10,
            standardno="BIS 3025 PT 24",
            display_stdNo="BIS 3025 PT 24 : 1986",
            standardyear=1986,
            recent=0,
        )
        current_edition = SimpleNamespace(
            id=2,
            status_id=11,
            standardno="BIS 3025 PT 24",
            display_stdNo="BIS 3025 PT 24 : 2021",
            standardyear=2021,
            recent=1,
        )
        selected = DocumentSearchService._select_best_current_candidate(
            [current_edition, withdrawn_edition],
            row,
            {
                10: {"name": "WITHDRAWN", "cart_show": 0, "std_show": 0},
                11: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
            },
        )
        self.assertEqual([candidate.id for candidate in selected], [2])

    def test_api_yearless_edition_placeholder_cannot_override_historical_editions(self):
        # Protect current API placeholder handling pending confirmation of
        # the publisher-specific zero-year contract.
        row = {
            "sdo_name": "API",
            "search_sdo_name": "API",
            "identity": parse_identity("API", "RP 2003"),
        }
        historical = SimpleNamespace(
            id=1,
            sdo_id=4,
            status_id=3,
            standardno="API RP 2003",
            display_stdNo="API RP 2003 : 2015 (R2020)",
            standardyear=2015,
            title="Protection Against Ignitions (8th Edition)",
        )
        yearless_seventh_edition = SimpleNamespace(
            id=2,
            sdo_id=4,
            status_id=1,
            standardno="API RP 2003",
            display_stdNo="API RP 2003",
            standardyear=0,
            title="Protection Against Ignitions (7th Edition)",
        )
        selected = DocumentSearchService._select_best_current_candidate(
            [yearless_seventh_edition, historical],
            row,
            {
                1: {"name": "ACTIVE", "cart_show": 1},
                3: {"name": "WITHDRAWN", "cart_show": 0},
            },
        )
        self.assertEqual(selected, [])

    def test_old_year_iso_request_selects_newer_active_edition(self):
        row = {
            "sdo_name": "ISO",
            "requested_sdo_name": "ISO",
            "identity": parse_identity("ISO", "ISO 15589-1:2015"),
        }
        old = SimpleNamespace(
            id=1,
            status_id=10,
            standardno="ISO 15589-1",
            display_stdNo="ISO 15589-1:2015",
            standardyear=2015,
            recent=1,
        )
        current = SimpleNamespace(
            id=2,
            status_id=11,
            standardno="ISO 15589-1",
            display_stdNo="ISO 15589-1:2026",
            standardyear=2026,
            recent=0,
        )
        with use_candidate_status_map({
                10: {"name": "WITHDRAWN", "cart_show": 0, "std_show": 0},
                11: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
        }):
            selected = DocumentSearchService._select_master_candidate(
                [old, current],
                row,
            )
        self.assertIs(selected, current)

    def test_current_iso_request_ignores_newer_withdrawn_edition(self):
        row = {
            "sdo_name": "ISO",
            "requested_sdo_name": "ISO",
            "identity": parse_identity("ISO", "ISO 15589-1"),
        }
        withdrawn_2015 = SimpleNamespace(
            id=1,
            status_id=10,
            standardno="ISO 15589-1",
            display_stdNo="ISO 15589-1:2015",
            standardyear=2015,
            recent=1,
        )
        active_2026 = SimpleNamespace(
            id=2,
            status_id=11,
            standardno="ISO 15589-1",
            display_stdNo="ISO 15589-1:2026",
            standardyear=2026,
            recent=0,
        )
        with use_candidate_status_map({
                10: {"name": "WITHDRAWN", "cart_show": 0, "std_show": 0},
                11: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
        }):
            selected = DocumentSearchService._select_master_candidate(
                [withdrawn_2015, active_2026],
                row,
            )
        self.assertIs(selected, active_2026)

    def test_current_iso_request_returns_no_candidate_when_all_are_withdrawn(self):
        row = {
            "sdo_name": "ISO",
            "requested_sdo_name": "ISO",
            "identity": parse_identity("ISO", "ISO 15589-1"),
        }
        withdrawn = SimpleNamespace(
            id=1,
            status_id=10,
            standardno="ISO 15589-1",
            display_stdNo="ISO 15589-1:2015",
            standardyear=2015,
            recent=1,
        )
        with use_candidate_status_map(
            {10: {"name": "WITHDRAWN", "cart_show": 0}}
        ):
            selected = DocumentSearchService._select_master_candidate(
                [withdrawn],
                row,
            )
        self.assertIsNone(selected)

    def test_bis_revision_year_notation_reaches_catalog_lifecycle_lookup(self):
        self.assertTrue(
            DocumentSearchService._is_bis_revision_edition(
                "BIS", "IS 2099 Rev 2, 1986"
            )
        )
        self.assertFalse(
            DocumentSearchService._is_bis_revision_edition(
                "IEC", "IEC 60079 Rev 2, 1986"
            )
        )
        self.assertFalse(
            DocumentSearchService._is_bis_revision_edition(
                "BIS", "IS 2099 AMD 2"
            )
        )
        self.assertTrue(
            self.matches(
                "BIS",
                "IS 2099 Rev 2, 1986",
                "BIS 2099 : 1986",
            )
        )

    def test_bis_2099_designation_parses_as_edition_identity(self):
        # Preserve the real designation as syntax input only. This test does
        # not assert an unverified replacement or supersession relationship.
        identity = parse_identity("BIS", "BIS 2099 : 1986")

        self.assertEqual(identity["sdo_name"], "BIS")
        self.assertEqual(identity["core_number"], "2099")
        self.assertEqual(identity["year"], 1986)

    def test_active_master_status_remains_available(self):
        self.assertEqual(
            DocumentSearchService._master_result_status(
                {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
                SimpleNamespace(DocumentAvailability=1),
            ),
            ("AVAILABLE", True),
        )

    def test_missing_master_status_fails_closed(self):
        self.assertEqual(
            DocumentSearchService._master_result_status(
                None,
                SimpleNamespace(DocumentAvailability=1),
            ),
            ("STATUS UNKNOWN", False),
        )

    def test_generic_sp_infers_publisher_when_catalog_match_is_unique(self):
        service = DocumentSearchService.__new__(DocumentSearchService)
        service.enrichment_repository = SimpleNamespace(
            search_master_candidates_across_sdos=lambda core: [
                (
                    SimpleNamespace(
                        sdo_id=250,
                        standardno="NACE SP 0104",
                        display_stdNo="NACE SP 0104 : 2020",
                    ),
                    "AMPP-NACE",
                )
            ]
        )

        self.assertEqual(
            service._infer_unique_catalog_sdo("SP", "0104"),
            ("NACE", 250),
        )

    def test_generic_sp_does_not_infer_when_catalog_publishers_ambiguous(self):
        service = DocumentSearchService.__new__(DocumentSearchService)
        service.enrichment_repository = SimpleNamespace(
            search_master_candidates_across_sdos=lambda core: [
                (
                    SimpleNamespace(
                        sdo_id=218,
                        standardno="IRC SP 75",
                        display_stdNo="IRC SP 75 : 2008",
                    ),
                    "IRC",
                ),
                (
                    SimpleNamespace(
                        sdo_id=52,
                        standardno="MSS SP 75",
                        display_stdNo="MSS SP 75 : 2025",
                    ),
                    "MSS",
                ),
            ]
        )

        self.assertIsNone(service._infer_unique_catalog_sdo("SP", "75"))

    def test_known_adoption_and_ip_aliases_resolve_catalog_sdo(self):
        self.assertEqual(
            canonicalize_search_request("NZS", "2885.1"),
            ("AS", "NZS 2885.1", "AS"),
        )
        self.assertEqual(
            canonicalize_search_request("EN", "12613"),
            ("BSI", "12613", "BSI"),
        )
        self.assertEqual(
            canonicalize_search_request("IP", "264"),
            ("EI", "IP 264", "EI"),
        )
        self.assertEqual(
            canonicalize_search_request("DIN", "EN 12613"),
            ("DIN", "DIN EN 12613", "DIN"),
        )
        self.assertEqual(
            canonicalize_search_request("DIN", "EN ISO 6142-1"),
            ("DIN", "DIN EN ISO 6142-1", "DIN"),
        )

    def test_edition_only_and_custom_collection_are_not_standard_numbers(self):
        self.assertIsNone(
            StandardExpressionParser.parse("ASME 2025 Edition")
        )
        self.assertIsNone(
            StandardExpressionParser.parse(
                "IEC CUSTOM COLLECTION (20 STANDARDS"
            )
        )

    def test_document_search_inferrs_sdo_from_number_when_category_is_used(self):
        mss_candidates = DocumentSearchService._candidate_sdo_names(
            "QUALITY",
            "MSS SP 120",
        )
        self.assertIn("MSS", mss_candidates)
        self.assertNotIn("QUALITY", mss_candidates)
        self.assertIn(
            "NORSOK",
            DocumentSearchService._candidate_sdo_names(
                "DESIGN",
                "NORSOK M-710",
            ),
        )
        dansk_candidates = DocumentSearchService._candidate_sdo_names(
            "SOFT",
            "DANSK DS/EN 287-1 + AC",
        )
        self.assertIn("DANSK DS/EN", dansk_candidates)
        self.assertIn("BSI", dansk_candidates)
        self.assertIn(
            "GLOBAL",
            DocumentSearchService._candidate_sdo_names(
                "QUALITY",
                "EEC 2014/68/EU",
            ),
        )

    def test_candidate_sdo_names_dispatches_tema_class_helper(self):
        calls = []

        def is_tema(row):
            calls.append(row)
            return True

        with patch.object(
            DocumentSearchService,
            "_is_tema_edition_request",
            staticmethod(is_tema),
        ):
            names = DocumentSearchService._candidate_sdo_names(
                "",
                "Custom publication",
            )

        self.assertEqual(
            calls,
            [{"sdo_name": "", "displaystdno": "Custom publication"}],
        )
        self.assertIn("TEMA", names)

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

    def test_indexable_identity_patterns_keep_a_left_prefix(self):
        from app.utils.standard_identity import (
            identity_fulltext_terms,
            identity_indexable_like_patterns,
            like_pattern_is_prefix_indexable,
        )

        patterns = identity_indexable_like_patterns("ISO", "9001")
        self.assertIn("ISO 9001%", patterns)
        self.assertIn("ISO9001%", patterns)
        self.assertTrue(
            all(like_pattern_is_prefix_indexable(pattern) for pattern in patterns)
        )
        self.assertFalse(any(pattern.startswith("%") for pattern in patterns))
        self.assertEqual(
            identity_fulltext_terms("A29A29M"),
            ["A29A29M", "A29"],
        )
        self.assertEqual(identity_fulltext_terms("9001"), ["9001"])

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

    def test_short_dual_designation_matches_full_metric_pair(self):
        self.assertTrue(
            self.matches("ASTM", "A29/29M", "ASTM A29/A29M : 23")
        )
        self.assertTrue(
            self.matches("ASTM", "A991/991M", "ASTM A991/A991M : 10")
        )

    def test_national_iso_and_shorthand_forms_match(self):
        self.assertTrue(
            self.matches("ASME", "BPVC II D", "ASME BPVC SECTION II PART D")
        )
        self.assertTrue(
            identity_matches(
                parse_identity(
                    *canonicalize_search_request(
                        "DANSK DS/EN",
                        "287-1 + AC",
                    )[:2]
                ),
                parse_identity("BSI", "BS EN 287-1:2011"),
                check_year=False,
            )
        )
        self.assertTrue(
            identity_matches(
                parse_identity(
                    *canonicalize_search_request(
                        "AMS",
                        "H 6875 REV C",
                    )[:2]
                ),
                parse_identity("SAE", "SAE AMSH6875C : 2020"),
                check_year=False,
            )
        )
        for sdo_name, number, catalog_title in (
            ("RP", "10D-2", "API RP 10D-2 : 2020"),
            ("SPEC", "6A", "API SPEC 6A : 2024"),
            ("BULL", "5C2", "API BULL 5C2 : 2020"),
            ("PUBL", "1149", "API PUBL 1149 : 2020"),
            ("STD", "1104", "API STD 1104 : 2021"),
            ("PCC", "2", "ASME PCC-2 : 2022"),
            ("HM", "31", "EI HM 31 : 2004"),
            ("DIS", "17089-1", "ISO DIS 17089-1 : 2009"),
            ("DIRECTIVE", "2014/68/EU", "GLOBAL EEC 2014/68/EU : 2014"),
            ("NORSOK", "M-630", "GLOBAL NORSOK M-630 : 2020"),
            ("ANSI/ASNT-CP", "189", "ASNT CP 189 : 2020"),
            ("ANSI/FCI", "70-2", "ANSI FCI 70-2 : 2021"),
        ):
            request_sdo, request_number, _ = canonicalize_search_request(
                sdo_name,
                number,
            )
            with self.subTest(sdo=sdo_name, number=number):
                self.assertTrue(
                    identity_matches(
                        parse_identity(request_sdo, request_number),
                        parse_identity(request_sdo, catalog_title),
                        check_year=False,
                    )
                )
        self.assertTrue(
            self.matches("ASTM", "E125-63", "ASTM E125 : 63(2023)")
        )
        self.assertTrue(
            self.matches("ISO", "DANSK DS/EN ISO 11970", "ISO 11970:2025")
        )
        self.assertTrue(
            self.matches("ISO", "AENOR UNE-EN ISO 10434", "ISO 10434:2020")
        )
        self.assertTrue(
            identity_matches(
                parse_identity(
                    *canonicalize_search_request(
                        "NACE",
                        "MR0175-2021/ISO 15156:2020 & Technical Circulars 1, 2, & 3",
                    )[:2]
                ),
                parse_identity(
                    *canonicalize_search_request(
                        "NACE",
                        "ANSI-NACE MR0175-2021-ISO 15156 : 2021",
                    )[:2]
                ),
                check_year=False,
            )
        )
        self.assertTrue(
            self.matches("SSPC", "VIS 1-02", "SSPC VIS 1 GUIDE : 2002")
        )
        self.assertTrue(
            self.matches(
                "SSPC",
                "SP 10 (WAB)/NACE WAB-2",
                "SSPC-SP 10 (WAB)-2015-NACE WAB-2 : 2015",
            )
        )
        self.assertTrue(
            self.matches(
                "MSS",
                "SP-55-2025 Standard and 11 x 17 Laminated Photo Set",
                "MSS SP 55:2025 AND 11 X 17 LAMINATED PHOTO SET",
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

    def test_catalogue_aliases_and_notes_are_normalized_for_search(self):
        self.assertEqual(
            canonicalize_search_request("RP", "10D-2"),
            ("API", "RP 10D-2", "API"),
        )
        self.assertEqual(
            canonicalize_search_request("SPEC", "6A"),
            ("API", "SPEC 6A", "API"),
        )
        self.assertEqual(
            canonicalize_search_request("BULL", "5C2"),
            ("API", "BULL 5C2", "API"),
        )
        self.assertEqual(
            canonicalize_search_request("PUBL", "1149"),
            ("API", "PUBL 1149", "API"),
        )
        self.assertEqual(
            canonicalize_search_request("STD", "1104"),
            ("API", "STD 1104", "API"),
        )
        self.assertEqual(
            canonicalize_search_request("PCC", "2"),
            ("ASME", "PCC-2", "ASME"),
        )
        self.assertEqual(
            canonicalize_search_request("MR", "0175 & ISO 15156"),
            ("NACE", "MR0175/ISO 15156", "AMPP-NACE"),
        )
        self.assertEqual(
            canonicalize_search_request("HM", "31"),
            ("EI", "HM 31", "EI"),
        )
        self.assertEqual(
            canonicalize_search_request("DIS", "17089-1"),
            ("ISO", "DIS 17089-1", "ISO"),
        )
        self.assertEqual(
            canonicalize_search_request("AMS", "H 6875 REV C"),
            ("SAE", "AMS H 6875C", "SAE"),
        )
        self.assertEqual(
            canonicalize_search_request("DIRECTIVE", "2014/68/EU"),
            ("EEC", "2014/68/EU", "GLOBAL"),
        )
        self.assertEqual(
            canonicalize_search_request("NORSOK", "M-630"),
            ("NORSOK", "M-630", "GLOBAL"),
        )
        self.assertEqual(
            canonicalize_search_request("ANSI/ASNT-CP", "189"),
            ("ASNT", "CP 189", "ASNT"),
        )
        self.assertEqual(
            canonicalize_search_request("ANSI/FCI", "70-2"),
            ("ANSI", "FCI 70-2", "ANSI"),
        )
        self.assertEqual(
            canonicalize_search_request("ISPM", "15"),
            ("ISPM", "15", "GLOBAL"),
        )
        self.assertEqual(
            canonicalize_search_request("MSS SP", "44"),
            ("MSS", "SP 44", "MSS"),
        )
        self.assertEqual(
            canonicalize_search_request("SSPC", "SP 1"),
            ("SSPC", "SP 1", "AMPP-SSPC"),
        )
        self.assertEqual(
            canonicalize_search_request("NACE", "SP0169"),
            ("NACE", "SP0169", "AMPP-NACE"),
        )
        self.assertEqual(
            canonicalize_search_request("ANSI", "HI 9.8"),
            ("HI", "HI 9.8", "HI"),
        )
        self.assertEqual(
            canonicalize_search_request("API", "545-WITHDRAWN"),
            ("API", "545", "API"),
        )
        self.assertEqual(
            canonicalize_search_request("AENOR", "13018"),
            ("AENOR", "13018", "AENOR"),
        )
        self.assertEqual(
            canonicalize_search_request("AENOR", "UNE-EN 13018"),
            ("AENOR", "UNE-EN 13018", "AENOR"),
        )
        self.assertEqual(
            canonicalize_search_request("UNI", "1371-1"),
            ("BSI", "1371-1", "BSI"),
        )
        self.assertEqual(
            canonicalize_search_request("EEC", "2014/68/EU"),
            ("EEC", "2014/68/EU", "GLOBAL"),
        )
        self.assertEqual(
            canonicalize_search_request(
                "NFPA",
                "12 (2025 Edition)",
            ),
            ("NFPA", "12", "NFPA"),
        )

    def test_part_range_matches_a_part_inside_the_range(self):
        self.assertTrue(
            self.matches(
                "IEC",
                "60947 (Pt 1-8)",
                "IEC 60947-3:2020",
            )
        )
        self.assertFalse(
            self.matches(
                "IEC",
                "60947 (Pt 1-8)",
                "IEC 60947-9:2020",
            )
        )

    def test_parenthesized_part_range_expands_to_clean_part_identifiers(self):
        expanded = DocumentService()._expand_canonical_rows([{
            "sdo_name": "BIS",
            "displaystdno": "IS 8909 (Part 1-5)",
        }])

        self.assertEqual(
            [row["displaystdno"] for row in expanded],
            [f"IS 8909 PART {part}" for part in range(1, 6)],
        )

    def test_part_number_does_not_match_same_suffix_under_another_parent(self):
        self.assertFalse(
            self.matches(
                "IEC",
                "62443 PART 1",
                "IEC 62443-3-1:2013",
            )
        )

    def test_with_subsections_expands_each_top_level_part_and_keeps_nested_parts(self):
        expanded = DocumentService()._expand_canonical_rows([{
            "sdo_name": "IEC",
            "displaystdno": (
                "IEC 62443 Parts 1-4 with subsections (Total- 10 Codes)"
            ),
        }])

        self.assertEqual(
            [row["displaystdno"] for row in expanded],
            [f"62443 PART {part}" for part in range(1, 5)],
        )
        self.assertTrue(all(row["include_subsections"] for row in expanded))

    def test_subsection_lookup_returns_only_children_of_requested_top_level_part(self):
        row = {
            "sdo_name": "IEC",
            "identity": {
                **parse_identity("IEC", "IEC 62443 PART 1"),
                "family_lookup": True,
            },
        }
        candidates = [
            SimpleNamespace(
                id=index,
                standardno=number,
                display_stdNo=number,
                standardyear=year,
            )
            for index, number, year in (
                (1, "IEC 62443-1-1:2024", 2024),
                (2, "IEC 62443-1-2:2020", 2020),
                (3, "IEC 62443-1-2/COR1:2021", 2021),
                (4, "IEC 62443-1-1:2018/COR1:2019", 2019),
                (5, "IEC 62443-2-1:2019", 2019),
                (6, "IEC 62443-3-1:2013", 2013),
            )
        ]

        selected = DocumentSearchService._select_candidates(candidates, row)
        selected_master = DocumentSearchService._select_master_candidates(
            candidates,
            row,
        )

        self.assertEqual(
            [candidate.display_stdNo for candidate in selected],
            [
                "IEC 62443-1-1:2024",
                "IEC 62443-1-2:2020",
            ],
        )

    def test_series_lookup_returns_latest_language_matched_parts_not_series_root(self):
        row = {
            "sdo_name": "IEC",
            "search_sdo_name": "IEC",
            "displaystdno": "IEC 62305:2025 SER (EN-FR)",
            "identity": parse_identity(
                "IEC",
                "IEC 62305:2025 SER (EN-FR)",
            ),
        }
        candidates = [
            SimpleNamespace(
                id=index,
                standardno=number,
                display_stdNo=number,
                standardyear=year,
            )
            for index, number, year in (
                (1, "IEC 62305 SER (EN-FR)", 2013),
                (2, "IEC 62305-1:2010 (EN-FR)", 2010),
                (3, "IEC 62305-1:2024 (EN-FR)", 2024),
                (4, "IEC 62305-1:2024/COR1:2024 (EN-FR)", 2024),
                (5, "IEC 62305-1:2024 (EN_D)", 2024),
                (6, "IEC 62305-2:2024 (EN-FR)", 2024),
            )
        ]

        selected = DocumentSearchService._select_candidates(candidates, row)

        self.assertEqual(
            [candidate.display_stdNo for candidate in selected],
            ["IEC 62305-1:2024 (EN-FR)", "IEC 62305-2:2024 (EN-FR)"],
        )

    def test_corrigendum_candidate_with_space_suffix_is_excluded(self):
        candidate = SimpleNamespace(
            standardno="IEC 61378-1 CORR 1 : 2012",
            display_stdNo="IEC 61378-1 CORR 1 : 2012",
            title="Corrigendum",
        )
        self.assertTrue(
            DocumentSearchService._candidate_should_be_excluded(candidate)
        )

    def test_amendment_no_suffix_candidate_is_excluded(self):
        candidate = SimpleNamespace(
            standardno="IEC 60079-0 Amendment No. 1",
            display_stdNo="IEC 60079-0:2017 Amendment No. 1",
            title="Amendment",
        )
        self.assertTrue(
            DocumentSearchService._candidate_should_be_excluded(candidate)
        )

    def test_subsection_lookup_prefers_requested_national_adoption_prefix(self):
        identity = {
            **parse_identity("DIN", "DIN IEC 61508 PART 2"),
            "family_lookup": True,
        }
        row = {"sdo_name": "DIN", "identity": identity}
        candidates = [
            SimpleNamespace(
                id=index,
                standardno=number,
                display_stdNo=number,
                standardyear=year,
            )
            for index, number, year in (
                (1, "DIN IEC 61508-2 (DRAFT) : 2006", 2006),
                (2, "DIN EN 61508-2 (DRAFT) : 2009", 2009),
            )
        ]

        selected = DocumentSearchService._select_candidates(candidates, row)
        selected_master = DocumentSearchService._select_master_candidates(
            candidates,
            row,
        )

        self.assertEqual(
            [candidate.standardno for candidate in selected],
            ["DIN IEC 61508-2 (DRAFT) : 2006"],
        )
        self.assertEqual(
            [candidate.standardno for candidate in selected_master],
            ["DIN IEC 61508-2 (DRAFT) : 2006"],
        )

    def test_subsection_lookup_honors_part_ranges_in_unexpanded_rows(self):
        row = {
            "sdo_name": "IEC",
            "identity": {
                **parse_identity("IEC", "IEC 62443 PART 1-2"),
                "family_lookup": True,
            },
        }
        candidates = [
            SimpleNamespace(
                id=index,
                standardno=number,
                display_stdNo=number,
                standardyear=year,
            )
            for index, number, year in (
                (1, "IEC 62443-1-1:2024", 2024),
                (2, "IEC 62443-2-1:2020", 2020),
                (3, "IEC 62443-3-1:2019", 2019),
            )
        ]

        selected = DocumentSearchService._select_candidates(candidates, row)

        self.assertEqual(
            [candidate.display_stdNo for candidate in selected],
            ["IEC 62443-1-1:2024", "IEC 62443-2-1:2020"],
        )

    def test_draft_label_is_not_part_of_din_identity(self):
        self.assertTrue(
            self.matches(
                "DIN",
                "DIN IEC 61508 PART 1",
                "DIN IEC 61508-1 (DRAFT) : 2006",
            )
        )

    def test_din_sdo_with_en_designation_matches_catalogued_din_adoption(self):
        for number in (
            "EN 12760",
            "EN 1370",
            "EN 1371-2",
            "EN 12681-1",
            "EN 12680-1",
        ):
            with self.subTest(number=number):
                lookup_sdo, lookup_number, _ = canonicalize_search_request(
                    "DIN",
                    number,
                )
                requested = parse_identity(lookup_sdo, lookup_number)
                candidate = parse_identity(
                    "DIN",
                    f"DIN {number}",
                )

                self.assertTrue(
                    identity_matches(
                        requested,
                        candidate,
                        check_year=False,
                    )
                )

    def test_din_en_iso_adoption_matches_catalog_identity(self):
        sdo, number, _ = canonicalize_search_request(
            "DIN",
            "EN ISO 6142-1",
        )
        requested = parse_identity(sdo, number)
        candidate = parse_identity(
            "DIN",
            "DIN EN ISO 6142-1 : 2015",
        )

        self.assertEqual(requested["core_number"], "6142")
        self.assertEqual(requested["qualifier"], "PART:1")
        self.assertTrue(
            identity_matches(
                requested,
                candidate,
                check_year=False,
            )
        )

    def test_jis_optional_department_letter_matches(self):
        self.assertTrue(
            self.matches("JIS", "0555:1995", "JIS K 0555:1995")
        )
        self.assertFalse(
            self.matches("JIS", "0555:1995", "JIS G 0555:2023")
        )

    def test_legacy_iec_month_labels_normalize_to_compound_parts(self):
        for number, expected in (
            ("60034 01-Feb Ed 2.0 - IEC 60034-2-1", "60034-2-1"),
            ("60034 02-Feb Ed 1.0", "60034-2-2"),
            ("60079 02-Oct 2009", "60079-10-2"),
            ("61800 01-May", "61800-5-1"),
        ):
            with self.subTest(number=number):
                _, normalized, _ = canonicalize_search_request("IEC", number)
                self.assertEqual(normalized, expected)
                self.assertIsNone(parse_identity("IEC", normalized)["year"])

    def test_iec_duplicate_publication_year_is_not_a_part(self):
        for number, expected, year in (
            ("60079 26-2006 2006", "60079 26:2006", 2006),
            (
                "BS EN ISO/IEC 80079 34-2020 2020",
                "BS EN ISO/IEC 80079 34:2020",
                2020,
            ),
        ):
            with self.subTest(number=number):
                sdo, normalized, _ = canonicalize_search_request(
                    "IEC",
                    number,
                )
                identity = parse_identity(sdo, normalized)
                self.assertEqual(normalized, expected)
                self.assertEqual(identity["qualifier"], "PART:26" if year == 2006 else "PART:34")
                self.assertEqual(identity["year"], year)

    def test_iec_prefixed_iso_code_uses_iso_sdo(self):
        sdo, normalized, id_name = canonicalize_search_request(
            "IEC",
            "ISO 1940 1",
        )

        self.assertEqual((sdo, id_name), ("ISO", "ISO"))
        self.assertEqual(parse_identity(sdo, normalized)["core_number"], "1940")
        self.assertEqual(parse_identity(sdo, normalized)["qualifier"], "PART:1")

    def test_explicit_iso_iec_and_bis_iec_designations_keep_catalogue_sdo(self):
        self.assertEqual(
            canonicalize_search_request("ISO/IEC", "80079 34 Ed 1.0"),
            ("IEC", "80079 34", "IEC"),
        )
        sdo, number, id_name = canonicalize_search_request(
            "BIS",
            "IS IEC 60079 29-4 2009",
        )
        identity = parse_identity(sdo, number)
        self.assertEqual((sdo, id_name), ("BIS", "BIS"))
        self.assertEqual(identity["core_number"], "60079PART29")
        self.assertEqual(identity["qualifier"], "SECTION:4")
        self.assertEqual(identity["year"], 2009)

    def test_bis_is_iec_identity_never_matches_iec_catalogue(self):
        bis = parse_identity("BIS", "IS IEC 60079 2 2014")
        iec = parse_identity("IEC", "IEC 60079-2:2014")
        self.assertEqual(bis["sdo_name"], "BIS")
        self.assertEqual(bis["core_number"], "60079")
        self.assertEqual(bis["qualifier"], "PART:2")
        self.assertFalse(identity_matches(bis, iec))

    def test_bis_standard_designations_are_displayed_as_is(self):
        standard = {
            "standardno": "BIS 513",
            "display_stdNo": "BIS 513 : 2008",
        }
        DocumentSearchService._normalize_bis_standard_designation(standard)
        self.assertEqual(standard["standardno"], "IS 513")
        self.assertEqual(standard["display_stdNo"], "IS 513 : 2008")

    def test_explicit_bis_is_iec_edition_surfaces_same_bis_record_with_year_mismatch(self):
        row = {
            "sdo_name": "BIS",
            "search_sdo_name": "BIS",
            "displaystdno": "IS IEC 60079 26-2006 2006",
            "identity": parse_identity("BIS", "IS IEC 60079 26-2006 2006"),
        }
        newer = SimpleNamespace(
            id=1,
            standardno="IS/IEC 60079 : Part 26",
            display_stdNo="IS/IEC 60079 : Part 26 : 2021",
            standardyear=2021,
            recent=1,
        )
        self.assertIs(
            DocumentSearchService._select_master_candidate([newer], row),
            newer,
        )

    def test_iec_legacy_three_digit_numbers_match_six_series_catalogue_ids(self):
        for legacy, catalog in (
            ("146-1-3", "IEC 60146-1-3:1991"),
            ("439-1", "IEC 60439-1:1999"),
        ):
            with self.subTest(legacy=legacy):
                self.assertTrue(
                    self.matches("IEC", legacy, catalog)
                )
                core = parse_identity("IEC", catalog)["core_number"]
                self.assertIn(
                    core[2:],
                    identity_index_cores("IEC", core),
                )
                self.assertIn(
                    f"60{legacy.rsplit('-', 1)[0]}",
                    identity_lookup_core_tokens(
                        "IEC",
                        parse_identity("IEC", legacy)["core_number_pattern"],
                    ),
                )

    def test_iec_joint_iso_iec_prefix_is_removed_from_candidate_identity(self):
        self.assertTrue(
            self.matches(
                "IEC",
                "80079 34",
                "ISO/IEC 80079-34:2018 (EN-FR)",
            )
        )

    def test_edition_revision_and_amendment_metadata_are_not_identity(self):
        for number in (
            "60034 1 Ed 14.0",
            "60034-1 Edition 14.0",
            "60034-1 Rev 2",
            "60034-1 Amendment 2, 2024",
        ):
            with self.subTest(number=number):
                _, normalized, _ = canonicalize_search_request("IEC", number)
                identity = parse_identity("IEC", normalized)
                self.assertEqual(identity["core_number"], "60034")
                self.assertEqual(identity["qualifier"], "PART:1")

    def test_legacy_is_date_components_are_metadata_not_parts(self):
        cases = {
            "3347 01-Jan": ("3347", None, None),
            "3347 02-Jan": ("3347", None, None),
            "3347 01-Mar 1988": ("3347", None, None),
            "3347 02-Aug 1992": ("3347", None, None),
        }
        for number, expected in cases.items():
            with self.subTest(number=number):
                _, normalized, _ = canonicalize_search_request("IS", number)
                identity = parse_identity("IS", normalized)
                self.assertEqual(
                    (
                        identity["core_number"],
                        identity["qualifier"],
                        identity["year"],
                    ),
                    expected,
                )
                self.assertFalse(identity["family_lookup"])

    def test_bis_explicit_part_section_is_kept_and_dates_are_ignored(self):
        cases = {
            "60079 29-2 2007": ("60079PART29", "SECTION:2", 2007),
            "60947 02-May 2007": ("60947", None, None),
            "5001 01-Feb 1973": ("5001", None, None),
            "14901 01-May 2010": ("14901", None, None),
            "3347 01-May PART 5 SECTION 1": (
                "3347PART5",
                "SECTION:1",
                None,
            ),
        }
        for number, expected in cases.items():
            with self.subTest(number=number):
                _, normalized, _ = canonicalize_search_request("BIS", number)
                identity = parse_identity("BIS", normalized)
                self.assertEqual(
                    (
                        identity["core_number"],
                        identity["qualifier"],
                        identity["year"],
                    ),
                    expected,
                )

    def test_explicit_part_request_selects_only_its_part_and_section(self):
        _, normalized, _ = canonicalize_search_request(
            "IS",
            "3347 PART 5 SECTION 1 1979",
        )
        identity = parse_identity("IS", normalized)
        row = {"sdo_name": "IS", "identity": identity}
        candidates = [
            SimpleNamespace(
                id=index,
                standardno=number,
                display_stdNo=number,
                standardyear=year,
            )
            for index, number, year in (
                (1, "IS 3347 PART 1 SECTION 1:1979", 1979),
                (2, "IS 3347 PART 1 SECTION 2:1979", 1979),
                (3, "IS 3347 PART 5 SECTION 1:1979", 1979),
                (4, "IS 3347 PART 8 SECTION 1:1992", 1992),
                (5, "IS 3348 PART 8 SECTION 2:1992", 1992),
            )
        ]

        selected = DocumentSearchService._select_candidates(candidates, row)
        self.assertEqual(
            [candidate.display_stdNo for candidate in selected],
            ["IS 3347 PART 5 SECTION 1:1979"],
        )

    def test_legacy_is_date_requests_share_one_base_identity(self):
        identities = []
        for number in ("3347 01-Mar 1988", "3347 02-Jan"):
            _, normalized, _ = canonicalize_search_request("IS", number)
            identities.append(parse_identity("IS", normalized))

        self.assertEqual(identities[0]["core_number"], "3347")
        self.assertEqual(identities[0]["core_number"], identities[1]["core_number"])
        self.assertIsNone(identities[0]["qualifier"])
        self.assertIsNone(identities[1]["qualifier"])
        self.assertIsNone(identities[0]["year"])
        self.assertIsNone(identities[1]["year"])

    def test_unqualified_local_request_selects_newest_catalog_year(self):
        identity = parse_identity("IS", "IS 7421")
        row = {
            "sdo_name": "IS",
            "search_sdo_name": "IS",
            "identity": identity,
        }
        candidates = [
            SimpleNamespace(
                id=1,
                standardno="IS 7421:1988",
                display_stdNo="IS 7421:1988",
                standardyear=1988,
            ),
            SimpleNamespace(
                id=2,
                standardno="IS 7421:2020",
                display_stdNo="IS 7421:2020",
                standardyear=2020,
            ),
        ]

        selected = DocumentSearchService._select_candidate(candidates, row)

        self.assertEqual(selected.id, 2)

    def test_date_suffix_on_unqualified_request_selects_latest_catalog_parts(self):
        _, normalized, _ = canonicalize_search_request("IS", "3347 01-Jan")
        identity = parse_identity("IS", normalized)
        row = {"sdo_name": "IS", "identity": identity}
        candidates = [
            SimpleNamespace(
                id=index,
                standardyear=year,
                recent=recent,
                standardno=number,
                display_stdNo=number,
            )
            for index, number, year, recent in (
                (1, "IS 3347 PART 1 SECTION 1:1979", 1979, 0),
                (2, "IS 3347 PART 1 SECTION 2:1989", 1989, 0),
                (3, "IS 3347 PART 2 SECTION 1:2001", 2001, 1),
            )
        ]

        selected = DocumentSearchService._select_candidates(
            candidates,
            row,
        )

        self.assertEqual([candidate.id for candidate in selected], [1, 2, 3])

    def test_bis_unqualified_root_selects_latest_embedded_parts(self):
        identity = parse_identity("BIS", "IS 3347")
        row = {"sdo_name": "BIS", "identity": identity}
        candidates = [
            SimpleNamespace(
                id=index,
                standardyear=year,
                recent=recent,
                standardno=number,
                display_stdNo=number,
            )
            for index, number, year, recent in (
                (1, "IS 3347 : Part 3 : Sec 1 : 1988", 1988, 0),
                (2, "IS 3347 : Part 8 : Sec 2 : 1992", 1992, 1),
            )
        ]

        selected = DocumentSearchService._select_master_candidates(
            candidates,
            row,
        )

        self.assertEqual([candidate.id for candidate in selected], [1, 2])

    def test_search_preserves_each_input_when_multiple_rows_match_one_standard(self):
        candidate = SimpleNamespace(
            id=10,
            Standard_id="BIS3347",
            sdo_id=1,
            status_id=11,
            DocumentAvailability=1,
            standardno="IS 3347",
            display_stdNo="IS 3347",
            title="Standard title",
        )

        class FakeRepository:
            def search_by_sdo_and_display_variants(self, _pairs):
                return [candidate]

            def search_by_sdo_and_display_numbers(self, _pairs):
                return []

            def search_by_sdo_and_normalized_numbers(self, _pairs):
                return []

            def search_by_sdo_and_standard_numbers(self, _pairs):
                return []

            def search_by_sdo_and_identity_hints(self, _hints):
                return []

        service = DocumentSearchService.__new__(DocumentSearchService)
        service.repository = FakeRepository()
        service.resolve_sdo_ids = lambda _names, fallback_names=None: {"BIS": 1}
        service.enrichment_repository = SimpleNamespace(
            get_standard_status_map=lambda _status_ids: {
                11: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
            },
        )
        service.search_service = SimpleNamespace(
            format_standard=lambda standard: {
                "Standard_id": standard.Standard_id,
                "sdo_id": standard.sdo_id,
                "standardno": standard.standardno,
                "display_stdNo": standard.display_stdNo,
                "title": standard.title,
            },
            validate_standard=lambda _standard: "AVAILABLE",
        )
        service.find_master_matches = lambda _rows: {}
        service.build_enrichment_map = lambda _standards: {
            "BIS3347": {
                "document_available": True,
                "has_database_price": True,
            },
        }

        results = service.search(
            [
                {"sdo_name": "BIS", "displaystdno": "IS 3347 01-Jan"},
                {"sdo_name": "BIS", "displaystdno": "IS 3347 02-Jan"},
            ]
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(
            [result["requested_standard"] for result in results],
            ["IS 3347 01-Jan", "IS 3347 02-Jan"],
        )
        self.assertTrue(all(result["matched"] for result in results))
        self.assertEqual(
            [result["standard"]["Standard_id"] for result in results],
            ["BIS3347", "BIS3347"],
        )
        self.assertTrue(
            all("duplicate_requests" not in result for result in results)
        )

    def test_ul_red_line_and_revision_records_are_not_base_standard_matches(self):
        candidates = [
            SimpleNamespace(
                standardno="UL 840",
                display_stdNo="UL 840 : 2022 (Red Line)",
            ),
            SimpleNamespace(
                standardno="UL 840",
                display_stdNo="UL 840 : 2016 (Revision)",
            ),
            SimpleNamespace(
                standardno="UL 840",
                display_stdNo="UL 840 : 2005",
            ),
            SimpleNamespace(
                standardno="UL 1741",
                display_stdNo=(
                    "UL 1741 : 2023 (Certification Requirement Decision)"
                ),
            ),
            SimpleNamespace(
                standardno="UL 1741",
                display_stdNo="UL 1741 : 2021",
            ),
            SimpleNamespace(
                standardno="IEC 840",
                display_stdNo="IEC 840 : 2022 (Red Line)",
            ),
        ]

        self.assertTrue(
            DocumentSearchService._candidate_should_be_excluded(candidates[0])
        )
        self.assertTrue(
            DocumentSearchService._candidate_should_be_excluded(candidates[1])
        )
        self.assertFalse(
            DocumentSearchService._candidate_should_be_excluded(candidates[2])
        )
        self.assertFalse(
            DocumentSearchService._candidate_should_be_excluded(candidates[4])
        )
        self.assertTrue(
            DocumentSearchService._candidate_should_be_excluded(candidates[3])
        )
        self.assertFalse(
            DocumentSearchService._candidate_should_be_excluded(candidates[5])
        )

    def test_explicit_family_request_keeps_multiple_family_members(self):
        identity = parse_identity("API", "API 560 PART")

        self.assertTrue(
            DocumentSearchService._should_expand_family(identity)
        )
        self.assertTrue(
            DocumentSearchService._should_expand_family(
                parse_identity("IEC", "IEC 62443 PART 1"),
                include_subsections=True,
            )
        )

    def test_is_roman_numeral_part_survives_trailing_year(self):
        identity = parse_identity("IS", "IS 3715 IV 1971")

        self.assertEqual(identity["core_number"], "3715")
        self.assertEqual(identity["qualifier"], "PART:IV")
        self.assertEqual(identity["year"], 1971)
        self.assertTrue(
            self.matches("IS", "IS 3715 IV", "IS 3715 PART IV:1971")
        )

    def test_bis_roman_part_matches_catalog_arabic_part(self):
        self.assertTrue(
            self.matches(
                "BIS",
                "IS 1076 II",
                "IS 1076 : Part 2 : 1985",
            )
        )
        self.assertTrue(
            self.matches(
                "BIS",
                "IS 6297 II",
                "IS 6297 : Part 2 : 1973",
            )
        )
        self.assertFalse(
            self.matches(
                "BIS",
                "IS 6297 II",
                "IS 6297 : Part 3 : 1974",
            )
        )

    def test_atex_directive_resolves_through_eec_catalog_sdo(self):
        self.assertEqual(
            canonicalize_search_request(
                "ATEX",
                "ATEX 2014/34/EU 2017",
            ),
            ("EEC", "2014/34/EU 2017", "GLOBAL"),
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
