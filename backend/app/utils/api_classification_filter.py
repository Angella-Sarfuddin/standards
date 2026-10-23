import re


# The API catalogue links some publications to broad cross-topic groups as
# well as their specific subject category. Keep the catalogue category that
# best fits each known multi-classified title.
API_PREFERRED_CLASSIFICATIONS = {
    "APISTD650": "8",
    "APISTD623": "8",
    "APISTD1164": "7",
    "APIRP500": "8",
    "APIRP575": "8",
    "APIRP651": "8",
    "APIRP652": "8",
    "APIPUBL346": "2",
    "APIRP54": "9",
    "APISPEC12P": "8",
}


def filter_api_classifications(standard_number, classifications):
    """Return only the relevant API category for known multi-category rows."""
    number = re.sub(r"[^A-Z0-9]", "", str(standard_number or "").upper())
    number = re.sub(r"(?:19|20)\d{2}.*$", "", number)
    number = re.sub(r"(?:STANDARD)?REVISIONTRACKER$", "", number)
    preferred_code = API_PREFERRED_CLASSIFICATIONS.get(number)
    if preferred_code is None:
        return classifications if classifications is not None else []

    selected = []
    for classification in classifications or []:
        code = re.sub(
            r"[^0-9]",
            "",
            str(classification.get("code") or ""),
        )
        if code == preferred_code:
            selected.append(classification)

    return selected or list(classifications or [])
