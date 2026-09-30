from app.services.extractors.base_extractor import BaseExtractor


class TextExtractor(BaseExtractor):

    def extract(self, file):
        content = file.read()

        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")

        return {
            "text": content,
            "source_type": "text"
        }