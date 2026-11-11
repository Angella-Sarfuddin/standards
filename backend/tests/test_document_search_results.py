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

    def test_boilerplate_detail_does_not_fake_withdrawn_status(self):
        results = self.normalize(
            [
                {
                    "requested_sdo": "IEEE",
                    "requested_standard": "C57.12.26",
                    "matched": False,
                    "status": "NOT FOUND",
                    "status_detail": (
                        "No available catalog record was found, and no "
                        "withdrawn or historical status was identified."
                    ),
                    "standard": None,
                    "_source_request_identity": (
                        "list.xlsx",
                        5,
                        "C57.12.26",
                    ),
                }
            ]
        )
        self.assertEqual(results[0]["status"], "NOT FOUND")
        self.assertEqual(
            results[0]["not_found_reason"],
            "Not found in catalog",
        )

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
        self.assertEqual(rows[0][2], "NOT FOUND")

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


class StandardsEPediaExportTests(unittest.TestCase):
    def test_quotation_and_not_found_include_subscription_flags(self):
        found = {
            "requested_sdo": "API",
            "requested_standard": "API STD 541 : 2014",
            "matched": True,
            "status": "AVAILABLE",
            "bsb_subscription": 1,
            "parent_status": "Active",
            "catalog_status": "ACTIVE",
            "standard": {
                "Standard_id": "API-STD-541-2014",
                "sdo_id": 10,
                "standardno": "API STD 541",
                "display_stdNo": "API STD 541 : 2014",
                "title": "Form-Wound Squirrel Cage Induction Motors",
                "standardyear": 2014,
                "BSBSubscription": 1,
                "parent_status": "Active",
                "enrichment": {
                    "price": 100,
                    "currency": "USD",
                    "year": 2014,
                    "subscription_available": True,
                    "classifications": [],
                },
            },
        }
        not_on_subscription = {
            "requested_sdo": "IEEE",
            "requested_standard": "C57.12.26",
            "matched": False,
            "status": "NOT FOUND",
            "bsb_subscription": 0,
            "parent_status": None,
            "standard": None,
            "actions": {"manual_search": True},
        }
        withdrawn_on_subscription = {
            "requested_sdo": "ASME",
            "requested_standard": "B18.2.3.5M : 1979",
            "matched": False,
            "status": "WITHDRAWN",
            "bsb_subscription": 1,
            "parent_status": "Withdrawn",
            "catalog_status": "WITHDRAWN",
            "standard": None,
        }

        quotation = load_workbook(
            BytesIO(
                ExportService.export_results(
                    {"results": [found], "grouping": {}}
                ).getvalue()
            ),
            read_only=True,
        )
        try:
            headers = [
                cell.value
                for cell in next(quotation["Quotation"].iter_rows(max_row=1))
            ]
            rows = list(
                quotation["Quotation"].iter_rows(min_row=2, values_only=True)
            )
        finally:
            quotation.close()

        self.assertIn("Standards-e-Pedia", headers)
        self.assertIn("Catalog Status", headers)
        self.assertEqual(
            rows[0][headers.index("Standards-e-Pedia")],
            "Available",
        )
        self.assertEqual(
            rows[0][headers.index("Catalog Status")],
            "Active",
        )

        not_found = load_workbook(
            BytesIO(
                ExportService.export_not_found_excel(
                    [not_on_subscription, withdrawn_on_subscription]
                ).getvalue()
            ),
            read_only=True,
        )
        try:
            headers = [
                cell.value
                for cell in next(not_found["Not Found"].iter_rows(max_row=1))
            ]
            rows = list(
                not_found["Not Found"].iter_rows(min_row=2, values_only=True)
            )
        finally:
            not_found.close()

        flag_index = headers.index("Standards-e-Pedia")
        by_standard = {row[1]: row[flag_index] for row in rows}
        self.assertEqual(by_standard["IEEE C57.12.26"], "Not Available")
        self.assertEqual(by_standard["ASME B18.2.3.5M : 1979"], "Available")
        status_index = headers.index("Catalog Status")
        by_catalog = {row[1]: row[status_index] for row in rows}
        self.assertEqual(by_catalog["ASME B18.2.3.5M : 1979"], "Withdrawn")

    def test_subscription_flag_helper_prefers_enrichment_then_fields(self):
        self.assertEqual(
            ExportService._standards_e_pedia_flag({"bsb_subscription": 1}),
            "Available",
        )
        self.assertEqual(
            ExportService._standards_e_pedia_flag(
                {
                    "bsb_subscription": 0,
                    "standard": {"BSBSubscription": 1},
                }
            ),
            "Available",
        )
        self.assertEqual(
            ExportService._standards_e_pedia_flag(
                {
                    "bsb_subscription": 0,
                    "standard": {
                        "BSBSubscription": 0,
                        "enrichment": {"subscription_available": True},
                    },
                }
            ),
            "Available",
        )
        self.assertEqual(
            ExportService._standards_e_pedia_flag({}),
            "Not Available",
        )


class DuplicateExportSheetTests(unittest.TestCase):
    def _found(self, requested, matched, year=2018, sdo="IS", standard_id="IS-5001"):
        return {
            "requested_sdo": sdo,
            "requested_standard": requested,
            "matched": True,
            "status": "AVAILABLE",
            "bsb_subscription": 1,
            "parent_status": "Active",
            "catalog_status": "Reaffirmed",
            "standard": {
                "Standard_id": standard_id,
                "sdo_id": 7,
                "standardno": "IS 5001",
                "display_stdNo": matched,
                "standardyear": year,
                "BSBSubscription": 1,
                "parent_status": "Active",
                "enrichment": {"year": year, "subscription_available": True},
            },
        }

    def test_duplicate_matched_standards_appear_on_duplicates_sheet(self):
        matched = "IS 5001 : 2018(IEC 60191-1 : 2007)"
        results = [
            self._found("IS 5001 2018", matched),
            self._found(
                "IS 5001 : 2018(IEC 60191-1 : 2007)",
                matched,
            ),
            self._found("IS 5001 01-Feb 1973", matched),
            {
                "requested_sdo": "IEEE",
                "requested_standard": "C57.12.26",
                "matched": False,
                "status": "NOT FOUND",
                "standard": None,
            },
            self._found(
                "API STD 541",
                "API STD 541 : 2014",
                year=2014,
                sdo="API",
                standard_id="API-STD-541",
            ),
        ]

        workbook = load_workbook(
            BytesIO(ExportService.export_not_found_excel(results).getvalue()),
            read_only=True,
        )
        try:
            self.assertEqual(
                workbook.sheetnames,
                ["Not Found", "Duplicates"],
            )
            not_found_rows = list(
                workbook["Not Found"].iter_rows(min_row=2, values_only=True)
            )
            duplicate_headers = [
                cell.value
                for cell in next(workbook["Duplicates"].iter_rows(max_row=1))
            ]
            duplicate_rows = list(
                workbook["Duplicates"].iter_rows(min_row=2, values_only=True)
            )
        finally:
            workbook.close()

        self.assertEqual(len(not_found_rows), 1)
        self.assertEqual(not_found_rows[0][1], "IEEE C57.12.26")
        self.assertEqual(
            duplicate_headers,
            ExportService.DUPLICATE_COLUMNS,
        )
        self.assertEqual(len(duplicate_rows), 3)
        requested = {
            row[duplicate_headers.index("Requested Standard")]
            for row in duplicate_rows
        }
        self.assertEqual(
            requested,
            {
                "IS 5001 2018",
                "IS 5001 : 2018(IEC 60191-1 : 2007)",
                "IS 5001 01-Feb 1973",
            },
        )
        for row in duplicate_rows:
            self.assertEqual(
                row[duplicate_headers.index("Matched Standard")],
                matched,
            )
            self.assertEqual(
                row[duplicate_headers.index("Status")],
                "AVAILABLE",
            )
            self.assertEqual(
                row[duplicate_headers.index("Duplicate Count")],
                3,
            )
            self.assertEqual(
                row[duplicate_headers.index("Standards-e-Pedia")],
                "Available",
            )

    def test_duplicate_not_found_standards_appear_on_duplicates_sheet(self):
        results = [
            {
                "requested_sdo": "IEEE",
                "requested_standard": "C57.12.26",
                "matched": False,
                "status": "NOT FOUND",
                "standard": None,
            },
            {
                "requested_sdo": "IEEE",
                "requested_standard": "IEEE C57.12.26",
                "matched": False,
                "status": "NOT FOUND",
                "standard": None,
            },
            {
                "requested_sdo": "IEEE",
                "requested_standard": "IEEE C2 ERTA",
                "matched": False,
                "status": "NOT FOUND",
                "standard": None,
                "source_row_identity": ["ieee.xlsx", 10, "IEEEC2ERTA"],
            },
            {
                "requested_sdo": "IEEE",
                "requested_standard": "IEEE C2 ERTA",
                "matched": False,
                "status": "NOT FOUND",
                "standard": None,
                "source_row_identity": ["ieee.xlsx", 11, "IEEEC2ERTA"],
            },
            {
                "requested_sdo": "NEMA",
                "requested_standard": "BI 50093",
                "matched": False,
                "status": "NOT FOUND",
                "standard": None,
            },
            {
                "requested_sdo": "ASME",
                "requested_standard": "B18.2.3.5M : 1979",
                "matched": False,
                "status": "WITHDRAWN",
                "standard": None,
            },
            {
                "requested_sdo": "ASME",
                "requested_standard": "ASME B18.2.3.5M : 1979",
                "matched": False,
                "status": "WITHDRAWN",
                "standard": None,
            },
        ]
        workbook = load_workbook(
            BytesIO(ExportService.export_not_found_excel(results).getvalue()),
            read_only=True,
        )
        try:
            not_found_rows = list(
                workbook["Not Found"].iter_rows(min_row=2, values_only=True)
            )
            headers = [
                cell.value
                for cell in next(workbook["Duplicates"].iter_rows(max_row=1))
            ]
            duplicate_rows = list(
                workbook["Duplicates"].iter_rows(min_row=2, values_only=True)
            )
        finally:
            workbook.close()

        # Not Found keeps one row per duplicate group; Duplicates keeps all.
        self.assertEqual(len(not_found_rows), 4)
        not_found_standards = {row[1] for row in not_found_rows}
        self.assertEqual(
            not_found_standards,
            {
                "IEEE C57.12.26",
                "IEEE C2 ERTA",
                "NEMA BI 50093",
                "ASME B18.2.3.5M : 1979",
            },
        )
        self.assertEqual(len(duplicate_rows), 6)
        by_request = {}
        for row in duplicate_rows:
            requested = row[headers.index("Requested Standard")]
            by_request.setdefault(requested, []).append(
                row[headers.index("Status")]
            )
            self.assertIsNone(row[headers.index("Matched Standard")])
            self.assertEqual(row[headers.index("Duplicate Count")], 2)
        self.assertEqual(len(by_request["IEEE C57.12.26"]), 2)
        self.assertEqual(len(by_request["IEEE C2 ERTA"]), 2)
        self.assertEqual(len(by_request["ASME B18.2.3.5M : 1979"]), 2)
        self.assertNotIn("NEMA BI 50093", by_request)

    def test_found_list_keeps_one_row_per_duplicate_group(self):
        matched = "IS 5001 : 2018(IEC 60191-1 : 2007)"
        results = [
            self._found("IS 5001 2018", matched),
            self._found(
                "IS 5001 : 2018(IEC 60191-1 : 2007)",
                matched,
            ),
            self._found("IS 5001 01-Feb 1973", matched),
            self._found(
                "API STD 541",
                "API STD 541 : 2014",
                year=2014,
                sdo="API",
                standard_id="API-STD-541",
            ),
        ]
        quotation = load_workbook(
            BytesIO(
                ExportService.export_results(
                    {"results": results}
                ).getvalue()
            ),
            read_only=True,
        )
        try:
            headers = [
                cell.value
                for cell in next(quotation["Quotation"].iter_rows(max_row=1))
            ]
            rows = list(
                quotation["Quotation"].iter_rows(min_row=2, values_only=True)
            )
        finally:
            quotation.close()

        matched_values = {
            row[headers.index("Matched Standard")] for row in rows
        }
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            matched_values,
            {matched, "API STD 541 : 2014"},
        )

    def test_export_preparation_keeps_distinct_source_duplicates(self):
        from app.services.export_preparation import expand_series_export_rows

        results = [
            {
                "requested_sdo": "IEEE",
                "requested_standard": "IEEE C2 ERTA",
                "matched": False,
                "status": "NOT FOUND",
                "status_detail": "missing",
                "standard": None,
                "source_row_identity": ["ieee.xlsx", 1, "IEEEC2ERTA"],
                "_seriesExpanded": True,
            },
            {
                "requested_sdo": "IEEE",
                "requested_standard": "IEEE C2 ERTA",
                "matched": False,
                "status": "NOT FOUND",
                "status_detail": "missing",
                "standard": None,
                "source_row_identity": ["ieee.xlsx", 2, "IEEEC2ERTA"],
                "_seriesExpanded": True,
            },
        ]
        kept = expand_series_export_rows(results, db=None)
        self.assertEqual(len(kept), 2)
        dup_rows = ExportService._duplicate_export_rows(kept)
        self.assertEqual(len(dup_rows), 2)
        self.assertEqual(dup_rows[0]["Requested Standard"], "IEEE C2 ERTA")
        self.assertEqual(dup_rows[0]["Duplicate Count"], 2)

    def test_unique_found_standards_do_not_fill_duplicates_sheet(self):
        results = [
            self._found(
                "API STD 541",
                "API STD 541 : 2014",
                year=2014,
                sdo="API",
                standard_id="API-STD-541",
            ),
            self._found(
                "IS 5001 2018",
                "IS 5001 : 2018(IEC 60191-1 : 2007)",
            ),
        ]
        workbook = load_workbook(
            BytesIO(ExportService.export_not_found_excel(results).getvalue()),
            read_only=True,
        )
        try:
            duplicate_rows = list(
                workbook["Duplicates"].iter_rows(min_row=2, values_only=True)
            )
        finally:
            workbook.close()
        self.assertEqual(duplicate_rows, [])


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
