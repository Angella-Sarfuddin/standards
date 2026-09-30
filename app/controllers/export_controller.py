from io import BytesIO

import pandas as pd

from app.services.export_service import ExportService


class ExportController:

    @staticmethod
    def export_standards(db, ids):

        service = ExportService(db)

        dataframe = service.get_standards_for_export(ids)

        output = BytesIO()

        dataframe.to_excel(
            output,
            index=False
        )

        output.seek(0)

        return output