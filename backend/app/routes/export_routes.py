import re

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.document_search_service import DocumentSearchService
from app.services.export_service import ExportService
from app.services.grouping_service import GroupingService
from app.services.catalog_lifecycle_overrides import (
    lookup as lookup_catalog_lifecycle_override,
)
from app.utils.standard_identity import parse_identity


XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

router = APIRouter(
    prefix="/export",
    tags=["Export"]
)


def _refresh_official_api_1176_rows(results, db):
    """Refresh RP 1176 rows before export so stale page state cannot win."""
    refreshed = []
    cache = {}

    for result in results or []:
        requested_sdo = str(result.get("requested_sdo") or "").strip()
        standard = result.get("standard") or {}
        requested_number = str(
            result.get("requested_standard")
            or standard.get("display_stdNo")
            or standard.get("standardno")
            or ""
        ).strip()
        identity = parse_identity(requested_sdo, requested_number)
        if not (
            str(requested_sdo).strip().upper() == "API"
            and str(identity.get("designation") or "").upper() == "RP"
            and str(identity.get("core_number") or "").strip() == "1176"
        ):
            refreshed.append(result)
            continue

        cache_key = (requested_sdo.casefold(), requested_number.casefold())
        if cache_key not in cache:
            cache[cache_key] = DocumentSearchService(db).search(
                [{"sdo_name": requested_sdo, "displaystdno": requested_number}]
            )
        refreshed.extend(cache[cache_key])

    return refreshed


def _refresh_official_nace_mr0103_rows(results, db):
    """Refresh legacy MR0103 aliases to AMPP's canonical active record."""
    refreshed = []
    cache = {}

    for result in results or []:
        requested_sdo = str(result.get("requested_sdo") or "").strip()
        standard = result.get("standard") or {}
        requested_number = str(
            result.get("requested_standard")
            or standard.get("display_stdNo")
            or standard.get("standardno")
            or ""
        ).strip()
        sdo_key = re.sub(r"[^A-Z0-9]", "", requested_sdo.upper())
        designation_key = re.sub(
            r"[^A-Z0-9]", "", requested_number.upper()
        )
        if (
            sdo_key not in {"NACE", "AMPPNACE", "ANSINACE"}
            or "MR0103" not in designation_key
            or "ISO17945" not in designation_key
        ):
            refreshed.append(result)
            continue

        cache_key = (requested_sdo.casefold(), requested_number.casefold())
        if cache_key not in cache:
            cache[cache_key] = DocumentSearchService(db).search(
                [{"sdo_name": requested_sdo, "displaystdno": requested_number}]
            )
        current = cache[cache_key]
        if any(
            item.get("matched")
            and (item.get("standard") or {}).get("Standard_id")
            and str((item.get("standard") or {}).get("Standard_id"))
            .startswith("ANSI-NACE-MR0103-ISO-17945-")
            for item in current
        ):
            refreshed.extend(current)
        else:
            refreshed.append(result)

    return refreshed


def _refresh_catalog_lifecycle_rows(results, db):
    """Re-run curated lifecycle cases before producing any Excel workbook."""
    refreshed = []
    cache = {}

    for result in results or []:
        requested_sdo = str(result.get("requested_sdo") or "").strip()
        standard = result.get("standard") or {}
        requested_number = str(
            result.get("requested_standard")
            or standard.get("display_stdNo")
            or standard.get("standardno")
            or ""
        ).strip()
        identity = parse_identity(requested_sdo, requested_number)
        lookup_row = {
            "sdo_name": requested_sdo,
            "search_sdo_name": requested_sdo,
            "identity": identity,
        }
        if not lookup_catalog_lifecycle_override(lookup_row):
            refreshed.append(result)
            continue

        cache_key = (requested_sdo.casefold(), requested_number.casefold())
        if cache_key not in cache:
            cache[cache_key] = DocumentSearchService(db).search(
                [{"sdo_name": requested_sdo, "displaystdno": requested_number}]
            )
        refreshed.extend(cache[cache_key])

    return refreshed


def _refresh_official_catalog_rows(results, db):
    results = _refresh_official_api_1176_rows(results, db)
    results = _refresh_official_nace_mr0103_rows(results, db)
    return _refresh_catalog_lifecycle_rows(results, db)


def _expand_series_export_rows(results, db):
    """Expand only series roots, preserving already-expanded part rows."""
    expanded = []
    cache = {}

    for result in results or []:
        if result.get("_seriesExpanded"):
            expanded.append(result)
            continue

        standard = result.get("standard") or {}
        requested_sdo = str(result.get("requested_sdo") or "").strip()
        requested_number = str(
            result.get("requested_standard")
            or standard.get("display_stdNo")
            or standard.get("standardno")
            or ""
        ).strip()

        matched_designations = (
            standard.get("display_stdNo"),
            standard.get("standardno"),
        )
        matched_series = next(
            (
                designation
                for designation in matched_designations
                if parse_identity(requested_sdo, designation).get("qualifier")
                == "SERIES"
            ),
            None,
        )
        requested_is_series = (
            parse_identity(requested_sdo, requested_number).get("qualifier")
            == "SERIES"
        )

        # Expanded family members keep the original series in
        # requested_standard. Do not mistake each member for a new root.
        if result.get("matched") and standard and not matched_series:
            expanded.append(result)
            continue

        series_designation = matched_series or (
            requested_number if requested_is_series else None
        )
        if not series_designation:
            expanded.append(result)
            continue

        cache_key = (
            requested_sdo.casefold(),
            str(series_designation).casefold(),
        )
        if cache_key not in cache:
            cache[cache_key] = DocumentSearchService(db).search(
                [{
                    "sdo_name": requested_sdo,
                    "displaystdno": series_designation,
                }]
            )
        current_results = cache[cache_key]
        current_parts = [item for item in current_results if item.get("matched")]
        if current_parts:
            expanded.extend(
                {**item, "_seriesExpanded": True}
                for item in current_results
            )
        else:
            expanded.append({**result, "_seriesExpanded": True})

    # A repeated root or an already-expanded frontend payload must not create
    # repeated quotation/not-found rows in the downloaded workbook.
    deduplicated = []
    seen = set()
    for result in expanded:
        requested_sdo = re.sub(
            r"[^A-Z0-9]", "", str(result.get("requested_sdo") or "").upper()
        )
        requested_standard = re.sub(
            r"[^A-Z0-9]",
            "",
            str(result.get("requested_standard") or "").upper(),
        )
        standard = result.get("standard") or {}
        if result.get("matched") and standard:
            resolved = (
                standard.get("Standard_id")
                or standard.get("id")
                or standard.get("display_stdNo")
                or standard.get("standardno")
            )
            key = (
                "found",
                requested_sdo,
                requested_standard,
                str(resolved or "").casefold(),
            )
        else:
            key = (
                "unmatched",
                requested_sdo,
                requested_standard,
                str(result.get("status") or "").casefold(),
                str(result.get("status_detail") or "").casefold(),
            )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(result)
    return deduplicated


@router.post("/excel")
def export_excel(results: list[dict], db: Session = Depends(get_db)):

    results = _refresh_official_catalog_rows(results, db)

    grouping = GroupingService.group_results(
        results
    )

    response = {
        "results": results,
        "grouping": grouping
    }

    file = ExportService.export_results(
        response
    )

    return Response(
        content=file.getvalue(),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": "attachment; filename=standards_quotation.xlsx"
        }
    )


@router.post("/latest-years")
def export_latest_years(results: list[dict], db: Session = Depends(get_db)):
    results = _refresh_official_catalog_rows(results, db)
    file = ExportService.export_latest_years(results)
    return Response(
        content=file.getvalue(),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                "attachment; filename=standards_latest_years.xlsx"
            )
        },
    )


@router.post("/both")
def export_both(payload: dict, db: Session = Depends(get_db)):
    quotation_results = payload.get("quotation_results", [])
    latest_year_results = payload.get("latest_year_results", [])
    quotation_results = _refresh_official_catalog_rows(quotation_results, db)
    latest_year_results = _refresh_official_catalog_rows(latest_year_results, db)
    grouping = GroupingService.group_results(quotation_results)
    file = ExportService.export_both({
        "results": quotation_results,
        "grouping": grouping,
    }, latest_year_results)
    return Response(
        content=file.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                "attachment; filename=standards_exports.zip"
            )
        },
    )


@router.post("/not-found")
def export_not_found(results: list[dict]):
    file = ExportService.export_not_found_excel(results)
    return Response(
        content=file.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                "attachment; filename=not_found_standards.xlsx"
            )
        },
    )


@router.post("/found-and-not-found")
def export_found_and_not_found(payload: dict, db: Session = Depends(get_db)):
    quotation_results = _refresh_official_catalog_rows(
        payload.get("quotation_results", []), db
    )
    all_results = _refresh_official_catalog_rows(
        payload.get("all_results", []), db
    )
    quotation_results = _expand_series_export_rows(
        quotation_results,
        db,
    )
    all_results = _expand_series_export_rows(
        all_results,
        db,
    )
    file = ExportService.export_found_and_not_found_zip(
        quotation_results,
        all_results,
    )
    return Response(
        content=file.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                "attachment; filename=standards_found_and_not_found.zip"
            )
        },
    )
