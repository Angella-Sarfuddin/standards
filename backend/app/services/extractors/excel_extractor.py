import re
from dataclasses import dataclass

import pandas as pd

from app.services.extractors.base_extractor import BaseExtractor
from app.core.legacy_office import (
    OfficeConversionError,
    OfficeConversionUnavailable,
    converted_office_file,
)
from app.core.standard_expression_parser import StandardExpressionParser
from app.core.standard_identity import parse_identity


@dataclass
class ColumnCandidate:
    name: str
    score: float
    role: str


class ExcelExtractor(BaseExtractor):
    """Generic Excel ingestion: detect table shape, classify columns, emit
    canonical ``{sdo_name, displaystdno}`` search rows.
    """

    HEADER_SCAN_ROWS = 15
    MIN_HEADER_SCORE = 2.0

    STANDARD_ALIASES = {
        "requested_standard": {
            "input standard": 12,
            "input standards": 12,
            "requested standard": 12,
            "requested standards": 12,
            "requested standard number": 12,
            "requested standard no": 12,
            "standard requested": 11,
            "customer standard": 11,
            "customer requirement": 9,
            "customer requirements": 9,
            "requirement": 7,
            "requirements": 7,
            "bcces list": 10,
            "standard number": 9,
            "standard no": 9,
            "std number": 8,
            "std no": 8,
            "std. no": 8,
            "standard code": 8,
            "document number": 7,
            "document no": 7,
            "reference number": 5,
            "reference no": 5,
            "reference": 3,
            "displaystdno": 11,
            "display stdno": 11,
            "display std no": 11,
            "display standard no": 11,
            "display standard number": 11,
            "stdno": 8,
            "std_no": 8,
            "standard title": 14,
            "standard title number": 14,
            "standard": 5,
            "standards": 5,
            "code": 4,
            "codes": 4,
        },
        "reference_standard": {
            "located standards": 1,
            "located standard": 1,
            "matched standard": 1,
            "matched standards": 1,
            "search result": 1,
            "search results": 1,
            "result": 1,
            "results": 1,
            "supplier reference": 1,
            "reference standard": 1,
        },
    }

    SDO_ALIASES = {
        "sdo name": 12,
        "standard name": 12,
        "standard organization": 11,
        "sdo": 11,
        "standards organization": 11,
        "standards organisation": 11,
        "organization": 8,
        "organisation": 8,
        "publisher": 7,
        "issuing body": 10,
        "issuing organization": 10,
        "issuing organisation": 10,
        "agency": 6,
        "body": 5,
    }

    IGNORED_COLUMNS = {
        "sl no",
        "sl. no",
        "serial no",
        "serial number",
        "s no",
        "sr no",
        "sr. no",
        "id",
        "index",
        "remarks",
        "remark",
        "notes",
        "note",
        "description",
        "title description",
        "latest revision edition",
        "revision edition",
        "file number",
        "department",
        "title",
        "title of the standard",
        "price",
        "member price",
        "nonmember price",
        "currency",
        "quantity",
        "status",
        "action",
    }
    YEAR_COLUMN_ALIASES = {
        "year",
        "standard year",
        "publication year",
        "edition year",
        "year of publication",
    }

    KNOWN_SDOS = {
        "ISO", "IEC", "ISO/IEC", "ISO/TS", "ISO/TR", "API", "ASTM", "IS", "BIS",
        "ASME", "NACE", "AWWA", "ASHRAE", "IEEE", "ACI", "JIS", "UL",
        "ANSI", "BSI", "TEMA", "NFPA", "SAE", "EN", "DIN", "BS",
        "CEN", "CENELEC", "CSA", "FM", "FM GLOBAL", "IGEM", "IETF",
        "AWS", "AISC", "ICC", "IAPMO", "SII", "GB", "KS", "SANS",
        "NEMA", "ISA", "EI", "DNV", "PD", "AMPP", "SSPC", "HI",
        "CIGRE", "EIA", "ETS", "IEC/TR", "IEC/TS", "EIA/TIA",
    }

    SDO_PATTERN = re.compile(
        r"\b("
        r"ISO(?:/IEC|/TS|/TR)?|API|ASTM|ASME|NACE|AWWA|ASHRAE|IEEE|ACI|JIS|UL|"
        r"IEC(?:\s*/\s*(?:TR|TS))?|EIA/TIA|ANSI|BSI|BIS|BS|IS|TEMA|NFPA|SAE|DIN|CEN|CENELEC|CSA|FM|IGEM|"
        r"AWS|AISC|ICC|IAPMO|SII|GB|KS|SANS|"
        r"NEMA|ISA|EI|DNV|PD|AMPP|SSPC|HI|CIGRE|EIA|ETS"
        r")(?=\d|\b)",
        re.IGNORECASE,
    )
    COMPOUND_STANDARD_PREFIXES = {
        "BIS": {"IS"},
        "BS": {"EN"},
        "DIN": {"EN"},
        "ISO": {"IEC"},
    }


    def extract(self, file, filename=None):
        extension = self._file_extension(file, filename)
        if extension == ".xls":
            try:
                if hasattr(file, "seek"):
                    file.seek(0)
                workbook = pd.read_excel(
                    file,
                    sheet_name=None,
                    header=None,
                    engine="xlrd",
                )
            except ImportError:
                try:
                    with converted_office_file(
                        file,
                        filename or getattr(file, "name", "upload.xls"),
                        ".xlsx",
                    ) as converted:
                        workbook = pd.read_excel(
                            converted,
                            sheet_name=None,
                            header=None,
                            engine="openpyxl",
                        )
                except OfficeConversionUnavailable as converter_error:
                    raise ValueError(
                        "The .xls file needs the xlrd Python package or "
                        "LibreOffice. Install project requirements or "
                        "configure LibreOffice to read legacy Excel files."
                    ) from converter_error
                except OfficeConversionError as converter_error:
                    raise ValueError(
                        f"Could not read this .xls file: {converter_error}"
                    ) from converter_error
        else:
            workbook = pd.read_excel(
                file,
                sheet_name=None,
                header=None,
            )

        sheet_candidates = []

        for sheet_name, raw in workbook.items():
            candidate = self._analyze_sheet(sheet_name, raw)
            if candidate["rows"]:
                sheet_candidates.append(candidate)

        if not sheet_candidates:
            return []

        selected = self._select_input_sheets(sheet_candidates)

        rows = []
        for sheet in selected:
            rows.extend(sheet["rows"])

        rows = self._deduplicate_representations(rows)
        return sorted(
            rows,
            key=lambda row: str(row.get("sdo_name", "")).strip().casefold(),
        )

    @staticmethod
    def _file_extension(file, filename=None):
        from pathlib import Path

        candidate = filename or getattr(file, "name", "")
        return Path(str(candidate)).suffix.lower()

    def _deduplicate_representations(self, rows):
        
        kept = []
        seen_cross_source = {}

        for row in rows:
            identity_key = (
                str(row.get("sdo_name", "")).upper().strip(),
                re.sub(r"\s+", "", str(row.get("displaystdno", "")).upper().strip()),
            )
            key = (
                *identity_key,
                row.get("source_sheet"),
                row.get("source_row"),
            )
            source = row.get("source_column")

            if not identity_key[0] or not identity_key[1]:
                kept.append(row)
                continue

            previous = seen_cross_source.get(key)
            if previous is None:
                seen_cross_source[key] = (source, len(kept))
                kept.append(row)
                continue

            previous_source, previous_index = previous

            if previous_source == source:
                kept.append(row)
                continue

            previous_is_reference = "located" in str(previous_source).lower() if previous_source else False
            current_is_reference = "located" in str(source).lower() if source else False

            if previous_is_reference and not current_is_reference:
                kept[previous_index] = row
                seen_cross_source[key] = (source, previous_index)

        return kept

    # ------------------------------------------------------------------
    # Sheet analysis
    # ------------------------------------------------------------------

    def _analyze_sheet(self, sheet_name: str, raw: pd.DataFrame) -> dict:
        raw = self._clean_dataframe(raw)
        if raw.empty:
            return {"sheet": sheet_name, "score": 0, "rows": []}

        header_row, header_score = self._detect_header_row(raw)

        if header_row is not None and header_score >= self.MIN_HEADER_SCORE:
            dataframe = self._make_dataframe_from_header(raw, header_row)
            rows = self._extract_structured_rows(sheet_name, dataframe)
            score = self._sheet_score(dataframe, rows, header_score)
        else:
            category_rows = self._extract_category_matrix(sheet_name, raw)
            if category_rows:
                return {
                    "sheet": sheet_name,
                    "score": self._category_matrix_score(raw, category_rows),
                    "rows": category_rows,
                }
            rows = self._extract_unstructured_rows(sheet_name, raw)
            score = self._unstructured_sheet_score(raw, rows)

        return {
            "sheet": sheet_name,
            "score": score,
            "rows": rows,
        }

    CATEGORY_HEADER_PATTERN = re.compile(
        r"^\s*(?P<category>[A-Za-z][A-Za-z0-9/& ._-]{0,60}?)"
        r"\s*:\s*(?P<count>\d+)\s+standards?\b",
        re.IGNORECASE,
    )

    # Plural "standards" and common typo "standarsds" (not bare "standard",
    # which appears in normal column headers like "Standard Name").
    CATEGORY_SECTION_SUFFIX = re.compile(
        r"(?i)\b(?:standards|standarsds)\b"
    )

    def _looks_like_category_header(self, text: str) -> bool:
        """True for SDO section titles (count-style or soft matrix headers)."""
        text = self._clean_text(text)
        if not text or len(text) > 100:
            return False

        if self.CATEGORY_HEADER_PATTERN.match(text):
            return True

        normalized = self._normalize_header(text)
        if normalized in self.IGNORED_COLUMNS:
            return False
        if normalized in self.SDO_ALIASES:
            return False
        if any(
            normalized in aliases
            for aliases in self.STANDARD_ALIASES.values()
        ):
            return False

        # Data cells usually carry catalogue digits; section headers do not.
        if len(re.findall(r"\d", text)) >= 3:
            return False

        if self.CATEGORY_SECTION_SUFFIX.search(text):
            return True

        if self.SDO_PATTERN.search(text) and not re.search(r"\d", text):
            return True

        return False

    def _category_header_to_sdo(self, text: str) -> str:
        """Map a matrix header to an SDO token, or '' for cell-inferred columns."""
        text = self._clean_text(text)
        if not text:
            return ""

        match = self.CATEGORY_HEADER_PATTERN.match(text)
        if match:
            return self._normalize_sdo(match.group("category").strip())

        return self._extract_sdo(text) or ""

    def _parse_category_matrix_cell(self, value: str, category_sdo: str):
        """Parse one matrix cell; optionally emit two rows for ``A / B`` pairs."""
        value = self._clean_text(value)
        if not value:
            return []

        # Skip long prose titles without catalogue digits (e.g. TEMA blurbs).
        if (
            not re.search(r"\d", value)
            and len(value.split()) > 5
            and not StandardExpressionParser.named_standard_title(value)
        ):
            return []

        if " / " in value:
            parts = [part.strip() for part in value.split(" / ", 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                left = self._parse_standard_value(parts[0], category_sdo)
                if not left:
                    left = self._parse_standard_value(parts[0], "")
                right = self._parse_standard_value(parts[1], "")
                if not right and category_sdo:
                    right = self._parse_standard_value(parts[1], category_sdo)
                if left and right:
                    return [left, right]

        parsed = self._parse_standard_value(value, category_sdo)
        if not parsed:
            parsed = self._parse_standard_value(value, "")
        return [parsed] if parsed else []

    def _extract_category_matrix(self, sheet_name: str, raw: pd.DataFrame):
        if raw.shape[0] < 2 or raw.shape[1] < 2:
            return []

        header_row = None
        categories = {}

        for row_index in range(min(5, len(raw))):
            found = {}
            soft_hits = 0

            for column_index, value in enumerate(raw.iloc[row_index].tolist()):
                text = self._safe_value(value)
                if not text:
                    continue

                match = self.CATEGORY_HEADER_PATTERN.match(text)
                if match:
                    found[column_index] = {
                        "name": match.group("category").strip(),
                        "declared_count": int(match.group("count")),
                        "sdo": self._normalize_sdo(
                            match.group("category").strip()
                        ),
                    }
                    soft_hits += 1
                    continue

                if self._looks_like_category_header(text):
                    found[column_index] = {
                        "name": text,
                        "declared_count": None,
                        "sdo": self._category_header_to_sdo(text),
                    }
                    soft_hits += 1

            if soft_hits >= 2:
                header_row = row_index
                categories = found
                break

        if header_row is None:
            return []

        rows = []

        for column_index in range(raw.shape[1]):
            meta = categories.get(column_index, {})
            category = meta.get("name", "")
            category_sdo = meta.get("sdo", "")
            if not category_sdo and category:
                category_sdo = self._category_header_to_sdo(category)

            for row_index in range(header_row + 1, raw.shape[0]):
                value = self._safe_value(raw.iat[row_index, column_index])
                if not value:
                    continue

                for parsed in self._parse_category_matrix_cell(
                    value,
                    category_sdo,
                ):
                    if not self._is_usable_parse(parsed):
                        continue

                    rows.append({
                        **parsed,
                        "source_sheet": sheet_name,
                        "source_row": row_index + 1,
                        "source_column": f"column_{column_index + 1}",
                        "source_layout": "category_matrix",
                        "raw_cell_value": value,
                        "source_data": {
                            "category": category,
                            "value": value,
                        },
                    })

        return rows

    @staticmethod
    def _category_matrix_score(raw, rows):
        density = len(rows) / max(1, raw.size)
        return 100.0 + len(rows) * 0.50 + density * 20.0

    @staticmethod
    def _clean_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
        dataframe = dataframe.copy()
        dataframe = dataframe.dropna(axis=0, how="all")
        dataframe = dataframe.dropna(axis=1, how="all")
        return dataframe.reset_index(drop=True)

    def _detect_header_row(self, dataframe: pd.DataFrame):
        best_row = None
        best_score = 0.0

        limit = min(self.HEADER_SCAN_ROWS, len(dataframe))

        for index in range(limit):
            values = [self._normalize_header(v) for v in dataframe.iloc[index].tolist()]
            values = [v for v in values if v]
            if not values:
                continue

            score = 0.0
            for value in values:
                if value in self.SDO_ALIASES:
                    score += 5
                for aliases in self.STANDARD_ALIASES.values():
                    if value in aliases:
                        score += max(2, abs(aliases[value]) / 2)
                if value in self.IGNORED_COLUMNS:
                    score += 0.5

            if len(set(values)) >= 2:
                score += 1

            if score > best_score:
                best_row = index
                best_score = score

        return best_row, best_score

    def _make_dataframe_from_header(self, raw: pd.DataFrame, header_row: int):
        headers = []
        seen = {}

        for position, value in enumerate(raw.iloc[header_row].tolist()):
            name = self._normalize_header(value)
            if not name:
                name = f"column_{position + 1}"

            count = seen.get(name, 0)
            seen[name] = count + 1
            if count:
                name = f"{name}_{count + 1}"

            headers.append(name)

        dataframe = raw.iloc[header_row + 1:].copy()
        dataframe.columns = headers
        return self._clean_dataframe(dataframe)

    # ------------------------------------------------------------------
    # Structured tables
    # ------------------------------------------------------------------

    def _extract_structured_rows(self, sheet_name: str, dataframe: pd.DataFrame):
        if dataframe.empty:
            return []

        standard_candidates = self._classify_standard_columns(dataframe)
        sdo_candidates = self._classify_sdo_columns(dataframe)

        if not standard_candidates:
            return self._extract_unstructured_rows(sheet_name, dataframe)

        # Never treat the detected SDO/organization column as the standard
        # number column (e.g. test_10000.xlsx: "sdo name" + "displaystdno").
        sdo_column_names = {
            candidate.name for candidate in sdo_candidates[:1]
        }
        standard_title_candidates = []
        for candidate in standard_candidates:
            if self._normalize_header(candidate.name) not in {
                "standard title",
                "standard title number",
            }:
                continue
            values = [
                self._safe_value(value)
                for value in dataframe[candidate.name].tolist()
            ]
            values = [value for value in values if value]
            parsed_count = sum(
                self._is_usable_parse(self._parse_standard_value(value))
                for value in values
            )
            # Some catalogs use "Standard Title" to mean the designation,
            # while others use it for prose descriptions. Only prefer it as
            # the identifier column when most populated cells actually parse
            # as standards; otherwise the real "Standard No." column wins.
            if values and parsed_count / len(values) >= 0.5:
                standard_title_candidates.append(candidate)
        if standard_title_candidates:
            usable_standard_candidates = standard_title_candidates
        else:
            usable_standard_candidates = [
                candidate
                for candidate in standard_candidates
                if candidate.name not in sdo_column_names
            ] or standard_candidates

        usable_standard_candidates.sort(
            key=lambda item: item.score,
            reverse=True,
        )

        rows = []

        for offset, (_, record) in enumerate(dataframe.iterrows(), start=1):
            source_data = {
                str(key): self._safe_value(value)
                for key, value in record.to_dict().items()
                if self._safe_value(value) != ""
            }

            if not source_data:
                continue

            sdo_value = ""
            if sdo_candidates:
                sdo_value = self._safe_value(
                    record.get(sdo_candidates[0].name)
                )

            parsed = None
            primary_name = usable_standard_candidates[0].name

            for candidate in usable_standard_candidates:
                standard_value = self._safe_value(
                    record.get(candidate.name)
                )
                if not standard_value:
                    continue

                candidate_parsed = self._parse_standard_value(
                    standard_value,
                    sdo_value,
                )
                if self._is_usable_parse(candidate_parsed):
                    parsed = candidate_parsed
                    primary_name = candidate.name
                    break

            if not parsed and not standard_title_candidates:
                parsed = self._parse_row_text(record.tolist())

            if not self._is_usable_parse(parsed):
                continue

            # Some workbooks store the edition year in a separate column.
            # Include it in the request identifier so distinct editions remain
            # distinguishable and the search does not silently use the latest
            # edition for every row.
            source_year = self._year_from_record(record)
            if source_year and not parse_identity(
                parsed["sdo_name"],
                parsed["displaystdno"],
            ).get("year"):
                parsed = {
                    **parsed,
                    "displaystdno": (
                        f"{parsed['displaystdno']} : {source_year}"
                    ),
                }

            rows.append({
                **parsed,
                "source_sheet": sheet_name,
                "source_row": offset,
                "source_column": primary_name,
                "source_data": source_data,
            })

        return rows

    @classmethod
    def _year_from_record(cls, record):
        for column, value in record.items():
            if cls._normalize_header(column) not in cls.YEAR_COLUMN_ALIASES:
                continue
            text = cls._safe_value(value)
            match = re.fullmatch(r"((?:19|20)\d{2})(?:\.0+)?", text)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _is_usable_parse(parsed):
        """Reject empty parses, SDO-only results, and spreadsheet notes."""
        if not parsed:
            return False
        sdo = str(parsed.get("sdo_name") or "").strip()
        number = str(parsed.get("displaystdno") or "").strip()
        if not sdo or not number:
            return False
        if sdo.upper() == number.upper():
            return False
        if StandardExpressionParser.is_note_or_legend(sdo):
            return False
        if StandardExpressionParser.is_note_or_legend(number):
            return False
        if not StandardExpressionParser.is_plausible_sdo(sdo):
            return False
        if not StandardExpressionParser.is_plausible_standard_request(
            sdo,
            number,
        ):
            return False
        return True

    # ------------------------------------------------------------------
    # Unstructured sheets / vertical lists / category layouts
    # ------------------------------------------------------------------

    def _extract_unstructured_rows(self, sheet_name: str, dataframe: pd.DataFrame):
        rows = []

        for row_index, (_, record) in enumerate(dataframe.iterrows(), start=1):
            values = [self._safe_value(value) for value in record.tolist()]
            values = [value for value in values if value]
            if not values:
                continue

            parsed = self._parse_row_text(values)
            if not parsed:
                continue

            rows.append({
                **parsed,
                "source_sheet": sheet_name,
                "source_row": row_index,
                "source_column": None,
                "source_data": {
                    f"column_{index + 1}": value
                    for index, value in enumerate(values)
                },
            })

        return rows

    # ------------------------------------------------------------------
    # Column/value classification
    # ------------------------------------------------------------------

    def _classify_standard_columns(self, dataframe: pd.DataFrame):
        candidates = []

        for column in dataframe.columns:
            normalized = self._normalize_header(column)
            score = 0.0
            role = "unknown"

            if normalized in self.IGNORED_COLUMNS:
                continue

            # ``STANDARD TITLE`` is the identifier column in many formal
            # master lists (with the publication title in a separate column).
            # This alias also prevents a preceding title block from winning
            # header detection over the real table header.
            for role_name, aliases in self.STANDARD_ALIASES.items():
                if normalized in aliases:
                    value = aliases[normalized]
                    score += value
                    if role_name == "reference_standard":
                        role = "reference"
                    else:
                        role = "requested"

            values = [self._safe_value(v) for v in dataframe[column].tolist()]
            values = [v for v in values if v]

            if values:
                standard_ratio = sum(
                    1 for value in values
                    if self._looks_like_standard_value(value)
                ) / len(values)
                score += standard_ratio * 12

                sdo_ratio = sum(
                    1 for value in values
                    if self._looks_like_sdo(value)
                ) / len(values)
                if sdo_ratio >= 0.7 and standard_ratio < 0.3:
                    score -= 15
                if "located" in normalized or "matched" in normalized:
                    score -= 8

            if score > 0:
                candidates.append(ColumnCandidate(column, score, role))

        return candidates

    def _classify_sdo_columns(self, dataframe: pd.DataFrame):
        candidates = []

        for column in dataframe.columns:
            normalized = self._normalize_header(column)
            score = float(self.SDO_ALIASES.get(normalized, 0))

            if score > 0:
                candidates.append(ColumnCandidate(column, score, "sdo"))

        return sorted(candidates, key=lambda item: item.score, reverse=True)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_standard_value(self, standard_value: str, sdo_value: str = ""):
        standard_value = self._clean_text(standard_value)
        standard_value = re.sub(
            r"(?i)\bIEC\s*/\s*(TR|TS)\b",
            r"IEC/\1",
            standard_value,
        )
        sdo_value = self._clean_text(sdo_value)

        if not standard_value:
            return None

        # Correct the common transposition in ``BN EN`` designations. Keep
        # the original cell intact in source_data for traceability.
        standard_value = re.sub(
            r"(?i)^BN(?=\s+EN\b)",
            "BS",
            standard_value,
        )

        # Preserve the issuing body for designations written as ANSI/ISA-xx;
        # the generic prefix parser otherwise splits this at ANSI and loses
        # the ISA standard number.
        ansi_isa = re.match(
            r"(?i)^ANSI\s*/\s*ISA\s*[-:]\s*(.+)$",
            standard_value,
        )
        if ansi_isa:
            standard_value = f"ISA {ansi_isa.group(1).strip()}"

        named_title = StandardExpressionParser.named_standard_title(
            standard_value
        )
        if named_title:
            return named_title

        explicit_sdo = self._normalize_sdo(sdo_value)

        if (
            explicit_sdo
            and not standard_value.upper().startswith(
                explicit_sdo.upper() + "/"
            )
        ):
            wrapper = re.match(
                rf"(?i)(?:[A-Z][A-Z0-9]{{1,10}}/)*"
                rf"{re.escape(explicit_sdo)}"
                rf"(?:/[A-Z][A-Z0-9]{{1,10}})?",
                standard_value,
            )
            if wrapper:
                standard_value = (
                    explicit_sdo
                    + standard_value[wrapper.end():]
                ).strip()

        inferred_sdo, inferred_number = (
            StandardExpressionParser.infer_sdo_and_body(standard_value)
        )
        if (
            explicit_sdo
            and inferred_sdo.startswith(f"{explicit_sdo}/")
        ):
            sdo, number = inferred_sdo, inferred_number
        else:
            sdo, number = StandardExpressionParser.infer_sdo_and_body(
                standard_value,
                explicit_sdo,
            )
        if sdo in {"AENOR", "DANSK DS/EN", "UNI"}:
            # National adoptions may contain the original SDO as well:
            # "DANSK DS/EN ISO 11970" is indexed as ISO 11970.
            for _ in range(2):
                inner_sdo, inner_number = (
                    StandardExpressionParser.infer_sdo_and_body(number)
                )
                if inner_sdo not in {
                    "EN",
                    "IEC",
                    "ISO",
                    "ISO/IEC",
                    "ISO/TS",
                    "ISO/TR",
                }:
                    break
                sdo, number = inner_sdo, inner_number
        if not sdo:
            number = ""
            embedded_sdo = self._extract_sdo(standard_value)
            if embedded_sdo and (
                not explicit_sdo
                or standard_value.upper().startswith(embedded_sdo.upper())
            ):
                sdo = embedded_sdo
            elif explicit_sdo:
                sdo = explicit_sdo
            else:
                sdo = self._infer_sdo_from_identifier(standard_value)

        if not sdo:
            return None

        if not number:
            number = re.sub(
                rf"^\s*{re.escape(sdo)}(?=\d|\b)\s*[:\-]?\s*",
                "",
                standard_value,
                flags=re.IGNORECASE,
            ).strip()

            if not number:
                number = standard_value[len(sdo):].lstrip(" :.-")

            if not number:
                number = standard_value

        number = number.split(";", 1)[0].strip()
        number = re.sub(
            r"(?i)\s+standard\s+and\s+\d+\s*[x×]\s*\d+.*$",
            "",
            number,
        ).strip()

        number = re.split(
            r"\s+[—–-]\s+|\s+\|\s+|\s+DESCRIPTION\s*:",
            number,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()

        if (
            not self._looks_like_identifier(number)
            or not StandardExpressionParser.is_plausible_standard_request(
                sdo,
                number,
            )
        ):
            return None

        if number.upper() == sdo.upper():
            return None

        return {
            "sdo_name": sdo,
            "displaystdno": number,
        }

    @classmethod
    def _infer_sdo_from_identifier(cls, value):
        value = cls._clean_text(value)
        if not value:
            return ""

        
        compound = re.match(r"^([A-Za-z]{1,6}(?:[/.-][A-Za-z]{1,8})+)\b", value)
        if compound:
            prefix = compound.group(1).upper()
            if re.search(r"\d", value[compound.end():]):
                return prefix

      
        tokens = value.split()
        if not tokens:
            return ""

        prefix_parts = []
        for token in tokens:
            clean = token.strip(" ,:;()[]")
            if re.search(r"\d", clean):
                break
            if not re.fullmatch(r"[A-Za-z][A-Za-z&./-]*", clean):
                break
            prefix_parts.append(clean)
            if len(prefix_parts) >= 2:
                break

        if prefix_parts:
            return " ".join(prefix_parts).upper()

        return ""

    def _parse_row_text(self, values):
        safe_values = [self._safe_value(value) for value in values]
        cells = [
            self._clean_text(value)
            for value in safe_values
            if value and value.casefold() not in {"nan", "none", "nat"}
        ]
        if not any(cells):
            return None

        for cell_index, cell in enumerate(cells):
            if not cell:
                continue

            for match in self.SDO_PATTERN.finditer(cell):
                sdo = self._normalize_sdo(match.group(1))
                if not sdo:
                    continue

                fragments = [cell[match.end():].strip(" |:.-")]
                for following_cell in cells[cell_index + 1:]:
                    if not following_cell:
                        continue
                    if self.SDO_PATTERN.match(following_cell):
                        prefix = following_cell.upper()
                        if prefix in self.COMPOUND_STANDARD_PREFIXES.get(
                            sdo, set()
                        ):
                            fragments.append(following_cell)
                            if sdo == "ISO" and prefix == "IEC":
                                sdo = "ISO/IEC"
                            continue
                        break
                    fragments.append(following_cell)

                candidate_fragments = []
                parsed_candidate = None
                for fragment in fragments:
                    if not fragment:
                        continue

                    if parsed_candidate and not self._is_identity_suffix_cell(
                        fragment
                    ):
                        break

                    candidate_fragments.append(fragment)
                    candidate = " ".join(candidate_fragments)
                    parsed = self._parse_standard_value(candidate, sdo)
                    if parsed:
                        parsed_candidate = parsed
                    elif parsed_candidate:
                        break

                    if (
                        parsed_candidate
                        and self._has_trailing_year(
                            " ".join(candidate_fragments)
                        )
                    ):
                        break

                if parsed_candidate:
                    return parsed_candidate

        return None

    @staticmethod
    def _is_identity_suffix_cell(value):
        """Allow only clearly identifier-shaped cells after a valid code."""
        value = str(value or "").strip()
        return bool(
            re.fullmatch(
                r"(?i)(?::|/|AMD|AMENDMENT|COR|CORR|CORRIGENDUM|ERRATA|"
                r"SERIES|PART|PT|CH\.?|CHAPTER|"
                r"\d+(?:[.-]\d+)*(?::\d{1,4})?|[IVXLCDM]{1,8})",
                value,
            )
        )

    @staticmethod
    def _has_trailing_year(value):
        return bool(re.search(r"(?<!\d)(?:19|20)\d{2}\s*$", value))

    # ------------------------------------------------------------------
    # Workbook selection / duplicate representations
    # ------------------------------------------------------------------

    def _select_input_sheets(self, candidates):
        # Every worksheet that yielded standards is part of the supplied
        # source. Do not discard a row because the same standard number also
        # appears on another worksheet: those rows may be separate requests.
        ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)
        return ranked

    @staticmethod
    def _row_keys(rows):
        keys = set()
        for row in rows:
            sdo = str(row.get("sdo_name", "")).strip().upper()
            number = str(row.get("displaystdno", "")).strip().upper()
            if sdo and number:
                keys.add((sdo, re.sub(r"\s+", "", number)))
        return keys

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _sheet_score(self, dataframe, rows, header_score):
        if dataframe.empty:
            return 0

        standard_candidates = self._classify_standard_columns(dataframe)
        requested_bonus = 0.0
        reference_penalty = 0.0

        for candidate in standard_candidates:
            if candidate.role == "requested":
                requested_bonus = max(requested_bonus, candidate.score)
            elif candidate.role == "reference":
                reference_penalty = max(reference_penalty, abs(candidate.score))

        density = len(rows) / max(1, len(dataframe))
      
        row_bonus = min(len(dataframe), 500) * 0.12

        return (
            header_score
            + requested_bonus * 1.5
            - reference_penalty * 0.15
            + density * 10
            + row_bonus
        )

    def _unstructured_sheet_score(self, dataframe, rows):
        density = len(rows) / max(1, len(dataframe))
        return density * 20 + min(len(rows), 100) * 0.05

    @classmethod
    def _normalize_header(cls, value):
        if value is None or pd.isna(value):
            return ""
        value = str(value).strip().lower()
        value = re.sub(r"[\n\r\t]+", " ", value)
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _safe_value(value):
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
        return str(value).strip()

    @staticmethod
    def _clean_text(value):
        value = str(value).replace("\n", " ").replace("\r", " ")
        # Excel can contain U+00AD soft hyphens in identifiers (for example,
        # ``ASNT CP­189``). Preserve the intended visible hyphen so the row
        # survives parsing and deduplication as CP-189.
        value = value.replace("\u00ad", "-")
        value = value.replace("‑", "-").replace("–", "-").replace("—", "-")
        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def _normalize_sdo(cls, value):
        value = cls._clean_text(value).upper()
        if StandardExpressionParser.is_note_or_legend(value):
            return ""
        match = cls.SDO_PATTERN.search(value)
        if match:
            return match.group(1).upper()
        if StandardExpressionParser.is_plausible_sdo(value):
            return value
        return ""

    @classmethod
    def _extract_sdo(cls, value):
        match = cls.SDO_PATTERN.search(value)
        return match.group(1).upper() if match else ""

    @classmethod
    def _looks_like_sdo(cls, value):
        value = cls._clean_text(value).upper()
        return StandardExpressionParser.is_plausible_sdo(value)

    @classmethod
    def _looks_like_standard_value(cls, value):
        value = cls._clean_text(value)
        if not value:
            return False

   
        if cls._looks_like_sdo(value):
            return False

        if cls.SDO_PATTERN.search(value) and re.search(r"\d", value):
            return True
        if re.search(r"\d", value) and cls._infer_sdo_from_identifier(value):
            return True

        tokens = value.split()
        first = tokens[0].upper() if tokens else ""
        return (
            first in cls.KNOWN_SDOS
            and 2 <= len(tokens) <= 6
            and not cls._looks_like_sdo(value)
        )

    @staticmethod
    def _looks_like_identifier(value):
        value = str(value).strip()
        if not re.search(r"\d", value):
            return (
                bool(value)
                and len(value.split()) <= 12
                and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._:/+()&,-]*", value))
                and bool(
                    StandardExpressionParser.NUMBERLESS_IDENTIFIER_PATTERN.search(
                        value
                    )
                )
            )
    
        return bool(re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9 ./:_()&+,\-]*",
            value,
        ))
