import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.uploads import read_limited_upload
from app.database.database import get_db
from app.schemas.document import (
    DocumentExtractResponse,
    DocumentSearchRequest,
    DocumentSearchResponse,
)
from app.services.document_query_service import DocumentQueryService
from app.services.document_service import DocumentService


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


@router.post("/extract", response_model=DocumentExtractResponse)
def extract_document(file: UploadFile = File(...)):
    read_limited_upload(file)
    try:
        DocumentService.detect_file_type(file.filename)
        extracted_rows = DocumentService().extract(file.filename, file.file)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception:
        logger.exception("Document extraction error")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while extracting the document",
        )
    return {
        "filename": file.filename,
        "total": len(extracted_rows),
        "results": extracted_rows,
    }


@router.post("/search", response_model=DocumentSearchResponse)
def search_document(
    request: DocumentSearchRequest,
    db: Session = Depends(get_db),
):
    try:
        return DocumentQueryService.search_document(
            db,
            request.rows,
            request.filename,
        )
    except OperationalError:
        raise
    except Exception:
        logger.exception("Document search error")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while searching the standards",
        )
