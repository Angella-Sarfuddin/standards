import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.services.extractors.base_extractor import BaseExtractor


@dataclass
class ColumnCandidate:
    name: str
    score: float
    role: str


class ExcelExtractor(BaseExtractor):
    """
    Generic Excel ingestion layer.

    The extractor does NOT depend on a particular workbook/sheet name.
    It inspects sheets, detects the most useful table structure, classifies
    columns by meaning + values, and emits canonical search rows.

    Canonical row:
        {
            "sdo_name": "ISO",
            "displaystdno": "7010:2019",
            "source_sheet": "Customer Requirements",
            "source_row": 12,
            "source_data": {...}
        }
    """

    HEADER_SCAN_ROWS = 15
    MIN_HEADER_SCORE = 2.0

    # Ordered from most specific to generic. Matching is semantic rather than
    # tied to one exact customer template.
    STANDARD_ALIASES = {
        "requested_standard": {
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
        "title",
        "title of the standard",
        "standard name",
        "price",
        "member price",
        "nonmember price",
        "currency",
        "quantity",
        "status",
        "action",
    }

    KNOWN_SDOS = {
        "ISO", "IEC", "ISO/IEC", "ISO/TS", "ISO/TR", "API", "ASTM", "IS", "BIS",
        "ASME", "NACE", "AWWA", "ASHRAE", "IEEE", "ACI", "JIS", "UL",
        "ANSI", "BSI", "TEMA", "NFPA", "SAE", "EN", "DIN", "BS",
        "CEN", "CENELEC", "CSA", "FM", "FM GLOBAL", "IGEM", "IETF",
        "AWS", "AISC", "ICC", "IAPMO", "SII", "GB", "KS", "SANS",
    }

    SDO_PATTERN = re.compile(
        r"\b(ISO(?:/IEC|/TS|/TR)?|API|ASTM|ASME|NACE|AWWA|ASHRAE|IEEE|ACI|JIS|UL|IEC|ANSI|BSI|BIS|IS|TEMA|NFPA|SAE|DIN|CEN|CENELEC|CSA|FM|IGEM|AWS|AISC|ICC|IAPMO|SII|GB|KS|SANS)(?=\d|\b)",
        re.IGNORECASE,
    )


    def extract(self, file):
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

        return self._deduplicate_representations(rows)

    def _deduplicate_representations(self, rows):
        """Collapse the same standard when it appears in different workbook
        representations, while preserving repeated rows inside one actual
        input table.
        """
        kept = []
        seen_cross_source = {}

        for row in rows:
            key = (
                str(row.get("sdo_name", "")).upper().strip(),
                re.sub(r"\s+", "", str(row.get("displaystdno", "")).upper().strip()),
            )
            source = (row.get("source_sheet"), row.get("source_column"))

            if not key[0] or not key[1]:
                kept.append(row)
                continue

            previous = seen_cross_source.get(key)
            if previous is None:
                seen_cross_source[key] = (source, len(kept))
                kept.append(row)
                continue

            previous_source, previous_index = previous

            # Same source column = genuine repeated input row; preserve it.
            if previous_source == source:
                kept.append(row)
                continue

            # Different representations of the same standard = one canonical
            # row. Prefer the non-reference/requested representation.
            previous_is_reference = "located" in str(previous_source[1]).lower() if previous_source[1] else False
            current_is_reference = "located" in str(source[1]).lower() if source[1] else False

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

        # Some workbooks are category matrices rather than conventional
        # tables. Example:
        #
        # AWWA: 3 Standards | ASHRAE: 6 Standards | IEC: 105 Standards
        # AWWA C950          | ASHRAE 15-2024       | IEC 60034-1:2026
        #
        # Treat each populated cell under those category headers as an
        # independent input. This is generic and does not depend on the
        # worksheet being called "Sheet1".
        category_rows = self._extract_category_matrix(sheet_name, raw)
        if category_rows:
            return {
                "sheet": sheet_name,
                "score": self._category_matrix_score(raw, category_rows),
                "rows": category_rows,
            }

        header_row, header_score = self._detect_header_row(raw)

        if header_row is not None and header_score >= self.MIN_HEADER_SCORE:
            dataframe = self._make_dataframe_from_header(raw, header_row)
            rows = self._extract_structured_rows(sheet_name, dataframe)
            score = self._sheet_score(dataframe, rows, header_score)
        else:
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

    def _extract_category_matrix(self, sheet_name: str, raw: pd.DataFrame):
        if raw.shape[0] < 2 or raw.shape[1] < 2:
            return []

        header_row = None
        categories = {}

        for row_index in range(min(5, len(raw))):
            found = {}
            for column_index, value in enumerate(raw.iloc[row_index].tolist()):
                text = self._safe_value(value)
                match = self.CATEGORY_HEADER_PATTERN.match(text)
                if match:
                    found[column_index] = {
                        "name": match.group("category").strip(),
                        "declared_count": int(match.group("count")),
                    }

            # Require at least two category headers so an ordinary cell
            # mentioning "3 standards" is not mistaken for a matrix.
            if len(found) >= 2:
                header_row = row_index
                categories = found
                break

        if header_row is None:
            return []

        rows = []

        for column_index in range(raw.shape[1]):
            category = categories.get(column_index, {}).get("name", "")

            for row_index in range(header_row + 1, raw.shape[0]):
                value = self._safe_value(raw.iat[row_index, column_index])
                if not value:
                    continue

                parsed = self._parse_standard_value(value, category)
                if not parsed:
                    parsed = self._parse_standard_value(value, "")

                if not parsed:
                    continue

                rows.append({
                    **parsed,
                    "source_sheet": sheet_name,
                    "source_row": row_index + 1,
                    "source_column": f"column_{column_index + 1}",
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

            # Headers generally contain multiple different textual labels.
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

        columns = list(dataframe.columns)
        standard_candidates = self._classify_standard_columns(dataframe)
        sdo_candidates = self._classify_sdo_columns(dataframe)

        if not standard_candidates:
            return self._extract_unstructured_rows(sheet_name, dataframe)

        # Prefer a requested/input column over a located/result/reference column.
        standard_candidates.sort(key=lambda item: item.score, reverse=True)
        primary = standard_candidates[0]

        rows = []

        for offset, (_, record) in enumerate(dataframe.iterrows(), start=1):
            source_data = {
                str(key): self._safe_value(value)
                for key, value in record.to_dict().items()
                if self._safe_value(value) != ""
            }

            # Ignore rows which contain no meaningful values at all.
            if not source_data:
                continue

            standard_value = self._safe_value(record.get(primary.name))

            # Do not silently turn a reference/result column into the primary
            # request when the requested column is blank. Blank requested rows
            # are handled separately by the secondary-block detector below.
            if not standard_value:
                continue

            sdo_value = ""
            if sdo_candidates:
                sdo_value = self._safe_value(record.get(sdo_candidates[0].name))

            parsed = self._parse_standard_value(standard_value, sdo_value)
            if not parsed:
                # The row may still contain the SDO and standard in separate
                # fields or a messy text value.
                parsed = self._parse_row_text(record.tolist())

            if not parsed:
                continue

            rows.append({
                **parsed,
                "source_sheet": sheet_name,
                "source_row": offset,
                "source_column": primary.name,
                "source_data": source_data,
            })

        # Reference/result columns are deliberately NOT promoted to input
        # rows when a requested/input standard column exists. A located or
        # matched standard is evidence about the request, not another request.
        return rows

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

                # A reference/result column is weaker if another requested
                # column already has a stronger semantic score.
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

            values = [self._safe_value(v) for v in dataframe[column].tolist()]
            values = [v for v in values if v]
            if values:
                sdo_ratio = sum(
                    1 for value in values
                    if self._looks_like_sdo(value)
                ) / len(values)
                score += sdo_ratio * 10

            if score > 0:
                candidates.append(ColumnCandidate(column, score, "sdo"))

        return sorted(candidates, key=lambda item: item.score, reverse=True)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_standard_value(self, standard_value: str, sdo_value: str = ""):
        standard_value = self._clean_text(standard_value)
        sdo_value = self._clean_text(sdo_value)

        if not standard_value:
            return None

        explicit_sdo = self._normalize_sdo(sdo_value)

        # Category/SDO columns sometimes contain values such as
        # ANSI/ASHRAE 15-2024, ANSI/ASHRAE/IES 90.1-2025, or
        # ANSI/NACE MR0103. When the category already tells us the SDO,
        # strip only the publishing wrappers around that SDO.
        if explicit_sdo:
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

        embedded_sdo = self._extract_sdo(standard_value)

        # Prefer a compound SDO embedded in the value when the explicit
        # category is only its shorter parent (for example ISO + ISO/IEC).
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

        number = re.sub(
            rf"^\s*{re.escape(sdo)}(?=\d|\b)\s*[:\-]?\s*",
            "",
            standard_value,
            flags=re.IGNORECASE,
        ).strip()

        # Some inferred SDOs are compound prefixes such as BS EN or TIA/EIA.
        if not number:
            number = standard_value[len(sdo):].lstrip(" :.-")

        if not number:
            # A bare organization/family such as TEMA can still be searched.
            number = standard_value

        number = number.split(";", 1)[0].strip()

        number = re.split(
            r"\s+[—–-]\s+|\s+\|\s+|\s+DESCRIPTION\s*:",
            number,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()

        if not self._looks_like_identifier(number):
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

        # Compound publishing prefixes commonly seen in standards data.
        compound = re.match(r"^([A-Za-z]{1,6}(?:[/.-][A-Za-z]{1,8})+)\b", value)
        if compound:
            prefix = compound.group(1).upper()
            if re.search(r"\d", value[compound.end():]):
                return prefix

        # Generic unknown SDO: take leading alphabetic token(s) immediately
        # before the first numeric/identifier token. This intentionally avoids
        # requiring a hardcoded global list of standards bodies.
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
        text = " | ".join(
            self._clean_text(value)
            for value in values
            if self._clean_text(value)
        )

        if not text:
            return None

        # Search for every embedded SDO and choose the first plausible
        # identifier. This is deliberately conservative: one row becomes one
        # request unless the row is clearly a list-style row.
        matches = list(self.SDO_PATTERN.finditer(text))
        for match in matches:
            sdo = self._normalize_sdo(match.group(1))
            remainder = text[match.end():].lstrip(" :.-")
            candidate = remainder.split(" | ", 1)[0].strip()
            parsed = self._parse_standard_value(
                f"{sdo} {candidate}",
                sdo,
            )
            if parsed:
                return parsed

        return None

    # ------------------------------------------------------------------
    # Workbook selection / duplicate representations
    # ------------------------------------------------------------------

    def _select_input_sheets(self, candidates):
        """Select the workbook's primary input table(s).

        We intentionally do not concatenate every sheet. A workbook commonly
        contains a main customer list plus summaries, lookup sheets, or
        previous search results. Prefer the table with the strongest requested
        standard-column signal and then use row count as a secondary signal.
        """
        ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)
        if not ranked:
            return []
        if len(ranked) == 1:
            return ranked

        primary = ranked[0]
        primary_keys = self._row_keys(primary["rows"])

        selected = [primary]
        primary_score = primary["score"]

        for candidate in ranked[1:]:
            candidate_keys = self._row_keys(candidate["rows"])
            overlap = len(primary_keys & candidate_keys) / max(1, len(candidate_keys))

            # Do not merge a smaller duplicate/reference representation.
            if overlap >= 0.45:
                continue

            # A second genuinely independent input table can be retained when
            # it has a strong score of its own.
            if candidate["score"] >= primary_score * 0.90:
                selected.append(candidate)

        return selected

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
        # Row count is useful because duplicate summary sheets are often much
        # smaller than the real input table.
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
        value = value.replace("‑", "-").replace("–", "-").replace("—", "-")
        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def _normalize_sdo(cls, value):
        value = cls._clean_text(value).upper()
        match = cls.SDO_PATTERN.search(value)
        if match:
            return match.group(1).upper()
        # When the workbook explicitly provides an SDO column, accept unknown
        # standards bodies instead of restricting the parser to a hardcoded
        # global list.
        if re.fullmatch(r"[A-Z][A-Z0-9&./ -]{0,30}", value):
            return value
        return ""

    @classmethod
    def _extract_sdo(cls, value):
        match = cls.SDO_PATTERN.search(value)
        return match.group(1).upper() if match else ""

    @classmethod
    def _looks_like_sdo(cls, value):
        value = cls._clean_text(value).upper()
        return value in cls.KNOWN_SDOS or bool(cls.SDO_PATTERN.fullmatch(value))

    @classmethod
    def _looks_like_standard_value(cls, value):
        value = cls._clean_text(value)
        if not value:
            return False
        if cls.SDO_PATTERN.search(value):
            return True
        if re.search(r"\d", value) and cls._infer_sdo_from_identifier(value):
            return True
        # Families such as ASHRAE HANDBOOK can be meaningful standards input
        # even without a numeric designation.
        first = value.split()[0].upper() if value.split() else ""
        return first in cls.KNOWN_SDOS and len(value.split()) <= 4

    @staticmethod
    def _looks_like_identifier(value):
        value = str(value).strip()
        if not re.search(r"\d", value):
            return bool(value and len(value.split()) <= 12 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._:/+()&,-]*", value))
        # Allow compound identifiers, spaces, slashes, hyphens, colons,
        # parentheses and common edition markers.
        return bool(re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9 ./:_()&+,\-]*",
            value,
        ))
