from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from app.controllers.standards_controller import StandardsController


router = APIRouter(
    prefix="/standards",
    tags=["Standards"]
)


class StandardsSearchRequest(BaseModel):
    standards: list[str]


@router.post("/search")
def search_standards(
    request: StandardsSearchRequest,
    db: Session = Depends(get_db)
):
    return {
        "results": StandardsController.search_standards(
            db,
            request.standards
        )
    }