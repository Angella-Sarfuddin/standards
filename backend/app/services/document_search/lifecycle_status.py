"""Lifecycle label interpretation helpers for document search."""

import re


def _status_label_is_unavailable(status_name):
    """Recognize lifecycle labels that must never be reported available."""
    return bool(
        re.search(
            r"(?i)\b(?:WITHDRAWN|WTHDRAWN|DO\s+NOT\s+USE|OBSOLETE|SUPERSEDED|INACTIVE|DISCONTINUED|HISTORIC(?:AL)?|ARCHIVED)\b",
            str(status_name or ""),
        )
    )


def _candidate_embedded_lifecycle_status(candidate):
    """Read explicit lifecycle labels embedded in catalogue identifiers."""
    value = " ".join(
        str(getattr(candidate, field, "") or "")
        for field in ("standardno", "display_stdNo")
    )
    match = re.search(
        r"(?i)\b(WITHDRAWN|WTHDRAWN|DO\s+NOT\s+USE|OBSOLETE|SUPERSEDED|INACTIVE|"
        r"DISCONTINUED|HISTORICAL|HISTORIC|ARCHIVED)\b",
        value,
    )
    if not match:
        return None
    label = match.group(1).upper()
    return "HISTORICAL" if label in {"HISTORICAL", "HISTORIC"} else label
