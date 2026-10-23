from app.services.document_search_service import DocumentSearchService


class StandardsController:

    @staticmethod
    def search_standards(db, standard_numbers: list[str]):
        rows = [
            {"displaystdno": str(value).strip()}
            for value in standard_numbers or []
            if value is not None and str(value).strip()
        ]
        return DocumentSearchService(db).search(rows)
