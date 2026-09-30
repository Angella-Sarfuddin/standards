import unittest

from openpyxl import load_workbook

from app.services.export_service import ExportService


class ExportServiceTests(unittest.TestCase):
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

        workbook = load_workbook(output, read_only=True)
        worksheet = workbook["Quotation"]
        headers = [cell.value for cell in worksheet[1]]
        values = [cell.value for cell in worksheet[2]]
        row = dict(zip(headers, values))

        self.assertEqual(row["Standard Year"], 2024)
        self.assertEqual(row["Currency"], "USD")
        self.assertEqual(row["Matched Standard"], "API STD 610 : 2021")
        self.assertIsNone(row["TC"])
        self.assertLess(
            headers.index("Standard"),
            headers.index("Matched Standard"),
        )
        workbook.close()


if __name__ == "__main__":
    unittest.main()