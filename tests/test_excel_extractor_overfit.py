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

    def test_iso_iec_compound_is_preserved(self):
        parsed = self.extractor._parse_standard_value(
            "ISO/IEC TR 24763:2011",
            "ISO",
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["sdo_name"], "ISO/IEC")
        self.assertIn("24763", parsed["displaystdno"])


if __name__ == "__main__":
    unittest.main()
