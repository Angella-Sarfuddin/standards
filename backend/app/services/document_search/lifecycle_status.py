"""Lifecycle label interpretation helpers for document search."""

import re

_UNAVAILABLE_LABEL = (
    r"WITHDRAWN|WTHDRAWN|DO\s+NOT\s+USE|OBSOLETE|SUPERSEDED|"
    r"INACTIVE|DISCONTINUED|HISTORICAL|HISTORIC|ARCHIVED"
)
_UNAVAILABLE_STATUS_RE = re.compile(
    rf"(?i)\b(?P<label>{_UNAVAILABLE_LABEL})\b"
)
# Boilerplate such as "no withdrawn or historical status was identified"
# must never be read as a positive lifecycle label.
_NEGATED_LIFECYCLE_MENTION_RE = re.compile(
    rf"(?i)\b(?:no|not|without|neither)\b(?:\s+\w+){{0,12}}\s+"
    rf"(?:{_UNAVAILABLE_LABEL})\b"
)


def _status_label_is_unavailable(status_name):
    """Recognize lifecycle labels that must never be reported available."""
    return bool(_UNAVAILABLE_STATUS_RE.search(str(status_name or "")))


def _normalize_unavailable_status_label(status_name):
    """Canonical unmatched lifecycle label, or None when not unavailable."""
    match = _UNAVAILABLE_STATUS_RE.search(str(status_name or ""))
    if not match:
        return None
    label = re.sub(r"\s+", " ", match.group("label").upper()).strip()
    if label in {"HISTORICAL", "HISTORIC"}:
        return "HISTORICAL"
    if label in {"WITHDRAWN", "WTHDRAWN"} or label == "DO NOT USE":
        return "WITHDRAWN"
    return label


def _lifecycle_status_from_evidence(*values):
    """Read an unavailable lifecycle label from positive evidence only.

    Negated wording such as ``no withdrawn or historical status`` is ignored
    so explanatory Not Found text cannot flip a missing row to WITHDRAWN.
    """
    text = " ".join(str(value or "") for value in values if str(value or "").strip())
    if not text:
        return None
    cleaned = _NEGATED_LIFECYCLE_MENTION_RE.sub(" ", text)
    return _normalize_unavailable_status_label(cleaned)


def _candidate_embedded_lifecycle_status(candidate):
    """Read explicit lifecycle labels embedded in catalogue identifiers."""
    value = " ".join(
        str(getattr(candidate, field, "") or "")
        for field in ("standardno", "display_stdNo")
    )
    return _normalize_unavailable_status_label(value)
