from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.responses import XLSX_MEDIA_TYPE, ZIP_MEDIA_TYPE, attachment
from app.database.database import get_db
from app.schemas.export import ExportBothRequest, FoundAndNotFoundExportRequest
from app.services.export_preparation import (
    prepare_both_export,
    prepare_found_and_not_found_export,
    prepare_latest_year_export,
    prepare_quotation_export,
)
from app.services.export_service import ExportService


router = APIRouter(
    prefix="/export",
    tags=["Export"],
)


@router.post("/excel")
def export_excel(results: list[dict], db: Session = Depends(get_db)):
    payload = prepare_quotation_export(results, db)
    file = ExportService.export_results(payload)
    return attachment(
        file.getvalue(),
        XLSX_MEDIA_TYPE,
        "standards_quotation.xlsx",
    )


@router.post("/latest-years")
def export_latest_years(results: list[dict], db: Session = Depends(get_db)):
    refreshed = prepare_latest_year_export(results, db)
    file = ExportService.export_latest_years(refreshed)
    return attachment(
        file.getvalue(),
        XLSX_MEDIA_TYPE,
        "standards_latest_years.xlsx",
    )


@router.post("/both")
def export_both(payload: ExportBothRequest, db: Session = Depends(get_db)):
    quotation, latest_year_results = prepare_both_export(
        payload.quotation_results,
        payload.latest_year_results,
        db,
    )
    file = ExportService.export_both(quotation, latest_year_results)
    return attachment(
        file.getvalue(),
        ZIP_MEDIA_TYPE,
        "standards_exports.zip",
    )


@router.post("/not-found")
def export_not_found(results: list[dict]):
    file = ExportService.export_not_found_excel(results)
    return attachment(
        file.getvalue(),
        XLSX_MEDIA_TYPE,
        "not_found_standards.xlsx",
    )


@router.post("/found-and-not-found")
def export_found_and_not_found(
    payload: FoundAndNotFoundExportRequest,
    db: Session = Depends(get_db),
):
    quotation_results, all_results = prepare_found_and_not_found_export(
        payload.quotation_results,
        payload.all_results,
        db,
    )
    file = ExportService.export_found_and_not_found_zip(
        quotation_results,
        all_results,
    )
    return attachment(
        file.getvalue(),
        ZIP_MEDIA_TYPE,
        "standards_found_and_not_found.zip",
    )
