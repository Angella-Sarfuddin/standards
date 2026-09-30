from app.services.extractors.excel_extractor import ExcelExtractor
from app.services.extractors.pdf_extractor import PDFExtractor
from app.services.extractors.word_extractor import WordExtractor
from app.services.extractors.text_extractor import TextExtractor
from app.services.extractors.csv_extractor import CSVExtractor
from app.services.standard_extractor import StandardExtractor
from app.utils.standard_expression_parser import StandardExpressionParser


class DocumentService:

    EXTRACTORS = {
        "excel": ExcelExtractor,
        "pdf": PDFExtractor,
        "word": WordExtractor,
        "text": TextExtractor,
        "csv": CSVExtractor,
    }

    SUPPORTED_EXTENSIONS = {
        ".xlsx": "excel",
        ".xls": "excel",
        ".pdf": "pdf",
        ".docx": "word",
        ".doc": "word",
        ".txt": "text",
        ".csv": "csv",
    }

    def __init__(self):
        self.standard_extractor = StandardExtractor()
        self.expression_parser = StandardExpressionParser()

    @staticmethod
    def detect_file_type(filename: str):
        from pathlib import Path

        if not filename:
            raise ValueError("File name is required")

        extension = Path(filename).suffix.lower()
        file_type = DocumentService.SUPPORTED_EXTENSIONS.get(extension)

        if not file_type:
            raise ValueError(f"Unsupported file type: {extension}")

        return file_type

    def extract(self, filename, file):
        file_type = self.detect_file_type(filename)
        extractor_class = self.EXTRACTORS[file_type]
        extractor = extractor_class()
        extracted = extractor.extract(file)

        if isinstance(extracted, list):
            if extracted and all(
                isinstance(row, dict)
                and "sdo_name" in row
                and "displaystdno" in row
                for row in extracted
            ):
                return self._expand_canonical_rows(extracted)

            rows = self.standard_extractor.extract_from_rows(extracted)
            return self._expand_canonical_rows(rows)

        text = extracted.get("text", "") if isinstance(extracted, dict) else str(extracted or "")
        return self._extract_from_text(text)

    def _expand_canonical_rows(self, rows):
        """Expand explicit part/section/chapter ranges without losing source data."""
        expanded_rows = []

        for row in rows or []:
            sdo = str(row.get("sdo_name") or "").strip()
            standard = str(row.get("displaystdno") or "").strip()

            if not standard or standard.upper() in {"NAN", "NONE"}:
                continue

            parsed_rows = self.expression_parser.expand(standard, explicit_sdo=sdo)
            if not parsed_rows:
                expanded_rows.append(row)
                continue

            for parsed in parsed_rows:
                new_row = dict(row)
                new_row["sdo_name"] = parsed["sdo_name"] or sdo
                new_row["displaystdno"] = parsed["displaystdno"]
                new_row["raw_standard_expression"] = parsed.get("raw", standard)
                new_row["standard_expression"] = parsed.get("expression")
                expanded_rows.append(new_row)

        return expanded_rows

    def _extract_from_text(self, text):
        """Parse text line-by-line so TXT/PDF/Word inputs get the same
        expression handling as Excel cells.
        """
        if not text:
            return []

        results = []
        for line in str(text).splitlines():
            line = line.strip()
            if not line:
                continue

            parsed = self.expression_parser.extract_from_line(line)
            if parsed:
                results.extend(parsed)
                continue

            # Keep the older parser as a fallback for legacy formats that are
            # not confidently recognized by the tolerant expression parser.
            legacy = self.standard_extractor.extract_from_text(line)
            if legacy:
                results.extend(self._expand_canonical_rows(legacy))

        return self._deduplicate_text_rows(results)

    @staticmethod
    def _deduplicate_text_rows(rows):
        seen = set()
        output = []
        for row in rows:
            key = (
                str(row.get("sdo_name") or "").upper().strip(),
                str(row.get("displaystdno") or "").upper().strip(),
            )
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            output.append(row)
        return output
