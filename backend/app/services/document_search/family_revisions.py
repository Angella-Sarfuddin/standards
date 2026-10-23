import re

from app.utils.standard_identity import parse_identity, standard_number_year


def _candidate_base_edition_year(candidate):
    number = str(
        getattr(candidate, "display_stdNo", "")
        or getattr(candidate, "standardno", "")
        or ""
    )
    revision = re.search(
        r"(?i)(?:/|\+|\s)\s*(?:CORR(?:IGENDUM)?|COR|AMD|AMENDMENT)"
        r"\s*\d+[A-Z]?",
        number,
    )
    if not revision:
        base_number = number
    else:
        base_number = number[:revision.start()].rstrip(" :/")
    return (
        parse_identity("", base_number).get("year")
        or standard_number_year(base_number)
    )


def _select_current_family_revisions(
    latest_by_part,
    requested_qualifier,
    *,
    service_class,
):
    family_members = {}
    prefix = f"{requested_qualifier}:"
    for key, value in latest_by_part.items():
        if isinstance(key, tuple):
            path, revision = key
        else:
            path_and_revision = key[len(prefix):]
            path, _, revision = path_and_revision.partition(":")
        family_members.setdefault(path, {})[revision] = value

    selected = []
    for revisions in family_members.values():
        base = revisions.get("")
        if base:
            selected.append(base[1])
            base_year = service_class._candidate_base_edition_year(base[1])
            for revision, value in revisions.items():
                if not revision:
                    continue
                revision_base_year = service_class._candidate_base_edition_year(
                    value[1]
                )
                if (
                    base_year is None
                    or revision_base_year is None
                    or base_year == revision_base_year
                ):
                    selected.append(value[1])
        else:
            selected.extend(value[1] for value in revisions.values())
    return selected
