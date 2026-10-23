import pandas as pd

from app.services.extractors.base_extractor import BaseExtractor


class CSVExtractor(BaseExtractor):

    def extract(self, file):
        dataframe = pd.read_csv(file)

        dataframe.columns = [
            str(column).strip().lower()
            for column in dataframe.columns
        ]

        required_columns = {"sdo name", "displaystdno"}

        if required_columns.issubset(dataframe.columns):
            dataframe = dataframe[
                ["sdo name", "displaystdno"]
            ].dropna(how="all")

            return dataframe.to_dict(orient="records")

        return {
            "text": dataframe.to_csv(index=False),
            "source_type": "csv"
        }