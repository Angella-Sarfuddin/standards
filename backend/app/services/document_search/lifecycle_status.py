"""Lifecycle label interpretation helpers for document search."""

import re

_UNAVAILABLE_STATUS_RE = re.compile(
    r"(?i)\b(?P<label>WITHDRAWN|WTHDRAWN|DO\s+NOT\s+USE|OBSOLETE|SUPERSEDED|"
    r"INACTIVE|DISCONTINUED|HISTORICAL|HISTORIC|ARCHIVED)\b"
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


def _candidate_embedded_lifecycle_status(candidate):
    """Read explicit lifecycle labels embedded in catalogue identifiers."""
    value = " ".join(
        str(getattr(candidate, field, "") or "")
        for field in ("standardno", "display_stdNo")
    )
    return _normalize_unavailable_status_label(value)
