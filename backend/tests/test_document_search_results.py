import unittest
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.core.standard_identity import (
    designation_is_ieee_iec_dual_logo,
    ieee_iec_joint_prefix,
    identity_lookup_core_tokens,
    parse_identity,
)
from app.services.document_search import result_helpers
from app.services.document_search.identity_discovery import (
    build_identity_candidate_index,
)
from app.services.document_search.result_assembly import (
    _requested_edition_year,
)
from app.services.document_search.enrichment_builder import (
    committee_display_codes,
)
from app.services.document_search_service import DocumentSearchService
from app.services.export_service import ExportService


class _SearchService:
    @staticmethod
    def _not_found_reason(result):
        return result_helpers.not_found_reason(result)


def _resolved_result(source_identity, returned):
    return {
        "requested_sdo": "BIS",
        "requested_standard": returned,
        "matched": True,
        "status": "AVAILABLE",
        "standard": {
            "Standard_id": "BIS-3025-PT24-2021",
            "sdo_id": 1,
            "standardno": returned,
            "display_stdNo": returned,
        },
        "_source_request_identity": source_identity,
    }


def _not_found_result(source_identity, requested):
    return {
        "requested_sdo": "BIS",
        "requested_standard": requested,
        "matched": False,
        "status": "NOT FOUND",
        "standard": None,
        "actions": {"manual_search": True},
        "_source_request_identity": source_identity,
    }


class ResolvedEditionReportingTests(unittest.TestCase):
    def setUp(self):
        self.old_edition = "IS 3025 PT 24 : 1986"
        self.current_edition = "IS 3025 PT 24 : 2021"
        self.source_identity = (
            "customer-list.xlsx",
            8,
            "IS3025PT24:1986",
        )

    def test_series_edition_year_does_not_constrain_individual_parts(self):
        self.assertIsNone(
            _requested_edition_year(
                {
                    "identity": {
                        "qualifier": "SERIES",
                        "year": 2026,
                    }
                }
            )
        )
        self.assertEqual(
            _requested_edition_year(
                {
                    "identity": {
                        "qualifier": "PART:6",
                        "year": 2010,
                    }
                }
            ),
            2010,
        )

    def normalize(self, results):
        return result_helpers.deduplicate_results(results, _SearchService)

    def test_resolved_older_edition_is_not_reported_not_found(self):
        resolved = _resolved_result(
            self.source_identity,
            self.current_edition,
        )
        stale_unmatched = _not_found_result(
            self.source_identity,
            self.old_edition,
        )

        results = self.normalize([resolved, stale_unmatched])
        not_found = [result for result in results if not result["matched"]]

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["standard"]["display_stdNo"],
            self.current_edition,
        )
        self.assertEqual(not_found, [])

    def test_genuinely_missing_standard_remains_not_found(self):
        missing = _not_found_result(
            ("customer-list.xlsx", 9, "IS3025PT99:2015"),
            "IS 3025 PT 99 : 2015",
        )

        results = self.normalize([missing])

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["matched"])
        self.assertEqual(results[0]["status"], "NOT FOUND")

    def test_similar_but_unrelated_standard_does_not_resolve_request(self):
        similar_found = _resolved_result(
            ("customer-list.xlsx", 10, "IS3025PT240:2021"),
            "IS 3025 PT 240 : 2021",
        )
        requested_missing = _not_found_result(
            ("customer-list.xlsx", 10, "IS3025PT24:1986"),
            self.old_edition,
        )

        results = self.normalize([similar_found, requested_missing])

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["matched"])
        self.assertFalse(results[1]["matched"])
        self.assertEqual(results[1]["requested_standard"], self.old_edition)

    def test_ambiguous_publisher_request_remains_unresolved(self):
        service = DocumentSearchService.__new__(DocumentSearchService)
        service.enrichment_repository = SimpleNamespace(
            search_master_candidates_across_sdos=lambda _core: [
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

        ambiguous = _not_found_result(
            ("customer-list.xlsx", 12, "SP75"),
            "SP 75",
        )
        ambiguous.update(
            requested_sdo="SP",
            status="SDO NOT FOUND",
        )

        results = self.normalize([ambiguous])

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["matched"])
        self.assertEqual(results[0]["status"], "SDO NOT FOUND")
        self.assertIsNone(results[0]["standard"])
        self.assertTrue(results[0]["actions"]["manual_search"])

    def test_explicit_amendment_request_remains_unresolved(self):
        base_found = _resolved_result(
            ("customer-list.xlsx", 11, "IS3025PT24:1986"),
            self.current_edition,
        )
        amendment_missing = _not_found_result(
            ("customer-list.xlsx", 11, "IS3025PT24:1986AMD1"),
            "IS 3025 PT 24 : 1986 AMD 1",
        )
        amendment_missing["status_detail"] = (
            "Revision/amendment requests are excluded from standard matching."
        )

        results = self.normalize([base_found, amendment_missing])

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["matched"])
        self.assertFalse(results[1]["matched"])
        self.assertIn("amendment", results[1]["status_detail"].casefold())

    def test_successful_request_does_not_hide_another_missing_request(self):
        resolved = _resolved_result(
            self.source_identity,
            self.current_edition,
        )
        missing = _not_found_result(
            ("customer-list.xlsx", 9, "IS3025PT99:2015"),
            "IS 3025 PT 99 : 2015",
        )

        results = self.normalize([resolved, missing])

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["matched"])
        self.assertFalse(results[1]["matched"])
        self.assertEqual(results[1]["requested_standard"], "IS 3025 PT 99 : 2015")

    def test_exact_version_match_remains_found(self):
        exact_source_identity = (
            "customer-list.xlsx",
            8,
            "IS3025PT24:2021",
        )
        exact = _resolved_result(
            exact_source_identity,
            self.current_edition,
        )

        results = self.normalize([exact])

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["matched"])
        self.assertEqual(
            results[0]["requested_standard"],
            self.current_edition,
        )

    def test_older_edition_on_another_row_is_not_reported_not_found(self):
        resolved = _resolved_result(
            ("customer-list.xlsx", 4, "IS3025PT24:2021"),
            self.current_edition,
        )
        older = _not_found_result(
            ("customer-list.xlsx", 8, "IS3025PT24:1986"),
            self.old_edition,
        )

        results = self.normalize([resolved, older])
        workbook_bytes = ExportService.export_not_found_excel(results)
        workbook = load_workbook(BytesIO(workbook_bytes.getvalue()), read_only=True)
        try:
            standards = [
                row[1]
                for row in workbook["Not Found"].iter_rows(
                    min_row=2,
                    values_only=True,
                )
            ]
        finally:
            workbook.close()

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["matched"])
        self.assertEqual(
            results[0]["standard"]["display_stdNo"],
            self.current_edition,
        )
        self.assertEqual(standards, [])

    def test_different_part_remains_not_found(self):
        resolved = _resolved_result(
            ("customer-list.xlsx", 1, "IEC623051:2024"),
            "IEC 62305-1:2024 (EN-FR)",
        )
        resolved["requested_sdo"] = "IEC"
        other_part = _not_found_result(
            ("customer-list.xlsx", 2, "IEC623052:2024"),
            "IEC 62305-2:2024 (EN-FR)",
        )
        other_part["requested_sdo"] = "IEC"

        results = self.normalize([resolved, other_part])

        self.assertEqual(len(results), 2)
        self.assertFalse(results[1]["matched"])
        self.assertEqual(
            results[1]["requested_standard"],
            "IEC 62305-2:2024 (EN-FR)",
        )

    def test_year_newer_than_found_edition_remains_not_found(self):
        resolved = _resolved_result(
            ("customer-list.xlsx", 1, "IEC61000429:2000"),
            "IEC 61000-4-29:2000 (EN-FR)",
        )
        resolved["requested_sdo"] = "IEC"
        newer = _not_found_result(
            ("customer-list.xlsx", 2, "IEC61000429:2026"),
            "IEC 61000-4-29:2026",
        )
        newer["requested_sdo"] = "IEC"

        results = self.normalize([resolved, newer])

        self.assertEqual(len(results), 2)
        self.assertFalse(results[1]["matched"])
        self.assertEqual(
            results[1]["requested_standard"],
            "IEC 61000-4-29:2026",
        )

    def test_filtered_results_keep_not_found_workbook_consistent(self):
        resolved = _resolved_result(
            self.source_identity,
            self.current_edition,
        )
        stale_unmatched = _not_found_result(
            self.source_identity,
            self.old_edition,
        )
        genuinely_missing = _not_found_result(
            ("customer-list.xlsx", 9, "IS3025PT99:2015"),
            "IS 3025 PT 99 : 2015",
        )
        results = self.normalize([resolved, stale_unmatched, genuinely_missing])

        workbook_bytes = ExportService.export_not_found_excel(results)
        workbook = load_workbook(BytesIO(workbook_bytes.getvalue()), read_only=True)
        try:
            standards = [
                row[1]
                for row in workbook["Not Found"].iter_rows(
                    min_row=2,
                    values_only=True,
                )
            ]
        finally:
            workbook.close()

        self.assertEqual(standards, ["IS 3025 PT 99 : 2015"])


class NotFoundLifecycleStatusTests(unittest.TestCase):
    def normalize(self, results):
        return result_helpers.deduplicate_results(results, _SearchService)

    def test_unmatched_withdrawn_status_is_preserved(self):
        results = self.normalize(
            [
                {
                    "requested_sdo": "ASME",
                    "requested_standard": "B18.2.3.5M : 1979",
                    "matched": False,
                    "status": "WITHDRAWN",
                    "status_detail": (
                        "The requested edition is withdrawn."
                    ),
                    "standard": None,
                    "_source_request_identity": (
                        "list.xlsx",
                        3,
                        "B18.2.3.5M:1979",
                    ),
                }
            ]
        )
        self.assertEqual(results[0]["status"], "WITHDRAWN")
        self.assertEqual(results[0]["not_found_reason"], "Withdrawn")

        workbook = load_workbook(
            BytesIO(
                ExportService.export_not_found_excel(results).getvalue()
            ),
            read_only=True,
        )
        try:
            rows = list(
                workbook["Not Found"].iter_rows(min_row=2, values_only=True)
            )
        finally:
            workbook.close()
        self.assertEqual(rows[0][2], "WITHDRAWN")

    def test_not_found_label_recovers_historical_from_detail(self):
        results = self.normalize(
            [
                {
                    "requested_sdo": "ASME",
                    "requested_standard": "B18.2.3.5M : 1979",
                    "matched": False,
                    "status": "NOT FOUND",
                    "status_detail": (
                        "Requested edition is marked HISTORICAL in the "
                        "catalogue and is not available."
                    ),
                    "standard": None,
                    "_source_request_identity": (
                        "list.xlsx",
                        4,
                        "B18.2.3.5M:1979",
                    ),
                }
            ]
        )
        self.assertEqual(results[0]["status"], "HISTORICAL")
        self.assertEqual(results[0]["not_found_reason"], "Historical")

    def test_unrelated_active_candidate_does_not_hide_withdrawn_status(self):
        row = {
            "sdo_name": "ASME",
            "search_sdo_name": "ASME",
            "requested_sdo_name": "ASME",
            "identity": parse_identity("ASME", "B18.2.3.5M"),
        }
        withdrawn = SimpleNamespace(
            id=1,
            status_id=10,
            standardno="B18.2.3.5M",
            display_stdNo="ASME B18.2.3.5M : 1979",
            standardyear=1979,
        )
        unrelated_active = SimpleNamespace(
            id=2,
            status_id=1,
            standardno="B16.5",
            display_stdNo="ASME B16.5 : 2020",
            standardyear=2020,
        )
        DocumentSearchService._record_requested_edition_status(
            [unrelated_active, withdrawn],
            row,
            {
                1: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
                10: {"name": "WITHDRAWN", "cart_show": 0, "std_show": 0},
            },
        )
        self.assertEqual(row["requested_edition_status"], "WITHDRAWN")

    def test_bis_withdrawn_edition_status_is_recorded(self):
        row = {
            "sdo_name": "BIS",
            "search_sdo_name": "BIS",
            "requested_sdo_name": "IS",
            "identity": parse_identity("IS", "IS 1234 : 1990"),
        }
        withdrawn = SimpleNamespace(
            id=9,
            status_id=3,
            standardno="IS 1234",
            display_stdNo="IS 1234 : 1990",
            standardyear=1990,
        )
        DocumentSearchService._record_requested_edition_status(
            [withdrawn],
            row,
            {3: {"name": "WITHDRAWN", "cart_show": 0, "std_show": 0}},
        )
        self.assertEqual(row["requested_edition_status"], "WITHDRAWN")


class IeeeIecDualLogoLookupTests(unittest.TestCase):
    def test_hyphenated_ieee_lookup_keeps_catalogue_spelling(self):
        self.assertEqual(
            identity_lookup_core_tokens("IEEE", "60076-57", "PART:1202"),
            ["60076-57"],
        )
        self.assertTrue(
            designation_is_ieee_iec_dual_logo(
                "IEC/IEEE 60076-57-1202:2017 (EN-FR)"
            )
        )
        self.assertFalse(
            designation_is_ieee_iec_dual_logo("IEEE C57.12.00-2021")
        )
        self.assertTrue(ieee_iec_joint_prefix("IEEE", "IEC/IEEE"))
        self.assertTrue(ieee_iec_joint_prefix("IEC", "IEEE/IEC"))
        self.assertFalse(ieee_iec_joint_prefix("ISO", "IEC/IEEE"))

    def test_dual_logo_rows_are_indexed_for_the_other_publisher(self):
        candidate = SimpleNamespace(
            id=274355,
            sdo_id=16,
            display_stdNo="IEC/IEEE 60076-57-1202:2017 (EN-FR)",
            standardno="IEC/IEEE 60076-57-1202 (EN-FR)",
        )
        index = build_identity_candidate_index(
            [candidate],
            [
                {
                    "sdo_id": 25,
                    "sdo_name": "IEEE",
                    "search_sdo_name": "IEEE",
                }
            ],
        )
        self.assertIn(candidate.id, index[(16, "IEEE", "6007657")])


class CommitteeCodeDisplayTests(unittest.TestCase):
    def test_publishers_show_full_codes_without_titles(self):
        self.assertEqual(
            committee_display_codes(
                "19",
                "Electrical Accessories & Special Equipment (GMB19)",
                "BSI",
            ),
            ["GMB 19"],
        )
        self.assertEqual(
            committee_display_codes(
                "36",
                "CHD 36 -- WATER QUALITY",
                "BIS",
            ),
            ["CHD 36"],
        )
        self.assertEqual(
            committee_display_codes(
                "16/12",
                "E-TD 16 and MHD 12",
                "BIS",
            ),
            ["E-TD 16", "MHD 12"],
        )
        self.assertEqual(
            committee_display_codes(
                "22/7",
                "Adjustable speed electric drive systems",
                "IEC",
            ),
            ["TC 22/SC 7"],
        )
        self.assertEqual(
            committee_display_codes(
                "1",
                "Volume 01.01 Steel--Piping, Tubing, Fittings",
                "ASTM",
            ),
            ["01.01"],
        )
        self.assertEqual(
            committee_display_codes(
                "28/5",
                "Measurement of refrigerated hydrocarbon (ISO/TC 28/SC 5.)",
                "ISO",
            ),
            ["ISO/TC 28/SC 5"],
        )
        self.assertEqual(
            committee_display_codes("07", "Pipeline Transportation", "API"),
            ["Pipeline Transportation"],
        )
        self.assertEqual(
            committee_display_codes(
                "15",
                "Pipelines & Tanks (SC 15)",
                "AMPP-NACE",
            ),
            ["15"],
        )


if __name__ == "__main__":
    unittest.main()
