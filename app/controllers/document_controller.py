import time

from app.services.document_search_service import DocumentSearchService
from app.services.document_service import DocumentService
from app.services.grouping_service import GroupingService


class DocumentController:
	@staticmethod
	def extract_document(filename, file):
		document_service = DocumentService()
		extracted_rows = document_service.extract(filename, file)

		return {
			"filename": filename,
			"total": len(extracted_rows),
			"results": extracted_rows,
		}

	@staticmethod
	def search_document(db, rows, filename=None):
		total_start = time.perf_counter()

		print(
			f"\n[SEARCH TIMING] START | "
			f"file={filename} | rows={len(rows)}"
		)

		step_start = time.perf_counter()
		search_service = DocumentSearchService(db)

		print(
			f"[SEARCH TIMING] DocumentSearchService init: "
			f"{time.perf_counter() - step_start:.3f}s"
		)

		step_start = time.perf_counter()
		results = search_service.search(rows)

		print(
			f"[SEARCH TIMING] DocumentSearchService.search: "
			f"{time.perf_counter() - step_start:.3f}s"
		)

		step_start = time.perf_counter()
		matched_count = sum(
			1
			for result in results
			if result["matched"]
		)
		sdo_not_found_count = sum(
			1
			for result in results
			if result["status"] == "SDO NOT FOUND"
		)
		not_found_count = sum(
			1
			for result in results
			if result["status"] == "NOT FOUND"
		)

		print(
			f"[SEARCH TIMING] Result counting: "
			f"{time.perf_counter() - step_start:.3f}s"
		)

		step_start = time.perf_counter()
		grouping = GroupingService.group_results(results)

		print(
			f"[SEARCH TIMING] Grouping: "
			f"{time.perf_counter() - step_start:.3f}s"
		)

		print(
			f"[SEARCH TIMING] END | "
			f"total={time.perf_counter() - total_start:.3f}s | "
			f"matched={matched_count} | "
			f"not_found={not_found_count} | "
			f"sdo_missing={sdo_not_found_count}\n"
		)

		return {
			"filename": filename,
			"total": len(results),
			"matched": matched_count,
			"not_found": not_found_count,
			"sdo_not_found": sdo_not_found_count,
			"grouping": grouping,
			"results": results,
		}
