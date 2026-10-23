import io
import unittest

import pymupdf

from app.services.document_service import DocumentService
from app.services.extractors.pdf_extractor import PDFExtractor


class PDFExtractorTests(unittest.TestCase):
    @staticmethod
    def _make_pdf(lines):
        document = pymupdf.open()
        page = document.new_page()
        for y, text in lines:
            page.insert_text((72, y), text)
        content = document.tobytes()
        document.close()
        return io.BytesIO(content)

    def test_pdf_text_is_read_in_visual_order(self):
        pdf = self._make_pdf([
            (160, "API 570"),
            (80, "ASME B16.5"),
        ])

        extracted = PDFExtractor().extract(pdf)

        self.assertEqual(
            [
                line
                for line in extracted["text"].splitlines()
                if line.strip()
            ],
            ["ASME B16.5", "API 570"],
        )

    def test_tema_publication_title_becomes_one_search_request(self):
        title = "Standards of the Tubular Exchanger Manufacturers Association"
        pdf = self._make_pdf([(80, title)])

        rows = DocumentService().extract("standards.pdf", pdf)

        self.assertEqual(
            [(row["sdo_name"], row["displaystdno"]) for row in rows],
            [("TEMA", "Standards")],
        )


if __name__ == "__main__":
    unittest.main()
