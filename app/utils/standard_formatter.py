import re

from app.utils.standard_identity import sdo_identifier_prefixes


def normalize_display_number(value):
    if not value:
        return ""

    value = str(value).strip()
    return re.sub(r"\s+", " ", value)


def build_full_display_number(sdo_name, displaystdno):
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