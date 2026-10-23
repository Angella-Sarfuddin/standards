"""Curated lifecycle corrections for known stale catalogue records.

The local catalogue mirrors occasionally mark obsolete API/ASTM publications
as active. Keep publisher-specific corrections here so every caller of the
shared document search (including Excel export) sees the same lifecycle.
"""

from __future__ import annotations

import re


def _normalize_core(value) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def lookup(row: dict) -> dict | None:
    """Return a verified lifecycle correction for a requested edition."""
    sdo = str(row.get("search_sdo_name") or row.get("sdo_name") or "")
    identity = row.get("identity") or {}
    designation = str(identity.get("designation") or "").strip().upper()
    core = _normalize_core(identity.get("core_number") or "")
    year = identity.get("year")

    if sdo.strip().upper() == "API":
        key = (designation, core)
        api_unavailable = {
            ("RP", "44"): {
                "status": "WITHDRAWN",
                "detail": "API lists RP 44 as withdrawn; the local catalogue incorrectly labels this edition active.",
            },
            ("RP", "5C7"): {
                "status": "HISTORICAL",
                "detail": "API lists RP 5C7 among its historical publications; this edition is not current.",
            },
            ("RP", "52"): {
                "status": "WITHDRAWN",
                "detail": "API's 2025 catalog lists RP 52 as historical, and its R2010 edition is listed as withdrawn; the local ACTIVE flag is stale.",
            },
            ("SPEC", "11IW"): {
                "status": "WITHDRAWN",
                "detail": "API withdrew Specification 11IW; API states it is no longer active or maintained and remains historical only.",
            },
            ("SPEC", "5D"): {
                "status": "HISTORICAL",
                "detail": "API Spec 5D is a historical designation; API moved the drill-pipe requirements to Spec 5DP.",
                "replacement": "API SPEC 5DP : 2020",
            },
            ("SPEC", "7"): {
                "status": "HISTORICAL",
                "detail": "API Spec 7, 40th Edition (2001), is listed as historical; the current rotary drill-stem designation is API Spec 7-1.",
                "replacement": "API SPEC 7-1 : 2023",
            },
        }
        if key in api_unavailable:
            return {"kind": "unavailable", **api_unavailable[key]}

        if key == ("RP", "74") and year == 2007:
            return {
                "kind": "unavailable",
                "status": "NOT FOUND",
                "detail": (
                    "API's catalog lists RP 74 as the October 2001 first edition, "
                    "reaffirmed in January 2013; it does not list a 2007 edition."
                ),
            }

        if key == ("RP", "74") and year == 2001:
            return {
                "kind": "reaffirmed_current",
                "status": "AVAILABLE",
                "edition_year": 2001,
                "display": "API RP 74 : 2001 (R2013)",
                "detail": "API lists the 2001 first edition as reaffirmed in January 2013.",
            }

    if sdo.strip().upper() == "ASTM" and year is not None:
        compact = re.sub(r"[^A-Z0-9]", "", str(identity.get("core_number") or "").upper())
        if compact.startswith("D1250") and int(year) < 2025:
            return {
                "kind": "unavailable",
                "status": "HISTORICAL",
                "detail": "This ASTM D1250 edition is historical; ASTM identifies D1250-25 as the active edition.",
                "replacement": "ASTM D1250 : 2025",
            }

    if (
        sdo.strip().upper() == "ASME"
        and core == "Z85GEM"
        and year is None
    ):
        return {
            "kind": "unavailable",
            "status": "NOT FOUND",
            "detail": (
                "The local record has no publication year or verified current edition; "
                "it cannot be reported as the current available version."
            ),
        }

    return None
