from pydantic import BaseModel


class DocumentSearchRequest(BaseModel):
    rows: list[dict]
    filename: str | None = None


class DocumentExtractResponse(BaseModel):
    filename: str
    total: int
    results: list[dict]


class DocumentSearchResponse(BaseModel):
    filename: str | None = None
    total: int
    input_requests: int
    duplicates_collapsed: int
    matched: int
    not_found: int
    sdo_not_found: int
    grouping: dict
    results: list[dict]
