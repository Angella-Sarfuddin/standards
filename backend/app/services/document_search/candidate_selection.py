"""Local and master candidate selection policies for document search."""

import re

from app.core.standard_identity import (
    normalize_identity_core,
    parse_identity,
    standard_number_year,
)


def _series_member_key(candidate, row):
    """Identify one series member independently of its edition."""
    identity = parse_identity(
        row.get("search_sdo_name") or row["sdo_name"],
        candidate.display_stdNo or candidate.standardno or "",
    )
    qualifier = str(identity.get("qualifier") or "")
    if qualifier.startswith(("PART:", "SECTION:", "CHAPTER:")):
        return (
            normalize_identity_core(identity.get("core_number") or ""),
            qualifier,
        )
    if qualifier == "SERIES":
        return None
    member = normalize_identity_core(identity.get("core_number") or "")
    root = normalize_identity_core(
        row["identity"].get("core_number") or ""
    )
    return (member, qualifier) if member and member != root else None

def _series_language_marker(value):
    match = re.search(
        r"(?i)\(\s*(EN\s*[-_]\s*FR|EN\s*[-_]\s*D)\s*\)",
        str(value or ""),
    )
    return (
        re.sub(r"\s+", "", match.group(1)).replace("_", "-").upper()
        if match
        else ""
    )

def _select_series_candidates(candidates, row, status_map=None, *, service_class):
    """Return the latest available edition of each catalogue part."""
    if service_class._is_api_request(row):
        candidates = service_class._filter_api_unavailable_candidates(
            candidates,
            status_map,
            row,
        )
    requested_language = service_class._series_language_marker(
        row.get("displaystdno") or row.get("result_displaystdno")
    )
    if requested_language:
        candidates = [
            candidate
            for candidate in candidates
            if service_class._series_language_marker(
                candidate.display_stdNo or candidate.standardno
            )
            == requested_language
        ]
    members = {}
    for candidate in service_class._unique_standards(candidates):
        designation = " ".join(
            str(value or "")
            for value in (
                getattr(candidate, "display_stdNo", ""),
                getattr(candidate, "standardno", ""),
            )
        )
        if re.search(
            r"(?i)(?<![A-Z0-9])CSS(?![A-Z0-9])|"
            r"(?<![A-Z0-9])(?:CORR(?:IGENDUM)?|COR\.?)(?![A-Z0-9])",
            designation,
        ):
            continue
        if not service_class._candidate_matches_identity(
            candidate,
            row,
        ):
            continue
        key = service_class._series_member_key(candidate, row)
        if key is not None:
            members.setdefault(key, []).append(candidate)

    selected = []
    for member_candidates in members.values():
        visible = [
            candidate
            for candidate in member_candidates
            if service_class._candidate_catalog_visibility(
                candidate,
                status_map,
            ) is True
        ]
        unknown = [
            candidate
            for candidate in member_candidates
            if service_class._candidate_catalog_visibility(
                candidate,
                status_map,
            ) is None
        ]
        # Prefer a visible/current edition, then one whose lifecycle is
        # unknown. If every edition of a member is known to be historical
        # or withdrawn, retain its newest record so result building can
        # place that part in the NOT FOUND output instead of silently
        # dropping it from the requested series.
        unavailable = [
            candidate
            for candidate in member_candidates
            if service_class._candidate_catalog_visibility(
                candidate,
                status_map,
            ) is False
        ]
        pool = visible or unknown or unavailable
        if not pool:
            continue
        selected.append(
            max(
                pool,
                key=lambda candidate: (
                    service_class._candidate_year(
                        candidate,
                        row.get("search_sdo_name") or row["sdo_name"],
                    )
                    or 0,
                    service_class._candidate_reaffirmation_year(candidate),
                    int(getattr(candidate, "recent", 0) or 0),
                    str(getattr(candidate, "id", "")),
                ),
            )
        )
    return sorted(
        selected,
        key=lambda candidate: service_class._series_member_key(
            candidate,
            row,
        ),
    )

def _select_candidates(candidates, row, status_map=None, *, service_class):
    service_class._record_requested_edition_status(
        candidates,
        row,
        status_map,
    )
    candidates = [
        candidate for candidate in candidates
        if not service_class._candidate_should_be_excluded(candidate)
    ]
    if service_class._is_api_request(row):
        candidates = service_class._filter_api_unavailable_candidates(
            candidates,
            status_map,
            row,
        )
    if row.get("identity", {}).get("qualifier") == "SERIES":
        return service_class._select_series_candidates(
            candidates,
            row,
            status_map,
        )
    candidates = service_class._prefer_catalog_visible_candidates(
        candidates,
        status_map,
        row,
    )
    if not candidates:
        return []
    selected = service_class._select_candidate(
        candidates,
        row,
    )

    if not service_class._is_bare_qualifier_request(row):
        if selected:
            return [selected]

        part_candidates = []

        for candidate in service_class._unique_standards(candidates):
            if service_class._candidate_is_part_of_root(
                candidate,
                row,
            ):
                part_candidates.append(candidate)

        if not part_candidates:
            return []

        family_row = {
            **row,
            "identity": {
                **row["identity"],
                "family_lookup": True,
                "qualifier": "PART",
            },
        }
        return service_class._select_candidates(
            part_candidates,
            family_row,
        )

    requested_qualifier = row["identity"].get("qualifier") or "PART"
    if requested_qualifier not in {"PART", "SECTION", "CHAPTER", "SERIES"}:
        requested_qualifier = "PART"
    validated = [
        candidate
        for candidate in service_class._unique_standards(candidates)
        if service_class._candidate_matches_identity(
            candidate,
            row,
        )
    ]
    latest_by_part = {}
    root_candidate = None
    family_lookup = bool(row["identity"].get("family_lookup"))
    root_score = (-1, -1)
    requested_prefix = service_class._normalized_identifier_prefix(
        row["identity"].get("identifier_prefix") or ""
    )

    if requested_qualifier == "SERIES":
        family_root = normalize_identity_core(
            row["identity"].get("core_number") or ""
        )
        latest_by_member = {}
        for candidate in validated:
            candidate_identity = parse_identity(
                row.get("search_sdo_name") or row["sdo_name"],
                candidate.display_stdNo or candidate.standardno or "",
            )
            member = normalize_identity_core(
                candidate_identity.get("core_number") or ""
            )
            if not member.startswith(family_root):
                continue
            year = (
                service_class._candidate_year(
                    candidate,
                    row["sdo_name"],
                )
                or 0
            )
            score = (
                year,
                service_class._candidate_reaffirmation_year(candidate),
            )
            current = latest_by_member.get(member)
            if current is None or score > current[0]:
                latest_by_member[member] = (score, candidate)
        return [item[1] for item in latest_by_member.values()]

    for candidate in validated:
        candidate_identity = parse_identity(
            row["sdo_name"],
            candidate.display_stdNo or candidate.standardno or "",
        )
        part_qualifier = candidate_identity.get("qualifier")
        family_path = ""
        if row["identity"].get("family_lookup"):
            family_path = service_class._part_family_path(
                candidate_identity,
                row["identity"],
            )
            if not family_path or not service_class._requested_part_matches_path(
                row,
                family_path,
            ):
                continue
        year = (
            service_class._candidate_year(
                candidate,
                row["sdo_name"],
            )
            or 0
        )
        exact_prefix = int(
            service_class._normalized_identifier_prefix(
                candidate_identity.get("identifier_prefix") or ""
            )
            == requested_prefix
        )
        # A later reaffirmation of the same edition outranks an older
        # one. Publication year still decides before that review year.
        reaffirmed = service_class._candidate_reaffirmation_year(candidate)
        # API catalogues can use a different prefix for a newer edition
        # (for example API versus ANSI/API). Let the publication year
        # decide first, with the exact prefix as a tie-breaker.
        score = (
            (year, reaffirmed, exact_prefix)
            if service_class._is_api_request(row)
            else (exact_prefix, year, reaffirmed)
        )

        if (
            not part_qualifier
            or part_qualifier == "SERIES"
            or (
                requested_qualifier == "SERIES"
                and str(part_qualifier).startswith("SERIES")
            )
        ):
            if score > root_score:
                root_candidate = candidate
                root_score = score
            continue

        if row["identity"].get("family_lookup"):
            if not part_qualifier.startswith(("PART:", "SECTION:")):
                continue
        elif not part_qualifier.startswith(f"{requested_qualifier}:"):
            continue

        part_key = (
            (
                family_path,
                service_class._candidate_revision_suffix(candidate),
            )
            if family_path
            else part_qualifier
        )
        current = latest_by_part.get(part_key)
        if current is None or score > current[0]:
            latest_by_part[part_key] = (score, candidate)

    if latest_by_part:
        if family_lookup:
            return service_class._select_current_family_revisions(
                latest_by_part,
                requested_qualifier,
            )
        return [
            latest_by_part[qualifier][1]
            for qualifier in sorted(latest_by_part)
        ]
    return [root_candidate] if root_candidate else []

def _select_master_candidate(
    candidates,
    row,
    status_map=None,
    *,
    service_class,
):

    candidates = list(
        {
            candidate.id: candidate
            for candidate in candidates
            if not service_class._candidate_should_be_excluded(candidate)
        }.values()
    )

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

    if not service_class._is_tema_edition_request(row):
        candidates = service_class._prefer_exact_designation(
            candidates,
            row,
        )

    candidates = service_class._prefer_externally_available_candidates(
        candidates
    )

    requested_prefix = service_class._normalized_identifier_prefix(
        (row.get("identity") or {}).get("identifier_prefix") or ""
    )

    # Preserve an explicit designation family (such as IS/IEC) before
    # choosing the newest year. Different catalogue prefixes can share
    # the same numeric core and part while representing different series.
    return max(
        candidates,
        key=lambda candidate: (
            int(
                service_class._normalized_identifier_prefix(
                    parse_identity(
                        row.get("search_sdo_name") or row["sdo_name"],
                        candidate.display_stdNo or candidate.standardno or "",
                    ).get("identifier_prefix") or ""
                ) == requested_prefix
            ),
            service_class._candidate_year(
                candidate,
                row.get("search_sdo_name") or row["sdo_name"],
            ) or 0,
            service_class._candidate_reaffirmation_year(candidate),
            int(getattr(candidate, "DocumentAvailability", 1) == 1),
            int(getattr(candidate, "recent", 0) == 1),
        ),
        default=None,
    )

def _select_master_candidates(candidates, row, status_map=None, *, service_class):
    service_class._record_requested_edition_status(
        candidates,
        row,
        status_map,
    )
    if row.get("identity", {}).get("qualifier") == "SERIES":
        return service_class._select_series_candidates(
            [
                candidate
                for candidate in candidates
                if not service_class._candidate_should_be_excluded(
                    candidate
                )
            ],
            row,
            status_map,
        )
    candidates = [
        candidate
        for candidate in candidates
        if not service_class._candidate_should_be_excluded(
            candidate
        )
    ]
    if service_class._is_api_request(row):
        candidates = service_class._filter_api_unavailable_candidates(
            candidates,
            status_map,
            row,
        )
        if not candidates:
            return []
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
    if not service_class._is_bare_qualifier_request(row):
        root_candidates = [
            candidate
            for candidate in candidates
            if (
                service_class._master_candidate_matches_identity(
                    candidate,
                    row,
                )
                or service_class._is_tema_edition_family_candidate(
                    candidate,
                    row,
                )
            )
        ]
        selected = service_class._select_master_candidate(
            root_candidates,
            row,
        )
        if selected:
            return [selected]

        part_candidates = []

        for candidate in {
            candidate.id: candidate
            for candidate in candidates
        }.values():
            if service_class._candidate_is_part_of_root(
                candidate,
                row,
            ):
                part_candidates.append(candidate)

        if not part_candidates:
            return []

        family_row = {
            **row,
            "identity": {
                **row["identity"],
                "family_lookup": True,
                "qualifier": "PART",
            },
        }
        return service_class._select_master_candidates(
            part_candidates,
            family_row,
        )

    requested_qualifier = row["identity"].get("qualifier") or "PART"
    if requested_qualifier not in {"PART", "SECTION", "CHAPTER", "SERIES"}:
        requested_qualifier = "PART"
    latest_by_part = {}
    root_candidate = None
    family_lookup = bool(row["identity"].get("family_lookup"))
    root_score = (-1, -1)
    requested_prefix = service_class._normalized_identifier_prefix(
        row["identity"].get("identifier_prefix") or ""
    )

    if requested_qualifier == "SERIES":
        family_root = normalize_identity_core(
            row["identity"].get("core_number") or ""
        )
        latest_by_member = {}
        for candidate in {
            candidate.id: candidate
            for candidate in candidates
        }.values():
            if not service_class._master_candidate_matches_identity(
                candidate,
                row,
            ):
                continue
            candidate_identity = parse_identity(
                row.get("search_sdo_name") or row["sdo_name"],
                candidate.display_stdNo or candidate.standardno or "",
            )
            member = normalize_identity_core(
                candidate_identity.get("core_number") or ""
            )
            if not member.startswith(family_root):
                continue
            year = (
                service_class._candidate_year(
                    candidate,
                    row["sdo_name"],
                )
                or 0
            )
            score = (
                year,
                service_class._candidate_reaffirmation_year(candidate),
            )
            current = latest_by_member.get(member)
            if current is None or score > current[0]:
                latest_by_member[member] = (score, candidate)
        return [item[1] for item in latest_by_member.values()]

    for candidate in {
        candidate.id: candidate
        for candidate in candidates
    }.values():
        if not service_class._master_candidate_matches_identity(
            candidate,
            row,
        ):
            continue

        candidate_identity = parse_identity(
            row["sdo_name"],
            candidate.display_stdNo or candidate.standardno,
        )
        part_qualifier = candidate_identity.get("qualifier")
        family_path = ""
        if row["identity"].get("family_lookup"):
            family_path = service_class._part_family_path(
                candidate_identity,
                row["identity"],
            )
            if not family_path or not service_class._requested_part_matches_path(
                row,
                family_path,
            ):
                continue
        year = candidate.standardyear or standard_number_year(
            candidate.standardno
        ) or 0
        reaffirmed = service_class._candidate_reaffirmation_year(candidate)
        exact_prefix = int(
            service_class._normalized_identifier_prefix(
                candidate_identity.get("identifier_prefix") or ""
            )
            == requested_prefix
        )
        # API catalogue rows can use a different prefix for a newer
        # edition (for example API versus ANSI/API). Let the year decide
        # first, with an exact prefix as a tie-breaker.
        score = (
            (year, reaffirmed, exact_prefix)
            if service_class._is_api_request(row)
            else (exact_prefix, year, reaffirmed)
        )

        if (
            not part_qualifier
            or part_qualifier == "SERIES"
            or (
                requested_qualifier == "SERIES"
                and str(part_qualifier).startswith("SERIES")
            )
        ):
            if score > root_score:
                root_candidate = candidate
                root_score = score
            continue

        if row["identity"].get("family_lookup"):
            if not part_qualifier.startswith(("PART:", "SECTION:")):
                continue
        elif not part_qualifier.startswith(f"{requested_qualifier}:"):
            continue

        part_key = (
            (
                family_path,
                service_class._candidate_revision_suffix(candidate),
            )
            if family_path
            else part_qualifier
        )
        current = latest_by_part.get(part_key)
        if current is None or score > current[0]:
            latest_by_part[part_key] = (score, candidate)

    if latest_by_part:
        if family_lookup:
            return service_class._select_current_family_revisions(
                latest_by_part,
                requested_qualifier,
            )
        return [
            latest_by_part[qualifier][1]
            for qualifier in sorted(latest_by_part)
        ]
    return [root_candidate] if root_candidate else []
