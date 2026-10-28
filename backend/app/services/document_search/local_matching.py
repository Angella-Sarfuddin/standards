"""Orchestrate local candidate discovery and matching for document search."""

import time

from app.services.document_search import identity_discovery
from app.services.document_search.selection_context import use_candidate_status_map
from app.core.standard_identity import normalize_identity_core, normalize_tokens


def match_local_standards(
    prepared_rows,
    display_candidates,
    exact_results,
    normalized_results,
    standard_number_results,
    candidate_map,
    exact_result_map,
    normalized_result_map,
    standard_number_map,
    repository,
    enrichment_repository,
    unique_standards,
    direct_candidate_lists,
    select_candidate,
    row_needs_identity_discovery,
    candidate_matches_identity,
    candidate_is_part_of_root,
    select_candidates,
    is_bare_qualifier_request,
):
    """Find local matches while retaining the service's established ordering."""
    direct_candidate_pool = unique_standards(
        [
            *display_candidates,
            *exact_results,
            *normalized_results,
            *standard_number_results,
        ]
    )
    direct_status_map = enrichment_repository.get_standard_status_map(
        {
            getattr(candidate, "status_id", None)
            for candidate in direct_candidate_pool
        }
    )

    unique_prepared_rows = {}

    for row in prepared_rows:
        unique_prepared_rows.setdefault(
            row["request_key"],
            row,
        )

    identity_lookup_rows = []

    for row in unique_prepared_rows.values():
        if not row["sdo_id"]:
            continue

        direct_candidates_by_lookup = direct_candidate_lists(
            row,
            candidate_map,
            exact_result_map,
            normalized_result_map,
            standard_number_map,
        )
        direct_candidates = unique_standards(
            [
                candidate
                for candidates in direct_candidates_by_lookup
                for candidate in candidates
            ]
        )
        with use_candidate_status_map(direct_status_map):
            selected_direct = select_candidate(
                direct_candidates,
                row,
            )

        # Designation-neutral LIKE is only for rows that still lack a
        # usable local match, or that need family/bare-qualifier
        # expansion from additional identity candidates.
        if row_needs_identity_discovery(row, selected_direct):
            identity_lookup_rows.append(row)

    stage_started = time.perf_counter()
    (
        identity_hints,
        identity_candidates,
        identity_candidate_index,
    ) = identity_discovery.discover_identity_candidates(
        identity_lookup_rows,
        repository,
    )

    local_candidate_pool = unique_standards(
        [
            *display_candidates,
            *exact_results,
            *normalized_results,
            *standard_number_results,
            *identity_candidates,
        ]
    )
    additional_local_status_ids = {
        getattr(candidate, "status_id", None)
        for candidate in identity_candidates
    } - set(direct_status_map)
    local_status_map = dict(direct_status_map)
    if additional_local_status_ids:
        local_status_map.update(
            enrichment_repository.get_standard_status_map(
                additional_local_status_ids
            )
        )

    print(
        f"[SEARCH TIMING] Identity lookup: "
        f"{time.perf_counter() - stage_started:.3f}s | "
        f"hints={len(identity_hints)} | "
        f"candidates={len(identity_candidates)}"
    )

    # --------------------------------------------------------
    # 6. LOCAL MATCHING
    # --------------------------------------------------------

    stage_started = time.perf_counter()

    local_matches = {}
    unresolved = []

    for row in unique_prepared_rows.values():

        key = row["request_key"]

        if not row["sdo_id"]:
            continue

        display_row_candidates, exact_candidates, normalized_candidates, standard_candidates = (
            direct_candidate_lists(
                row,
                candidate_map,
                exact_result_map,
                normalized_result_map,
                standard_number_map,
            )
        )

        candidates = list(display_row_candidates)

        # ----------------------------------------------------
        # Designation-neutral candidates
        # ----------------------------------------------------

        identity = row["identity"]

        core = identity.get(
            "core_number"
        )

        if core:

            normalized_core = normalize_identity_core(
                core
            )

            possible_identity_candidates = (
                identity_candidate_index.get(
                    (
                        row["sdo_id"],
                        normalize_tokens(
                            row.get("search_sdo_name") or row["sdo_name"]
                        ),
                        normalized_core,
                    ),
                    {},
                ).values()
            )

            for candidate in possible_identity_candidates:

                if (
                    candidate.sdo_id
                    != row["sdo_id"]
                ):
                    continue

                if (
                    candidate_matches_identity(candidate, row)
                    or candidate_is_part_of_root(candidate, row)
                ):
                    candidates.append(
                        candidate
                    )

        candidates.extend(exact_candidates)
        candidates.extend(normalized_candidates)
        candidates.extend(standard_candidates)

        # ----------------------------------------------------
        # Remove duplicates
        # ----------------------------------------------------

        candidates = unique_standards(
            candidates
        )

        with use_candidate_status_map(local_status_map):
            selected = select_candidates(
                candidates,
                row,
            )

        if selected:
            local_matches[key] = selected
            if is_bare_qualifier_request(row):
                # Local family/bare-qualifier match is already
                # authoritative for the response. Still consult master
                # via cheap display/standardno IN lookups for edition
                # enrichment, but skip the expensive identity LIKE scan.
                unresolved.append(
                    {
                        **row,
                        "skip_master_identity": (
                            row["identity"].get("qualifier")
                            != "SERIES"
                        ),
                    }
                )
            else:
                # Local display-number matches cannot establish that the
                # selected edition is the newest available. Consult the
                # master catalogue even when an older requested year has
                # an exact local match.
                unresolved.append(row)
        else:
            unresolved.append(row)

    print(
        f"[SEARCH TIMING] Local matching: "
        f"{time.perf_counter() - stage_started:.3f}s"
    )

    return unique_prepared_rows, local_matches, unresolved
