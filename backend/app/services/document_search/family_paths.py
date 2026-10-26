"""Pure helpers for mapping and matching standard-family part paths."""

import re

from app.utils.standard_identity import normalize_identity_core, parse_identity


def _candidate_is_part_of_root(candidate, row):
    requested = row["identity"]
    if requested.get("qualifier") or requested.get("family_lookup"):
        return False

    candidate_identity = parse_identity(
        row["sdo_name"],
        candidate.display_stdNo or candidate.standardno or "",
    )
    requested_core = normalize_identity_core(
        requested.get("core_number") or ""
    )
    candidate_core = normalize_identity_core(
        candidate_identity.get("core_number") or ""
    )
    extension = candidate_core[len(requested_core):]
    return bool(
        requested_core
        and candidate_core.startswith(requested_core)
        and (
            (
                (candidate_identity.get("qualifier") or "").startswith(
                    "PART:"
                )
                and candidate_core == requested_core
            )
            or re.fullmatch(r"PART\d+", extension)
            and (candidate_identity.get("qualifier") or "").startswith(
                "SECTION:"
            )
        )
    )


def _part_family_path(candidate_identity, requested_identity):
    """Return the complete part path relative to a requested series root."""
    requested_core = normalize_identity_core(
        requested_identity.get("core_number") or ""
    )
    candidate_core = normalize_identity_core(
        candidate_identity.get("core_number") or ""
    )
    if not requested_core or not candidate_core.startswith(requested_core):
        return ""

    extension = candidate_core[len(requested_core):]
    part_extension = re.fullmatch(r"PART(\d+)", extension)
    if extension and not extension.isdigit() and not part_extension:
        return ""

    qualifier = str(candidate_identity.get("qualifier") or "")
    if qualifier.startswith("PART:"):
        part_number = qualifier.partition(":")[2]
        if not all(value.isdigit() for value in part_number.split("-")):
            return ""
        return "-".join(
            value
            for value in (
                part_extension.group(1) if part_extension else extension,
                part_number,
            )
            if value
        )
    if qualifier.startswith("SECTION:") and part_extension:
        section_number = qualifier.partition(":")[2]
        if not section_number.isdigit():
            return ""
        return f"{part_extension.group(1)}-{section_number}"

    return extension


def _requested_part_matches_path(row, part_path):
    qualifier = str(row["identity"].get("qualifier") or "")
    if not qualifier.startswith("PART:"):
        return True
    requested_part = qualifier.partition(":")[2]
    if not part_path:
        return False
    top_level_part = part_path.split("-", 1)[0]
    requested_range = requested_part.split("-", 1)
    if len(requested_range) == 2 and all(
        value.isdigit() for value in requested_range
    ):
        return int(requested_range[0]) <= int(top_level_part) <= int(
            requested_range[1]
        )
    return top_level_part == requested_part
