import re


class StandardExtractor:

    # Known SDOs. Longer/more specific forms must come first.
    KNOWN_SDOS = [
        "ISO/IEC",
        "ISO/TS",
        "ISO/TR",
        "ISO",
        "API",
        "ASTM",
        "ASME",
        "NACE",
        "AWWA",
        "ASHRAE",
        "IEEE",
        "ACI",
        "JIS",
        "UL",
        "IEC",
        "ANSI",
        "BSI",
        "TEMA",
    ]

    SDO_PATTERN = re.compile(
        r"^(ISO/IEC|ISO/TS|ISO/TR|ISO|API|ASTM|ASME|NACE|AWWA|ASHRAE|IEEE|ACI|JIS|UL|IEC|ANSI|BSI|TEMA)\b",
        re.IGNORECASE,
    )

    SDO_SEARCH_PATTERN = re.compile(
        r"\b(ISO/IEC|ISO/TS|ISO/TR|ISO|API|ASTM|ASME|NACE|AWWA|ASHRAE|IEEE|ACI|JIS|UL|IEC|ANSI|BSI|TEMA)\b",
        re.IGNORECASE,
    )

    # Words that commonly mark the beginning of a description.
    DESCRIPTION_WORDS = {
        "SPECIFICATION",
        "SPECIFICATIONS",
        "STANDARD",
        "STANDARDS",
        "RECOMMENDED",
        "PRACTICE",
        "RECOMMENDED PRACTICE",
        "DESIGN",
        "GUIDE",
        "GUIDELINE",
        "CODE",
        "REQUIREMENTS",
        "TEST",
        "TESTS",
        "PERFORMANCE",
        "MEASUREMENT",
        "MEASUREMENTS",
        "METHOD",
        "METHODS",
        "INSTALLATION",
        "CONTROL",
        "EVALUATION",
        "DESIGNATION",
        "SAFETY",
        "BUILDING",
        "VENTILATION",
        "TUBULAR",
        "FLANGES",
        "PIPE",
        "PIPES",
        "FIBERGLASS",
        "INDUSTRIAL",
        "ELECTRICAL",
        "ELECTRIC",
        "TEMPERATURE",
        "CORROSION",
        "MACHINERY",
        "AIR-COOLED",
        "AIR",
        "LINE",
        "GAS",
        "STEEL",
        "WELDED",
        "OIL",
        "LIQUID",
        "NICKEL-CADMIUM",
        "HVAC",
        "HANDBOOK",
        "EDITION",
        "NOT",
        "AVAILABLE",
        "NAN",
    }

    # Prefixes that are part of a standard identifier.
    SPECIAL_PREFIXES = {
        "API": {
            "RP",
            "TR",
            "MPMS",
            "STD",
            "SPEC",
        },
        "ASME": {
            "PTC",
            "B",
            "N",
            "Y",
            "A",
        },
        "NACE": {
            "RP",
            "SP",
            "TM",
        },
        "ACI": {
            "PRC",
            "SP",
        },
        "IEC": set(),
        "IEEE": set(),
        "ISO": set(),
        "UL": {
            "STD",
        },
        "AWWA": {
            "C",
            "M",
        },
        "ASHRAE": set(),
        "JIS": set(),
        "ASTM": set(),
        "TEMA": set(),
        "ANSI": set(),
        "BSI": set(),
    }

    @classmethod
    def normalize_sdo(cls, value):

        if not value:
            return ""

        value = str(value).strip()

        match = cls.SDO_PATTERN.match(value)

        if match:
            return match.group(1).upper()

        return value.upper()

    @classmethod
    def remove_sdo_prefix(cls, value, sdo_name):

        if not value:
            return ""

        value = str(value).strip()

        if not sdo_name:
            return value

        return re.sub(
            rf"^{re.escape(sdo_name)}\b\s*",
            "",
            value,
            count=1,
            flags=re.IGNORECASE,
        ).strip()

    @classmethod
    def clean_text(cls, value):

        if not value:
            return ""

        value = str(value)

        value = value.replace("\n", " ")
        value = value.replace("\r", " ")
        value = re.sub(r"\s+", " ", value)

        return value.strip()

    @classmethod
    def looks_like_number(cls, token):

        if not token:
            return False

        token = token.strip()

        # Must contain at least one digit.
        if not re.search(r"\d", token):
            return False

        # Standard number characters.
        return bool(
            re.fullmatch(
                r"[A-Z0-9]+(?:[-./:][A-Z0-9]+)*",
                token,
                re.IGNORECASE,
            )
        )

    @classmethod
    def is_year(cls, token):

        if not token:
            return False

        return bool(
            re.fullmatch(
                r"(19|20)\d{2}",
                token.strip(),
            )
        )

    @classmethod
    def is_description_start(cls, token):

        if not token:
            return False

        token_upper = token.upper().strip()

        return token_upper in cls.DESCRIPTION_WORDS

    @classmethod
    def extract_identifier_after_sdo(
        cls,
        text,
        sdo_name,
    ):

        text = cls.clean_text(text)

        if not text:
            return None

        # Remove the SDO if it is already included in the text.
        remainder = cls.remove_sdo_prefix(
            text,
            sdo_name,
        )

        if not remainder:
            return None

        # Remove punctuation around the beginning.
        remainder = remainder.lstrip(" :-")

        if not remainder:
            return None

        tokens = remainder.split()

        if not tokens:
            return None

        identifier_parts = []

        first_token = tokens[0].strip(",:;")

        # -------------------------------------------------
        # CASE 1:
        # API RP 12J
        # API MPMS 5.6
        # NACE SP0169
        # -------------------------------------------------

        if first_token.upper() in cls.SPECIAL_PREFIXES.get(
            sdo_name,
            set(),
        ):

            identifier_parts.append(
                first_token
            )

            if len(tokens) < 2:
                return None

            second_token = tokens[1].strip(
                " ,:;"
            )

            if not cls.looks_like_number(
                second_token
            ):
                return None

            identifier_parts.append(
                second_token
            )

        # -------------------------------------------------
        # CASE 2:
        # ASME PTC 10
        # -------------------------------------------------

        elif (
            sdo_name == "ASME"
            and first_token.upper() in {"PTC"}
        ):

            identifier_parts.append(
                first_token
            )

            if len(tokens) < 2:
                return None

            second_token = tokens[1].strip(
                " ,:;"
            )

            if not cls.looks_like_number(
                second_token
            ):
                return None

            identifier_parts.append(
                second_token
            )

        # -------------------------------------------------
        # CASE 3:
        # JIS K 0555
        # -------------------------------------------------

        elif (
            sdo_name == "JIS"
            and re.fullmatch(
                r"[A-Z]",
                first_token,
                re.IGNORECASE,
            )
        ):

            identifier_parts.append(
                first_token
            )

            if len(tokens) < 2:
                return None

            second_token = tokens[1].strip(
                " ,:;"
            )

            if not cls.looks_like_number(
                second_token
            ):
                return None

            identifier_parts.append(
                second_token
            )

        # -------------------------------------------------
        # CASE 4:
        # Normal identifiers
        #
        # API 620
        # ISO 15848-1
        # IEC 61158
        # IEEE 1115
        # ACI 318
        # -------------------------------------------------

        else:

            if not cls.looks_like_number(
                first_token
            ):
                return None

            identifier_parts.append(
                first_token
            )

        return " ".join(
            identifier_parts
        )

    @classmethod
    def parse_standard_text(cls, text):

        text = cls.clean_text(text)

        if not text:
            return None

        sdo_name = cls.extract_sdo_from_text(
            text
        )

        if not sdo_name:
            return None

        standard_number = (
            cls.extract_identifier_after_sdo(
                text,
                sdo_name,
            )
        )

        if not standard_number:
            return None

        return {
            "sdo_name": sdo_name,
            "displaystdno": standard_number,
        }

    @classmethod
    def extract_sdo_from_text(cls, text):

        if not text:
            return None

        text = cls.clean_text(text)

        match = cls.SDO_PATTERN.match(
            text
        )

        if not match:
            return None

        return cls.normalize_sdo(
            match.group(1)
        )

    def extract_from_text(self, text):

        if not text:
            return []

        text = self.clean_text(text)

        if not text:
            return []

        results = []

        # -------------------------------------------------
        # First try the complete text as one standard.
        # -------------------------------------------------

        parsed = self.parse_standard_text(
            text
        )

        if parsed:
            results.append(parsed)
            return self.remove_duplicates(
                results
            )

        # -------------------------------------------------
        # If the text contains multiple standards,
        # locate each SDO and parse the following text.
        # -------------------------------------------------

        matches = list(
            self.SDO_SEARCH_PATTERN.finditer(
                text
            )
        )

        for index, match in enumerate(matches):

            sdo_name = self.normalize_sdo(
                match.group(1)
            )

            start = match.start()

            if index + 1 < len(matches):
                end = matches[index + 1].start()
            else:
                end = len(text)

            candidate = text[
                start:end
            ].strip()

            parsed = self.parse_standard_text(
                candidate
            )

            if parsed:
                results.append(parsed)

        return self.remove_duplicates(
            results
        )

    def extract_from_rows(self, rows):

        if not rows:
            return []

        results = []

        for row in rows:

            # Normalize column names.
            normalized_row = {
                str(key).strip().lower(): value
                for key, value in row.items()
            }

            # -------------------------------------------------
            # STRUCTURED FORMAT
            #
            # Example:
            #
            # sdo name     displaystdno
            # ISO          22391-1:2009
            #
            # Because the spreadsheet explicitly separates
            # SDO and standard number, do not run the standard
            # number through the free-text parser.
            # -------------------------------------------------

            sdo_value = normalized_row.get(
                "sdo name",
                "",
            )

            display_value = normalized_row.get(
                "displaystdno",
                "",
            )

            sdo_name = (
                ""
                if sdo_value is None
                else str(sdo_value).strip()
            )

            displaystdno = (
                ""
                if display_value is None
                else str(display_value).strip()
            )

            # Handle pandas NaN values.
            if sdo_name.upper() in {
                "NAN",
                "NONE",
            }:
                sdo_name = ""

            if displaystdno.upper() in {
                "NAN",
                "NONE",
            }:
                displaystdno = ""

            if sdo_name and displaystdno:

                normalized_sdo = self.normalize_sdo(
                    sdo_name
                )

                # Remove SDO only when it is actually
                # present at the beginning of the value.
                cleaned_standard = (
                    self.remove_sdo_prefix(
                        displaystdno,
                        normalized_sdo,
                    )
                )

                cleaned_standard = (
                    self.clean_text(
                        cleaned_standard
                    )
                )

                # -------------------------------------------------
                # IMPORTANT:
                #
                # This is already a dedicated standard-number
                # column, so preserve the complete value.
                #
                # Examples:
                # 22391-1:2009
                # TR 10929:2012
                # IEC TR 24763:2011
                # 3747:2010
                #
                # Do not use extract_identifier_after_sdo()
                # here because that function is intended for
                # free-text parsing.
                # -------------------------------------------------

                if cleaned_standard:

                    results.append({
                        "sdo_name": normalized_sdo,
                        "displaystdno": cleaned_standard,
                    })

                continue

            # -------------------------------------------------
            # OTHER COMMON COLUMN NAMES
            # -------------------------------------------------

            possible_sdo_columns = [
                "sdo",
                "sdo_name",
                "standard body",
                "standard body name",
                "standardbody",
                "organization",
                "organisation",
            ]

            possible_standard_columns = [
                "standard",
                "standard no",
                "standard number",
                "standard_no",
                "standardno",
                "standards",
                "located standards",
                "located standard",
                "code",
            ]

            detected_sdo = ""

            for column in possible_sdo_columns:

                value = normalized_row.get(
                    column
                )

                if value is not None:

                    value = str(
                        value
                    ).strip()

                    if value:
                        detected_sdo = value
                        break

            detected_standard = ""

            for column in possible_standard_columns:

                value = normalized_row.get(
                    column
                )

                if value is not None:

                    value = str(
                        value
                    ).strip()

                    if value:
                        detected_standard = value
                        break

            if (
                detected_sdo
                and detected_standard
            ):

                normalized_sdo = (
                    self.normalize_sdo(
                        detected_sdo
                    )
                )

                cleaned_standard = (
                    self.remove_sdo_prefix(
                        detected_standard,
                        normalized_sdo,
                    )
                )

                identifier = (
                    self.extract_identifier_after_sdo(
                        cleaned_standard,
                        normalized_sdo,
                    )
                )

                if identifier:

                    results.append({
                        "sdo_name": normalized_sdo,
                        "displaystdno": identifier,
                    })

                continue

            # -------------------------------------------------
            # FALLBACK
            # -------------------------------------------------

            row_text = " ".join(
                str(value)
                for value in row.values()
                if value is not None
                and str(value).strip()
            )

            extracted = (
                self.extract_from_text(
                    row_text
                )
            )

            results.extend(
                extracted
            )

        return self.remove_duplicates(
            results
        )

    @staticmethod
    def remove_duplicates(results):

        unique = []
        seen = set()

        for result in results:

            sdo_name = str(
                result.get(
                    "sdo_name",
                    "",
                )
            ).strip()

            displaystdno = str(
                result.get(
                    "displaystdno",
                    "",
                )
            ).strip()

            if (
                not sdo_name
                or not displaystdno
            ):
                continue

            key = (
                sdo_name.upper(),
                displaystdno.upper(),
            )

            if key not in seen:

                seen.add(key)

                unique.append({
                    "sdo_name": sdo_name,
                    "displaystdno": displaystdno,
                })

        return unique