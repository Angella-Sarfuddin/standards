import re
from typing import Dict, List, Optional, Tuple


YEAR_RE = re.compile(r"(?:^|[\s:()\[\]{},./-])((?:19|20)\d{2})\s*$")
REAFFIRMATION_RE = re.compile(
    r"\s*\(\s*R\s*(?:19|20)\d{2}\s*\)\s*$",
    re.IGNORECASE,
)
WITHDRAWAL_RE = re.compile(
    r"\s*/\s*(?:WITHDRAWN|OBSOLETE|SUPERSEDED)\s*$",
    re.IGNORECASE,
)
LANGUAGE_SUFFIX_RE = re.compile(
    r"\s*(?:/\s*EN\s*[-/]\s*FR|\(\s*EN\s*[-/]\s*FR\s*\))\s*$",
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
    "MPMS",
    "BUL",
    "BULL",
    "BULLETIN",
    "PUB",
    "PUBLICATION",
    "GUIDE",
}

SDO_IDENTIFIER_PREFIX_ALIASES = {
    "ISO": ("ISO/IEC", "ISO/TS", "ISO/TR"),
    "BSI": ("BS", "BS EN", "BS EN ISO", "PD", "PD CEN", "PD CEN/TR"),
    "BIS": ("IS", "BIS"),
    "IS": ("IS", "BIS"),
}

QUALIFIER_RE = re.compile(
    r"\b(?P<label>PARTS?|PT|SECTION|SEC|CHAPTER|CH|SERIES|SER)\b"
    r"(?:(?:\s*[:/.-]\s*|\s+)"
    r"(?P<value>[A-Z0-9]+(?:\s*(?:-|–|—|/|TO|THRU|THROUGH|\.)\s*[A-Z0-9]+)*)?)?\s*$",
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
    """Keep identifier characters literal and wildcard only separators."""
    return re.sub(r"[^A-Z0-9]+", "%", normalize_tokens(value)).strip("%")


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


def like_pattern_is_prefix_indexable(pattern: str) -> bool:
    """True when LIKE can use a leftmost prefix (no early `%`)."""
    text = str(pattern or "")
    wildcard_at = text.find("%")
    if wildcard_at < 0:
        return True
    return text[wildcard_at:].replace("%", "") == ""


def identity_core_appears(normalized_value: str, core: str) -> bool:
    """True when ``core`` appears without a longer leading numeric prefix.

    Rejects ``1610`` for core ``610`` (leading digit extension) while allowing
    trailing edition/part digits such as ``6102020`` from ``610:2020`` or
    ``8751`` from ``875-1``. Selective SQL patterns already exclude most
    supersets such as ``6100``.
    """
    value = normalize_identity_core(normalized_value)
    core = normalize_identity_core(core)
    if not value or not core:
        return False

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
    return tuple(
        dict.fromkeys(
            (sdo, *SDO_IDENTIFIER_PREFIX_ALIASES.get(sdo, ()))
        )
    ) if sdo else ()


def extract_year(value: str) -> Tuple[str, Optional[int]]:
    value = REAFFIRMATION_RE.sub("", clean(value)).rstrip()
    match = YEAR_RE.search(value)
    if not match:
        return value, None
    year = int(match.group(1))
    body = value[:match.start()].strip(" :.,-()[]{}")
    return body, year


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


def parse_identity(sdo_name: str, display_number: str) -> Dict:
    sdo = clean(sdo_name).upper()
    value = clean(display_number)

    value = WITHDRAWAL_RE.sub("", value).rstrip()
    value = LANGUAGE_SUFFIX_RE.sub("", value).rstrip()
    series_marker = bool(SERIES_SUFFIX_RE.search(value))
    if series_marker:
        value = SERIES_SUFFIX_RE.sub("", value).rstrip()

    body, year = extract_year(value)
    body = normalize_tokens(body)

    # Publisher names may differ from identifier prefixes (BSI -> BS EN,
    # BIS -> IS), and some identifiers use compound prefixes (ISO/IEC).
    normalized_sdo = normalize_tokens(sdo)
    identifier_prefix = normalized_sdo
    prefix_removed = False
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
            break

    if not prefix_removed and normalized_sdo:
        body = re.sub(
            rf"^{re.escape(normalized_sdo)}(?:\s+|\s*[-:/]\s*|(?=\d))",
            "",
            body,
            flags=re.IGNORECASE,
        )
        body = body.strip(" :.,-/")

    designation, core = _split_designation(body)
    core = VOLUME_SUFFIX_RE.sub("", core).rstrip(" -./")

    # Qualifiers are identity-bearing; only designation tokens are ignored.
    core_number = core
    qualifier = None
    family_lookup = False
    core = re.sub(
        r"(?i)(PART|PT|SECTION|SEC|CHAPTER|CH|SERIES|SER)(\d+)$",
        r"\1 \2",
        core,
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
            r"\s*(?:[-–—/.:]|TO|THRU|THROUGH)\s*",
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
            r"^(?P<base>.+?)(?P<separator>[-./])(?P<part>\d+)$",
            core,
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
                and len(implicit_part.group("part")) > 1
            )
        ):
            core_number = implicit_part.group("base")
            qualifier = f"PART:{implicit_part.group('part')}"

    if series_marker:
        qualifier = "SERIES"
        family_lookup = True

    if sdo == "ASME" and re.match(r"^B\d", core_number, re.IGNORECASE):
        core_number = core_number[1:]

    if (
        sdo == "MSS"
        and designation == "SP"
        and core_number.isdigit()
    ):
        core_number = str(int(core_number))

    return {
        "sdo_name": sdo,
        "body": body,
        "designation": designation,
        "core": core,
        "core_number": normalize_identity_core(core_number),
        "core_number_pattern": normalize_tokens(core_number),
        "qualifier": qualifier,
        "family_lookup": family_lookup,
        "year": year,
        "full_base": normalize_tokens(f"{sdo} {body}"),
        "identifier_prefix": identifier_prefix,
        "variants": _full_variants(sdo, body),
    }


def _full_variants(sdo: str, body: str) -> List[str]:
    body_variants = _qualifier_variants(body)
    variants = []
    prefixes = sdo_identifier_prefixes(sdo)
    for item in body_variants:
        for prefix in prefixes:
            variants.append(normalize_tokens(f"{prefix} {item}"))
    return list(dict.fromkeys(v for v in variants if v))


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
    elif requested_core != candidate_core:
        return False

    requested_qualifier = requested.get("qualifier")
    candidate_qualifier = candidate.get("qualifier")
    if requested.get("family_lookup"):
        if (
            candidate_qualifier is not None
            and not candidate_qualifier.startswith("PART:")
            and candidate_qualifier != "SERIES"
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


def standard_number_year(standard_number: str):
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
