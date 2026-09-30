from fastapi import APIRouter, Depends, UploadFile, File

from sqlalchemy.orm import Session

from database import get_db
from app.controllers.excel_controller import ExcelController


router = APIRouter(
    prefix="/excel",
    tags=["Excel"]
)


@router.post("/upload")
def upload_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Extract and search an Excel upload using the single application DB.

    Search and enrichment both use the same ``bsbedge_test`` session supplied
    by ``get_db``. There is intentionally no second/enrichment DB dependency.
    """
    return ExcelController.search_excel(
        db,
        file.filename,
        file.file,
    )
