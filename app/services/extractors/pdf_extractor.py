import pymupdf

from app.services.extractors.base_extractor import BaseExtractor


class PDFExtractor(BaseExtractor):

    def extract(self, file):
        document = pymupdf.open(
            stream=file.read(),
            filetype="pdf"
        )

        text_parts = []

        for page in document:
            text = page.get_text("text")

            if text:
                text_parts.append(text)

        document.close()

        return {
            "text": "\n".join(text_parts),
            "source_type": "pdf"
        }