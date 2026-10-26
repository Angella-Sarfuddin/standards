"""Compatibility import. The search class lives in ``document_search``."""

from app.services.document_search.service import DocumentSearchService

__all__ = ["DocumentSearchService"]
