"""Pydantic request models for the HTTP API."""

from app.schemas.document import DocumentSearchRequest
from app.schemas.standards import StandardsSearchRequest

__all__ = [
    "DocumentSearchRequest",
    "StandardsSearchRequest",
]
