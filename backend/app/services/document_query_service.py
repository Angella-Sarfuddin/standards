import logging
import time

from app.services.document_search_service import DocumentSearchService
from app.services.grouping_service import GroupingService


logger = logging.getLogger(__name__)

STATUS_NOT_FOUND = "NOT FOUND"
STATUS_SDO_NOT_FOUND = "SDO NOT FOUND"


class DocumentQueryService:

    @staticmethod
    def search_document(db, rows, filename=None):
        total_start = time.perf_counter()
        logger.info(
            "[SEARCH TIMING] START | file=%s | rows=%s",
            filename,
            len(rows),
        )

        step_start = time.perf_counter()
        search_service = DocumentSearchService(db)
        logger.info(
            "[SEARCH TIMING] DocumentSearchService init: %.3fs",
            time.perf_counter() - step_start,
        )

        step_start = time.perf_counter()
        results = search_service.search(rows)
        logger.info(
            "[SEARCH TIMING] DocumentSearchService.search: %.3fs",
            time.perf_counter() - step_start,
        )

        step_start = time.perf_counter()
        matched_count = sum(1 for result in results if result["matched"])
        sdo_not_found_count = sum(
            1 for result in results if result["status"] == STATUS_SDO_NOT_FOUND
        )
        not_found_count = sum(
            1 for result in results if result["status"] == STATUS_NOT_FOUND
        )
        logger.info(
            "[SEARCH TIMING] Result counting: %.3fs",
            time.perf_counter() - step_start,
        )

        step_start = time.perf_counter()
        grouping = GroupingService.group_results(results)
        logger.info(
            "[SEARCH TIMING] Grouping: %.3fs",
            time.perf_counter() - step_start,
        )
        logger.info(
            "[SEARCH TIMING] END | total=%.3fs | matched=%s | "
            "not_found=%s | sdo_missing=%s",
            time.perf_counter() - total_start,
            matched_count,
            not_found_count,
            sdo_not_found_count,
        )

        return {
            "filename": filename,
            "total": len(results),
            "input_requests": len(rows),
            "duplicates_collapsed": 0,
            "matched": matched_count,
            "not_found": not_found_count,
            "sdo_not_found": sdo_not_found_count,
            "grouping": grouping,
            "results": results,
        }

    @staticmethod
    def search_standards(db, standard_numbers):
        rows = [
            {"displaystdno": str(value).strip()}
            for value in standard_numbers or []
            if value is not None and str(value).strip()
        ]
        return {"results": DocumentSearchService(db).search(rows)}
