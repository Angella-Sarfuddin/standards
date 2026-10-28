"""Lookup indexes for exact, normalized, and standard-number results."""

from app.core.standard_formatter import normalize_display_number
from app.core.standard_identity import normalize_tokens


def build_lookup_indexes(
    exact_results,
    normalized_results,
    standard_number_results,
):
    exact_result_map = {}

    for standard in exact_results:
        key = (
            standard.sdo_id,
            normalize_display_number(standard.display_stdNo or ""),
        )
        exact_result_map.setdefault(key, []).append(standard)

    normalized_result_map = {}

    for standard in normalized_results:
        key = (
            standard.sdo_id,
            normalize_tokens(standard.stdNo_normalized or "").replace(" ", ""),
        )
        normalized_result_map.setdefault(key, []).append(standard)

    standard_number_map = {}

    for standard in standard_number_results:
        key = (
            standard.sdo_id,
            normalize_display_number(standard.standardno or ""),
        )
        standard_number_map.setdefault(key, []).append(standard)

    return exact_result_map, normalized_result_map, standard_number_map
