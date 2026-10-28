from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.schemas.standards import StandardsSearchRequest, StandardsSearchResponse
from app.services.document_query_service import DocumentQueryService


router = APIRouter(
    prefix="/standards",
    tags=["Standards"],
)


@router.post("/search", response_model=StandardsSearchResponse)
def search_standards(
    request: StandardsSearchRequest,
    db: Session = Depends(get_db),
):
    return DocumentQueryService.search_standards(db, request.standards)
