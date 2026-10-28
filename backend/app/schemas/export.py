from pydantic import BaseModel


class ExportBothRequest(BaseModel):
    quotation_results: list[dict] = []
    latest_year_results: list[dict] = []


class FoundAndNotFoundExportRequest(BaseModel):
    quotation_results: list[dict] = []
    all_results: list[dict] = []
