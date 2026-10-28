from pydantic import BaseModel


class StandardsSearchRequest(BaseModel):
    standards: list[str]


class StandardsSearchResponse(BaseModel):
    results: list[dict]
