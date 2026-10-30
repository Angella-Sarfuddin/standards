"""Stateless result formatting and not-found helpers for document search."""

import re

from app.core.standard_formatter import remove_draft_marker
from app.core.standard_identity import (
    identity_matches,
    normalize_tokens,
    parse_identity,
)


def _source_request_key(result):
    """Identify one source request without merging separate worksheet rows."""
    source_identity = result.get("_source_request_identity")
    if source_identity is None:
        source_identity = result.get("source_row_identity")
    if not isinstance(source_identity, (tuple, list)):
        return None

    return (
        normalize_tokens(result.get("requested_sdo") or ""),
        tuple(source_identity),
    )


def _result_identity(result, display):
    """Parse one designation. Empty text has no identity."""
    text = str(display or "").strip()
    sdo_name = str(result.get("requested_sdo") or "").strip()
    if not text or not sdo_name:
        return None
    identity = parse_identity(sdo_name, text)
    if not (identity.get("core_number") or identity.get("core")):
        return None
    return identity


def _edition_year(identity):
    if not identity:
        return None
    try:
        year = identity.get("year")
        return int(year) if year is not None else None
    except (TypeError, ValueError):
        return None


def _must_remain_unmatched(result):
    """Requests that stay unresolved even when a related edition was found."""
    status = str(result.get("status") or "").strip().casefold()
    detail = str(result.get("status_detail") or "")
    if status == "sdo not found":
        return True
    if re.search(
        r"(?i)revision/amendment requests are excluded|standalone "
        r"(?:revision|amendment)",
        detail,
    ):
        return True
    if re.search(
        r"(?i)no database edition is available for requested year",
        detail,
    ):
        return True
    return False


def _resolved_by_found_standard(result, found_identities):
    """True when this unmatched row is an edition of a standard already found.

    A requested year newer than every found edition of that standard stays
    unmatched. A different number, part, or section does not match.
    """
    if _must_remain_unmatched(result):
        return False
    requested = _result_identity(result, result.get("requested_standard"))
    if requested is None:
        return False
    requested_year = _edition_year(requested)
    for found in found_identities:
        if not identity_matches(requested, found, check_year=False):
            continue
        found_year = _edition_year(found)
        if (
            requested_year is not None
            and found_year is not None
            and requested_year > found_year
        ):
            continue
        return True
    return False


def deduplicate_results(results, service_class):
    """Keep resolved standards out of the unmatched result set."""
    resolved_source_requests = {
        source_key
        for result in results or []
        if result.get("matched") and result.get("standard")
        if (source_key := _source_request_key(result)) is not None
    }
    found_identities = []
    for result in results or []:
        standard = result.get("standard") or {}
        if not result.get("matched") or not standard:
            continue
        display = (
            standard.get("display_stdNo") or standard.get("standardno")
            if isinstance(standard, dict)
            else getattr(standard, "display_stdNo", None)
            or getattr(standard, "standardno", None)
        )
        identity = _result_identity(result, display)
        if identity is not None:
            found_identities.append(identity)

    deduplicated = []
    seen = set()
    for result in results or []:
        if not result.get("matched") and (
            (
                (source_key := _source_request_key(result)) is not None
                and source_key in resolved_source_requests
            )
            or _resolved_by_found_standard(result, found_identities)
        ):
            continue

        if not result.get("matched"):
            result = dict(result)
            reason = service_class._not_found_reason(result)
            result["not_found_reason"] = reason
            if not str(result.get("status_detail") or "").strip():
                result["status_detail"] = (
                    "The requested SDO was not found in the catalog."
                    if reason == "SDO not found"
                    else (
                        "No available catalog record was found, and no "
                        "withdrawn or historical status was identified."
                        if reason == "Not found in catalog"
                        else f"The requested edition is {reason.casefold()}."
                    )
                )
        standard = result.get("standard") or {}
        if result.get("matched") and standard:
            catalog_sdo_id = (
                standard.get("sdo_id")
                if isinstance(standard, dict)
                else getattr(standard, "sdo_id", None)
            )
            standard_id = (
                standard.get("Standard_id") or standard.get("id")
                if isinstance(standard, dict)
                else getattr(standard, "Standard_id", None)
                or getattr(standard, "id", None)
            )
            display_number = (
                standard.get("display_stdNo")
                or standard.get("standardno")
                or ""
                if isinstance(standard, dict)
                else getattr(standard, "display_stdNo", None)
                or getattr(standard, "standardno", None)
                or ""
            )
            standard_year = (
                standard.get("standardyear")
                or (standard.get("enrichment") or {}).get("year")
                if isinstance(standard, dict)
                else getattr(standard, "standardyear", None)
            )
            key = (
                "found",
                catalog_sdo_id
                or normalize_tokens(result.get("requested_sdo") or ""),
                standard_id or normalize_tokens(display_number),
                normalize_tokens(display_number),
                standard_year,
                normalize_tokens(result.get("requested_standard") or ""),
                result.get("_source_request_identity"),
            )
        else:
            key = (
                "unmatched",
                normalize_tokens(result.get("requested_sdo") or ""),
                normalize_tokens(result.get("requested_standard") or ""),
                normalize_tokens(result.get("status") or ""),
                result.get("_source_request_identity"),
            )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(result)
    for result in deduplicated:
        result.pop("_edition_rewritten", None)
        source_identity = result.pop(
            "_source_request_identity",
            None,
        )
        if source_identity is not None:
            result["source_row_identity"] = list(source_identity)
    return deduplicated


def not_found_reason(result):
    """Classify unmatched rows using lifecycle evidence when available."""
    status = str(result.get("status") or "").strip().casefold()
    detail = str(result.get("status_detail") or "").strip()
    replacement = str(
        result.get("superseded_by")
        or result.get("replacement_standard")
        or ""
    ).strip()
    evidence = " ".join((status, detail, replacement)).casefold()
    if re.search(r"\bwithdrawn\b", evidence):
        return "Withdrawn"
    if re.search(r"\bdo\s+not\s+use\b", evidence):
        return "Withdrawn"
    if re.search(
        r"\b(?:historical|historic|superseded|obsolete|archived)\b",
        evidence,
    ):
        return "Historical"
    if re.search(
        r"(?i)revision/amendment requests are excluded|standalone "
        r"(?:revision|amendment)",
        detail,
    ):
        return "Standalone amendment request"
    if re.search(r"\b(?:inactive|discontinued|not available)\b", evidence):
        return "Unavailable"
    if status == "sdo not found":
        return "SDO not found"
    return "Not found in catalog"


def format_master_standard(standard):
    return {
        "Standard_id": standard.Standard_id,
        "standardno": remove_draft_marker(standard.standardno),
        "display_stdNo": remove_draft_marker(standard.display_stdNo),
        "title": standard.title,
        "url": standard.url,
        "sdo_id": standard.sdo_id,
        "standardyear": standard.standardyear,
    }
