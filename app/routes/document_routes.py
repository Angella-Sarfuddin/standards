from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException
)
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from app.controllers.document_controller import DocumentController
from app.services.document_service import DocumentService


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)


MAX_FILE_SIZE = 10 * 1024 * 1024


class DocumentSearchRequest(BaseModel):
    rows: list[dict]
    filename: str | None = None


@router.post("/extract")
def extract_document(
    file: UploadFile = File(...)
):

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="File name is required"
        )

    file_content = file.file.read()

    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File size must not exceed 10 MB"
        )

    file.file.seek(0)

    try:

        DocumentService.detect_file_type(
            file.filename
        )

        return DocumentController.extract_document(
            file.filename,
            file.file
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:

        print("Document extraction error:", error)

        raise HTTPException(
            status_code=500,
            detail="An error occurred while extracting the document"
        )


@router.post("/search")
def search_document(
    request: DocumentSearchRequest,
    db: Session = Depends(get_db),
):

    try:

        return DocumentController.search_document(
            db,
            request.rows,
            request.filename
        )

    except Exception as error:

        print("Document search error:", error)

        raise HTTPException(
            status_code=500,
            detail="An error occurred while searching the standards"
        )