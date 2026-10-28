from pydantic import BaseModel


class StandardsSearchRequest(BaseModel):
    standards: list[str]
