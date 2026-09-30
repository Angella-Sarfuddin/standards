import re


def normalize_standard_number(value: str) -> str:
    if not value:
        return ""

    value = value.upper().strip()

    # Normalize repeated whitespace
    value = re.sub(r"\s+", "", value)

    return value