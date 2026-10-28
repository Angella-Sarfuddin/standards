import re
from typing import Dict, List, Optional


class StandardExpressionParser:
    """Parse tolerant standards expressions without destroying identifier structure.

    This parser is deliberately independent of Excel. It can be used for text,
    CSV, PDF/Word extracted text, or a value coming from an Excel cell.
    """

    QUALIFIER_ALIASES = {
        "pt": "PT",
        "part": "PART",
        "parts": "PART",
        "ser": "SER",
        "series": "SERIES",
        "sec": "SEC",
        "section": "SECTION",
        "ch": "CH",
        "chapter": "CHAPTER",
    }

    # Words that can be part of an identifier rather than a description.
    IDENTIFIER_WORDS = {
        "STD", "SPEC", "RP", "TR", "TS", "TP", "SP", "TM", "PTC",
        "MPMS", "PRC", "M", "C", "B", "N", "Y", "PUBLICATION",
        "PUB", "NE", "PR", "PS", "SR", "STD.",
    }
    NUMBERLESS_IDENTIFIER_PATTERN = re.compile(
        r"\b(?:STD\.?|SPEC|RP|TR|TS|TP|SP|TM|PTC|MPMS|PRC|"
        r"PUBLICATION|PUB|HANDBOOK|NE|PR|PS|SR|BPVC|PT|PARTS?|SEC|SECTION|"
        r"CH|CHAPTER|SER(?:IES)?|REGLN)\b",
        re.IGNORECASE,
    )

    # Spreadsheet legend / summary lines that must never become search rows.
    NOTE_OR_LEGEND_PATTERN = re.compile(
        r"(?i)^(?:"
        r"reviewed\s+by|prepared\s+by|approved\s+by|checked\s+by|"
        r"revision\s+changes?|yellow\s+highlighted|"
        r"remarks?|notes?|legend|summary|instructions?|"
        r"refer\s+(?:the\s+)?remarks|end\s+of\s+(?:list|document|file)|"
        r"page\s+\d+|are\s+revised\b"
        r")\b"
    )
    NON_STANDARD_TEXT_PATTERN = re.compile(
        r"(?i)\b(?:webstore|subscription\s+packages?|"
        r"subscription\s+(?:start|end)\s+date|"
        r"custom\s+collections?)\b"
    )
    NAMED_STANDARD_TITLES = {
        "standards of the tubular exchanger manufacturers association": (
            "TEMA",
            "Standards",
        ),
        "tubular exchanger manufacturers association standards": (
            "TEMA",
            "Standards",
        ),
        "tema standards": ("TEMA", "Standards"),
        "standard methods for the examination of water and wastewater": (
            "AWWA",
            "Standard Methods for the Examination of Water and Wastewater",
        ),
    }
    EDITION_ONLY_PATTERN = re.compile(
        r"(?i)^(?:19|20)\d{2}\s+edition$"
    )
    NON_SDO_LABELS = {
        "QUALITY",
        "SOFT",
        "DESIGN",
        "CASTINGS-RECEIPT",
        "CASTINGS RECEIPT",
    }

    # Compact org codes that appear in the catalogue but not in KNOWN_SDO_PATTERN.
    SHORT_SDO_PATTERN = re.compile(
        r"^[A-Z]{2,12}(?:[/-][A-Z0-9]{1,12}){0,3}$"
    )

    # Known SDOs are only hints. Unknown SDOs are inferred from the leading
    # alphabetic portion so the parser isn't restricted to this list.
    KNOWN_SDO_PATTERN = re.compile(
        r"^(?P<sdo>ISO(?:/IEC|/TS|/TR)?|API|ASTM|ASME|NACE|AWWA|ASHRAE|IEEE|ACI|JIS|UL|IEC(?:/TR|/TS)?|ANSI|BSI|TEMA|NFPA|SAE|DIN|CEN|CENELEC|CSA|FM(?:\s+GLOBAL)?|IGEM|IETF|AWS|AISC|ICC|IAPMO|SII|GB|KS|SANS|NORSOK|MSS|EEMUA|NAMUR|TIA/EIA|EIA/TIA|EN|BS|PD|EI|IBC|AENOR|DANSK|CIGRE|EIA|ETS)\b",
        re.IGNORECASE,
    )

    QUALIFIER_PATTERN = re.compile(
        r"(?P<label>PT\.?|PARTS?|SEC\.?|SECTION|CH\.?|CHAPTER)\s*"
        r"(?P<value>[0-9]+(?:\.[0-9]+)?"
        r"(?:\s*(?:-|–|—|TO|THRU|THROUGH|/)\s*[0-9]+(?:\.[0-9]+)?)?)",
        re.IGNORECASE,
    )

    STANDALONE_SERIES_PATTERN = re.compile(r"\b(?P<label>SER\.?|SERIES)\b", re.IGNORECASE)

    RANGE_VALUE_PATTERN = re.compile(
        r"^(?P<start>[0-9]+)\s*(?:-|–|—|TO|THRU|THROUGH|/)\s*(?P<end>[0-9]+)$",
        re.IGNORECASE,
    )

    @staticmethod
    def clean(value) -> str:
        if value is None:
            return ""
        value = str(value)
        value = value.replace("\u2010", "-").replace("\u2011", "-")
        value = value.replace("\u2012", "-").replace("\u2013", "-")
        value = value.replace("\u2014", "-").replace("\u2212", "-")
        value = value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        value = re.sub(r"\s+", " ", value)
        return value.strip()

    @classmethod
    def _strip_outer_brackets(cls, value: str) -> str:
        text = cls.clean(value)
        matching_open = {")": "(", "]": "[", "}": "{"}
        matching_close = {"(": ")", "[": "]", "{": "}"}

        while (
            len(text) >= 2
            and text[0] in matching_close
            and text[-1] == matching_close[text[0]]
        ):
            stack = []
            encloses_all = True
            for index, char in enumerate(text):
                if char in matching_close:
                    stack.append(char)
                elif char in matching_open:
                    if not stack or stack.pop() != matching_open[char]:
                        encloses_all = False
                        break
                    if not stack and index != len(text) - 1:
                        encloses_all = False
                        break
            if not encloses_all or stack:
                break
            text = text[1:-1].strip()

        return text

    @classmethod
    def is_note_or_legend(cls, value: str) -> bool:
        """True for spreadsheet notes / legends, not standard designations."""
        text = cls.clean(value)
        if not text:
            return False
        return bool(cls.NOTE_OR_LEGEND_PATTERN.match(text))

    @classmethod
    def is_plausible_sdo(cls, sdo: str) -> bool:
        """Accept real publishing bodies; reject multi-word spreadsheet labels."""
        sdo = cls.clean(sdo).upper()
        if (
            not sdo
            or cls.is_note_or_legend(sdo)
            or sdo in cls.NON_SDO_LABELS
        ):
            return False
        known = cls.KNOWN_SDO_PATTERN.match(sdo)
        if known and not sdo[known.end():].strip():
            return True
        if sdo in {"FM GLOBAL", "AMPP-NACE", "AMPP-SSPC", "AMPP NACE", "AMPP SSPC"}:
            return True
        if re.fullmatch(r"(?:DANSK\s+DS(?:/|\s)EN|AENOR\s+UNE(?:-|\s)?EN|UNE(?:-|\s)?EN)", sdo, re.IGNORECASE):
            return True
        # Unknown short codes such as MSS, ASNT, HI, TIA.
        return bool(cls.SHORT_SDO_PATTERN.fullmatch(sdo))

    @classmethod
    def is_plausible_standard_body(cls, body: str) -> bool:
        """Reject prose / person names that are not catalogue designations."""
        body = cls.clean(body).strip(" :.-")
        if (
            not body
            or cls.is_note_or_legend(body)
            or cls.NON_STANDARD_TEXT_PATTERN.search(body)
            or cls.EDITION_ONLY_PATTERN.fullmatch(body)
        ):
            return False
        if re.search(r"\d", body):
            return bool(
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ./:_()&+,\-]*", body)
            )
        # Digitless designations need an explicit marker (BPVC, SECTION, SP…).
        return bool(
            len(body.split()) <= 12
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._:/+()&,-]*", body)
            and cls.NUMBERLESS_IDENTIFIER_PATTERN.search(body)
        )

    @classmethod
    def named_standard_title(cls, value: str):
        normalized = re.sub(
            r"[^a-z0-9]+",
            " ",
            cls.clean(value).casefold(),
        ).strip()
        result = cls.NAMED_STANDARD_TITLES.get(normalized)
        if not result:
            return None
        sdo, body = result
        return {"sdo_name": sdo, "displaystdno": body}

    @classmethod
    def is_plausible_standard_request(cls, sdo: str, body: str) -> bool:
        normalized_sdo = cls.clean(sdo).upper()
        normalized_body = re.sub(
            r"[^a-z0-9]+",
            " ",
            cls.clean(body).casefold(),
        ).strip()
        named_titles = {
            (
                title_sdo,
                re.sub(r"[^a-z0-9]+", " ", title_body.casefold()).strip(),
            )
            for title_sdo, title_body in cls.NAMED_STANDARD_TITLES.values()
        }
        return cls.is_plausible_standard_body(body) or (
            normalized_sdo,
            normalized_body,
        ) in named_titles

    @classmethod
    def infer_sdo_and_body(cls, value: str, explicit_sdo: str = ""):
        value = cls.clean(value)
        explicit_sdo = cls.clean(explicit_sdo)

        named_title = cls.named_standard_title(value)
        if named_title:
            return named_title["sdo_name"], named_title["displaystdno"]

        if explicit_sdo:
            if not cls.is_plausible_sdo(explicit_sdo):
                return "", value
            sdo = explicit_sdo.upper()
            body = re.sub(
                rf"^\s*{re.escape(explicit_sdo)}\b\s*[:.-]?\s*",
                "",
                value,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            # If the cell itself begins with a compound SDO, don't strip a
            # longer SDO down to a shorter category accidentally.
            if not body and value:
                body = value
            return sdo, body

        if cls.is_note_or_legend(value):
            return "", value

        # ANSI/HI is the Hydraulic Institute publication prefix. Treat it as
        # HI so searches resolve against the HI catalogue instead of ANSI's
        # stale mirrored records.
        hydraulic_institute = re.match(
            r"(?i)^ANSI\s*(?:/|\s)\s*HI(?=$|[\s:.-])",
            value,
        )
        if hydraulic_institute:
            body = value[hydraulic_institute.end():].lstrip(" :.-")
            return "HI", body

        for pattern, sdo in (
            (r"^UNI\s+EN\b", "UNI"),
            (r"^(?:DANSK\s+DS(?:/|\s)EN)\b", "DANSK DS/EN"),
            (r"^(?:AENOR\s+UNE(?:-|\s)?EN)\b", "AENOR"),
            (r"^(?:UNE(?:-|\s)?EN)\b", "AENOR"),
            (r"^(?:DS(?:/|\s)EN)\b", "DANSK DS/EN"),
        ):
            if re.match(pattern, value, flags=re.IGNORECASE):
                body = re.sub(pattern, "", value, flags=re.IGNORECASE).strip(" :.-")
                return sdo, body

        match = cls.KNOWN_SDO_PATTERN.match(value)
        if match:
            sdo = cls.clean(match.group("sdo")).upper()
            body = value[match.end():].lstrip(" :.-")
            return sdo, body

        # Generic SDO inference: consume leading alphabetic tokens until the
        # first token that contains a digit. This handles NORSOK M-001,
        # EEMUA Publication 182, MSS SP-44, etc.
        tokens = value.split()
        prefix = []
        for token in tokens:
            stripped = token.strip("()[],:;")
            if not stripped:
                continue
            if re.search(r"\d", stripped):
                break
            if re.fullmatch(r"[A-Za-z][A-Za-z&./-]*", stripped):
                prefix.append(stripped)
                if len(prefix) >= 2:
                    # Stop after a second leading organization word unless it
                    # is an obvious compound such as TIA/EIA.
                    break
            else:
                break

        if not prefix:
            return "", value

        sdo = " ".join(prefix).upper()
        if not cls.is_plausible_sdo(sdo):
            return "", value
        body = value
        for token in prefix:
            body = re.sub(rf"^\s*{re.escape(token)}\b\s*", "", body, count=1, flags=re.IGNORECASE)
        return sdo, body.strip(" :.-")

    @classmethod
    def _canonical_label(cls, label: str) -> str:
        label = label.upper().replace(".", "")
        return cls.QUALIFIER_ALIASES.get(label.lower(), label)

    @classmethod
    def _expand_qualifier(cls, label: str, value: str):
        label = cls._canonical_label(label)
        value = cls.clean(value)
        range_match = cls.RANGE_VALUE_PATTERN.fullmatch(value)

        if range_match:
            start = int(range_match.group("start"))
            end = int(range_match.group("end"))
            if start <= end and end - start <= 1000:
                return [f"{label} {n}" for n in range(start, end + 1)]

        return [f"{label} {value}"]

    @classmethod
    def parse(cls, value: str, explicit_sdo: str = "") -> Optional[Dict]:
        value = cls.clean(value)
        if not value:
            return None

        named_title = cls.named_standard_title(value)
        if named_title:
            return {
                "sdo_name": named_title["sdo_name"],
                "base": named_title["displaystdno"],
                "raw": value,
                "qualifier": None,
            }

        sdo, body = cls.infer_sdo_and_body(value, explicit_sdo)
        if not sdo:
            return None

        # Remove surrounding punctuation only. Internal -, ., / and : are
        # deliberately preserved.
        body = cls._strip_outer_brackets(body)
        if not body:
            return {"sdo_name": sdo, "base": "", "raw": value, "qualifier": None}

        body = re.sub(
            r"(?i)\s*\+F\d+\s*:\s*F\d+\b.*$",
            "",
            body,
        ).strip()
        body = re.sub(
            r"(?i)\b(PARTS?)\s+(\d+)\s*&\s*(\d+)\b",
            r"\1 \2-\3",
            body,
        )
        body = re.sub(
            r"(?i)\s+with\s+subsections\b.*$",
            "",
            body,
        ).strip()
        body = re.sub(
            r"(?i)\s*\(?\s*total\s*[-:]\s*\d+\s*codes?\s*\)?\s*$",
            "",
            body,
        ).strip()
        body = re.sub(
            r"(?i)\s*\(?\s*total\s*$",
            "",
            body,
        ).strip()

        qualifier_match = cls.QUALIFIER_PATTERN.search(body)
        standalone_series = None if qualifier_match else cls.STANDALONE_SERIES_PATTERN.search(body)
        qualifier = None
        qualifier_before = ""
        qualifier_after = ""
        if qualifier_match:
            label = cls._canonical_label(qualifier_match.group("label"))
            qualifier_value = qualifier_match.group("value")
            qualifier_before = cls._strip_outer_brackets(
                body[:qualifier_match.start()]
            ).rstrip("([{").strip()
            qualifier_after = cls._strip_outer_brackets(
                body[qualifier_match.end():]
            ).lstrip(")]}").strip()
            qualifier = {
                "type": label,
                "value": qualifier_value,
                "expanded": cls._expand_qualifier(label, qualifier_value),
                "before": qualifier_before,
                "after": qualifier_after,
            }
            base = qualifier_before
        elif standalone_series:
            qualifier_before = cls._strip_outer_brackets(
                body[:standalone_series.start()]
            )
            qualifier_after = cls._strip_outer_brackets(
                body[standalone_series.end():]
            )
            qualifier = {
                "type": "SERIES",
                "value": "",
                "expanded": ["SERIES"],
                "before": qualifier_before,
                "after": qualifier_after,
            }
            base = qualifier_before
        else:
            base = body

        base = cls._strip_outer_brackets(base)
        base = re.sub(r"\s{2,}", " ", base)

        # If a series/section/chapter/part marker is the only meaningful body,
        # keep it rather than rejecting the expression.
        if not base and qualifier:
            base = ""

        if base and not cls.is_plausible_standard_request(sdo, base):
            return None

        return {
            "sdo_name": sdo,
            "base": base,
            "raw": value,
            "qualifier": qualifier,
        }

    @classmethod
    def expand(cls, value: str, explicit_sdo: str = "") -> List[Dict]:
        parsed = cls.parse(value, explicit_sdo)
        if not parsed:
            return []

        qualifier = parsed.get("qualifier")
        sdo = parsed["sdo_name"]
        base = parsed["base"]

        if not qualifier:
            return [{
                "sdo_name": sdo,
                "displaystdno": base or value,
                "raw": parsed["raw"],
                "expression": parsed,
            }]

        expanded = qualifier.get("expanded") or []
        if not expanded:
            return [{
                "sdo_name": sdo,
                "displaystdno": base or parsed["raw"],
                "raw": parsed["raw"],
                "expression": parsed,
            }]

        before = qualifier.get("before") or base
        after = qualifier.get("after") or ""
        output = []
        for part in expanded:
            display = " ".join(x for x in [before, part] if x).strip()
            if after:
                # Preserve compound references such as API 579 PT 1/ASME FFS-1.
                display = f"{display}/{after.lstrip('/')}"
            display = cls._strip_outer_brackets(
                re.sub(r"\s+", " ", display)
            )
            output.append({
                "sdo_name": sdo,
                "displaystdno": display,
                "raw": parsed["raw"],
                "expression": parsed,
            })
        return output

    @classmethod
    def designation_cell(cls, cell: str) -> List[Dict]:
        """One table cell that is already a document number, not a sentence.

        Free-text extraction still requires a digit so descriptions are not
        treated as standards. A number column is trusted: roman sections,
        glued codes such as ``IS1337``, and codes without a digit are kept.
        """
        found = cls.extract_from_line(cell)
        if found:
            return found

        cell = cls.clean(cell)
        if not cell:
            return []

        spaced = re.match(
            r"^(?P<sdo>[A-Z][A-Z0-9]*(?:[/-][A-Z0-9]+)*)\s+(?P<number>.+)$",
            cell,
            re.IGNORECASE,
        )
        glued = re.match(
            r"^(?P<sdo>[A-Z]{2,})(?P<number>\d.*)$",
            cell,
            re.IGNORECASE,
        )
        hyphen = re.match(
            r"^(?P<sdo>.+)-(?P<number>\d.*)$",
            cell,
            re.IGNORECASE,
        )
        match = spaced or glued or hyphen
        if not match:
            return []
        number = match.group("number").strip(" -/")
        if not number:
            return []
        if (
            not re.search(r"\d", number)
            and not cls.NUMBERLESS_IDENTIFIER_PATTERN.search(number)
        ):
            return []
        return [{
            "sdo_name": match.group("sdo").upper(),
            "displaystdno": number,
        }]

    @classmethod
    def extract_from_line(cls, line: str) -> List[Dict]:
        """Extract standards from one free-text line.

        If multiple SDO-led expressions are present, each is considered. This
        is useful for TXT/PDF/Word extraction where there is no reliable table.
        """
        line = cls.clean(line)
        if not line:
            return []

        # First try the whole line. This handles compound expressions such as
        # API 579 PT 1/ASME FFS-1 without splitting them at '/'.
        whole = cls.expand(line)
        if whole and cls._looks_plausible(whole):
            return whole

        matches = list(re.finditer(
            r"(?<![A-Za-z0-9])(?:ISO(?:/IEC|/TS|/TR)?|API|ASTM|ASME|NACE|AWWA|ASHRAE|IEEE|ACI|JIS|UL|IEC|ANSI|BSI|TEMA|NFPA|SAE|DIN|CEN|CENELEC|CSA|FM|IGEM|IETF|AWS|AISC|ICC|IAPMO|SII|GB|KS|SANS|NORSOK|MSS|EEMUA|NAMUR|TIA/EIA|EN|BS|PD|EI|IBC)(?![A-Za-z0-9])",
            line,
            re.IGNORECASE,
        ))

        results = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            candidate = line[match.start():end].strip(" |,;")
            expanded = cls.expand(candidate)
            for row in expanded:
                if cls._looks_plausible([row]):
                    results.append(row)
        return results

    @staticmethod
    def _looks_plausible(rows) -> bool:
        if not rows:
            return False
        row = rows[0]
        sdo = row.get("sdo_name", "")
        number = row.get("displaystdno", "")
        if not sdo:
            return False
        # Allow family/series expressions without digits, but avoid treating
        # arbitrary prose beginning with a known organization as a standard.
        return bool(number) and (
            bool(re.search(r"\d", number))
            or bool(re.search(r"\b(?:SER|SERIES|HANDBOOK|PUBLICATION)\b", number, re.I))
            or (
                sdo.upper() == "TEMA"
                and number.casefold() == "standards"
            )
        )
