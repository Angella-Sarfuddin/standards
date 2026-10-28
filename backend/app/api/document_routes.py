import time

from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException
)
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.database.database import get_db
from app.schemas.document import DocumentSearchRequest
from app.services.document_search_service import DocumentSearchService
from app.services.document_service import DocumentService
from app.services.grouping_service import GroupingService


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)


MAX_FILE_SIZE = 10 * 1024 * 1024


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

        document_service = DocumentService()
        extracted_rows = document_service.extract(
            file.filename,
            file.file,
        )
        return {
            "filename": file.filename,
            "total": len(extracted_rows),
            "results": extracted_rows,
        }

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

        return _search_document(
            db,
            request.rows,
            request.filename,
        )

    except OperationalError as error:

        print(
            "Document search database error:",
            type(error.orig).__name__,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "The standards database is currently unavailable. "
                "Check the database network or VPN connection, then retry."
            ),
        )

    except Exception as error:

        print("Document search error:", error)

        raise HTTPException(
            status_code=500,
            detail="An error occurred while searching the standards"
        )


def _search_document(db, rows, filename=None):
    total_start = time.perf_counter()
    print(
        f"\n[SEARCH TIMING] START | "
        f"file={filename} | rows={len(rows)}"
    )

    step_start = time.perf_counter()
    search_service = DocumentSearchService(db)
    print(
        f"[SEARCH TIMING] DocumentSearchService init: "
        f"{time.perf_counter() - step_start:.3f}s"
    )

    step_start = time.perf_counter()
    results = search_service.search(rows)
    print(
        f"[SEARCH TIMING] DocumentSearchService.search: "
        f"{time.perf_counter() - step_start:.3f}s"
    )

    step_start = time.perf_counter()
    matched_count = sum(1 for result in results if result["matched"])
    sdo_not_found_count = sum(
        1 for result in results if result["status"] == "SDO NOT FOUND"
    )
    not_found_count = sum(
        1 for result in results if result["status"] == "NOT FOUND"
    )
    print(
        f"[SEARCH TIMING] Result counting: "
        f"{time.perf_counter() - step_start:.3f}s"
    )

    step_start = time.perf_counter()
    grouping = GroupingService.group_results(results)
    print(
        f"[SEARCH TIMING] Grouping: "
        f"{time.perf_counter() - step_start:.3f}s"
    )
    print(
        f"[SEARCH TIMING] END | "
        f"total={time.perf_counter() - total_start:.3f}s | "
        f"matched={matched_count} | "
        f"not_found={not_found_count} | "
        f"sdo_missing={sdo_not_found_count}\n"
    )

    return {
        "filename": filename,
        "total": len(results),
        "input_requests": len(rows),
        "duplicates_collapsed": 0,
        "matched": matched_count,
        "not_found": not_found_count,
        "sdo_not_found": sdo_not_found_count,
        "grouping": grouping,
        "results": results,
    }
