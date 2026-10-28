import re


def alphanumeric_upper(value: object) -> str:
    """Uppercase and keep only letters and digits.

    This is the catalogue-key form. Identity parsing uses
    ``normalize_tokens`` first, so the two must stay separate.
    """
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def normalize_standard_number(value: str) -> str:
    if not value:
        return ""

    value = value.upper().strip()

    # Normalize repeated whitespace
    value = re.sub(r"\s+", "", value)

    return value