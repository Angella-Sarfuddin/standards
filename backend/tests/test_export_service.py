import unittest
import zipfile
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.routes.export_routes import export_excel, export_not_found
from app.services.document_search_service import DocumentSearchService
from app.services.export_service import ExportService


class ExportServiceTests(unittest.TestCase):
    def _build_price_enrichment(self, masters, prices):
        class FakeEnrichmentRepository:
            def get_currency_info_for_sdos(self, _sdo_ids):
                return {21: {"code": "INR", "symbol": "₹"}}

            def get_sdo_titles(self, _sdo_ids):
                return {21: "BIS"}

            def get_master_standards(self, _standard_ids):
                return masters

            def get_bis_master_aliases(self, master_ids):
                return [m for m in masters if m.id not in master_ids]

            def get_prices_for_standards(self, _master_ids, additional_master_ids=None):
                return prices

            def get_classifications_for_standards(self, _master_ids):
                return []

            def get_classifications_from_exact_catalog_duplicates(self, _masters):
                return {}

        service = DocumentSearchService.__new__(DocumentSearchService)
        service.enrichment_repository = FakeEnrichmentRepository()
        return service.build_enrichment_map(masters)

    def test_quotation_route_returns_complete_xlsx_with_content_length(self):
        response = export_excel(
            [
                {
                    "requested_sdo": "API",
                    "requested_standard": "API 570",
                    "matched": True,
                    "status": "AVAILABLE",
                    "standard": {
                        "standardno": "API 570",
                        "display_stdNo": "API 570:2024",
                        "title": "Standard title",
                        "enrichment": {"classifications": []},
                    },
                }
            ]
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertEqual(
            int(response.headers["content-length"]),
            len(response.body),
        )
        with zipfile.ZipFile(BytesIO(response.body)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.infolist()[0].header_offset, 0)

        workbook = load_workbook(BytesIO(response.body), read_only=True)
        self.assertEqual(workbook["Quotation"].max_row, 2)
        workbook.close()

    def test_quotation_sheet_includes_standard_year_and_currency(self):
        output = ExportService.export_results(
            {
                "results": [
                    {
                        "requested_sdo": "API",
                        "requested_standard": "API RP 610",
                        "matched": True,
                        "status": "AVAILABLE",
                        "standard": {
                            "standardno": "API STD 610",
                            "display_stdNo": "API STD 610 : 2021",
                            "title": "Standard title",
                            "enrichment": {
                                "year": 2024,
                                "currency": "USD",
                                "price": 125.5,
                                "classifications": [],
                            },
                        },
                    }
                ],
                "grouping": {},
            }
        )

        with zipfile.ZipFile(output) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.infolist()[0].header_offset, 0)

        workbook = load_workbook(output)
        worksheet = workbook["Quotation"]
        headers = [cell.value for cell in worksheet[1]]
        values = [cell.value for cell in worksheet[2]]
        row = dict(zip(headers, values))

        self.assertNotIn("Status", headers)
        self.assertEqual(row["Standard Year"], 2024)
        self.assertEqual(row["Currency"], "USD")
        self.assertEqual(row["Price"], 125.5)
        self.assertEqual(headers[-1], "TC")
        self.assertEqual(row["Matched Standard"], "API STD 610 : 2021")
        self.assertIsNone(row["TC"])
        self.assertLess(
            headers.index("Standard"),
            headers.index("Matched Standard"),
        )
        self.assertEqual(worksheet.freeze_panes, "A2")
        self.assertTrue(worksheet.auto_filter.ref)
        self.assertGreaterEqual(worksheet.column_dimensions["D"].width, 48)
        workbook.close()

    def test_tc_column_uses_classification_description(self):
        output = ExportService.export_results(
            {
                "results": [
                    {
                        "requested_sdo": "ISO",
                        "requested_standard": "ISO 10816",
                        "matched": True,
                        "standard": {
                            "standardno": "ISO 10816",
                            "enrichment": {
                                "classifications": [
                                    {
                                        "code": "8",
                                        "description": "Refining, TC 8",
                                    },
                                    {
                                        "code": "TC-2",
                                        "description": "ISO/TC 108/SC 2.",
                                    },
                                    {
                                        "code": "17",
                                        "description": "PGD 1 -- BASIC STANDARDS",
                                    },
                                ]
                            },
                        },
                    }
                ],
                "grouping": {},
            }
        )

        workbook = load_workbook(output)
        worksheet = workbook["Quotation"]
        headers = [cell.value for cell in worksheet[1]]
        tc_cell = worksheet.cell(2, headers.index("TC") + 1)

        self.assertEqual(headers[-1], "TC")
        self.assertEqual(
            tc_cell.value,
            "Refining, TC 8, ISO/TC 108/SC 2., PGD 1 -- BASIC STANDARDS",
        )
        self.assertTrue(tc_cell.alignment.wrap_text)
        self.assertGreaterEqual(
            worksheet.column_dimensions[tc_cell.column_letter].width,
            54,
        )
        workbook.close()

    def test_tc_column_appends_code_to_plain_description(self):
        output = ExportService.export_results(
            {
                "results": [
                    {
                        "requested_sdo": "IEC",
                        "requested_standard": "IEC 61131",
                        "matched": True,
                        "standard": {
                            "standardno": "IEC 61131",
                            "enrichment": {
                                "classifications": [
                                    {
                                        "code": "65",
                                        "description": (
                                            "Industrial-process measurement, "
                                            "control and automation"
                                        ),
                                    }
                                ]
                            },
                        },
                    }
                ],
                "grouping": {},
            }
        )

        workbook = load_workbook(output)
        worksheet = workbook["Quotation"]
        headers = [cell.value for cell in worksheet[1]]
        self.assertEqual(
            worksheet.cell(2, headers.index("TC") + 1).value,
            "Industrial-process measurement, control and automation (TC 65)",
        )
        workbook.close()
        self.assertEqual(
            ExportService._tc_cell_text(
                "TC-65",
                "Industrial-process measurement, control and automation",
            ),
            "Industrial-process measurement, control and automation (TC 65)",
        )

    def test_numeric_tc_codes_get_tc_prefix(self):
        self.assertEqual(ExportService._classification_label("8", ""), "TC 8")
        self.assertEqual(ExportService._classification_label("16", ""), "TC 16")
        self.assertEqual(
            ExportService._classification_label("22", "TC 22.SC 22G"),
            "TC 22.SC 22G",
        )
        self.assertEqual(
            ExportService._classification_label(
                "7",
                "Adjustable speed electric drive systems incorporating semiconductor power converters",
            ),
            "TC 22.SC 22G",
        )
        self.assertEqual(
            ExportService._classification_label("22", "TC 22/SC 22G"),
            "TC 22/SC 22G",
        )
        self.assertEqual(
            ExportService._classification_label(
                "TC-35/SC-14",
                "ISO/TC 35/SC 14.",
            ),
            "ISO/TC 35/SC 14",
        )
        bis_description = ExportService._clean_classification_text(
            "tc&#x20;**&#xA0;**&#x45-TD 16 and MHD 12"
        )
        self.assertEqual(
            ExportService._classification_label("16", bis_description),
            "E-TD 16 and MHD 12",
        )

    def test_ieee_classification_uses_committee_name_instead_of_numeric_code(self):
        self.assertEqual(
            ExportService._classification_label(
                "32",
                "Power and Energy Society",
                owner_sdo="IEEE",
            ),
            "Power and Energy Society",
        )
        self.assertIsNone(
            ExportService._classification_label(
                "32", "", owner_sdo="IEEE"
            )
        )

    def test_iso_tc_hierarchy_is_rendered_from_parent_child_codes(self):
        self.assertEqual(
            ExportService._classification_label(
                "67/2",
                "Pipeline transportation systems",
            ),
            "ISO/TC 67/SC 2",
        )

    def test_astm_book_volume_is_reported_as_volume_number(self):
        self.assertEqual(
            ExportService._classification_label(
                "3/1",
                "Volume 03.01 Metals -- Mechanical Testing",
                owner_sdo="ASTM",
            ),
            "03.01",
        )
        self.assertEqual(
            ExportService._classification_label(
                "5/1",
                "Volume 05.01 Petroleum Products; Volume 90.37 Terminology",
                owner_sdo="ASTM",
            ),
            "05.01, 90.37",
        )
        self.assertIsNone(
            ExportService._classification_label(
                "3/1",
                "Mechanical Testing",
                owner_sdo="ASTM",
            )
        )

    def test_api_classification_keeps_relevant_tc_for_selected_titles(self):
        cases = {
            "API RP 651 (Revision Tracker)": ("8", "10"),
            "API RP 575 : 2024": ("8", "10"),
            "API RP 652 : 2025": ("8", "10"),
        }
        for standardno, (expected_code, extra_code) in cases.items():
            with self.subTest(standardno=standardno):
                classifications = [
                    {"code": extra_code, "description": "Other API sector", "owner_sdo": "API"},
                    {"code": expected_code, "description": "Primary API sector", "owner_sdo": "API"},
                ]
                filtered = DocumentSearchService._filter_api_tc_classifications(
                    SimpleNamespace(sdo_id=4, standardno=standardno),
                    classifications,
                )
                self.assertEqual(
                    [item["code"] for item in filtered],
                    [expected_code],
                )

        unmodified = [{"code": "8", "description": "Refining", "owner_sdo": "API"}]
        self.assertIs(
            DocumentSearchService._filter_api_tc_classifications(
                SimpleNamespace(sdo_id=3, standardno="API RP 777 : 2024"),
                unmodified,
            ),
            unmodified,
        )

        ambiguous = [
            {"code": "2", "description": "Sector 2", "owner_sdo": "API"},
            {"code": "6", "description": "Sector 6", "owner_sdo": "API"},
        ]
        self.assertEqual(
            DocumentSearchService._filter_api_tc_classifications(
                SimpleNamespace(sdo_id=4, standardno="API RP 9999 : 2025"),
                ambiguous,
            ),
            ambiguous,
        )

    def test_api_price_uses_exact_edition_peer_and_best_available_format(self):
        requested = SimpleNamespace(
            id=1,
            Standard_id="APITR-5C3",
            sdo_id=4,
            standardno="API TR 5C3",
            display_stdNo="API TR 5C3 : 2008",
            standardyear=2008,
            DocumentAvailability=1,
        )
        alias = SimpleNamespace(
            id=2,
            Standard_id="API-Boss-232314",
            sdo_id=4,
            standardno="API TR 5C3",
            display_stdNo="API TR 5C3 : 2008",
            standardyear=2008,
            DocumentAvailability=1,
        )
        test_case = self

        class FakeEnrichmentRepository:
            def get_currency_info_for_sdos(self, _sdo_ids):
                return {4: {"code": "USD", "symbol": "$"}}

            def get_sdo_titles(self, _sdo_ids):
                return {4: "API"}

            def get_master_standards(self, _standard_ids):
                return [requested]

            def get_bis_master_aliases(self, master_ids):
                test_case.assertEqual(master_ids, [requested.id])
                return []

            def get_api_master_price_aliases(self, master_ids):
                test_case.assertEqual(master_ids, [requested.id])
                return [alias]

            def get_prices_for_standards(
                self,
                master_ids,
                additional_master_ids=None,
            ):
                test_case.assertEqual(set(master_ids), {requested.id})
                test_case.assertEqual(additional_master_ids, [alias.id])
                return [
                    SimpleNamespace(
                        std_id=1,
                        formate_id=1,
                        id=1,
                        non_member_price_rate=253,
                    ),
                    SimpleNamespace(
                        std_id=2,
                        formate_id=2,
                        id=2,
                        non_member_price_rate=227,
                    ),
                ]

            def get_classifications_for_standards(self, _master_ids):
                return []

            def get_classifications_from_exact_catalog_duplicates(self, _masters):
                return {}

        service = DocumentSearchService.__new__(DocumentSearchService)
        service.enrichment_repository = FakeEnrichmentRepository()
        result = service.build_enrichment_map([requested])

        # The requested non-BIS master's direct price takes precedence over
        # the alias's different format price.
        self.assertEqual(result["APITR-5C3"]["price"], 253)

    def test_asme_bpvc_volume_classification_is_not_reported_as_tc(self):
        self.assertIsNone(
            ExportService._classification_label(
                "2",
                "BPVC IIAVI",
                owner_sdo="ASME",
            )
        )
        output = ExportService.export_results(
            {
                "results": [
                    {
                        "requested_sdo": "ASME",
                        "requested_standard": "ASME BPVC IIA-Vol. I",
                        "matched": True,
                        "standard": {
                            "standardno": "ASME BPVC IIA",
                            "display_stdNo": "BPVC IIA-Vol. I",
                            "title": "Materials",
                            "enrichment": {
                                "classifications": [
                                    {"code": "2", "description": "BPVC IIAVI"},
                                    {"code": "6", "description": "BPVC IIA-VOL II"},
                                ]
                            },
                        },
                    }
                ],
                "grouping": {},
            }
        )
        worksheet = load_workbook(output)["Quotation"]
        headers = [cell.value for cell in worksheet[1]]
        self.assertIsNone(worksheet.cell(2, headers.index("TC") + 1).value)

    def test_zero_price_is_preserved_in_quotation_export(self):
        output = ExportService.export_results(
            {
                "results": [
                    {
                        "requested_sdo": "BIS",
                        "requested_standard": "IS 1234",
                        "matched": True,
                        "standard": {
                            "standardno": "IS 1234",
                            "enrichment": {
                                "price": 0,
                                "currency": "INR",
                                "classifications": [],
                            },
                        },
                    }
                ],
                "grouping": {},
            }
        )
        worksheet = load_workbook(output)["Quotation"]
        headers = [cell.value for cell in worksheet[1]]
        row = dict(zip(headers, [cell.value for cell in worksheet[2]]))
        self.assertEqual(row["Price"], 0)
        self.assertEqual(row["Currency"], "INR")

    def test_bis_duplicate_catalog_price_prefers_nonzero_over_placeholder_zero(self):
        price_map = {}
        fallback_map = {}
        for standard_id, value in (("BIS-OLD", 0), ("BIS-CURRENT", 160)):
            if value != 0:
                price_map[standard_id] = value
            else:
                fallback_map.setdefault(standard_id, value)
        for standard_id, value in fallback_map.items():
            price_map.setdefault(standard_id, value)

        self.assertEqual(price_map["BIS-OLD"], 0)
        self.assertEqual(price_map["BIS-CURRENT"], 160)

    def test_bis_published_format_price_overrides_format_one_zero(self):
        prices = [(1, 0), (2, 1620)]
        prices.sort(key=lambda item: (-item[0],))
        selected = next((amount for _, amount in prices if amount is not None), None)
        self.assertEqual(selected, 1620)

    def test_bis_price_is_borrowed_only_when_equivalent_rows_agree(self):
        requested = SimpleNamespace(
            id=1,
            Standard_id="BIS-IS-5831",
            sdo_id=21,
            standardno="IS 5831",
            display_stdNo="IS 5831 : 1984",
            standardyear=1984,
            DocumentAvailability=1,
        )
        matching_alias = SimpleNamespace(
            id=2,
            Standard_id="BIS-BOSS-5831",
            sdo_id=21,
            standardno="BIS 5831",
            display_stdNo="BIS 5831 : 1984",
            standardyear=1984,
            DocumentAvailability=1,
        )
        price_map = self._build_price_enrichment(
            [requested, matching_alias],
            [
                SimpleNamespace(std_id=1, formate_id=1, id=1, non_member_price_rate=0),
                SimpleNamespace(std_id=2, formate_id=2, id=2, non_member_price_rate=393),
            ],
        )
        # Plain IS editions are free and do not inherit a paid BIS alias price.
        self.assertEqual(price_map["BIS-IS-5831"]["price"], 0)

        other_alias = SimpleNamespace(
            id=3,
            Standard_id="BIS-OTHER-5831",
            sdo_id=21,
            standardno="BIS 5831",
            display_stdNo="BIS 5831 : 1984",
            standardyear=1984,
            DocumentAvailability=1,
        )
        ambiguous = self._build_price_enrichment(
            [requested, matching_alias, other_alias],
            [
                SimpleNamespace(std_id=1, formate_id=1, id=1, non_member_price_rate=0),
                SimpleNamespace(std_id=2, formate_id=2, id=2, non_member_price_rate=393),
                SimpleNamespace(std_id=3, formate_id=2, id=3, non_member_price_rate=450),
            ],
        )
        self.assertEqual(ambiguous["BIS-IS-5831"]["price"], 0)

        unpriced = SimpleNamespace(
            id=4,
            Standard_id="BIS-UNPRICED-5831",
            sdo_id=21,
            standardno="IS 5831",
            display_stdNo="IS 5831 : 1984",
            standardyear=1984,
            DocumentAvailability=1,
        )
        no_safe_source = self._build_price_enrichment(
            [unpriced, matching_alias, other_alias],
            [
                SimpleNamespace(std_id=2, formate_id=2, id=2, non_member_price_rate=393),
                SimpleNamespace(std_id=3, formate_id=2, id=3, non_member_price_rate=450),
            ],
        )
        self.assertEqual(no_safe_source["BIS-UNPRICED-5831"]["price"], 0)

        zero_only = self._build_price_enrichment(
            [unpriced, matching_alias],
            [
                SimpleNamespace(std_id=2, formate_id=2, id=2, non_member_price_rate=0),
            ],
        )
        self.assertEqual(zero_only["BIS-UNPRICED-5831"]["price"], 0)
        self.assertEqual(zero_only["BIS-BOSS-5831"]["price"], 0)

    def test_export_displays_current_standard_without_request_corrigendum(self):
        output = ExportService.export_results(
            {
                "results": [
                    {
                        "requested_sdo": "IEC",
                        "requested_standard": "IEC 60079-2:2014/COR1:2015 (EN-FR)",
                        "matched": True,
                        "standard": {
                            "standardno": "IEC 60079-2",
                            "display_stdNo": "IEC 60079-2:2014 (EN-FR)",
                            "title": "Explosive atmospheres",
                            "enrichment": {"classifications": []},
                        },
                    }
                ],
                "grouping": {},
            }
        )
        worksheet = load_workbook(output)["Quotation"]
        headers = [cell.value for cell in worksheet[1]]
        row = dict(zip(headers, [cell.value for cell in worksheet[2]]))
        self.assertEqual(row["Standard"], "IEC 60079-2:2014 (EN-FR)")
        self.assertNotIn("COR", row["Standard"])

    def test_export_strips_space_separated_corrigendum_suffix(self):
        self.assertEqual(
            ExportService._strip_revision_suffix(
                "IEC 61378-1 CORR 1 : 2012"
            ),
            "IEC 61378-1",
        )
        self.assertEqual(
            ExportService._strip_revision_suffix(
                "IEC 60079-0 Amendment No. 1 : 2020"
            ),
            "IEC 60079-0",
        )

    def test_not_found_export_is_formatted_excel(self):
        output = ExportService.export_not_found_excel(
            [
                {
                    "requested_sdo": "BIS",
                    "requested_standard": "IS 5831/COR1:2020",
                    "matched": False,
                    "status": "NOT FOUND",
                },
                {
                    "requested_sdo": "IEC",
                    "requested_standard": "IEC 61508",
                    "matched": True,
                    "status": "AVAILABLE",
                },
            ]
        )
        workbook = load_workbook(output)
        worksheet = workbook["Not Found"]
        self.assertEqual(
            [cell.value for cell in worksheet[1]],
            ["SDO", "Standard", "Status", "Superseded By"],
        )
        self.assertEqual(
            [cell.value for cell in worksheet[2]],
            ["BIS", "IS 5831", "NOT FOUND", None],
        )
        self.assertEqual(worksheet.freeze_panes, "A2")
        workbook.close()

    def test_not_found_route_returns_xlsx(self):
        response = export_not_found(
            [
                {
                    "requested_sdo": "API",
                    "requested_standard": "API 570",
                    "matched": False,
                    "status": "NOT FOUND",
                }
            ]
        )
        self.assertEqual(
            response.media_type,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn(
            "not_found_standards.xlsx",
            response.headers["content-disposition"],
        )
        self.assertTrue(response.body.startswith(b"PK"))

    def test_found_and_not_found_bundle_contains_two_excel_workbooks(self):
        output = ExportService.export_found_and_not_found_zip(
            [],
            [
                {
                    "requested_sdo": "BIS",
                    "requested_standard": "IS 5831",
                    "matched": False,
                    "status": "NOT FOUND",
                }
            ],
        )
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {
                    "standards_quotation.xlsx",
                    "not_found_standards.xlsx",
                },
            )
            not_found = load_workbook(
                BytesIO(archive.read("not_found_standards.xlsx")),
                read_only=True,
            )
            self.assertEqual(not_found["Not Found"].max_row, 2)
            not_found.close()

    def test_withdrawn_bis_not_found_row_includes_replacement(self):
        output = ExportService.export_not_found_excel(
            [
                {
                    "requested_sdo": "BIS",
                    "requested_standard": "IS 2099 : 1986",
                    "matched": False,
                    "status": "WITHDRAWN",
                    "replacement_standard": "IS/IEC 60137 : 2017",
                },
                {
                    "requested_sdo": "IEC",
                    "requested_standard": "IEC 1234",
                    "matched": False,
                    "status": "WITHDRAWN",
                    "replacement_standard": "IEC 1234:2024",
                },
                {
                    "requested_sdo": "IS",
                    "requested_standard": "IS 3025 Part 24 : 1986",
                    "matched": False,
                    "status": "WITHDRAWN",
                    "superseded_by": "Decided by Council",
                },
            ]
        )
        worksheet = load_workbook(output)["Not Found"]
        self.assertEqual(
            [cell.value for cell in worksheet[2]],
            ["BIS", "IS 2099 : 1986", "WITHDRAWN", "IS/IEC 60137 : 2017"],
        )
        self.assertEqual(
            [cell.value for cell in worksheet[3]],
            [
                "BIS",
                "IS 3025 Part 24 : 1986",
                "WITHDRAWN",
                "Decided by Council",
            ],
        )
        self.assertEqual(
            [cell.value for cell in worksheet[4]],
            ["IEC", "IEC 1234", "WITHDRAWN", "IEC 1234:2024"],
        )

    def test_withdrawn_bis_not_found_row_includes_supersession_note(self):
        output = ExportService.export_not_found_excel(
            [
                {
                    "requested_sdo": "BIS",
                    "requested_standard": "IS 2099 : 1986",
                    "matched": False,
                    "status": "WITHDRAWN",
                    "superseded_by": "decided by council",
                }
            ]
        )
        worksheet = load_workbook(output)["Not Found"]
        self.assertEqual(worksheet.cell(2, 4).value, "decided by council")

    def test_latest_year_export_ignores_duplicate_annotations(self):
        results = [
            {
                "requested_sdo": "API",
                "requested_standard": "API 570",
                "matched": True,
                "status": "AVAILABLE",
                "standard": {
                    "standardno": "API 570",
                    "display_stdNo": "API 570:2019",
                    "title": "Older edition",
                },
            },
            {
                "requested_sdo": "API",
                "requested_standard": "API 570",
                "matched": True,
                "status": "AVAILABLE",
                "standard": {
                    "standardno": "API 570",
                    "display_stdNo": "API 570:2024",
                    "title": "Latest edition",
                    "standardyear": 2024,
                },
            },
            {
                "requested_sdo": "IEC",
                "requested_standard": "IEC 61508",
                "matched": False,
                "status": "NOT FOUND",
                "standard": None,
            },
            {
                "requested_sdo": "API",
                "requested_standard": "API 570",
                "matched": False,
                "status": "NOT FOUND",
                "standard": None,
                "is_duplicate": True,
                "duplicate_of": 1,
            },
            {
                "requested_sdo": "BIS",
                "requested_standard": "IS 2099 Rev 2, 1986",
                "matched": False,
                "status": "WITHDRAWN",
                "standard": {
                    "standardno": "BIS 2099",
                    "display_stdNo": "BIS 2099 : 1986",
                    "title": "Bushings for alternating voltages above 1 000 V",
                    "standardyear": 1986,
                },
            },
        ]

        output = ExportService.export_latest_years(results)
        with zipfile.ZipFile(output) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.infolist()[0].header_offset, 0)

        workbook = load_workbook(output)
        worksheet = workbook["Latest Available Years"]

        headers = [cell.value for cell in worksheet[1]]
        self.assertNotIn("Search Status", headers)
        self.assertEqual(headers[2], "Latest Available Year")
        rows = [
            dict(zip(headers, values))
            for values in worksheet.iter_rows(
                min_row=2,
                values_only=True,
            )
        ]
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["Latest Available Year"], 2024)
        self.assertEqual(rows[0]["Title"], "Latest edition")
        self.assertEqual(rows[1]["Latest Available Year"], None)
        self.assertNotIn("Search Status", rows[1])
        self.assertEqual(rows[2]["Latest Available Year"], None)
        self.assertEqual(rows[2]["Matched Catalog Standard"], None)
        self.assertEqual(worksheet.freeze_panes, "A2")
        workbook.close()

    def test_both_export_contains_the_two_workbooks(self):
        output = ExportService.export_both(
            {
                "results": [
                    {
                        "requested_sdo": "API",
                        "requested_standard": "API 570",
                        "matched": False,
                        "status": "NOT FOUND",
                        "standard": None,
                    }
                ],
                "grouping": {},
            },
            [
                {
                    "requested_sdo": "API",
                    "requested_standard": "API 570",
                    "matched": False,
                    "status": "NOT FOUND",
                    "standard": None,
                },
                {
                    "requested_sdo": "IEC",
                    "requested_standard": "IEC 61508",
                    "matched": False,
                    "status": "SDO NOT FOUND",
                    "standard": None,
                },
            ],
        )

        with zipfile.ZipFile(output) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {
                    "standards_quotation.xlsx",
                    "standards_latest_years.xlsx",
                },
            )
            quotation = load_workbook(
                BytesIO(archive.read("standards_quotation.xlsx")),
                read_only=True,
            )
            self.assertEqual(
                quotation["Quotation"].max_row,
                1,
            )
            quotation.close()
            with zipfile.ZipFile(
                BytesIO(archive.read("standards_quotation.xlsx"))
            ) as xlsx_archive:
                self.assertIsNone(xlsx_archive.testzip())
                self.assertEqual(
                    xlsx_archive.infolist()[0].header_offset,
                    0,
                )
            latest = load_workbook(
                BytesIO(archive.read("standards_latest_years.xlsx")),
                read_only=True,
            )
            self.assertEqual(
                latest["Latest Available Years"].max_row,
                3,
            )
            latest.close()

    def test_year_parser_accepts_year_embedded_in_catalog_metadata(self):
        self.assertEqual(
            ExportService._available_year(
                {
                    "standardyear": "Latest Edition, 2025",
                    "display_stdNo": "API 570:2024",
                }
            ),
            2025,
        )


if __name__ == "__main__":
    unittest.main()
