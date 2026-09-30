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
        "parts": "PARTS",
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

    # Known SDOs are only hints. Unknown SDOs are inferred from the leading
    # alphabetic portion so the parser isn't restricted to this list.
    KNOWN_SDO_PATTERN = re.compile(
        r"^(?P<sdo>ISO(?:/IEC|/TS|/TR)?|API|ASTM|ASME|NACE|AWWA|ASHRAE|IEEE|ACI|JIS|UL|IEC|ANSI|BSI|TEMA|NFPA|SAE|DIN|CEN|CENELEC|CSA|FM(?:\s+GLOBAL)?|IGEM|IETF|AWS|AISC|ICC|IAPMO|SII|GB|KS|SANS|NORSOK|MSS|EEMUA|NAMUR|TIA/EIA|EN|BS|PD|EI|IBC)\b",
        re.IGNORECASE,
    )

    QUALIFIER_PATTERN = re.compile(
        r"(?P<label>PT\.?|PARTS?|SEC\.?|SECTION|CH\.?|CHAPTER)\s*"
        r"(?P<value>[0-9]+(?:\s*(?:-|–|—|TO|THRU|THROUGH|/)\s*[0-9]+)?)",
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
    def infer_sdo_and_body(cls, value: str, explicit_sdo: str = ""):
        value = cls.clean(value)
        explicit_sdo = cls.clean(explicit_sdo)

        if explicit_sdo:
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

        sdo, body = cls.infer_sdo_and_body(value, explicit_sdo)
        if not sdo:
            return None

        # Remove surrounding punctuation only. Internal -, ., / and : are
        # deliberately preserved.
        body = body.strip(" ()[]{}")
        if not body:
            return {"sdo_name": sdo, "base": "", "raw": value, "qualifier": None}

        qualifier_match = cls.QUALIFIER_PATTERN.search(body)
        standalone_series = None if qualifier_match else cls.STANDALONE_SERIES_PATTERN.search(body)
        qualifier = None
        qualifier_before = ""
        qualifier_after = ""
        if qualifier_match:
            label = cls._canonical_label(qualifier_match.group("label"))
            qualifier_value = qualifier_match.group("value")
            qualifier_before = body[:qualifier_match.start()].strip(" ()[]{}")
            qualifier_after = body[qualifier_match.end():].strip(" ()[]{}")
            qualifier = {
                "type": label,
                "value": qualifier_value,
                "expanded": cls._expand_qualifier(label, qualifier_value),
                "before": qualifier_before,
                "after": qualifier_after,
            }
            base = qualifier_before
        elif standalone_series:
            qualifier_before = body[:standalone_series.start()].strip(" ()[]{}")
            qualifier_after = body[standalone_series.end():].strip(" ()[]{}")
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

        base = cls.clean(base).strip("()[]{}")
        base = re.sub(r"\s{2,}", " ", base)

        # If a series/section/chapter/part marker is the only meaningful body,
        # keep it rather than rejecting the expression.
        if not base and qualifier:
            base = ""

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
            display = re.sub(r"\s+", " ", display).strip(" ()[]{}")
            output.append({
                "sdo_name": sdo,
                "displaystdno": display,
                "raw": parsed["raw"],
                "expression": parsed,
            })
        return output

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
        )
