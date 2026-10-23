from app.services.document_service import DocumentService


class ExcelController:

    @staticmethod
    def search_excel(
        db,
        filename,
        file,
    ):
        """
        Extract an Excel file only.

        The actual standards search is handled separately by
        /documents/search so the same uploaded file is not searched twice.
        """
        document_service = DocumentService()

        rows = document_service.extract(
            filename,
            file
        )

        return {
            "filename": filename,
            "total": len(rows),
            "results": rows,
        }