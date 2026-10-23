"""Pin request-aware result deduplication behavior."""

import unittest

from app.services.document_search_service import DocumentSearchService


def _result(requested_standard, source_identity=None):
    result = {
        "requested_sdo": "ISO",
        "requested_standard": requested_standard,
        "matched": True,
        "status": "AVAILABLE",
        "standard": {
            "Standard_id": "ISO-1-2020",
            "sdo_id": 1,
            "standardno": "ISO 1",
            "display_stdNo": "ISO 1:2020",
            "standardyear": 2020,
        },
    }
    if source_identity is not None:
        result["_source_request_identity"] = tuple(source_identity)
    return result


class DocumentSearchDeduplicationTests(unittest.TestCase):
    def test_exact_repeated_requests_without_source_identity_deduplicate(self):
        results = DocumentSearchService._deduplicate_results(
            [_result("ISO 1"), _result("ISO 1")]
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["requested_standard"], "ISO 1")
        self.assertNotIn("source_row_identity", results[0])

    def test_exact_repeated_requests_with_distinct_source_identities_survive(self):
        results = DocumentSearchService._deduplicate_results(
            [
                _result("ISO 1", ("input.xlsx", 2, "ISO 1")),
                _result("ISO 1", ("input.xlsx", 3, "ISO 1")),
            ]
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(
            [result["source_row_identity"] for result in results],
            [["input.xlsx", 2, "ISO 1"], ["input.xlsx", 3, "ISO 1"]],
        )

    def test_distinct_requests_resolving_to_same_catalog_record_survive(self):
        results = DocumentSearchService._deduplicate_results(
            [_result("ISO 1"), _result("ISO 1:2020")]
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(
            [result["requested_standard"] for result in results],
            ["ISO 1", "ISO 1:2020"],
        )
        self.assertEqual(
            [result["standard"]["Standard_id"] for result in results],
            ["ISO-1-2020", "ISO-1-2020"],
        )


if __name__ == "__main__":
    unittest.main()
