from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.uploads import read_limited_upload
from app.schemas.document import DocumentExtractResponse
from app.services.document_service import DocumentService


router = APIRouter(
    prefix="/excel",
    tags=["Excel"],
)


@router.post("/upload", response_model=DocumentExtractResponse)
def upload_excel(file: UploadFile = File(...)):
    """Extract rows from an Excel upload. Search is a separate request."""
    read_limited_upload(file)
    try:
        rows = DocumentService().extract(file.filename, file.file)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "filename": file.filename,
        "total": len(rows),
        "results": rows,
    }
