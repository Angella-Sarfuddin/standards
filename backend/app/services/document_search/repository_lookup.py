"""Repository lookups used by the document-search workflow."""

from app.core.standard_formatter import normalize_display_number
from app.core.standard_identity import normalize_tokens


def row_has_display_candidates(row, candidate_map):
    """Whether a request has candidates for any normalized display variant."""
    sdo_id = row.get("sdo_id")

    if not sdo_id:
        return False

    for variant in row["identity"].get("variants", []):
        if candidate_map.get((sdo_id, normalize_tokens(variant))):
            return True

    return False


def direct_candidate_lists(
    row,
    candidate_map,
    exact_result_map,
    normalized_result_map,
    standard_number_map,
):
    """Collect the four direct candidate groups for a prepared request."""
    display_candidates = []

    for variant in row["identity"].get("variants", []):
        candidate_key = (
            row["sdo_id"],
            normalize_tokens(variant),
        )
        display_candidates.extend(candidate_map.get(candidate_key, []))

    full_display_number = row["full_display_number"]

    exact_key = (
        row["sdo_id"],
        normalize_display_number(full_display_number),
    )
    normalized_key = (
        row["sdo_id"],
        normalize_tokens(full_display_number).replace(" ", ""),
    )
    standard_number_key = (
        row["sdo_id"],
        normalize_display_number(full_display_number),
    )

    return (
        display_candidates,
        exact_result_map.get(exact_key, []),
        normalized_result_map.get(normalized_key, []),
        standard_number_map.get(standard_number_key, []),
    )


def lookup_display_candidates(
    prepared_rows,
    repository,
    enrichment_repository,
    is_api_request,
):
    """Fetch display-number candidates and group them without reordering."""
    display_pairs = []

    for row in prepared_rows:
        if not row["sdo_id"]:
            continue

        for variant in row["identity"].get("variants", []):
            display_pairs.append((row["sdo_id"], variant))

    display_pairs = list(dict.fromkeys(display_pairs))
    display_candidates = repository.search_by_sdo_and_display_variants(
        display_pairs
    )

    # API's legacy search table may contain an ACTIVE duplicate while its
    # master catalogue marks that same edition Historical/Withdrawn. Include
    # those master rows in the common candidate selection path.
    api_master_pairs = [
        (row["sdo_id"], variant)
        for row in prepared_rows
        if is_api_request(row) and row.get("sdo_id")
        for variant in row["identity"].get("variants", [])
    ]
    if api_master_pairs:
        display_candidates.extend(
            enrichment_repository.search_master_by_sdo_and_display_variants(
                api_master_pairs
            )
        )

    candidate_map = {}
    for standard in display_candidates:
        key = (
            standard.sdo_id,
            normalize_tokens(standard.display_stdNo or ""),
        )
        candidate_map.setdefault(key, []).append(standard)

    return display_candidates, candidate_map


def lookup_number_candidates(
    prepared_rows,
    candidate_map,
    repository,
    row_has_display_candidates,
):
    """Fetch exact, normalized, and standard-number lookup candidates."""
    exact_pairs = []
    normalized_pairs = []

    for row in prepared_rows:
        if not row["sdo_id"]:
            continue

        if row_has_display_candidates(row, candidate_map):
            continue

        full = row["full_display_number"]
        exact_pairs.append((row["sdo_id"], full))
        normalized_pairs.append(
            (
                row["sdo_id"],
                normalize_tokens(full).replace(" ", ""),
            )
        )

    exact_pairs = list(dict.fromkeys(exact_pairs))
    normalized_pairs = list(dict.fromkeys(normalized_pairs))

    exact_results = repository.search_by_sdo_and_display_numbers(exact_pairs)
    normalized_results = repository.search_by_sdo_and_normalized_numbers(
        normalized_pairs
    )
    standard_number_results = repository.search_by_sdo_and_standard_numbers(
        exact_pairs
    )

    return exact_results, normalized_results, standard_number_results
