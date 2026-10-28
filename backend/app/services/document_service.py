import re

from app.services.extractors.excel_extractor import ExcelExtractor
from app.services.extractors.pdf_extractor import PDFExtractor
from app.services.extractors.word_extractor import WordExtractor
from app.services.extractors.text_extractor import TextExtractor
from app.services.extractors.csv_extractor import CSVExtractor
from app.services.standard_extractor import StandardExtractor
from app.core.standard_expression_parser import StandardExpressionParser
from app.core.standard_identity import (
    canonicalize_search_request,
    normalize_identity_core,
    normalize_tokens,
    parse_identity,
)


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
        if file_type == "excel":
            extracted = extractor.extract(file, filename=filename)
        elif file_type == "word":
            extracted = extractor.extract(file, filename=filename)
        else:
            extracted = extractor.extract(file)

        if isinstance(extracted, list):
            if extracted and all(
                isinstance(row, dict)
                and "sdo_name" in row
                and "displaystdno" in row
                for row in extracted
            ):
                rows = self._expand_canonical_rows(extracted)
            else:
                rows = self.standard_extractor.extract_from_rows(extracted)
                rows = self._expand_canonical_rows(rows)
        else:
            text = (
                extracted.get("text", "")
                if isinstance(extracted, dict)
                else str(extracted or "")
            )
            rows = self._extract_from_text(text)

        rows = self._attach_source_identity(rows, filename)

        # Excel rows are explicit request records. Keep repeated standards on
        # separate source rows: they can represent distinct line items, and
        # collapsing by normalized identity silently drops valid spreadsheet
        # entries (including editions whose source designation is incomplete).
        # ExcelExtractor removes duplicate representations of the same
        # worksheet row across columns; expression expansion within a cell
        # remains intact here.
        if file_type == "excel":
            return rows

        # Repeated lines are separate customer requests. Preserve them so the
        # UI can reconcile every source line with its search result.
        return rows

    @staticmethod
    def _attach_source_identity(rows, filename):
        tagged = []
        for index, row in enumerate(rows or [], start=1):
            row = dict(row)
            if row.get("source_row") is None:
                row["source_row"] = index
            if not row.get("source_sheet") and not row.get("source_file"):
                row["source_file"] = filename or "document"
            tagged.append(row)
        return tagged

    def _expand_canonical_rows(self, rows):
        """Expand explicit part/section/chapter ranges without losing source data."""
        expanded_rows = []

        for row in rows or []:
            sdo = str(row.get("sdo_name") or "").strip()
            standard = str(row.get("displaystdno") or "").strip()

            if not standard or standard.upper() in {"NAN", "NONE"}:
                continue

            # Spreadsheet legends / reviewer notes are not standards.
            if (
                StandardExpressionParser.is_note_or_legend(sdo)
                or StandardExpressionParser.is_note_or_legend(standard)
                or (
                    sdo
                    and not StandardExpressionParser.is_plausible_sdo(sdo)
                )
                or not StandardExpressionParser.is_plausible_standard_request(
                    sdo,
                    standard,
                )
            ):
                continue

            # Category-matrix Excel cells are one RFQ line each. Do not explode
            # ``Pt 1-30`` / ``Parts 0-7`` ranges into dozens of search rows.
            if row.get("source_layout") == "category_matrix":
                expanded_rows.append({
                    **row,
                    "raw_standard_expression": (
                        row.get("raw_cell_value") or standard
                    ),
                    "include_subsections": (
                        "with subsections" in standard.casefold()
                    ),
                })
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
                new_row["include_subsections"] = (
                    "with subsections" in standard.casefold()
                )
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

        # De-duplicate once, at the shared extract() boundary, using the same
        # conservative standard-identity rules used for spreadsheet rows.
        # That keeps TXT/PDF/Word extraction from applying a looser raw-string
        # comparison than the other supported upload formats.
        return results

    @staticmethod
    def _deduplicate_request_rows(rows):
        """Remove only repeated requests with the same standard identity.

        Edition, revision, amendment, year, part/section, SDO, and family
        expansion are identity-bearing for this purpose. Keeping them in the
        key prevents similar-looking but distinct requests from collapsing.
        """
        seen = set()
        output = []
        metadata_re = re.compile(
            r"\b(?P<label>ED(?:ITION)?|REV(?:ISION)?|AMEND(?:MENT)?|AMD)"
            r"\.?\s*(?P<value>[A-Z0-9]+(?:\.\d+)*)",
            re.IGNORECASE,
        )

        for row in rows or []:
            sdo = str(row.get("sdo_name") or "").strip()
            display = str(row.get("displaystdno") or "").strip()
            if not sdo or not display:
                output.append(row)
                continue

            identity_sdo, canonical_number, _ = canonicalize_search_request(
                sdo,
                display,
            )
            identity = parse_identity(
                identity_sdo or sdo,
                canonical_number or display,
            )
            core = normalize_identity_core(
                identity.get("core_number") or identity.get("core") or ""
            )
            if not core:
                # Unknown/ambiguous forms are retained; raw identity is safer
                # than guessing that two requests refer to one standard.
                output.append(row)
                continue

            raw_value = str(
                row.get("raw_standard_expression") or display
            )
            metadata = tuple(
                (
                    match.group("label").upper().replace("EDITION", "ED")
                    .replace("REVISION", "REV")
                    .replace("AMENDMENT", "AMEND"),
                    normalize_tokens(match.group("value")),
                )
                for match in metadata_re.finditer(raw_value)
            )
            key = (
                normalize_tokens(sdo),
                core,
                identity.get("qualifier"),
                identity.get("year"),
                bool(identity.get("family_lookup")),
                bool(row.get("include_subsections")),
                metadata,
            )
            if key in seen:
                continue
            seen.add(key)
            output.append(row)

        return output
