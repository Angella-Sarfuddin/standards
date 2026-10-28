from fastapi import APIRouter, Depends, UploadFile, File

from sqlalchemy.orm import Session

from app.database.database import get_db
from app.services.document_service import DocumentService


router = APIRouter(
    prefix="/excel",
    tags=["Excel"]
)


@router.post("/upload")
def upload_excel(
    file: UploadFile = File(...),
    _db: Session = Depends(get_db),
):
    """Extract and search an Excel upload using the single application DB.

    Search and enrichment both use the same ``bsbedge_test`` session supplied
    by ``get_db``. There is intentionally no second/enrichment DB dependency.
    """
    rows = DocumentService().extract(file.filename, file.file)
    return {
        "filename": file.filename,
        "total": len(rows),
        "results": rows,
    }
