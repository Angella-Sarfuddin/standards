import re

from app.core.standard_identity import sdo_identifier_prefixes


def normalize_display_number(value: object) -> str:
    if not value:
        return ""

    value = str(value).strip()
    return re.sub(r"\s+", " ", value)


def remove_draft_marker(value: object) -> object:
    """Remove a trailing catalogue ``(DRAFT)`` label from display text."""
    if value is None:
        return value
    value = str(value).strip()
    value = re.sub(
        r"(?i)\s*\(\s*DRAFT\s*\)(?=\s*(?::|$))",
        "",
        value,
    )
    return re.sub(r"\s+", " ", value).strip()


def build_full_display_number(sdo_name: object, displaystdno: object) -> str:
    sdo_name = normalize_display_number(sdo_name)
    displaystdno = normalize_display_number(displaystdno)

    if not sdo_name:
        return displaystdno

    if not displaystdno:
        return sdo_name

    identifier_prefixes = sdo_identifier_prefixes(sdo_name)
    if any(
        displaystdno.upper() == prefix.upper()
        or displaystdno.upper().startswith(prefix.upper() + " ")
        or displaystdno.upper().startswith(prefix.upper() + "/")
        for prefix in identifier_prefixes
    ):
        return displaystdno

    default_prefix = (
        identifier_prefixes[1]
        if len(identifier_prefixes) > 1
        else sdo_name
    )
    return f"{default_prefix} {displaystdno}"
