"""Candidate identity and selection functions used by document search."""

import re

from app.utils.standard_identity import (
    identity_matches,
    normalize_identity_core,
    parse_identity,
    standard_number_year,
)

def _select_candidate(
    candidates,
    row,
    status_map=None, *, service_class):

    if not candidates:
        return None

    if service_class._is_api_request(row):
        candidates = service_class._filter_api_unavailable_candidates(
            candidates,
            status_map,
            row,
        )
        if not candidates:
            return None

    service_class._record_requested_edition_status(
        candidates,
        row,
        status_map,
    )

    candidates = service_class._prefer_catalog_visible_candidates(
        candidates,
        status_map,
        row,
    )

    if service_class._current_edition_request_requires_active_status(
        row, status_map
    ):
        active_candidates = [
            candidate
            for candidate in candidates
            if service_class._candidate_catalog_visibility(
                candidate, status_map
            ) is True
        ]
        if active_candidates:
            candidates = active_candidates

    validated = [
        candidate
        for candidate in candidates
        if service_class._candidate_matches_identity(
            candidate,
            row,
        )
    ]

    validated = service_class._prefer_exact_designation(
        validated,
        row,
    )

    if validated:
        requested_prefix = service_class._normalized_identifier_prefix(
            (row.get("identity") or {}).get("identifier_prefix") or ""
        )

        def candidate_rank(candidate):
            candidate_identity = parse_identity(
                row.get("search_sdo_name") or row["sdo_name"],
                candidate.display_stdNo or candidate.standardno or "",
            )
            exact_prefix = int(
                service_class._normalized_identifier_prefix(
                    candidate_identity.get("identifier_prefix") or ""
                )
                == requested_prefix
            )
            year = (
                service_class._candidate_year(
                    candidate,
                    row.get("search_sdo_name") or row["sdo_name"],
                )
                or 0
            )
            if service_class._is_api_request(row):
                # API records may carry alternate prefixes across
                # editions (for example API versus ANSI/API). Select the
                # newest matching edition before using prefix as a tie-breaker.
                return (
                    year,
                    int(getattr(candidate, "DocumentAvailability", 1) == 1),
                    exact_prefix,
                    int(getattr(candidate, "recent", 0) == 1),
                    int(hasattr(candidate, "standardyear")),
                )
            return (
                exact_prefix,
                year,
                int(getattr(candidate, "DocumentAvailability", 1) == 1),
                int(getattr(candidate, "recent", 0) == 1),
                int(hasattr(candidate, "standardyear")),
            )

        return max(
            validated,
            key=candidate_rank,
        )

    return None

def _select_best_current_candidate(candidates, row, status_map=None, *, service_class):
    service_class._record_requested_edition_status(
        candidates,
        row,
        status_map,
    )
    seen = set()
    unique_candidates = []
    for candidate in candidates:
        key = (
            hasattr(candidate, "standardyear"),
            candidate.id,
        )
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)
    candidates = [
        candidate for candidate in unique_candidates
        if not service_class._candidate_should_be_excluded(candidate)
    ]
    if service_class._is_api_request(row):
        candidates = service_class._filter_api_unavailable_candidates(
            candidates,
            status_map,
            row,
        )
    candidates = service_class._prefer_catalog_visible_candidates(
        candidates,
        status_map,
        row,
    )
    if service_class._current_edition_request_requires_active_status(
        row, status_map
    ):
        active_candidates = [
            candidate
            for candidate in candidates
            if service_class._candidate_catalog_visibility(
                candidate, status_map
            ) is True
        ]
        if active_candidates:
            candidates = active_candidates
    if not candidates:
        return []

    # Requests identify the standard; the returned edition is the latest
    # available one even when the input includes an old publication year.
    if service_class._current_edition_request_requires_active_status(
        row, status_map
    ):
        explicitly_available = [
            candidate
            for candidate in candidates
            if service_class._candidate_catalog_visibility(
                candidate,
                status_map,
            ) is True
        ]
        if explicitly_available:
            candidates = explicitly_available

    validated = [
        candidate
        for candidate in candidates
        if service_class._candidate_matches_identity(
            candidate,
            row,
        )
    ]
    if not validated:
        validated = candidates

    if service_class._current_edition_request_requires_active_status(
        row, status_map
    ):
        active_candidates = [
            candidate
            for candidate in validated
            if service_class._candidate_catalog_visibility(
                candidate, status_map
            ) is True
        ]
        if active_candidates:
            validated = active_candidates

    requested_prefix = service_class._normalized_identifier_prefix(
        row["identity"].get("identifier_prefix") or ""
    )

    def ranking(candidate):
        year = (
            service_class._candidate_year(
                candidate,
                row["sdo_name"],
            )
            or 0
        )
        candidate_identity = parse_identity(
            row.get("search_sdo_name") or row["sdo_name"],
            candidate.display_stdNo or candidate.standardno or "",
        )
        exact_prefix = int(
            service_class._normalized_identifier_prefix(
                candidate_identity.get("identifier_prefix") or ""
            )
            == requested_prefix
        )
        recent = int(getattr(candidate, "recent", 0) == 1)
        is_master_record = int(hasattr(candidate, "standardyear"))
        has_document = int(
            getattr(candidate, "DocumentAvailability", 1) == 1
        )
        if service_class._is_api_request(row):
            return (
                year,
                has_document,
                exact_prefix,
                recent,
                is_master_record,
            )
        return (
            exact_prefix,
            year,
            has_document,
            recent,
            is_master_record,
        )

    return [max(validated, key=ranking)]

def _candidate_year(candidate, sdo_name):
    if getattr(candidate, "standardyear", None) is not None:
        return candidate.standardyear

    candidate_identity = parse_identity(
        sdo_name,
        candidate.display_stdNo or candidate.standardno or "",
    )
    return (
        candidate_identity.get("year")
        or standard_number_year(candidate.standardno)
    )

def _normalized_identifier_prefix(value):
    key = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    # IS/IEC and IS/IEC/IEEE are the same adoption. The joint IEEE
    # marker must not make the older IS/IEC edition outrank the current one.
    if key.startswith("ISIEC"):
        key = re.sub(r"IEEE$", "", key)
    return key

def _candidate_matches_identity(
    candidate,
    row,
):

    requested = row[
        "identity"
    ]

    candidate_values = [
        candidate.display_stdNo or "",
        candidate.standardno or "",
    ]

    for value in candidate_values:

        if not value:
            continue

        candidate_identity = parse_identity(
            requested[
                "sdo_name"
            ],
            value,
        )

        if not identity_matches(
            requested,
            candidate_identity,
            check_year=False,
        ):
            continue

        return True

    return False

def _filter_api_unavailable_candidates(candidates, status_map, row, *, service_class):
    """Do not let API active duplicates override withdrawn editions."""
    candidates = list(candidates or [])
    if not candidates or not status_map:
        return candidates

    # Master API rows with a zero year and an edition-bearing title are
    # legacy placeholders, not a current edition. API matching must use a
    # dated edition so lifecycle status can be determined reliably.
    candidates = [
        candidate
        for candidate in candidates
        if not (
            hasattr(candidate, "standardyear")
            and not (getattr(candidate, "standardyear", None) or 0)
            and re.search(
                r"(?i)\b(?:\d+(?:ST|ND|RD|TH)|FIRST|SECOND|THIRD|FOURTH|"
                r"FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH)\s+EDITION\b",
                str(getattr(candidate, "title", "") or ""),
            )
        )
    ]
    if not candidates:
        return []

    unavailable_editions = set()
    dated_edition_cores = set()
    for candidate in candidates:
        identity = parse_identity(
            "API",
            getattr(candidate, "display_stdNo", "")
            or getattr(candidate, "standardno", ""),
        )
        core = normalize_identity_core(
            identity.get("core_number") or identity.get("core") or ""
        )
        year = (
            service_class._candidate_year(candidate, "API")
            or None
        )
        if core and year is not None:
            dated_edition_cores.add(core)
        status_info = status_map.get(
            getattr(candidate, "status_id", None)
        ) or {}
        lifecycle_status = str(
            service_class._candidate_embedded_lifecycle_status(
                candidate
            )
            or status_info.get("name")
            or ""
        ).strip()
        if not service_class._status_label_is_unavailable(
            lifecycle_status
        ):
            continue
        if core:
            unavailable_editions.add(
                (core, int(year) if year is not None else None)
            )

    if not unavailable_editions:
        return candidates

    unavailable_cores = {core for core, _year in unavailable_editions}
    dated_available_cores = set()
    for candidate in candidates:
        status_info = status_map.get(
            getattr(candidate, "status_id", None)
        ) or {}
        lifecycle_status = str(
            service_class._candidate_embedded_lifecycle_status(
                candidate
            )
            or status_info.get("name")
            or ""
        ).strip()
        if service_class._status_label_is_unavailable(
            lifecycle_status
        ):
            continue
        identity = parse_identity(
            "API",
            getattr(candidate, "display_stdNo", "")
            or getattr(candidate, "standardno", ""),
        )
        core = normalize_identity_core(
            identity.get("core_number") or identity.get("core") or ""
        )
        year = service_class._candidate_year(candidate, "API") or None
        if core in unavailable_cores and year is not None:
            dated_available_cores.add(core)
    yearless_unavailable_cores = unavailable_cores - dated_available_cores

    filtered = []
    for candidate in candidates:
        status_info = status_map.get(
            getattr(candidate, "status_id", None)
        ) or {}
        lifecycle_status = str(
            service_class._candidate_embedded_lifecycle_status(
                candidate
            )
            or status_info.get("name")
            or ""
        ).strip()
        if service_class._status_label_is_unavailable(
            lifecycle_status
        ):
            filtered.append(candidate)
            continue
        identity = parse_identity(
            "API",
            getattr(candidate, "display_stdNo", "")
            or getattr(candidate, "standardno", ""),
        )
        core = normalize_identity_core(
            identity.get("core_number") or identity.get("core") or ""
        )
        year = (
            service_class._candidate_year(candidate, "API")
            or None
        )
        if core in dated_edition_cores and year is None:
            # API has legacy yearless rows (often old editions) that carry
            # ACTIVE despite a dated catalogue edition being historical.
            # They cannot represent the current edition.
            continue
        if core in yearless_unavailable_cores and year is None:
            continue
        if core and (core, int(year) if year is not None else None) in unavailable_editions:
            continue
        filtered.append(candidate)
    return filtered
