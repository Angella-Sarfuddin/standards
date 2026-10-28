from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.standards import StandardsSearchRequest
from app.services.document_search_service import DocumentSearchService


router = APIRouter(
    prefix="/standards",
    tags=["Standards"]
)


@router.post("/search")
def search_standards(
    request: StandardsSearchRequest,
    db: Session = Depends(get_db)
):
    rows = [
        {"displaystdno": str(value).strip()}
        for value in request.standards or []
        if value is not None and str(value).strip()
    ]
    return {
        "results": DocumentSearchService(db).search(rows)
    }
