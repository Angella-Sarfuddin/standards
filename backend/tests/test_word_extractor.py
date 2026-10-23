import unittest

from app.services.extractors.word_extractor import WordExtractor


class WordExtractorTests(unittest.TestCase):
    def test_designation_column_ignores_summary_text(self):
        rows = WordExtractor._as_rows([
            "REVISION CHANGES",
            "YELLOW HIGHLIGHTED are revised and Refer the remarks column for details",
        ])
        self.assertEqual(rows, [])

    def test_designation_column_keeps_standards(self):
        rows = WordExtractor._as_rows([
            "API Spec 6A",
            "ASME BPVC SEC I",
        ])
        self.assertEqual(
            [(row["sdo_name"], row["displaystdno"]) for row in rows],
            [("API", "Spec 6A"), ("ASME", "BPVC SEC I")],
        )


if __name__ == "__main__":
    unittest.main()
