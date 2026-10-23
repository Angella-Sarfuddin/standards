import unittest

from app.services.extractors.excel_extractor import ExcelExtractor


class ExcelExtractorOverfitTests(unittest.TestCase):
    def setUp(self):
        self.extractor = ExcelExtractor()

    def test_bare_sdo_is_not_a_standard_value(self):
        self.assertFalse(self.extractor._looks_like_standard_value("ISO"))
        self.assertFalse(self.extractor._looks_like_standard_value("API"))
        self.assertTrue(
            self.extractor._looks_like_standard_value("ISO 22391-5:2009")
        )
        self.assertTrue(
            self.extractor._looks_like_standard_value("API 570")
        )
        # Bare numbers without SDO context are scored via header aliases
        # when an SDO column exists; they are not self-identifying.
        self.assertFalse(self.extractor._looks_like_standard_value("570"))

    def test_sdo_column_not_chosen_over_displaystdno(self):
        import pandas as pd

        dataframe = pd.DataFrame(
            {
                "sdo name": ["ISO", "UL", "JIS"],
                "displaystdno": [
                    "ISO 22391-5:2009",
                    "UL 869A:2006",
                    "JIS K 0094",
                ],
            }
        )
        rows = self.extractor._extract_structured_rows("Sheet1", dataframe)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["sdo_name"], "ISO")
        self.assertEqual(rows[0]["displaystdno"], "22391-5:2009")
        self.assertEqual(rows[0]["source_column"], "displaystdno")
        self.assertNotEqual(rows[0]["displaystdno"], "ISO")

    def test_rejects_parse_where_display_equals_sdo(self):
        parsed = self.extractor._parse_standard_value("ISO", "ISO")
        self.assertIsNone(parsed)
        self.assertFalse(
            self.extractor._is_usable_parse(
                {"sdo_name": "ISO", "displaystdno": "ISO"}
            )
        )

    def test_rejects_summary_text_as_standard(self):
        self.assertIsNone(
            self.extractor._parse_standard_value("REVISION CHANGES")
        )
        self.assertIsNone(
            self.extractor._parse_standard_value(
                "YELLOW HIGHLIGHTED are revised and Refer the remarks column for details"
            )
        )
        self.assertIsNone(
            self.extractor._parse_standard_value(
                "REVISION CHANGES",
                "API",
            )
        )
        self.assertIsNone(
            self.extractor._parse_standard_value(
                "R.Thangaraj Manager",
                "REVIEWED BY",
            )
        )
        self.assertEqual(self.extractor._normalize_sdo("REVIEWED BY"), "")
        self.assertEqual(self.extractor._normalize_sdo("YELLOW HIGHLIGHTED"), "")

    def test_structured_sheet_skips_legend_note_rows(self):
        import pandas as pd

        dataframe = pd.DataFrame(
            {
                "sdo name": [
                    "API",
                    "REVIEWED BY",
                    "REVISION CHANGES",
                    "YELLOW HIGHLIGHTED",
                    "ASTM",
                ],
                "displaystdno": [
                    "570",
                    "R.Thangaraj Manager",
                    "Revision Changes:",
                    "are revised and Refer the remarks column for details",
                    "A29/A29M",
                ],
            }
        )
        rows = self.extractor._extract_structured_rows("Sheet1", dataframe)
        self.assertEqual(
            [(row["sdo_name"], row["displaystdno"]) for row in rows],
            [("API", "570"), ("ASTM", "A29/A29M")],
        )

    def test_structured_table_headers_take_precedence_over_category_detection(self):
        import pandas as pd

        raw = pd.DataFrame(
            [
                [
                    "S.No",
                    "SDO",
                    "Category",
                    "Standard Code",
                    "Year",
                    "Standard Title / Scope",
                ],
                [
                    93,
                    "BIS",
                    "IS standard",
                    "IS 3347 01-Mar 1988",
                    None,
                    "Bushings 17.5kV",
                ],
                [
                    182,
                    "ATEX",
                    "ATEX",
                    "ATEX 2014/34/EU 2017",
                    None,
                    "Guidelines - 2nd Edition December",
                ],
            ]
        )

        analyzed = self.extractor._analyze_sheet("TMInd Std List2", raw)

        self.assertEqual(
            [
                (row["sdo_name"], row["displaystdno"])
                for row in analyzed["rows"]
            ],
            [
                ("BIS", "IS 3347 01-Mar 1988"),
                ("ATEX", "2014/34/EU 2017"),
            ],
        )
        self.assertTrue(
            all(row["source_column"] == "standard code" for row in analyzed["rows"])
        )

    def test_input_standard_header_and_fragmented_identifiers(self):
        import pandas as pd

        raw = pd.DataFrame(
            [
                [
                    "Case",
                    "Input Standard",
                    "Fragment 2",
                    "Fragment 3",
                    "Fragment 4",
                    "Description",
                ],
                ["complete", "IEEE Std C57.162", None, None, None, "Expected"],
                ["fragmented", "IEEE", "C57.104", ":", "2019", "Expected"],
                [
                    "description",
                    "IEEE",
                    "C57.104",
                    None,
                    None,
                    "Transformer gas analysis",
                ],
            ]
        )

        header_row, header_score = self.extractor._detect_header_row(raw)
        self.assertEqual(header_row, 0)
        self.assertGreaterEqual(header_score, self.extractor.MIN_HEADER_SCORE)

        analyzed = self.extractor._analyze_sheet("Test Cases", raw)
        self.assertEqual(
            [
                (row["sdo_name"], row["displaystdno"])
                for row in analyzed["rows"]
            ],
            [
                ("IEEE", "Std C57.162"),
                ("IEEE", "C57.104 : 2019"),
                ("IEEE", "C57.104"),
            ],
        )

    def test_split_publisher_prefixes_and_empty_cells(self):
        import pandas as pd

        self.assertEqual(
            self.extractor._parse_row_text(["BIS", "IS", 5469, 1]),
            {"sdo_name": "BIS", "displaystdno": "IS 5469 1"},
        )
        self.assertEqual(
            self.extractor._parse_row_text(["DIN", "EN", 12760]),
            {"sdo_name": "DIN", "displaystdno": "EN 12760"},
        )
        self.assertEqual(
            self.extractor._parse_row_text(["IEEE", "C57.104", pd.NA, "2019"]),
            {"sdo_name": "IEEE", "displaystdno": "C57.104 2019"},
        )

    def test_chapter_fragments_join_but_descriptions_do_not(self):
        parsed = self.extractor._parse_row_text(
            ["API", "MPMS", "Ch.", "6.6"]
        )
        self.assertEqual(
            parsed,
            {"sdo_name": "API", "displaystdno": "MPMS Ch. 6.6"},
        )
        from app.services.document_service import DocumentService

        expanded = DocumentService()._expand_canonical_rows([parsed])
        self.assertEqual(
            [row["displaystdno"] for row in expanded],
            ["MPMS CH 6.6"],
        )
        self.assertEqual(
            self.extractor._parse_row_text(
                ["IEEE", "C57.104", "Transformer gas analysis"]
            ),
            {"sdo_name": "IEEE", "displaystdno": "C57.104"},
        )

    def test_tema_publication_title_is_a_searchable_standard(self):
        title = "Standards of the Tubular Exchanger Manufacturers Association"

        self.assertEqual(
            self.extractor._parse_standard_value(title),
            {"sdo_name": "TEMA", "displaystdno": "Standards"},
        )
        self.assertEqual(
            self.extractor._parse_category_matrix_cell(title, ""),
            [{"sdo_name": "TEMA", "displaystdno": "Standards"}],
        )
        self.assertEqual(
            self.extractor._parse_standard_value(
                "A descriptive note about tubular exchanger equipment"
            ),
            None,
        )

        from app.services.document_service import DocumentService

        self.assertEqual(
            [
                (row["sdo_name"], row["displaystdno"])
                for row in DocumentService()._expand_canonical_rows(
                    [{"sdo_name": "TEMA", "displaystdno": "Standards"}]
                )
            ],
            [("TEMA", "Standards")],
        )

    def test_named_standards_without_numeric_codes_are_retained(self):
        ibr_request = self.extractor._parse_standard_value(
            "IBR INDIAN BOILER REGLN. (AKALANK)",
            "IBR",
        )
        self.assertEqual(
            ibr_request,
            {
                "sdo_name": "IBR",
                "displaystdno": "INDIAN BOILER REGLN. (AKALANK)",
            },
        )
        self.assertEqual(
            self.extractor._parse_standard_value(
                "Standard Methods for the Examination of Water and Wastewater",
                "AWWA",
            ),
            {
                "sdo_name": "AWWA",
                "displaystdno": (
                    "Standard Methods for the Examination of Water and Wastewater"
                ),
            },
        )
        self.assertIsNone(
            self.extractor._parse_standard_value(
                "CUSTOM COLLECTION (20 STANDARDS) - ONLINE",
                "IEC",
            )
        )

        from app.services.document_service import DocumentService

        self.assertEqual(
            DocumentService()._expand_canonical_rows([ibr_request])[0][
                "displaystdno"
            ],
            "INDIAN BOILER REGLN. (AKALANK)",
        )

    def test_keeps_digitless_standard_designations(self):
        parsed = self.extractor._parse_standard_value(
            "ASME BPVC SEC I",
            "ASME",
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["displaystdno"], "BPVC SEC I")

    def test_engineering_style_standard_name_sdo_column(self):
        import pandas as pd

        dataframe = pd.DataFrame(
            {
                "standard name": ["API", "API"],
                "standard number": ["570", "579 PT 1"],
                "title of the standard": ["Piping", "Fitness"],
            }
        )
        rows = self.extractor._extract_structured_rows("Sheet1", dataframe)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["sdo_name"], "API")
        self.assertEqual(rows[0]["displaystdno"], "570")
        self.assertEqual(rows[1]["displaystdno"], "579 PT 1")

    def test_explicit_sdo_wins_over_identifier_prefix(self):
        expected = [
            ("API", "TR 10TR1", "API", "TR 10TR1"),
            ("AS", "NZS 2885.1", "AS", "NZS 2885.1"),
            ("MSS", "SP 75", "MSS", "SP 75"),
            ("NACE", "SP 0104", "NACE", "SP 0104"),
            ("GPA", "STD 2145", "GPA", "STD 2145"),
            ("DIN", "EN 12613", "DIN", "EN 12613"),
            ("EI", "IP 264", "EI", "IP 264"),
        ]

        for explicit_sdo, number, expected_sdo, expected_number in expected:
            with self.subTest(sdo=explicit_sdo, number=number):
                self.assertEqual(
                    self.extractor._parse_standard_value(number, explicit_sdo),
                    {
                        "sdo_name": expected_sdo,
                        "displaystdno": expected_number,
                    },
                )

    def test_master_list_uses_standard_title_not_department_or_description(self):
        import pandas as pd

        dataframe = pd.DataFrame(
            [
                ["S. No", "STANDARD TITLE", "Title / Description",
                 "LATEST REVISION / EDITION", "Remarks", "FILE NUMBER",
                 "Department"],
                [1, "ASNT SNT-TC-1A", "Recommended Practice", "2024 Edition",
                 None, "Soft", "Quality"],
                [2, "DANSK DS/EN ISO 11970", "Welding procedures", "2025",
                 None, "Soft", "Quality"],
                [3, "EEC 2014/68/EU", "Pressure Equipment Directive", "2014",
                 None, "Soft", "Quality"],
                [4, "MSS SP 53", "Quality Standard for castings", "2021",
                 None, "Soft", "Quality"],
                [5, "MSS SP-55-2025 Standard and 11 x 17 Laminated Photo Set",
                 "Quality Standard for castings", "2025", None, "Soft",
                 "Quality"],
                [6, "AENOR UNE-EN 13018", "Visual testing", "2016",
                 None, "Soft", "Quality"],
                [7, "UNI EN 1371-1", "Liquid penetrant testing", "2011",
                 None, "Soft", "Quality"],
                [8, "2024", "API SPEC 570", None, None, "Soft", "Quality"],
                [9, "API WEBSTORE STANDARDS SUBSCRIPTION PACKAGES "
                 "Subscription Start Date: 22nd Jan 2026 and Subscription "
                 "End Date: 22nd Jan 2027", None, None, None, "Soft", "API"],
            ]
        )
        dataframe = self.extractor._make_dataframe_from_header(
            dataframe,
            0,
        )

        rows = self.extractor._extract_structured_rows("Master", dataframe)

        self.assertEqual(
            [(row["sdo_name"], row["displaystdno"]) for row in rows],
            [
                ("ASNT", "SNT-TC-1A"),
                ("ISO", "11970"),
                ("EEC", "2014/68/EU"),
                ("MSS", "SP 53"),
                ("MSS", "SP-55-2025"),
                ("AENOR", "13018"),
                ("UNI", "1371-1"),
            ],
        )
        self.assertTrue(
            all(row["source_column"] == "standard title" for row in rows)
        )

    def test_iso_iec_compound_is_preserved(self):
        parsed = self.extractor._parse_standard_value(
            "ISO/IEC TR 24763:2011",
            "ISO",
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["sdo_name"], "ISO/IEC")
        self.assertIn("24763", parsed["displaystdno"])

    def test_soft_hyphen_in_standard_identifier_is_preserved_as_hyphen(self):
        parsed = self.extractor._parse_standard_value("ASNT CP\u00ad189")
        self.assertEqual(
            parsed,
            {"sdo_name": "ASNT", "displaystdno": "CP-189"},
        )

    def test_soft_multi_column_category_matrix(self):
        """Headers like 'API Standards' (no ': N Standards') yield one row per cell."""
        import pandas as pd

        raw = pd.DataFrame(
            [
                [
                    "API Standards",
                    "ISO standarsds",
                    "ASME BPVC & STANDARDS",
                    "OUTRIGHT PURCHASE",
                ],
                ["API STD 610", "ISO 21940-1", "ASME BPVC SEC I", "EI 1581"],
                ["API SPEC 5L", "ISO 4006", "", "ISA 75.01"],
                ["", "", "", "NEMA ICS-6"],
            ]
        )

        rows = self.extractor._extract_category_matrix("Sheet1", raw)
        self.assertGreaterEqual(len(rows), 7)

        by_sdo = {}
        for row in rows:
            by_sdo.setdefault(row["sdo_name"], []).append(row["displaystdno"])

        self.assertIn("API", by_sdo)
        self.assertIn("ISO", by_sdo)
        self.assertIn("ASME", by_sdo)
        self.assertIn("EI", by_sdo)
        self.assertIn("ISA", by_sdo)
        self.assertIn("NEMA", by_sdo)
        self.assertTrue(any("610" in n for n in by_sdo["API"]))
        self.assertTrue(any("21940" in n for n in by_sdo["ISO"]))

    def test_category_matrix_slash_pair_emits_both(self):
        import pandas as pd

        raw = pd.DataFrame(
            [
                ["NACE/AMPP Standards", "API Standards"],
                ["MR0175 / ISO 15156 (Pt 1/2/3)", "API 570"],
            ]
        )
        rows = self.extractor._extract_category_matrix("Sheet1", raw)
        sdos = {row["sdo_name"] for row in rows}
        self.assertIn("NACE", sdos)
        self.assertIn("ISO", sdos)
        self.assertIn("API", sdos)
        self.assertGreaterEqual(len(rows), 3)

    def test_count_style_category_matrix_still_works(self):
        import pandas as pd

        raw = pd.DataFrame(
            [
                ["AWWA: 3 Standards", "API: 2 Standards"],
                ["AWWA C600", "API 5L"],
                ["AWWA C651", "API 1104"],
                ["AWWA C200", ""],
            ]
        )
        rows = self.extractor._extract_category_matrix("Sheet1", raw)
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            {row["sdo_name"] for row in rows},
            {"AWWA", "API"},
        )


    def test_category_matrix_rows_skip_part_range_expansion(self):
        from app.services.document_service import DocumentService

        rows = [
            {
                "sdo_name": "IEC",
                "displaystdno": "60947 (Pt 1-8)",
                "source_layout": "category_matrix",
                "raw_cell_value": "IEC 60947 (Pt 1-8)",
            }
        ]
        out = DocumentService()._expand_canonical_rows(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["displaystdno"], "60947 (Pt 1-8)")


if __name__ == "__main__":
    unittest.main()
