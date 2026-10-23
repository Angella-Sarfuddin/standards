"""Identity-hint candidate discovery for document searches."""

from app.utils.standard_identity import (
    identity_index_cores,
    identity_lookup_core_tokens,
    normalize_identity_core,
    normalize_tokens,
    parse_identity,
)


def discover_identity_candidates(identity_lookup_rows, repository):
    """Find and index candidates for rows requiring identity discovery."""
    identity_hints = []

    for row in identity_lookup_rows:
        identity = row["identity"]
        core = (
            identity.get("core_number_pattern")
            or identity.get("core_number")
            or ""
        ).split("/", 1)[0]

        if not core:
            continue

        search_sdo_name = (
            row.get("search_sdo_name") or row["sdo_name"]
        )
        identity_hints.extend(
            (
                row["sdo_id"],
                search_sdo_name,
                lookup_core,
            )
            for lookup_core in identity_lookup_core_tokens(
                search_sdo_name,
                core,
            )
        )

    identity_hints = list(dict.fromkeys(identity_hints))
    identity_candidates = repository.search_by_sdo_and_identity_hints(
        identity_hints
    )
    identity_candidate_index = build_identity_candidate_index(
        identity_candidates,
        identity_lookup_rows,
    )
    return identity_hints, identity_candidates, identity_candidate_index


def build_identity_candidate_index(candidates, rows):
    sdo_names_by_id = {}

    for row in rows:
        sdo_id = row.get("sdo_id")
        sdo_name = row.get("search_sdo_name") or row.get("sdo_name")

        if sdo_id and sdo_name:
            sdo_names_by_id.setdefault(
                sdo_id,
                set(),
            ).add(sdo_name)

    index = {}

    for candidate in candidates:
        sdo_names = sdo_names_by_id.get(
            candidate.sdo_id,
            (),
        )

        for sdo_name in sdo_names:
            for value in (
                candidate.display_stdNo or "",
                candidate.standardno or "",
            ):
                if not value:
                    continue

                candidate_identity = parse_identity(
                    sdo_name,
                    value,
                )
                candidate_core = normalize_identity_core(
                    candidate_identity.get("core_number")
                    or candidate_identity.get("core")
                    or ""
                )

                if not candidate_core:
                    continue

                for index_core in identity_index_cores(
                    sdo_name,
                    candidate_core,
                    candidate_identity.get("core_number_pattern") or "",
                ):
                    key = (
                        candidate.sdo_id,
                        normalize_tokens(sdo_name),
                        index_core,
                    )
                    index.setdefault(key, {})[
                        candidate.id
                    ] = candidate

    return index
