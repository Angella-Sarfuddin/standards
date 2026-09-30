from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.services.export_service import ExportService
from app.services.grouping_service import GroupingService


router = APIRouter(
    prefix="/export",
    tags=["Export"]
)


@router.post("/excel")
def export_excel(results: list[dict]):

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

    return StreamingResponse(
        file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=standards_quotation.xlsx"
        }
    )