"""Candidate exclusion predicates used by document search."""

import re

from app.utils.standard_identity import normalize_tokens


def _candidate_revision_suffix(candidate):
    for value in (
        getattr(candidate, "standardno", ""),
        getattr(candidate, "display_stdNo", ""),
    ):
        match = re.search(
            r"(?i)(?:/|\+|\s)\s*(?:CORR(?:IGENDUM)?\.?|COR\.?|AMD\.?|AMEND(?:MENT)?\.?)"
            r"\s*(?:NO\.?\s*)?\d+[A-Z]?",
            str(value or ""),
        )
        if match:
            return normalize_tokens(match.group(0))
    return ""


def _candidate_is_amendment(candidate):
    """Return whether the catalogue designation names an amendment."""
    for value in (
        getattr(candidate, "display_stdNo", ""),
        getattr(candidate, "standardno", ""),
    ):
        if value and re.search(
            r"(?i)(?:^|[\s:/+,(\[])"
            r"(?:AMEND(?:MENT)?|AMD)\s*[-.:#]?\s*(?:NO\.?\s*)?\d+\b",
            str(value),
        ):
            return True
    return False


def _candidate_is_proposal(candidate):
    """Proposal records are not published standards for matching output."""
    designation = " ".join(
        str(value or "")
        for value in (
            getattr(candidate, "display_stdNo", ""),
            getattr(candidate, "standardno", ""),
            getattr(candidate, "title", ""),
        )
    )
    return bool(
        re.search(
            r"(?i)\b(?:CSDS\s+)?PROPOSAL\b|\bPROPOSED\s+(?:STANDARD|EDITION)\b",
            designation,
        )
    )


def _candidate_is_ul_supplemental_publication(candidate):
    """Exclude UL supplemental publications from base-standard search."""
    identifiers = " ".join(
        str(value or "")
        for value in (
            getattr(candidate, "display_stdNo", ""),
            getattr(candidate, "standardno", ""),
        )
    )
    if not re.search(r"(?i)(?:^|\s)UL\s+\d", identifiers):
        return False

    return bool(
        re.search(
            r"(?i)\(\s*(?:RED\s+LINE|REVISION|"
            r"CERTIFICATION\s+REQUIREMENT\s+DECISION)\s*\)",
            identifiers,
        )
    )


def _candidate_should_be_excluded(candidate, *, service_class):
    return (
        service_class._candidate_is_amendment(candidate)
        or bool(service_class._candidate_revision_suffix(candidate))
        or service_class._candidate_is_proposal(candidate)
        or service_class._candidate_is_ul_supplemental_publication(
            candidate
        )
    )
