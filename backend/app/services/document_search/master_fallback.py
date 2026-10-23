"""Master-catalogue fallback orchestration for document search."""

import time

from app.services.document_search.selection_context import use_candidate_status_map

from app.utils.standard_identity import (
    identity_lookup_core_tokens,
    normalize_identity_core,
    normalize_tokens,
)


def find_master_matches(
    unresolved_rows,
    enrichment_repository,
    is_tema_edition_request,
    masters_satisfy_row,
    display_masters_satisfy,
    unique_standards,
    build_identity_candidate_index,
    master_candidate_matches_identity,
    candidate_is_part_of_root,
    select_master_candidates,
):
    """Run the existing master fallback queries and collect row matches."""
    if not unresolved_rows:
        return {}

    # --------------------------------------------------------
    # Display-number candidates
    # --------------------------------------------------------

    pairs = []

    for row in unresolved_rows:

        for variant in row[
            "identity"
        ].get(
            "variants",
            [],
        ):

            pairs.append(
                (
                    row["sdo_id"],
                    variant,
                )
            )

    pairs = list(
        dict.fromkeys(pairs)
    )

    stage_started = time.perf_counter()
    masters = (
        enrichment_repository
        .search_master_by_sdo_and_display_variants(
            pairs
        )
    )
    print(
        f"[SEARCH TIMING] Master display query: "
        f"{time.perf_counter() - stage_started:.3f}s | "
        f"pairs={len(pairs)} candidates={len(masters)}"
    )

    # --------------------------------------------------------
    # Exact standardno candidates (narrower than identity LIKE)
    # --------------------------------------------------------

    standard_pairs = list(pairs)
    for row in unresolved_rows:
        full = row.get("full_display_number")
        if row.get("sdo_id") and full:
            standard_pairs.append((row["sdo_id"], full))

    standard_pairs = list(dict.fromkeys(standard_pairs))

    stage_started = time.perf_counter()
    standard_masters = (
        enrichment_repository
        .search_master_by_sdo_and_standard_numbers(
            standard_pairs
        )
    )
    masters.extend(standard_masters)
    tema_latest_by_sdo = {}
    for row in unresolved_rows:
        if not is_tema_edition_request(row):
            continue
        sdo_id = row.get("sdo_id")
        if sdo_id and sdo_id not in tema_latest_by_sdo:
            tema_latest_by_sdo[sdo_id] = (
                enrichment_repository.get_latest_tema_edition(sdo_id)
            )
    masters.extend(
        candidate
        for candidate in tema_latest_by_sdo.values()
        if candidate is not None
    )
    status_lookup = getattr(
        enrichment_repository,
        "get_standard_status_map",
        None,
    )
    master_status_map = (
        status_lookup(
            {
                getattr(candidate, "status_id", None)
                for candidate in masters
            }
        )
        if callable(status_lookup)
        else {}
    )
    print(
        f"[SEARCH TIMING] Master standardno query: "
        f"{time.perf_counter() - stage_started:.3f}s | "
        f"pairs={len(standard_pairs)} candidates={len(standard_masters)}"
    )

    # --------------------------------------------------------
    # Identity-hint candidates (only rows still unresolved)
    # --------------------------------------------------------

    identity_hints = []

    display_grouped = {}

    for master in masters:
        display_grouped.setdefault(
            (
                master.sdo_id,
                normalize_tokens(master.display_stdNo or ""),
            ),
            [],
        ).append(master)
        display_grouped.setdefault(
            (
                master.sdo_id,
                normalize_tokens(master.standardno or ""),
            ),
            [],
        ).append(master)

    for row in unresolved_rows:
        row_masters = []
        for variant in row["identity"].get("variants", []):
            row_masters.extend(
                display_grouped.get(
                    (
                        row["sdo_id"],
                        normalize_tokens(variant),
                    ),
                    [],
                )
            )
        full = row.get("full_display_number")
        if full:
            row_masters.extend(
                display_grouped.get(
                    (
                        row["sdo_id"],
                        normalize_tokens(full),
                    ),
                    [],
                )
            )
        row_masters = unique_standards(row_masters)

        if row.get("skip_master_identity"):
            # Local match already covers the response; keep only the
            # cheap display/standardno masters gathered above.
            continue

        if masters_satisfy_row(
            row,
            row_masters,
            master_status_map,
        ):
            continue

        if display_masters_satisfy(
            row,
            display_grouped,
            master_status_map,
        ):
            continue

        core = (
            row["identity"].get("core_number_pattern")
            or row["identity"].get("core_number")
            or ""
        ).split("/", 1)[0]

        if not core:
            continue

        # Query without a year filter once; edition selection stays in
        # Python. This replaces the previous year-pass + year-stripped
        # second LIKE scan with a single identity lookup per core.
        search_sdo_name = (
            row.get("search_sdo_name") or row["sdo_name"]
        )
        identity_hints.extend(
            (
                row["sdo_id"],
                search_sdo_name,
                lookup_core,
                None,
            )
            for lookup_core in identity_lookup_core_tokens(
                search_sdo_name,
                core,
            )
        )

    identity_hints = list(
        dict.fromkeys(
            identity_hints
        )
    )

    stage_started = time.perf_counter()
    if identity_hints:
        identity_masters = (
            enrichment_repository
            .search_master_by_sdo_and_identity_hints(
                identity_hints
            )
        )
    else:
        identity_masters = []

    masters.extend(identity_masters)
    additional_status_ids = {
        getattr(candidate, "status_id", None)
        for candidate in identity_masters
    } - set(master_status_map)
    if additional_status_ids:
        master_status_map.update(
            enrichment_repository.get_standard_status_map(
                additional_status_ids
            )
        )
    print(
        f"[SEARCH TIMING] Master identity query: "
        f"{time.perf_counter() - stage_started:.3f}s | "
        f"hints={len(identity_hints)} candidates={len(identity_masters)}"
    )

    # --------------------------------------------------------
    # Group master candidates
    # --------------------------------------------------------

    grouped = {}

    for master in masters:

        key = (
            master.sdo_id,
            normalize_tokens(
                master.display_stdNo or ""
            ),
        )

        grouped.setdefault(
            key,
            [],
        ).append(master)

    # --------------------------------------------------------
    # Select master for each unresolved row
    # --------------------------------------------------------

    matches = {}
    master_identity_index = (
        build_identity_candidate_index(
            masters,
            unresolved_rows,
        )
    )
    stage_started = time.perf_counter()

    for row in unresolved_rows:

        candidates = []

        # ----------------------------------------------------
        # Display variants
        # ----------------------------------------------------

        for variant in row[
            "identity"
        ].get(
            "variants",
            [],
        ):

            candidates.extend(
                grouped.get(
                    (
                        row["sdo_id"],
                        normalize_tokens(
                            variant
                        ),
                    ),
                    [],
                )
            )

        # ----------------------------------------------------
        # Designation-neutral candidates
        # ----------------------------------------------------

        core = row[
            "identity"
        ].get(
            "core_number"
        )

        if core:

            normalized_core = normalize_identity_core(
                core
            )

            possible_masters = (
                master_identity_index.get(
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

            for master in possible_masters:

                if (
                    master_candidate_matches_identity(master, row)
                    or candidate_is_part_of_root(master, row)
                ):
                    candidates.append(
                        master
                    )

        if is_tema_edition_request(row):
            latest_tema_edition = tema_latest_by_sdo.get(row.get("sdo_id"))
            if latest_tema_edition is not None:
                candidates.append(latest_tema_edition)

        with use_candidate_status_map(master_status_map):
            selected = select_master_candidates(
                candidates,
                row,
            )

        if selected:
            matches[row["request_key"]] = selected

    print(
        f"[SEARCH TIMING] Master candidate selection: "
        f"{time.perf_counter() - stage_started:.3f}s"
    )

    return matches
