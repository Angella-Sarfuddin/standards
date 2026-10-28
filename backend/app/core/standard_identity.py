import re
from typing import Dict, List, Optional, Tuple


YEAR_RE = re.compile(r"(?:^|[\s:()\[\]{},./-])((?:19|20)\d{2})\s*$")
REAFFIRMATION_MARKER = (
    r"(?:R"
    r"|REAFFIRMED(?:\s+(?:YEAR|IN))?"
    r"|REAFFIRMATION(?:\s+YEAR)?"
    r"|REAFF(?:IRM(?:ED|ATION)?)?"
    r"|REFF(?:IRM(?:ED|ATION)?)?"
    r"|REVIEWED(?:\s+AND\s+(?:CONFIRMED|REAFFIRMED))?(?:\s+IN)?"
    r"|CONFIRMED(?:\s+IN)?)"
)
REAFFIRMATION_RE = re.compile(
    # Require a token boundary before the marker: otherwise the bare ``R``
    # shorthand can match the final letter in month names such as ``Mar 1988``.
    rf"(?<![A-Z])\s*(?:\(|\[|,|;)?\s*{REAFFIRMATION_MARKER}"
    r"\s*[:=\-]?\s*((?:19|20)\d{2})\s*(?:\)|\])?\s*$",
    re.IGNORECASE,
)
WITHDRAWAL_RE = re.compile(
    r"(?:\s*/\s*|\s*\(\s*|\s*[-–—]\s*)(?:WITHDRAWN|WTHDRAWN|OBSOLETE|SUPERSEDED)\b.*$",
    re.IGNORECASE,
)
TRAILING_NOTE_RE = re.compile(
    r"(?i)(?:\s+replaced\b.*$"
    r"|\s*\([^)]*(?:edition|book)[^)]*\)\s*$"
    r"|\s+with subsections.*$)"
)


STATED_REPLACEMENT_RE = re.compile(
    r"(?i)^(?P<original>.+?)"
    r"(?:\s+|\s*[-–—/]\s*|\s*\(\s*)"
    r"(?:withdrawn|wthdrawn)"
    r"\)?\s+and\s+replaced(?:\s+by)?\s+"
    r"(?P<replacement>.+?)\s*$"
)


def split_stated_replacement(value: str) -> Optional[Dict]:
    """Read "X withdrawn and replaced Y" as a search for Y.

    The status may be separated by a space, hyphen, slash, or parenthesis,
    as in "6.6-WITHDRAWN and replaced by ...".
    """
    match = STATED_REPLACEMENT_RE.match(clean(value))
    if not match:
        return None
    original = match.group("original").strip(" :,-/")
    replacement = match.group("replacement").strip(" :,-/")
    if not original or not replacement:
        return None
    return {"original": original, "replacement": replacement}


def _prepare_printed_designation(display: str) -> str:
    """Drop title prose and BIS print marks that hide the designation."""
    display = re.sub(
        r"(?i)\s*:\s*indian\s+standards?\s*$",
        "",
        display,
    ).strip()
    display = re.sub(
        r"(?i)\s*[\(\[]\s*(?:reaffirmed|reaffirmation|reviewed|confirmed)"
        r"(?:\s+(?:in|year))?\s*[:=\-]?\s*(?:19|20)\d{2}\s*[\)\]]",
        "",
        display,
    ).strip()
    # BIS prints the edition as "PART 2/-1989".
    display = re.sub(
        r"(?i)(?<=\d)\s*/\s*-\s*((?:19|20)\d{2})\b",
        r" : \1",
        display,
    )
    return display.strip(" :,-/")


def reaffirmation_year(value: str) -> Optional[int]:
    """Return a standard's reaffirmation/review year without treating it as edition year."""
    match = REAFFIRMATION_RE.search(clean(value))
    return int(match.group(1)) if match else None
# Excel label -> (identity SDO used for parsing, catalogue title used for sdo_id).
SDO_LOOKUP_ALIASES = {
    "GPA": ("GLOBAL", "GLOBAL"),
    "AMS": ("SAE", "SAE"),
    "BULL": ("API", "API"),
    "BUL": ("API", "API"),
    "PUBL": ("API", "API"),
    "PUB": ("API", "API"),
    "RP": ("API", "API"),
    "SPEC": ("API", "API"),
    "STD": ("API", "API"),
    "PCC": ("ASME", "ASME"),
    "MR": ("NACE", "AMPP-NACE"),
    "HM": ("EI", "EI"),
    "DIS": ("ISO", "ISO"),
    "NZS": ("AS", "AS"),
    "EN": ("BSI", "BSI"),
    "IP": ("EI", "EI"),
    "SSPC-SP": ("SSPC", "AMPP-SSPC"),
    "DIRECTIVE": ("EEC", "GLOBAL"),
    "ATEX": ("EEC", "GLOBAL"),
    "ISO/IEC": ("IEC", "IEC"),
    "NORSOK": ("NORSOK", "GLOBAL"),
    "ANSI/ASNT-CP": ("ASNT", "ASNT"),
    "ANSI/FCI": ("ANSI", "ANSI"),
    "ISPM": ("ISPM", "GLOBAL"),
    "MSS SP": ("MSS", "MSS"),
    "MSS-SP": ("MSS", "MSS"),
    "SNT-TC": ("ASNT", "ASNT"),
    "SNT TC": ("ASNT", "ASNT"),
    "SSPC": ("SSPC", "AMPP-SSPC"),
    "NACE": ("NACE", "AMPP-NACE"),
    "DANSK DS/EN": ("BSI", "BSI"),
    "DANSK DS EN": ("BSI", "BSI"),
    "DS/EN": ("BSI", "BSI"),
    "DS EN": ("BSI", "BSI"),
    "UNE-EN": ("BSI", "BSI"),
    "UNE EN": ("BSI", "BSI"),
    "UNI": ("BSI", "BSI"),
    "UNI EN": ("BSI", "BSI"),
    "EEC": ("EEC", "GLOBAL"),
}
LANGUAGE_SUFFIX_RE = re.compile(
    r"\s*(?:/\s*EN\s*[-/]\s*FR|\(\s*EN\s*[-/]\s*FR\s*\))\s*$",
    re.IGNORECASE,
)
CORRIGENDUM_RE = re.compile(
    r"(?:/|\s+)(?:COR(?:R)?(?:IGENDUM)?)\.?\s*:?\s*\d+"
    r"(?:\s*:\s*(?:19|20)\d{2})?\s*$",
    re.IGNORECASE,
)
SERIES_SUFFIX_RE = re.compile(
    r"\s+SER(?:IES)?\s*$",
    re.IGNORECASE,
)
VOLUME_SUFFIX_RE = re.compile(
    r"\s*[- ]VOL(?:UME)?\.?\s*[IVX0-9]+"
    r"(?:\s*&\s*VOL(?:UME)?\.?\s*[IVX0-9]+)*\s*$",
    re.IGNORECASE,
)
MONTH_NUMBER = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
EXCEL_DATE_COMPONENT_RE = re.compile(
    r"(?i)(?P<day>\d{1,2})-(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b"
)

# These are designation/type markers that may appear between an SDO and the
# actual standard number. They are deliberately explicit: we do NOT strip
# arbitrary alphabetic tokens because many standards legitimately begin with
# letter-number identifiers such as C950, NACE MR0175, EN 1090, etc.
DESIGNATION_TOKENS = {
    "STD",
    "STANDARD",
    "RP",
    "RECOMMENDED PRACTICE",
    "SPEC",
    "SPECIFICATION",
    "SP",
    "SPECIAL PUBLICATION",
    "TR",
    "TECHNICAL REPORT",
    "DIS",
    "MPMS",
    "BUL",
    "BULL",
    "PUBL",
    "BULLETIN",
    "PUB",
    "PUBLICATION",
    "GUIDE",
}

SDO_IDENTIFIER_PREFIX_ALIASES = {
    "ISO": ("ISO/IEC", "ISO/TS", "ISO/TR"),
    "BSI": (
        "BS",
        "BS EN",
        "BS EN ISO",
        "BS EN ISO/IEC",
        "EN",
        "PD",
        "PD CEN",
        "PD CEN/TR",
        "ISO/IEC",
    ),
    "IEC": ("ISO/IEC", "ISO/TS", "ISO/TR"),
    "DIN": (
        "DIN EN IEC",
        "DIN EN ISO/IEC",
        "DIN EN ISO",
        "DIN IEC",
        "DIN EN",
        "IEC",
    ),
    "BIS": (
        "BIS IS/IEC/IEEE",
        "BIS IS IEC IEEE",
        "BIS IS/IEC",
        "BIS IS IEC",
        "BIS IEC",
        "IS/IEC/IEEE",
        "IS IEC IEEE",
        "IS/IEC",
        "IS IEC",
        "IS",
        "BIS",
    ),
    "IS": ("IS", "BIS"),
    "SSPC": ("SSPC", "SSPC-SP"),
    "NACE": ("NACE",),
    "HI": ("HI", "ANSI/HI", "ANSI HI"),
    "ICC": ("ICC", "ICC I-CODE", "I-CODE"),
    "EEC": ("EEC", "EC", "GLOBAL EEC", "GLOBAL EC"),
}

QUALIFIER_RE = re.compile(
    r"\b(?P<label>PARTS?|PT|SECTION|SEC|CHAPTER|CH|SERIES|SER)\b"
    r"(?:(?:\s*[:/.-]\s*|\s+)"
    r"(?P<value>[A-Z0-9]+(?:\s*(?:-|–|—|/|&|TO|THRU|THROUGH|\.)\s*[A-Z0-9]+)*)?)?\s*$",
    re.IGNORECASE,
)
VOLUME_SUFFIX_RE = re.compile(
    r"\s*[- ]VOL(?:UME)?\.?\s*[IVX0-9]+"
    r"(?:\s*&\s*VOL(?:UME)?\.?\s*[IVX0-9]+)*\s*$",
    re.IGNORECASE,
)


def clean(value: str) -> str:
    value = str(value or "").strip()
    value = value.replace("\u2010", "-").replace("\u2011", "-")
    value = value.replace("\u2012", "-").replace("\u2013", "-")
    value = value.replace("\u2014", "-").replace("\u2212", "-")
    value = value.replace("\u201c", "").replace("\u201d", "")
    value = value.replace("\u2018", "").replace("\u2019", "")
    value = value.replace('"', "").replace("'", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_tokens(value: str) -> str:
    value = clean(value).upper()
    value = re.sub(r"\s*([:/.,-])\s*", r"\1", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" :.,-()[]{}")


def normalize_identity_core(value: str) -> str:
    """Normalize punctuation-only differences in a standard identity."""
    return re.sub(r"[^A-Z0-9]", "", normalize_tokens(value))


def identity_core_sql_pattern(value: str) -> str:
    """Keep identifier characters literal and wildcard only separators.

    Letter/digit boundaries also become optional wildcards so compact forms
    such as ``D1250`` match spaced catalogue values like ``D 1250``.
    """
    pattern = re.sub(r"[^A-Z0-9]+", "%", normalize_tokens(value)).strip("%")
    pattern = re.sub(r"([A-Z])(\d)", r"\1%\2", pattern)
    pattern = re.sub(r"(\d)([A-Z])", r"\1%\2", pattern)
    return pattern


def _spacing_variants(value: str) -> List[str]:
    """Generate compact/spaced letter-digit forms of an identifier body."""
    value = normalize_tokens(value)
    if not value:
        return []

    variants = [value]
    variants.append(re.sub(r"([A-Z])(\d)", r"\1 \2", value))
    variants.append(re.sub(r"([A-Z])\s+(\d)", r"\1\2", value))
    return list(dict.fromkeys(item for item in variants if item))


def identity_index_cores(sdo_name: str, core: str, raw: str = "") -> List[str]:
    """Cores under which a candidate should be indexed for discovery joins."""
    normalized = normalize_identity_core(core)
    if not normalized:
        return []

    cores = [normalized]
    metric = re.fullmatch(r"(.+)M", normalized)
    if metric and any(ch.isdigit() for ch in metric.group(1)):
        cores.append(metric.group(1))
    adopted = re.fullmatch(r"(?:EN|ISO|IEC)+(\d{4,})", normalized)
    if adopted and normalize_tokens(sdo_name) in {"BS", "BSI"}:
        cores.append(adopted.group(1))
    head = re.match(r"(\d{4,})", normalize_tokens(raw))
    if head:
        cores.append(head.group(1))
    root = re.match(r"(\d{4,})", normalized)
    if root and root.group(1) != normalized:
        cores.append(root.group(1))
    part_suffix = re.fullmatch(r"(\d{4,})P\d+", normalized)
    if part_suffix:
        cores.append(part_suffix.group(1))
    extension = re.fullmatch(r"(\d{4,})(\d{2})", normalized)
    if extension and extension.group(2) == "01":
        cores.append(extension.group(1))
    family_root = re.match(r"^([A-Z]+\d+)\.", normalize_tokens(raw))
    if family_root:
        cores.append(normalize_identity_core(family_root.group(1)))
    if normalize_tokens(sdo_name) == "SAE" and re.fullmatch(r".*\d[A-Z]", normalized):
        cores.append(normalized[:-1])
    if (
        normalize_tokens(sdo_name) == "IEC"
        and re.fullmatch(r"60([1-9]\d{2}\d*)", normalized)
    ):
        cores.append(normalized[2:])
    if normalize_tokens(sdo_name) == "ISA":
        isa_family = re.fullmatch(r"(\d{2})\d+", normalized)
        if isa_family:
            cores.append(isa_family.group(1))
    if normalize_tokens(sdo_name) == "JIS":
        department = re.fullmatch(r"([A-Z]+)(\d+)", normalized)
        if department:
            cores.append(department.group(2))
    return list(dict.fromkeys(cores))


def identity_lookup_core_tokens(
    sdo_name: str,
    core_token: str,
    qualifier: str = None,
) -> List[str]:
    """Add catalogue query forms for legacy IEC numbers without the ``60``."""
    core = normalize_tokens(core_token)
    if not core:
        return []

    qualifier_text = str(qualifier or "").upper()
    part = re.fullmatch(r"PART:(\d+)", qualifier_text)
    section = re.fullmatch(r"SECTION:(\d+)", qualifier_text)
    root = normalize_identity_core(core)
    numbered = re.fullmatch(r"(?P<root>\d+)PART(?P<part>\d+)", root)
    tokens = []
    # A part or section request must not search the bare root. "60079%"
    # returns every part of that standard.
    if section and numbered:
        tokens.append(
            f"{numbered.group('root')} PART {int(numbered.group('part'))} "
            f"SECTION {int(section.group(1))}"
        )
    elif part and re.fullmatch(r"\d{4,}", root):
        tokens.append(f"{root} PART {int(part.group(1))}")
    elif numbered:
        tokens.append(
            f"{numbered.group('root')} PART {int(numbered.group('part'))}"
        )
    else:
        tokens.append(core)
        if (
            normalize_tokens(sdo_name) == "IEC"
            and re.fullmatch(r"\d{3}(?:[-./]\d+)*", core)
        ):
            tokens.append(f"60{core}")
    return list(dict.fromkeys(tokens))


def _jis_optional_department_match(
    sdo_name: str,
    requested_core: str,
    candidate_core: str,
) -> bool:
    """Allow bare JIS numbers to match department-letter catalogue ids.

    Example: request ``0555`` matches stored ``K0555`` / ``G0555``. Year and
    qualifier checks in ``identity_matches`` still apply afterward.
    """
    if normalize_tokens(sdo_name) != "JIS":
        return False
    if not requested_core.isdigit():
        return False
    department = re.fullmatch(r"([A-Z]+)(\d+)", candidate_core)
    return bool(department and department.group(2) == requested_core)


# Continuations allowed after a core token in LIKE predicates. Digits are not
# left open-ended (`core%`) so short cores such as "610" do not match "6100".
_CORE_BOUNDARY_SUFFIXES = (
    "",
    " %",
    ":%",
    "/%",
    "(%",
    "-%",
    ".%",
)

# Bare unprefixed cores shorter than this are too selective-hostile inside an
# SDO partition (e.g. "1%", "12%") and must be prefix-anchored instead.
_MIN_UNPREFIXED_CORE_LEN = 4


def identity_bound_like_patterns(prefix: str, core_pattern: str) -> List[str]:
    """Build prefix-anchored LIKE patterns with core token boundaries.

    Prefer patterns that start with the SDO/identifier prefix so indexes can
    be used, and require a separator (or end) after the core instead of a
    bare ``{core}%`` / ``{prefix} %{core}%`` scan.
    """
    prefix = normalize_tokens(prefix)
    core_pattern = str(core_pattern or "").strip("%")
    if not prefix or not core_pattern:
        return []

    patterns: List[str] = []
    for suffix in _CORE_BOUNDARY_SUFFIXES:
        # "API 610", "API 610:2020", "API 610-1"
        patterns.append(f"{prefix} {core_pattern}{suffix}")
        # Designation between prefix and core: "API STD 610", "API RP 610"
        patterns.append(f"{prefix} % {core_pattern}{suffix}")
        # Compact forms: "API610", "IS875"
        patterns.append(f"{prefix}{core_pattern}{suffix}")

    return list(dict.fromkeys(patterns))


_UNPREFIXED_DESIGNATIONS = (
    "STD",
    "RP",
    "SPEC",
    "SP",
    "TR",
    "BUL",
    "BULL",
    "PUB",
    "GUIDE",
    "MPMS",
)


def identity_unprefixed_like_patterns(core_pattern: str, core: str) -> List[str]:
    """Bounded unprefixed patterns for rows stored without an SDO prefix."""
    core_pattern = str(core_pattern or "").strip("%")
    core = normalize_identity_core(core)
    if not core_pattern or len(core) < _MIN_UNPREFIXED_CORE_LEN:
        return []

    patterns: List[str] = []
    for suffix in _CORE_BOUNDARY_SUFFIXES:
        patterns.append(f"{core_pattern}{suffix}")
        for designation in _UNPREFIXED_DESIGNATIONS:
            patterns.append(f"{designation} {core_pattern}{suffix}")
            patterns.append(f"{designation}{core_pattern}{suffix}")

    return list(dict.fromkeys(patterns))


def identity_like_patterns_for_hint(
    sdo_prefix: str,
    core_token: str,
) -> Tuple[str, List[str]]:
    """Build (normalized_core, LIKE patterns) for one identity hint."""
    core_text = normalize_tokens(core_token)
    core = normalize_identity_core(core_text)
    core_pattern = identity_core_sql_pattern(core_text)
    prefixes = sdo_identifier_prefixes(sdo_prefix)

    if not prefixes or not core or not core_pattern:
        return "", []

    patterns: List[str] = []
    for prefix in prefixes:
        patterns.extend(
            identity_bound_like_patterns(prefix, core_pattern)
        )
    patterns.extend(
        identity_unprefixed_like_patterns(core_pattern, core)
    )
    return core, list(dict.fromkeys(patterns))


# Cores shorter than this are too broad for ``%{core}%`` scans inside an
# SDO partition (e.g. ``%12%``). Those keep the selective prefix-bound path.
# Length 3 (``610``, ``560``) is the common case and is safe with the
# ``identity_core_appears`` post-filter.
_MIN_CONTAINMENT_CORE_LEN = 3


def identity_discovery_terms(
    sdo_prefix: str,
    core_token: str,
) -> Tuple[str, Optional[str], List[str]]:
    """Return discovery terms for one identity hint.

    Returns ``(normalized_core, containment_pattern, bound_patterns)``.

    - Long cores (``len >= 4``): ``containment_pattern`` is set for a single
      ``%{pattern}%`` predicate per column. Accuracy stays in
      ``identity_core_appears`` after the query.
    - Short cores: ``containment_pattern`` is ``None`` and ``bound_patterns``
      carries the selective prefix-anchored LIKE set.
    """
    core_text = normalize_tokens(core_token)
    core = normalize_identity_core(core_text)
    core_pattern = identity_core_sql_pattern(core_text)
    prefixes = sdo_identifier_prefixes(sdo_prefix)

    if not prefixes or not core or not core_pattern:
        return "", None, []

    if len(core) >= _MIN_CONTAINMENT_CORE_LEN:
        return core, core_pattern, []

    bound: List[str] = []
    for prefix in prefixes:
        bound.extend(identity_bound_like_patterns(prefix, core_pattern))
    return core, None, list(dict.fromkeys(bound))


def identity_indexable_like_patterns(sdo_prefix: str, core: str) -> List[str]:
    """Prefix-anchored forms an index can seek for one compact core.

    The trailing ``%`` still admits later editions (``ISO 9001:2015`` and
    ``ISO 9001:2024``). A leading ``%`` is never used here. Adopted
    spellings such as ``ISO/IEC 9001`` are found by the fulltext lookup,
    not by expanding every publisher alias into this list.
    """
    compact = normalize_identity_core(core)
    prefix = normalize_tokens(sdo_prefix)
    if not compact or not prefix or len(compact) < _MIN_CONTAINMENT_CORE_LEN:
        return []

    numbered_part = re.fullmatch(
        r"(?P<root>\d+)PART(?P<part>\d+)(?:SECTION(?P<section>\d+))?",
        compact,
    )
    patterns = []
    if not numbered_part:
        patterns.extend([
            f"{prefix} {compact}%",
            f"{prefix}{compact}%",
        ])
        glued = normalize_identity_core(prefix)
        compact_prefix = prefix.replace(" ", "")
        if glued and glued not in {prefix, compact_prefix}:
            patterns.append(f"{glued}{compact}%")
        if len(compact) >= _MIN_UNPREFIXED_CORE_LEN:
            patterns.append(f"{compact}%")
    else:
        # One family prefix per spelling. A long root such as 60079 is a
        # small index range; the part and section are checked afterwards.
        # Listing every Part/Sec spelling here multiplies the ranges until
        # the query stops using the index. Short roots stay specific so
        # "IS 5%" is never searched.
        root = numbered_part.group("root")
        part = str(int(numbered_part.group("part")))
        section = numbered_part.group("section")
        for spelling in sdo_identifier_prefixes(prefix):
            if len(root) >= 4:
                patterns.append(f"{spelling} {root}%")
                continue
            if section:
                sec = str(int(section))
                patterns.extend([
                    f"{spelling} {root}-{part}-{sec}%",
                    f"{spelling} {root} : Part {part} : Sec {sec}%",
                    f"{spelling} {root} PART {part} SECTION {sec}%",
                ])
            else:
                patterns.extend([
                    f"{spelling} {root}-{part}%",
                    f"{spelling} {root} : Part {part}%",
                    f"{spelling} {root} {part}%",
                    f"{spelling} {root} PART {part}%",
                    f"{spelling} {root} (Part {part})%",
                ])
    return [
        pattern
        for pattern in dict.fromkeys(patterns)
        if like_pattern_is_prefix_indexable(pattern)
    ]


def adoption_price_like_patterns(
    sdo_name: str,
    core_number: str,
    qualifier: str = None,
) -> List[str]:
    """Indexable patterns for the one edition a BIS adoption names.

    Search can read a whole family and pick the part afterwards. Price
    lookup must not: ``IEC 60079%`` returns every part, amendment, and
    redline. These patterns keep the part and, when present, the section.
    """
    compact = normalize_identity_core(core_number)
    section = re.fullmatch(r"SECTION:(\d+)", str(qualifier or "").upper())
    numbered = re.fullmatch(r"(?P<root>\d+)PART(?P<part>\d+)", compact)
    patterns = []
    if numbered:
        root = numbered.group("root")
        part = str(int(numbered.group("part")))
        for spelling in sdo_identifier_prefixes(sdo_name):
            if section:
                sec = str(int(section.group(1)))
                patterns.extend([
                    f"{spelling} {root}-{part}-{sec}%",
                    f"{spelling} {root} : Part {part} : Sec {sec}%",
                ])
            else:
                patterns.extend([
                    f"{spelling} {root}-{part}%",
                    f"{spelling} {root} : Part {part}%",
                ])
    else:
        for prefix in sdo_identifier_prefixes(sdo_name):
            patterns.extend(identity_indexable_like_patterns(prefix, compact))
    return [
        pattern
        for pattern in dict.fromkeys(patterns)
        if like_pattern_is_prefix_indexable(pattern)
    ]


def identity_fulltext_terms(core: str) -> List[str]:
    """Boolean-mode words that still contain this core.

    ``A29/A29M`` is stored as the words ``A29`` and ``A29M``, so the leading
    letter-number token is included beside the full compact core.
    """
    compact = normalize_identity_core(core)
    if len(compact) < _MIN_CONTAINMENT_CORE_LEN:
        return []
    terms = [compact]
    head = re.match(r"[A-Z]+\d+", compact)
    if head and head.group(0) != compact and len(head.group(0)) >= 3:
        terms.append(head.group(0))
    return list(dict.fromkeys(terms))


def like_pattern_is_prefix_indexable(pattern: str) -> bool:
    """True when LIKE can use a leftmost prefix (no early `%`)."""
    text = str(pattern or "")
    wildcard_at = text.find("%")
    if wildcard_at < 0:
        return True
    return text[wildcard_at:].replace("%", "") == ""


def _catalogue_section_appears(value: str, root: str, part: str, section: str) -> bool:
    """True when a compact designation is this part and section.

    ``60079-35-2:2011`` compacts to ``600793522011``. Part 35 alone, or
    section 1, does not satisfy section 2.
    """
    return bool(
        re.search(
            rf"(?<!\d){re.escape(root)}(?:PART)?{re.escape(part)}"
            rf"(?:SEC(?:TION)?)?{re.escape(section)}"
            rf"(?:(?:19|20)\d{{2}})?(?!\d)",
            value,
        )
    )


def _catalogue_part_appears(value: str, root: str, part: str) -> bool:
    """True when a compact designation contains this part, including hyphens.

    ``60079-28:2023`` compacts to ``60079282023``. ``60079-280`` must not
    satisfy a search for part 28.
    """
    return bool(
        re.search(
            rf"(?<!\d){re.escape(root)}(?:PART)?{re.escape(part)}"
            rf"(?:SEC(?:TION)?\d{{1,2}}|[1-9]\d?)?"
            rf"(?:(?:19|20)\d{{2}})?(?!\d)",
            value,
        )
    )


def identity_core_appears(normalized_value: str, core: str) -> bool:
    """True when ``core`` appears without a longer leading numeric prefix.

    Rejects ``1610`` for core ``610`` (leading digit extension) while allowing
    trailing edition/part digits such as ``6102020`` from ``610:2020`` or
    ``8751`` from ``875-1``. Selective SQL patterns already exclude most
    supersets such as ``6100``.
    """
    value = normalize_identity_core(normalized_value)
    core = normalize_identity_core(core)
    # Drop embedded edition years so MR0175-2021-ISO and SP 55:2025 AND…
    # still contain the designation core.
    value = re.sub(r"(?<=\d)(?:19|20)\d{2}(?=[A-Z])", "", value)
    core = re.sub(r"(?<=\d)(?:19|20)\d{2}(?=[A-Z])", "", core)
    if not value or not core:
        return False

    section_form = re.fullmatch(
        r"(?P<root>\d+)PART(?P<part>\d+)SECTION(?P<section>\d+)",
        core,
    )
    if section_form and _catalogue_section_appears(
        value,
        section_form.group("root"),
        section_form.group("part"),
        section_form.group("section"),
    ):
        return True

    part_form = re.fullmatch(r"(?P<root>\d+)PART(?P<part>\d+)", core)
    if part_form and _catalogue_part_appears(
        value,
        part_form.group("root"),
        part_form.group("part"),
    ):
        return True

    start = 0
    while True:
        pos = value.find(core, start)
        if pos < 0:
            return False
        if pos == 0 or not value[pos - 1].isdigit():
            return True
        start = pos + 1


def sdo_identifier_prefixes(sdo_name: str) -> Tuple[str, ...]:
    sdo = normalize_tokens(sdo_name)
    if not sdo:
        return ()
    # IS and BIS are one catalogue. Compound adoptions such as IS/IEC
    # and IS/ISO use the BIS prefix list.
    names = [sdo]
    if sdo == "IS":
        names.append("BIS")
    aliases = []
    for name in names:
        aliases.extend(SDO_IDENTIFIER_PREFIX_ALIASES.get(name, ()))
    return tuple(dict.fromkeys((*names, *aliases)))


def extract_year(value: str) -> Tuple[str, Optional[int]]:
    value = REAFFIRMATION_RE.sub("", clean(value)).rstrip()
    shortened, two_digit_year = _edition_from_two_digit_suffix(value)
    if two_digit_year is not None:
        return shortened, two_digit_year
    # Year in the middle: "SP 55:2025 AND 11 X 17 LAMINATED PHOTO SET"
    if not re.search(r"(?:19|20)\d{2}-\d{2}-(?:19|20)\d{2}", value):
        mid_year = re.match(
            r"^(?P<body>.*?\d)\s*[:\-]\s*(?P<year>(?:19|20)\d{2})\b(?P<tail>\s+.*)?$",
            value,
        )
        if mid_year and re.search(r"[A-Z]", mid_year.group("body"), re.I):
            body = (
                mid_year.group("body") + (mid_year.group("tail") or "")
            ).strip()
            return body, int(mid_year.group("year"))
    match = YEAR_RE.search(value)
    if not match:
        return value, None
    year = int(match.group(1))
    body = value[:match.start()].strip(" :.,-()[]{}")
    # Catalogue numbers that are themselves 19xx/20xx (API 2003, IS 1905,
    # RP 2009) must keep those digits as identity, not edition metadata.
    if re.search(r"(?:19|20)\d{2}-\d{2}-(?:19|20)\d{2}$", value):
        return value, None
    if not re.search(r"\d", body):
        # "API 2003" is the designation. "IBC-2024" and "IBC : 2024" are editions.
        separator_at = match.start()
        separator = value[separator_at:separator_at + 1]
        if separator.isspace() and separator_at > 0 and value[separator_at - 1] in ":/-":
            separator = value[separator_at - 1]
        if separator not in "-:":
            return value, None
    return body, year


def _century_from_two_digit_year(year_digits: int) -> int:
    """Map ASTM-style two-digit editions: ``63`` → 1963, ``23`` → 2023."""
    return 1900 + year_digits if year_digits >= 50 else 2000 + year_digits


def _edition_from_two_digit_suffix(value: str) -> Tuple[str, Optional[int]]:
    """ASTM stores editions as ``: 23``, ``: 63(2023)``, or ``E125-63``."""
    match = re.search(
        r":\s*(\d{2})(?:[a-z]\d*)?(?:\s*\((?:19|20)\d{2}\))?\s*$",
        value,
        re.IGNORECASE,
    )
    if match:
        body = value[:match.start()].strip(" :.,-()[]{}")
        if re.search(r"\d", body):
            return body, _century_from_two_digit_year(int(match.group(1)))

    # Letter-number designations with a trailing edition year (E125-63, VIS 1-02).
    compact = re.search(
        r"^(?P<body>(?:[A-Z]+\s*)?\d+(?:\.\d+)*|[A-Z]+\d+(?:/[A-Z]*\d+M)?)"
        r"-(?P<yy>\d{2})$",
        normalize_tokens(value),
        re.IGNORECASE,
    )
    if compact:
        return (
            compact.group("body"),
            _century_from_two_digit_year(int(compact.group("yy"))),
        )
    return value, None


def _qualifier_variants(body: str) -> List[str]:
    body = normalize_tokens(body)
    variants = [body]

    # PT/PART N -> -N / space-N / dot-N representations.
    m = re.search(r"\b(?:PT|PART)\.?\s*(\d+)\s*$", body, re.I)
    if m:
        base = body[:m.start()].rstrip(" -./")
        n = m.group(1)
        variants.extend([
            f"{base}-{n}",
            f"{base} {n}",
            f"{base}.{n}",
        ])

    # Section/chapter forms are preserved but also get compact punctuation
    # variants because databases commonly store them differently.
    m = re.search(r"\b(?:SEC|SECTION|CH|CHAPTER)\.?\s*(\d+)\s*$", body, re.I)
    if m:
        base = body[:m.start()].rstrip(" -./")
        n = m.group(1)
        variants.extend([
            f"{base} SEC {n}",
            f"{base} CH {n}",
            f"{base}-{n}",
        ])

    return list(dict.fromkeys(v for v in variants if v))


def _split_designation(body: str) -> Tuple[Optional[str], str]:
    """Return (designation, core) without guessing unknown designations.

    Examples:
        STD 610       -> (STD, 610)
        RP 610        -> (RP, 610)
        C950          -> (None, C950)
        NACE MR0175   -> (None, NACE MR0175)  [SDO normally removed first]
    """
    body = normalize_tokens(body)
    if not body:
        return None, ""

    # Long multi-word designation markers first.
    for token in sorted(DESIGNATION_TOKENS, key=len, reverse=True):
        normalized = normalize_tokens(token)
        if body == normalized:
            return normalized, ""
        match = re.match(
            rf"^{re.escape(normalized)}(?=$|[\s:/.-])",
            body,
        )
        if match:
            core = body[match.end():].strip(" :/.-")
            if core:
                return normalized, core

    return None, body


def _prepare_display(display: str) -> str:
    """Collapse wording that is not part of the stored designation."""
    display = display.lstrip("/").strip()
    display = re.sub(
        r"(?i)\(\s*((?:PART|PT|SECTION|SEC|CHAPTER|CH)\b[^)]*)\)",
        r"\1",
        display,
    )
    display = re.sub(
        r"(?i)\s*\((?:ISO|IEC)\s+\d[^)]*\)\s*$",
        "",
        display,
    ).strip()
    # CEN national-adoption corrigenda may be shown as a trailing "+ AC";
    # this is publication metadata, not part of the base standard number.
    display = re.sub(
        r"(?i)\s*\+\s*AC(?:\s*[:/-]\s*(?:19|20)\d{2})?\s*$",
        "",
        display,
    ).strip()
    display = re.sub(r"(?i)\s+materials\b", "", display)
    display = re.sub(r"(?i)\s+customary\b", "", display)
    display = re.sub(r"(?i)\brev\.?\s*([A-Z])\b", r"\1", display)
    display = re.sub(r"(?i)(\d)\s+([A-Z])$", r"\1\2", display)
    display = re.sub(r"(?i)\s+amendment\s*-?\s*\d+\b", "", display)
    display = re.sub(r"(?i)\s*\+\s*A\d+\b", "", display)
    display = re.sub(
        r"(?i)\s*\(DRAFT\)(?=\s*(?::|$))",
        "",
        display,
    ).strip()
    display = re.sub(
        r"(?i)\s*-?\s*parts?\s*-?\s*1\s*,\s*2\s*,\s*3\b",
        "",
        display,
    )
    display = re.sub(r"(?i)\s*&\s*technical\s+circulars\b.*$", "", display)
    display = re.sub(r"(?i)\bstandard\s+and\b", "AND", display)
    display = re.sub(
        r"(?i)^(SP\s*-?\s*\d+)-((?:19|20)\d{2})\b",
        r"\1 : \2",
        display,
    )
    display = re.sub(r"(?i)\bCEN-TR\b", "CEN/TR", display)
    # National adoptions of ISO: keep the ISO number only.
    display = re.sub(
        r"(?i)^(?:AENOR\s+|DANSK\s+)?(?:UNE|DS|DIN|NF|UNI|SIS|SN|NEN|NS|SFS|IST)"
        r"(?:\s*[-/]\s*EN)?(?:\s+|-)ISO\b",
        "ISO",
        display,
    )
    # ASME shorthand: BPVC II D -> BPVC SECTION II PART D
    display = re.sub(
        r"(?i)\bBPVC\s+(I{1,3}|IV|V|VI|VII|VIII|IX|X|XI|XII)\s+([A-D])\b",
        r"BPVC SECTION \1 PART \2",
        display,
    )
    display = re.sub(
        r"(?i)\bSEC(?:TION)?\.?\s*",
        "SECTION ",
        display,
    )
    display = re.sub(r"(?i)\bDIV(?:ISION)?\s*-?\s*(\d+)", r"DIVISION \1", display)
    display = re.sub(r"(?i)\bPARTS?\s*-?\s*([A-Z0-9]+)\b", r"PART \1", display)
    display = re.sub(r"(?i)\s+CMV\s*$", "", display).strip()
    display = re.sub(r"\s+", " ", display).strip(" -/")
    return display


def _catalogue_sdo_for_adoption(sdo: str, display: str) -> Tuple[str, str]:
    """Keep an Indian adoption on the BIS catalogue.

    ``IS/IEC``, ``IS/ISO``, ``IS/IEC/IEEE`` and the same chains written
    with spaces are BIS rows. The publishers after IS stay on the
    designation so the numeric standard can be read from either spelling.
    """
    compound = re.fullmatch(
        r"(?:IS|BIS)(?:\s*/\s*[A-Z][A-Z0-9]*)+",
        sdo,
    )
    if compound:
        prefix = re.sub(r"\s*/\s*", "/", sdo)
        if not re.match(
            rf"(?i)^{re.escape(prefix)}(?=$|[\s:/.-]|\d)",
            display,
        ):
            display = f"{prefix} {display}".strip()
        return "BIS", display

    if sdo in {"IS", "BIS"} and re.match(
        r"(?i)^(?:BIS\s+)?IS\s*/\s*[A-Z]",
        display,
    ):
        return "BIS", display
    return sdo, display


def _strip_leading_publishers(body: str) -> str:
    """Drop adopted publisher words that sit in front of the number.

    ``IEC 60079`` and ``ISO/IEC 60079`` are the same numeric standard.
    Designation words such as ``SP`` and qualifier words such as ``PART``
    stay in place.
    """
    body = body.strip()
    while body:
        match = re.match(r"^([A-Z][A-Z0-9]*)(?:\s*/\s*|\s+)", body)
        if not match:
            break
        token = match.group(1)
        if (
            token in DESIGNATION_TOKENS
            or token in _ADOPTION_QUALIFIER_WORDS
            or not re.fullmatch(r"[A-Z]{2,}", token)
        ):
            break
        rest = body[match.end():].strip()
        if not re.match(r"(?:[A-Z]{2,}(?:\s*/\s*|\s+)|\d)", rest):
            break
        body = rest
    return body


def canonicalize_search_request(
    sdo_name: str,
    display_number: str,
) -> Tuple[str, str, str]:
    """Return ``(identity_sdo, cleaned_number, sdo_id_name)``.

    Identity SDO stays a catalogue prefix (``NACE``, ``SSPC``, ``HI``).
    ``sdo_id_name`` is the title actually stored on the SDO table
    (``AMPP-NACE``, ``AMPP-SSPC``, ``HI``). Status notes are removed from
    the number so withdrawn / edition text does not hide the designation.
    """
    sdo = clean(sdo_name).upper()
    display = _prepare_printed_designation(clean(display_number))
    sdo, display = _catalogue_sdo_for_adoption(sdo, display)
    stated_replacement = split_stated_replacement(display)
    if stated_replacement:
        display = stated_replacement["replacement"]
    if (
        sdo in {"ANSI/HI", "ANSI HI"}
        or (
            sdo == "ANSI"
            and re.match(r"(?i)^ANSI\s*(?:/|\s)\s*HI\b", display)
        )
    ):
        sdo = "HI"
        display = re.sub(
            r"(?i)^ANSI\s*(?:/|\s)\s*HI\b\s*",
            "HI ",
            display,
        ).strip()
    # IS IEC numbers are Indian adoptions of IEC publications. Keep BIS/IS
    # as the catalogue SDO so an adoption can never resolve to IEC directly.
    # When the caller explicitly selected IEC, remove only the national
    # adoption marker from its display number.
    if sdo == "IEC" and re.match(r"(?i)^IS\s+IEC\b", display):
        display = re.sub(r"(?i)^IS\s+", "", display, count=1)
    elif sdo and re.match(
        rf"(?i)^(?:IS|BIS)\s*/\s*{re.escape(sdo)}\b",
        display,
    ):
        display = re.sub(
            r"(?i)^(?:IS|BIS)\s*/\s*",
            "",
            display,
            count=1,
        )
    elif sdo == "IEC" and re.match(r"(?i)^ISO\s+\d", display):
        sdo = "ISO"
    elif sdo == "IEC" and re.match(r"(?i)^BS\s+EN\b", display):
        sdo = "BSI"

    duplicate_year = re.search(
        r"(?P<designation>.*\d)-(?P<year>(?:19|20)\d{2})"
        r"\s+(?P=year)\s*$",
        display,
        re.IGNORECASE,
    )
    if duplicate_year:
        display = (
            f"{duplicate_year.group('designation')}:"
            f"{duplicate_year.group('year')}"
        )

    display = WITHDRAWAL_RE.sub("", display).strip(" -/")
    display = re.sub(r"(?i)\s+with subsections.*$", "", display).strip()
    display = re.sub(
        r"(?i)\s*\+F\d+\s*:\s*F\d+\b.*$",
        "",
        display,
    ).strip()
    display = re.sub(
        r"(?i)\s*\(?\s*total\s*[-:]\s*\d+\s*codes?\s*\)?\s*$",
        "",
        display,
    ).strip()
    display = re.sub(
        r"(?i)\s*\(?\s*total\s*$",
        "",
        display,
    ).strip()
    display = re.sub(r"(?i)\s*\((?:ex|total)[^)]*\)\s*", " ", display).strip()
    display = TRAILING_NOTE_RE.sub("", display).strip(" -/")
    display = re.sub(r"(?i)(?<=\d)\s*&\s*(?=\d)", "/", display)
    display = re.sub(r"(?i)\+F\d.*$", "", display).strip(" -/")
    display = re.sub(r"(?i)^STD\s+", "", display).strip()

    # Some catalog exports append a fully qualified designation after the
    # legacy number. Prefer that identifier over the preceding metadata.
    sdo_prefix = re.escape(sdo)
    explicit_identifier = re.search(
        rf"(?:\s+[-–—]\s+|\s+){sdo_prefix}\s+(?P<number>[A-Z0-9][A-Z0-9 .:/+-]*)$",
        display,
        flags=re.IGNORECASE,
    )
    if explicit_identifier:
        display = explicit_identifier.group("number").strip()

    display = re.sub(
        r"(?i)\s+(?:ED(?:ITION)?\.?)\s*\d+(?:\.\d+)*\s*$",
        "",
        display,
    ).strip()
    display = re.sub(
        r"(?i)\s+(?:REV(?:ISION)?\.?|AMEND(?:MENT)?|AMD)\s*\.?\s*"
        r"\d*(?:\.\d+)?(?:\s*,.*)?$",
        "",
        display,
    ).strip()

    # Date suffixes in the BIS/IS source list are revision metadata, not
    # implicit part/section identifiers. Explicit PART/SECTION text is parsed
    # below and remains identity-bearing. IEC uses a separate Excel-date
    # encoding for numeric two-level parts.
    date_component = EXCEL_DATE_COMPONENT_RE.search(display)
    if date_component:
        if sdo in {"IS", "BIS"}:
            after_date = display[date_component.end():]
            after_date = re.sub(
                r"^\s+(?:19|20)\d{2}\b",
                "",
                after_date,
                count=1,
            )
            display = (
                display[:date_component.start()] + after_date
            ).strip()
        elif sdo in {"IEC", "ISO/IEC"}:
            month = MONTH_NUMBER[date_component.group("month").upper()]
            day = int(date_component.group("day"))
            display = (
                f"{display[:date_component.start()].rstrip()}-"
                f"{month}-{day}"
            )

    display = _prepare_display(display)
    if sdo == "DIN" and re.match(r"(?i)^EN\b", display):
        display = f"DIN {display}"
    id_name = sdo

    alias = SDO_LOOKUP_ALIASES.get(sdo)
    if alias:
        alias_key = sdo
        sdo, id_name = alias
        if alias_key == "GPA":
            display = re.sub(r"(?i)^STD\s+", "", display).strip()
            if not re.match(r"(?i)^GPA\b", display):
                display = f"GPA {display}".strip()
        if alias_key in {"BULL", "BUL", "PUBL", "PUB", "RP", "SPEC", "STD"}:
            display = f"{alias_key} {display}".strip()
        if alias_key == "PCC":
            display = f"PCC-{display}".strip("- ")
        if alias_key == "MR":
            if not re.match(r"(?i)^MR\b", display):
                display = f"MR {display}".strip()
            display = re.sub(r"(?i)^MR\s*(\d)", r"MR\1", display)
            display = re.sub(r"(?i)\s*&\s*ISO\s+", "/ISO ", display)
        if alias_key in {"HM", "DIS"}:
            display = f"{alias_key} {display}".strip()
        if alias_key == "ATEX":
            display = re.sub(r"(?i)^ATEX\b\s*[:.-]?\s*", "", display)
        if alias_key == "NZS" and not re.match(r"(?i)^NZS\b", display):
            display = f"NZS {display}".strip()
        if alias_key == "IP" and not re.match(r"(?i)^IP\b", display):
            display = f"IP {display}".strip()
        if alias_key == "SSPC-SP" and re.match(r"(?i)^WJ\b", display):
            sdo, id_name = "NACE", "AMPP-NACE"
        if sdo == "ASNT" and "ANSI/ASNT-CP" in str(sdo_name or "").upper():
            if not re.match(r"(?i)^CP\b", display):
                display = f"CP {display}".strip()
        if sdo == "ANSI" and "ANSI/FCI" in str(sdo_name or "").upper():
            if not re.match(r"(?i)^FCI\b", display):
                display = f"FCI {display}".strip()
        if sdo == "SAE" and not re.match(r"(?i)^AMS\b", display):
            display = f"AMS {display}".strip()
        if sdo == "MSS" and not re.match(r"(?i)^SP\b", display):
            display = f"SP {display}".strip()
        if (
            alias_key in {"SNT-TC", "SNT TC"}
            and sdo == "ASNT"
            and not re.match(r"(?i)^SNT", display)
        ):
            display = f"SNT-TC-{display}".strip("- ")

    if sdo == "ANSI" and re.match(r"(?i)^HI\b", display):
        sdo = "HI"
        id_name = "HI"

    if sdo == "ANSI" and re.match(r"(?i)^NACE\b", display):
        sdo = "NACE"
        id_name = "AMPP-NACE"

    if sdo == "ANSI" and re.match(r"(?i)^MSS\b", display):
        sdo = "MSS"
        id_name = "MSS"

    if sdo == "ANSI" and re.match(r"(?i)^ASNT\b", display):
        sdo = "ASNT"
        id_name = "ASNT"

    if sdo == "GLOBAL":
        display = re.sub(r"(?i)^GPA\s+STD\b", "GPA", display).strip()

    if sdo == "NACE" and re.match(r"(?i)^SSPC[- ](?:SP|PA)\b", display):
        sdo = "SSPC"
        id_name = "AMPP-SSPC"

    if sdo == "EN" and re.match(r"(?i)^ISO\b", display):
        sdo = "ISO"
        id_name = "ISO"

    if sdo == "ASME" and re.match(r"(?i)^SECTION\b", display):
        display = f"BPVC {display}"

    if sdo == "ANSI" and re.search(r"(?i)\bTIA\b", display):
        sdo = "TIA"
        id_name = "GLOBAL"
        display = re.sub(r"(?i)^TIA\s+(?:ANSI/)?", "", display)
        display = re.sub(r"(?i)^ANSI/", "", display)

    # These DNV document types are filed under the GLOBAL catalogue title.
    if sdo == "DNV" and re.match(r"(?i)^(ST|RP|OS|GL)[-\s]", display):
        id_name = "GLOBAL"

    if sdo == "ISA":
        display = re.sub(r"(?i)^S(?=\d)", "", display)

    # SSPC-SP WJ-1 is the same document as NACE WJ-1.
    if sdo == "SSPC" and re.match(r"(?i)^SP\s+WJ\b", display):
        sdo = "NACE"
        id_name = "AMPP-NACE"
        display = re.sub(r"(?i)^SP\s+", "", display)

    # NACE No. 6 is published as the joint SSPC-SP 13 document.
    if sdo == "NACE" and re.match(r"(?i)^NO\.?\s*6\b", display):
        id_name = "AMPP-SSPC"

    return sdo, display, id_name


def _roman_numeral_value(value: str) -> Optional[int]:
    value = str(value or "").upper()
    if not value or not re.fullmatch(r"[IVXLCDM]+", value):
        return None

    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    previous = 0
    for character in reversed(value):
        current = values[character]
        total += -current if current < previous else current
        previous = current

    remaining = total
    canonical = ""
    for number, symbol in (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ):
        count, remaining = divmod(remaining, number)
        canonical += symbol * count
    return total if canonical == value else None


def _normalize_bis_roman_part(qualifier: Optional[str]) -> Optional[str]:
    match = re.fullmatch(r"PART:([IVXLCDM]+)", str(qualifier or ""))
    if not match:
        return qualifier
    value = _roman_numeral_value(match.group(1))
    return f"PART:{value}" if value is not None else qualifier


def _qualifier_range_covers(requested_qualifier: str, candidate_qualifier: str) -> bool:
    """True when a requested part range includes the candidate part.

    ``PART:1-8`` covers ``PART:3`` and ``PART:5`` from ``60947-5``.
    """
    if (
        not requested_qualifier
        or not candidate_qualifier
        or ":" not in requested_qualifier
        or ":" not in candidate_qualifier
    ):
        return False

    requested_label, requested_value = requested_qualifier.split(":", 1)
    candidate_label, candidate_value = candidate_qualifier.split(":", 1)
    if requested_label != candidate_label:
        return False
    if "-" not in requested_value and "/" not in requested_value:
        return False

    candidate_token = re.split(r"[-./]", candidate_value, maxsplit=1)[0]
    if not candidate_token.isdigit():
        return False
    candidate_number = int(candidate_token)

    pieces = [piece for piece in re.split(r"[-/]", requested_value) if piece]
    if len(pieces) == 2 and all(piece.isdigit() for piece in pieces):
        start, end = int(pieces[0]), int(pieces[1])
        if start > end or end - start > 40:
            return False
        return start <= candidate_number <= end

    numbers = [int(piece) for piece in pieces if piece.isdigit()]
    return candidate_number in numbers


def parse_identity(sdo_name: str, display_number: str) -> Dict:
    sdo = clean(sdo_name).upper()
    value = _prepare_display(clean(display_number))

    value = re.sub(
        r"(?i)\s*[\(\[]\s*(?:I-P|SI|IP)\s*[\)\]]",
        "",
        value,
    ).rstrip()
    value = WITHDRAWAL_RE.sub("", value).rstrip()
    value = LANGUAGE_SUFFIX_RE.sub("", value).rstrip()
    value = CORRIGENDUM_RE.sub("", value).rstrip()
    series_marker = bool(SERIES_SUFFIX_RE.search(value))
    if series_marker:
        value = SERIES_SUFFIX_RE.sub("", value).rstrip()

    body, year = extract_year(value)
    body = normalize_tokens(body)

    # BIS labels such as "IS 2099 Rev 2, 1986" use REV as catalog edition
    # metadata, not as a Part/Revision qualifier in the standard identity.
    if sdo in {"BIS", "IS"} and year is not None:
        body = re.sub(
            r"(?i)\s+REV(?:ISION)?\.?\s*\d+\s*$",
            "",
            body,
        ).strip()

    # Publisher names may differ from identifier prefixes (BSI -> BS EN,
    # BIS -> IS), and some identifiers use compound prefixes (ISO/IEC).
    normalized_sdo = normalize_tokens(sdo)
    identifier_prefix = normalized_sdo
    prefix_removed = False
    if sdo in {"IS", "BIS"}:
        adoption = re.match(
            r"(?i)^((?:BIS\s+)?IS(?:\s*/\s*[A-Z][A-Z0-9]*)+)",
            body,
        )
        if adoption:
            identifier_prefix = re.sub(
                r"\s*/\s*",
                "/",
                adoption.group(1).upper(),
            )
            body = body[adoption.end():].strip(" :/.-")
            prefix_removed = True
    if not prefix_removed:
        for prefix in sorted(
            sdo_identifier_prefixes(sdo),
            key=len,
            reverse=True,
        ):
            match = re.match(
                rf"^{re.escape(prefix)}(?=$|[\s:/.-]|\d)",
                body,
                flags=re.IGNORECASE,
            )
            if match:
                identifier_prefix = prefix
                body = body[match.end():].strip(" :/.-")
                prefix_removed = True
                # "HI ANSI/HI 9.8" still starts with a known identifier.
                again = re.match(
                    rf"^(?:{'|'.join(re.escape(item) for item in sdo_identifier_prefixes(sdo))})(?=$|[\s:/.-]|\d)",
                    body,
                    flags=re.IGNORECASE,
                )
                if again:
                    body = body[again.end():].strip(" :/.-")
                break

    body = re.sub(
        r"^(?:ANSI(?:\s*[-/]\s*|\s+)|GLOBAL\s+)",
        "",
        body,
        flags=re.IGNORECASE,
    ).strip(" :/.-")
    body = re.sub(r"(?i)^TECHNICAL PAPER\s+", "", body).strip()
    body = re.sub(
        r"(?i)(\d)-((?:19|20)\d{2})[-/](?=ISO\b)",
        r"\1/",
        body,
    )
    if prefix_removed or normalized_sdo:
        again = re.match(
            rf"^(?:{'|'.join(re.escape(item) for item in sdo_identifier_prefixes(sdo))})(?=$|[\s:/.-]|\d)",
            body,
            flags=re.IGNORECASE,
        )
        if again:
            body = body[again.end():].strip(" :/.-")

    if not prefix_removed and normalized_sdo:
        body = re.sub(
            rf"^{re.escape(normalized_sdo)}(?:\s+|\s*[-:/]\s*|(?=\d))",
            "",
            body,
            flags=re.IGNORECASE,
        )
        body = body.strip(" :.,-/")

    if sdo in {"IS", "BIS"}:
        body = _strip_leading_publishers(body)

    # AMPP-NACE catalog entries vary between ``SP0775`` and ``SP 0775``.
    # Treat the compact form as the same SP designation and numeric core.
    if sdo == "NACE":
        body = re.sub(r"(?i)^SP(?=\d)", "SP ", body)

    # Joint titles such as "SP 6-2007-NACE No. 3" are the SSPC number plus a note.
    # Keep "NACE No. 6" when the request itself is that NACE designation.
    if sdo != "NACE":
        # Keep "(WAB)" on the designation; strip only the joint NACE/SSPC tail.
        body = re.sub(
            r"(?i)(?:[:\-]\d{4})?[-/](?:NACE|SSPC)\b.*$",
            "",
            body,
        ).strip(" -/")
    # "SP21412:2020-SSPC-CPC 1" is SP21412 plus the joint SSPC title.
    body = re.sub(
        r"(?i)(?:[:\-/]\d{4})?(?:/|-)\s*SSPC\b.*$",
        "",
        body,
    ).strip(" -/")
    # API 579-1 and ASME FFS-1 are joint designations for the same part.
    # Use the API primary number as the identity so legacy ``API 579 PT 1``
    # requests can resolve to the current joint API/ASME edition.
    if sdo == "API":
        body = re.sub(
            r"(?i)\s*/\s*ASME\s+FFS\s*-?\s*\d+(?:\.\d+)*\s*$",
            "",
            body,
        ).strip(" -/")

    designation, core = _split_designation(body)
    core = VOLUME_SUFFIX_RE.sub("", core).rstrip(" -./")
    core = re.sub(r"(?i)\s+(?:I-P|SI|IP)$", "", core).strip()
    # "VIS 1 GUIDE" is the same document as "VIS 1".
    core = re.sub(r"(?i)\s+GUIDE\b", "", core).strip()

    # Qualifiers are identity-bearing; only designation tokens are ignored.
    core_number = core
    qualifier = None
    family_lookup = False
    core = re.sub(
        r"(?i)(PART|PT|SECTION|SEC|CHAPTER|CH|SERIES|SER)(\d+)$",
        r"\1 \2",
        core,
    )
    # "Part 35-2" is part 35, section 2. The same split is used for a
    # bare numeric tail such as "35-2".
    core = re.sub(
        r"(?i)\b(?P<label>PART|PT)\s*(?P<part>\d+)\s*-\s*(?P<section>\d{1,2})\s*$",
        lambda match: (
            f"{match.group('label')} {int(match.group('part'))} SECTION "
            f"{int(match.group('section'))}"
        ),
        core,
    )
    # A trailing part and section may be written as words or as two short
    # numeric groups: "Part 35 : Sec 2" and "35-2" are the same division
    # of the root standard. A four-digit year is not a section. Excel
    # month labels are removed earlier.
    implicit_section = re.fullmatch(
        r"(?P<root>\d{3,})(?:\s+|-)(?P<part>\d{1,3})-(?P<section>\d{1,2})",
        core,
    )
    if implicit_section and not re.fullmatch(
        r"(?:19|20)\d{2}",
        implicit_section.group("part"),
    ):
        core = (
            f"{implicit_section.group('root')} PART "
            f"{int(implicit_section.group('part'))} SECTION "
            f"{int(implicit_section.group('section'))}"
        )
    core = re.sub(r"([./:-])[./:-]+", r"\1", core)
    qualifier_match = QUALIFIER_RE.search(core)
    if qualifier_match:
        core_number = core[:qualifier_match.start()].strip(" :/.-")
        label = qualifier_match.group("label").upper()
        canonical_label = {
            "PT": "PART",
            "PARTS": "PART",
            "SEC": "SECTION",
            "CH": "CHAPTER",
            "SER": "SERIES",
        }.get(label, label)
        qualifier_value = qualifier_match.group("value") or ""
        qualifier_value = re.sub(
            r"\s*(?:[-–—/.:&]|TO|THRU|THROUGH)\s*",
            "-",
            qualifier_value,
            flags=re.IGNORECASE,
        ).replace(" ", "").upper()
        qualifier = (
            f"{canonical_label}:{qualifier_value}"
            if qualifier_value
            else canonical_label
        )
        if not core_number:
            core_number = qualifier_value
    else:
        compound_section = re.match(
            r"^(?P<base>.+)-(?P<section>\d+)\.(?P<subsection>\d+)$",
            core,
        )
        slash_zero = re.match(r"^(?P<base>.+)/0$", core)
        implicit_part = re.match(
            r"^(?P<base>.+?)(?P<separator>[-./]|\s+)(?P<part>\d+)$",
            core,
        )
        implicit_roman_part = re.match(
            r"^(?P<base>.+?)(?P<separator>[-./]|\s+)"
            r"(?P<part>[IVXLCDM]+)$",
            core,
            re.IGNORECASE,
        )

        if compound_section:
            core_number = compound_section.group("base")
            qualifier = (
                f"SECTION:{compound_section.group('section')}-"
                f"{compound_section.group('subsection')}"
            )
        elif slash_zero:
            core_number = slash_zero.group("base")
            family_lookup = True
        elif (
            implicit_part
            and re.search(r"\d", implicit_part.group("base"))
            and not (
                implicit_part.group("separator") == "."
                and (
                    len(implicit_part.group("part")) > 1
                    or sdo in {"ASHRAE", "ACI"}
                )
            )
        ):
            core_number = implicit_part.group("base")
            qualifier = f"PART:{implicit_part.group('part')}"
        elif (
            sdo in {"IS", "BIS"}
            and implicit_roman_part
            and re.search(r"\d", implicit_roman_part.group("base"))
        ):
            core_number = implicit_roman_part.group("base")
            qualifier = f"PART:{implicit_roman_part.group('part').upper()}"

    if series_marker:
        qualifier = "SERIES"
        family_lookup = True

    if sdo == "ISA" and re.fullmatch(r"\d{2}", str(core_number)):
        family_lookup = True

    embedded_nace_no = re.search(r"NACE\s+NO\.?\s*(\d+)", body, re.IGNORECASE)
    if sdo == "NACE" and embedded_nace_no and not re.match(r"(?i)^NO\b", body):
        body = f"NO.{embedded_nace_no.group(1)}"
        designation, core = _split_designation(body)
        core_number = core
        qualifier = None

    core_number = re.sub(r"(\d)-([A-Z])$", r"\1\2", str(core_number))

    if sdo == "ASME" and re.match(r"^B\s*\d", core_number, re.IGNORECASE):
        core_number = re.sub(r"^B\s*", "", core_number, flags=re.IGNORECASE)

    if (
        sdo == "MSS"
        and designation == "SP"
        and core_number.isdigit()
    ):
        core_number = str(int(core_number))

    core_number_value = _primary_slash_alternative(core_number)
    normalized_core_number = normalize_identity_core(core_number_value)
    if sdo == "ACI" and re.fullmatch(r"\d+(?:\.\d+)+", core_number_value):
        # Dotted ACI document numbers (for example, 364.9 and 207.1) are
        # identifiers in their own right, not punctuation variants.
        normalized_core_number = core_number_value

    return {
        "sdo_name": sdo,
        "body": body,
        "designation": designation,
        "core": core,
        "core_number": normalized_core_number,
        "core_number_pattern": normalize_tokens(core_number),
        "qualifier": qualifier,
        "family_lookup": family_lookup,
        "year": year,
        "full_base": normalize_tokens(f"{sdo} {body}"),
        "identifier_prefix": identifier_prefix,
        "variants": _full_variants(sdo, body),
    }


_ADOPTION_QUALIFIER_WORDS = {
    "PART",
    "PT",
    "SEC",
    "SECTION",
    "AMD",
    "AMENDMENT",
    "REV",
    "REVISION",
    "COR",
    "CORRIGENDUM",
    "MOD",
    "IDT",
    "EQV",
    "NEQ",
}
_PUBLISHER_TOKEN = r"[A-Z][A-Z0-9]{1,}(?:\s*/\s*[A-Z][A-Z0-9]{1,})*"
_ADOPTION_REFERENCE_RE = re.compile(
    rf"(?i)(?<![A-Z0-9])(?P<sdo>{_PUBLISHER_TOKEN})\s+"
    r"(?P<number>[A-Z0-9][A-Z0-9./-]*\d[A-Z0-9./-]*)"
    r"(?:"
    r"\s*[: ]\s*(?:PART|PT)\s*\d+"
    r"(?:"
    r"\s*[: ]\s*(?:SEC(?:TION)?|CH(?:APTER)?)\s*\d+"
    r"|(?:\s*[-/]\s*)\d{1,2}"
    r")?"
    r"|(?:\s*-\s*\d{1,3}\s*-\s*\d{1,2})"
    r")?"
    r"\s*:\s*(?P<year>(?:19|20)\d{2})\b"
)
_JOINT_ADOPTION_RE = re.compile(
    r"(?i)\b(?:IS|BIS)\s*/\s*(?!PART\b|PT\b|SEC\b|SECTION\b)[A-Z]{2,}"
    r"|\b(?:IS|BIS)\s+(?!PART\b|PT\b|SEC\b|SECTION\b|AMD\b|REV\b)"
    r"[A-Z]{2,}\b"
)


def _reference_is_inside_parentheses(value: str, start: int) -> bool:
    return value.rfind("(", 0, start) > value.rfind(")", 0, start)


def _referenced_publishers(publisher: str, *, inside_parentheses: bool) -> List[str]:
    tokens = [
        token
        for token in re.split(r"\s*/\s*", re.sub(r"\s+", "", publisher).upper())
        if token and token not in _ADOPTION_QUALIFIER_WORDS
    ]
    if not tokens:
        return []
    if all(token in {"IS", "BIS"} for token in tokens):
        return tokens if inside_parentheses else []
    return [token for token in tokens if token not in {"IS", "BIS"}]


def extract_international_references(display_number: str) -> List[Dict]:
    """Extract an adopted edition named by a BIS designation.

    The adopted publisher can be any catalogue publisher, as in
    ``IS 12065 : 2025(IEC 60034-9 : 2021, MOD)``. A publisher, number, and
    year must all be present. The outer IS number itself is not a reference.
    """
    value = clean(display_number)
    references = []
    seen = set()
    for match in _ADOPTION_REFERENCE_RE.finditer(value):
        publishers = _referenced_publishers(
            match.group("sdo"),
            inside_parentheses=_reference_is_inside_parentheses(
                value,
                match.start(),
            ),
        )
        number = match.group("number").strip()
        part = match.group(0)[match.end("number"):match.start("year")]
        part = re.sub(r"\s*:\s*$", "", part).strip(" :")
        year = int(match.group("year"))
        for sdo_name in publishers:
            designation = " ".join(
                piece
                for piece in (f"{sdo_name} {number}", part, f": {year}")
                if piece
            )
            identity = parse_identity(sdo_name, designation)
            key = (
                sdo_name,
                identity.get("core_number"),
                identity.get("qualifier"),
                identity.get("year"),
            )
            if not key[1] or key in seen:
                continue
            seen.add(key)
            references.append(
                {
                    "sdo_name": sdo_name,
                    "designation": designation,
                    "identity": key,
                }
            )
    return references


def bis_names_another_standard(*values: str) -> bool:
    """A BIS adoption names another standard; a plain IS number does not."""
    text = " ".join(str(value or "") for value in values)
    if not text.strip():
        return False
    if extract_international_references(text):
        return True
    return bool(_JOINT_ADOPTION_RE.search(text))


def _full_variants(sdo: str, body: str) -> List[str]:
    body_variants = []
    for item in _qualifier_variants(body):
        body_variants.extend(_spacing_variants(item))

    variants = []
    prefixes = sdo_identifier_prefixes(sdo)
    for item in body_variants:
        # Unprefixed body helps rows stored without an SDO prefix (e.g. SP 72)
        # and spaced ASTM forms (D 1250 ...) hit exact/display lookups.
        variants.append(normalize_tokens(item))
        for prefix in prefixes:
            variants.append(normalize_tokens(f"{prefix} {item}"))
    return list(dict.fromkeys(v for v in variants if v))


def _expand_short_dual(core: str) -> str:
    """Restore a dropped letter in ``A29/29M`` so it matches ``A29/A29M``."""
    compact = re.sub(r"\s+", "", str(core))
    match = re.fullmatch(
        r"([A-Z]+)(\d+(?:\.\d+)*)/(\2)(M)?",
        compact,
        re.IGNORECASE,
    )
    if not match:
        return str(core)
    prefix, number, _, metric = match.groups()
    prefix = prefix.upper()
    suffix = (metric or "").upper()
    return f"{prefix}{number}/{prefix}{number}{suffix}"


def _primary_slash_alternative(core: str) -> str:
    """Use the first side of ``B36.19M/36.19`` and keep ``CEN/TR`` intact."""
    core = _expand_short_dual(core)
    if "/" not in str(core):
        return str(core)
    left, right = str(core).split("/", 1)
    left_compact = re.sub(r"\s+", "", left)
    right_compact = re.sub(r"\s+", "", right)
    # A991/A991M is one dual designation. B36.19M/36.19 is two alternatives.
    if left_compact and left_compact in right_compact:
        return str(core)
    # Joint documents such as MR0175/ISO 15156 keep both sides.
    if re.match(r"(?i)^(ISO|EN|IEC|NACE|SSPC)", right_compact):
        return str(core)
    if re.search(r"\d", left) and re.search(r"\d", right):
        return left
    return str(core)


def _cores_compatible(requested, candidate, requested_core, candidate_core) -> bool:
    """True when cores are the same designation despite formatting.

    Accepts a metric ``M`` suffix, a slash pair such as ``B36.19M/36.19``,
    and one extra two-digit extension such as ``75.05`` vs ``75.05.01``.
    """
    if requested_core == candidate_core:
        return True

    # ASTM paired designations such as E165/E165M are the same standard
    # family as the unpaired E165 request. The slash sides are metric/unit
    # variants, not two unrelated standards.
    if normalize_tokens(requested.get("sdo_name")) == "ASTM":
        for identity, other_core in (
            (requested, candidate_core),
            (candidate, requested_core),
        ):
            pattern = str(identity.get("core_number_pattern") or "")
            if "/" not in pattern:
                continue
            for piece in pattern.split("/"):
                piece_core = normalize_identity_core(piece)
                if piece_core == other_core or re.sub(r"M$", "", piece_core) == re.sub(r"M$", "", other_core):
                    return True

    def _without_metric(core: str) -> str:
        return re.sub(r"M$", "", core)

    if (
        _without_metric(requested_core)
        and _without_metric(requested_core) == _without_metric(candidate_core)
    ):
        return True

    if normalize_tokens(requested.get("sdo_name")) == "IEC":
        requested_pattern = normalize_tokens(
            requested.get("core_number_pattern") or ""
        )
        legacy_number = normalize_identity_core(requested_pattern)
        if (
            re.fullmatch(r"\d{3}(?:[-./]\d+)*", requested_pattern)
            and candidate_core == f"60{legacy_number}"
        ):
            return True

    pattern = str(requested.get("core_number_pattern") or "")
    if "/" in pattern:
        for piece in pattern.split("/"):
            piece_core = _without_metric(normalize_identity_core(piece))
            if piece_core and piece_core == _without_metric(candidate_core):
                return True

    requested_part = re.fullmatch(
        r"PART:(\d+)",
        str(requested.get("qualifier") or ""),
    )
    if (
        requested_part
        and candidate_core.startswith(requested_core)
        and candidate_core[len(requested_core):].isdigit()
        and candidate_core[len(requested_core):] != requested_part.group(1)
    ):
        return False

    requested_part_number = re.fullmatch(
        r"(?P<base>.+PART)(?P<part>\d+)",
        requested_core,
    )
    candidate_part_number = re.fullmatch(
        r"(?P<base>.+PART)(?P<part>\d+)",
        candidate_core,
    )
    if (
        requested_part_number
        and candidate_part_number
        and requested_part_number.group("base") == candidate_part_number.group("base")
        and requested_part_number.group("part") != candidate_part_number.group("part")
    ):
        # Part 3 is not part 30. The digit-extension rule below must not
        # treat the shorter part number as a prefix.
        return False

    if (
        len(requested_core) >= 4
        and candidate_core.startswith(requested_core)
        and candidate_core[len(requested_core):].isdigit()
        and len(candidate_core) - len(requested_core) <= 2
    ):
        return True

    if (
        len(requested_core) >= 4
        and re.fullmatch(rf"{re.escape(requested_core)}P\d+", candidate_core)
    ):
        return True

    if (
        normalize_tokens(requested.get("sdo_name")) == "SAE"
        and re.fullmatch(rf"{re.escape(requested_core)}[A-Z]", candidate_core)
    ):
        return True

    if normalize_tokens(requested.get("sdo_name")) in {"BS", "BSI"}:
        adopted = re.fullmatch(r"(?:EN|ISO|IEC)+(\d{4,})", candidate_core)
        if adopted and adopted.group(1) == requested_core:
            return True

    if (
        normalize_tokens(requested.get("sdo_name")) == "ISA"
        and requested_core.startswith("S")
        and requested_core[1:]
        and candidate_core.startswith(requested_core[1:])
    ):
        return True

    return False


def identity_matches(
    requested: Dict,
    candidate: Dict,
    *,
    check_year: bool = True,
) -> bool:
    """Compare two parsed identities without assuming a designation change.

    The SDO and core identity must agree. A requested edition must also agree
    when the candidate exposes an edition. Qualifiers remain meaningful, so a
    PART/SECTION/SERIES mismatch is not silently accepted.
    """
    if normalize_tokens(requested.get("sdo_name")) != normalize_tokens(candidate.get("sdo_name")):
        return False

    requested_core = normalize_identity_core(
        requested.get("core_number") or requested.get("core")
    )
    candidate_core = normalize_identity_core(
        candidate.get("core_number") or candidate.get("core")
    )
    if not requested_core:
        return False

    if requested.get("family_lookup"):
        if not candidate_core.startswith(requested_core):
            return False
    elif not _cores_compatible(requested, candidate, requested_core, candidate_core):
        if not _jis_optional_department_match(
            requested.get("sdo_name"),
            requested_core,
            candidate_core,
        ):
            return False

    requested_qualifier = requested.get("qualifier")
    candidate_qualifier = candidate.get("qualifier")
    if normalize_tokens(requested.get("sdo_name")) in {"IS", "BIS"}:
        requested_qualifier = _normalize_bis_roman_part(
            requested_qualifier
        )
        candidate_qualifier = _normalize_bis_roman_part(
            candidate_qualifier
        )
    if requested.get("family_lookup") and requested.get("qualifier") != "SERIES":
        if (
            candidate_qualifier is not None
            and not candidate_qualifier.startswith("PART:")
            and not candidate_qualifier.startswith("SECTION:")
            and not str(candidate_qualifier).startswith("SERIES")
        ):
            return False
    elif requested.get("qualifier") == "SERIES":
        if not (
            candidate_core == requested_core
            or (
                candidate_core.startswith(requested_core)
                and len(candidate_core) > len(requested_core)
                and candidate_core[len(requested_core)].isdigit()
            )
        ):
            return False
    elif requested_qualifier in {
        "PART",
        "SECTION",
        "CHAPTER",
        "SERIES",
    }:
        if candidate_qualifier is not None and not candidate_qualifier.startswith(
            f"{requested_qualifier}:"
        ):
            return False
    elif (
        requested_qualifier is None
        and candidate_qualifier == "SERIES"
    ):
        pass
    elif _qualifier_range_covers(requested_qualifier, candidate_qualifier or ""):
        pass
    elif requested_qualifier != candidate_qualifier:
        return False

    requested_year = requested.get("year")
    candidate_year = candidate.get("year")
    if check_year and requested_year is not None and candidate_year is not None:
        return requested_year == candidate_year

    # If one side has an explicit year and the other does not, the caller may
    # resolve the edition through the master table. Do not reject solely on
    # that basis here.
    return True


def standard_number_year(standard_number: str) -> Optional[int]:
    """Best-effort extraction of an edition year from database standardno.

    Four-digit years are authoritative. Two-digit suffixes such as '-25' are
    interpreted as 20xx only when they appear at the end of an identifier.
    """
    value = clean(standard_number)
    four = re.search(r"(?:^|[^0-9])((?:19|20)\d{2})$", value)
    if four:
        return int(four.group(1))
    two = re.search(r"(?:^|[-./ ])(\d{2})$", value)
    if two:
        n = int(two.group(1))
        if 0 <= n <= 99:
            return 2000 + n if n <= 49 else 1900 + n
    return None
