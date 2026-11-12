"""Identity-hint candidate discovery for document searches."""

from app.core.standard_identity import (
    canonicalize_search_request,
    designation_is_ieee_iec_dual_logo,
    identity_index_cores,
    identity_lookup_core_tokens,
    identity_pattern_prefix,
    ieee_iec_joint_request,
    normalize_identity_core,
    normalize_tokens,
    parse_identity,
)
from app.core.standard_expression_parser import StandardExpressionParser


def candidate_sdo_names(sdo_name, displaystdno, *, service_class):
    """Return plausible SDO aliases for one request's identity fields."""
    candidates = set()
    raw_sdo = str(sdo_name or "").strip()
    raw_display = str(displaystdno or "").strip()

    if raw_sdo:
        candidates.add(raw_sdo)

    if service_class._is_tema_edition_request(
        {"sdo_name": raw_sdo, "displaystdno": raw_display}
    ):
        candidates.add("TEMA")

    lookup_sdo, _lookup_standard, id_name = canonicalize_search_request(
        raw_sdo,
        raw_display,
    )
    for candidate in (lookup_sdo, id_name):
        if candidate and str(candidate).strip():
            candidates.add(str(candidate).strip())

    inferred_sdo, _ = StandardExpressionParser.infer_sdo_and_body(
        raw_display
    )
    if inferred_sdo and str(inferred_sdo).strip():
        candidates.add(str(inferred_sdo).strip())
        inferred_lookup_sdo, _inferred_standard, inferred_id_name = (
            canonicalize_search_request(
                inferred_sdo,
                raw_display,
            )
        )
        candidates.update(
            candidate
            for candidate in (
                inferred_lookup_sdo,
                inferred_id_name,
            )
            if candidate and str(candidate).strip()
        )

    return list(
        {
            candidate.upper()
            for candidate in candidates
            if candidate
            and str(candidate).strip()
            and StandardExpressionParser.is_plausible_sdo(candidate)
        }
    )


def discover_identity_candidates(identity_lookup_rows, repository):
    """Find and index candidates for rows requiring identity discovery."""
    identity_hints = []

    for row in identity_lookup_rows:
        identity = row["identity"]
        # Keep slash duals such as ``B36.19M/36.19`` intact so lookup-token
        # expansion can search both sides and the non-metric form.
        core = (
            identity.get("core_number_pattern")
            or identity.get("core_number")
            or ""
        )

        if not core:
            continue

        search_sdo_name = (
            row.get("search_sdo_name") or row["sdo_name"]
        )
        pattern_prefix = identity_pattern_prefix(
            search_sdo_name,
            identity.get("identifier_prefix"),
        )
        identity_hints.extend(
            (
                row["sdo_id"],
                pattern_prefix,
                lookup_core,
            )
            for lookup_core in identity_lookup_core_tokens(
                search_sdo_name,
                core,
                identity.get("qualifier"),
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
    joint_request_names = set()

    for row in rows:
        sdo_id = row.get("sdo_id")
        sdo_name = row.get("search_sdo_name") or row.get("sdo_name")

        if sdo_id and sdo_name:
            sdo_names_by_id.setdefault(
                sdo_id,
                set(),
            ).add(sdo_name)
            if ieee_iec_joint_request(sdo_name):
                joint_request_names.add(sdo_name)

    index = {}
    parsed_identities = {}

    for candidate in candidates:
        sdo_names = set(sdo_names_by_id.get(candidate.sdo_id, ()))
        # Dual-logo IEC/IEEE rows are stored under one owner. Index them
        # under the other publisher's request name in the same pass so an
        # IEEE sheet line can resolve the IEC dual-logo edition.
        if joint_request_names and designation_is_ieee_iec_dual_logo(
            getattr(candidate, "display_stdNo", None),
            getattr(candidate, "standardno", None),
        ):
            sdo_names.update(joint_request_names)

        for sdo_name in sdo_names:
            for value in (
                candidate.display_stdNo or "",
                candidate.standardno or "",
            ):
                if not value:
                    continue

                identity_key = (sdo_name, value)
                if identity_key not in parsed_identities:
                    parsed_identities[identity_key] = parse_identity(
                        sdo_name,
                        value,
                    )
                candidate_identity = parsed_identities[identity_key]
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
