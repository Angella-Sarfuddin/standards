from app.repositories.standards_repository import StandardsRepository
from app.utils.normalizer import normalize_standard_number


class SearchService:

    def __init__(self, repository: StandardsRepository):
        self.repository = repository

    def search_standard(self, standard_number: str):
        if not standard_number:
            return {
                "requested_standard": standard_number,
                "matched": False,
                "status": "NOT FOUND",
                "standard": None
            }

        original_number = standard_number.strip()
        normalized_number = normalize_standard_number(original_number)

        # 1. Exact display standard number
        results = self.repository.search_by_display_number(
            original_number
        )

        # 2. Exact normalized standard number
        if not results:
            results = self.repository.search_by_normalized_number(
                normalized_number
            )

        # 3. Exact base standard number
        if not results:
            results = self.repository.search_by_standard_number(
                original_number
            )

        if not results:
            return {
                "requested_standard": original_number,
                "matched": False,
                "status": "NOT FOUND",
                "standard": None
            }

        standard = results[0]

        return {
            "requested_standard": original_number,
            "matched": True,
            "status": self.validate_standard(standard),
            "standard": self.format_standard(standard)
        }

    def search_standards(self, standard_numbers: list[str]):
        if not standard_numbers:
            return []

        # Keep every original request
        original_numbers = [
            value.strip()
            for value in standard_numbers
            if value and value.strip()
        ]

        if not original_numbers:
            return []

        # Remove duplicates ONLY for database lookup
        unique_numbers = list(dict.fromkeys(original_numbers))

        # Normalize unique values
        normalized_numbers = {
            value: normalize_standard_number(value)
            for value in unique_numbers
        }

        # --------------------------------------------------
        # 1. Bulk display number lookup
        # --------------------------------------------------

        display_results = self.repository.search_by_display_numbers(
            unique_numbers
        )

        display_map = {
            standard.display_stdNo: standard
            for standard in display_results
        }

        # --------------------------------------------------
        # 2. Bulk normalized number lookup
        # --------------------------------------------------

        normalized_values = list(normalized_numbers.values())

        normalized_results = self.repository.search_by_normalized_numbers(
            normalized_values
        )

        normalized_map = {
            standard.stdNo_normalized: standard
            for standard in normalized_results
        }

        # --------------------------------------------------
        # 3. Bulk standard number lookup
        # --------------------------------------------------

        standard_results = self.repository.search_by_standard_numbers(
            unique_numbers
        )

        standard_map = {
            standard.standardno: standard
            for standard in standard_results
        }

        # --------------------------------------------------
        # 4. Match against ORIGINAL requests
        # --------------------------------------------------

        results = []

        for requested in original_numbers:

            normalized = normalize_standard_number(requested)

            # Matching priority:
            # 1. display_stdNo
            # 2. stdNo_normalized
            # 3. standardno

            standard = (
                display_map.get(requested)
                or normalized_map.get(normalized)
                or standard_map.get(requested)
            )

            if not standard:
                results.append({
                    "requested_standard": requested,
                    "matched": False,
                    "status": "NOT FOUND",
                    "standard": None
                })
                continue

            results.append({
                "requested_standard": requested,
                "matched": True,
                "status": self.validate_standard(standard),
                "standard": self.format_standard(standard)
            })

        return results

    def validate_standard(self, standard):
        if standard.status == 1 and standard.esales == 1:
            return "AVAILABLE"

        if standard.status == 0:
            return "INACTIVE"

        if standard.status == 1 and standard.esales == 0:
            return "NOT FOR SALE"

        return "REVIEW"

    def format_standard(self, standard):
        return {
            "id": standard.id,
            "standardno": standard.standardno,
            "display_stdNo": standard.display_stdNo,
            "stdNo_normalized": standard.stdNo_normalized,
            "title": standard.title,
            "url": standard.url,
            "sdo_id": standard.sdo_id,
            "status": standard.status,
            "esales": standard.esales
        }