from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.services.export_preparation import (
    _expand_series_export_rows,
    _refresh_official_catalog_rows,
)
from app.services.export_service import ExportService
from app.services.grouping_service import GroupingService


XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

router = APIRouter(
    prefix="/export",
    tags=["Export"]
)


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
