from pydantic import BaseModel


class DocumentSearchRequest(BaseModel):
    rows: list[dict]
    filename: str | None = None
