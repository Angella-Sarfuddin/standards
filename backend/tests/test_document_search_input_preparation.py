"""Characterize the input-preparation portion of document search."""

import json
from pathlib import Path
import unittest
from types import SimpleNamespace

from app.services.document_search_service import DocumentSearchService


class StopAfterPreparation(Exception):
    """Stop search at the first consumer after all rows are prepared."""


BASELINE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "document_search_input_preparation_baseline.json"
)


def _fixture_rows():
    return [
        {
            "sdo_name": "ISO",
            "displaystdno": "ISO 17025:2017",
            "source_file": "sample.xlsx",
            "source_row": 2,
        },
        {
            "sdo_name": "ISO",
            "displaystdno": "ISO 17025:2017",
            "source_file": "sample.xlsx",
            "source_row": 3,
        },
        {
            "sdo_name": "BIS",
            "displaystdno": "IS 2099 Rev 2, 1986",
            "source_file": "sample.xlsx",
            "source_row": 4,
        },
        {
            "sdo_name": "IEC",
            "displaystdno": "IEC 60034-1:2022 AMD 1",
            "source_file": "sample.xlsx",
            "source_row": 5,
        },
        {
            "sdo_name": "SP",
            "displaystdno": "0104",
            "source_file": "sample.xlsx",
            "source_row": 6,
        },
        {
            "sdo_name": "SP",
            "displaystdno": "0104",
            "source_file": "sample.xlsx",
            "source_row": 7,
        },
        {
            "sdo_name": "SP",
            "displaystdno": "75",
            "source_file": "sample.xlsx",
            "source_row": 8,
        },
        {
            "sdo_name": "IEC",
            "displaystdno": "IEC 62443 Part 1",
            "include_subsections": True,
            "source_sheet": "Sheet A",
            "source_row": 9,
        },
    ]


def _identity_trace(identity):
    return {
        key: identity.get(key)
        for key in (
            "sdo_name",
            "core_number",
            "qualifier",
            "year",
            "identifier_prefix",
            "family_lookup",
        )
    }


def capture_prepared_rows_and_callback_trace():
    """Observe search after preparation and stop before lookup orchestration."""
    rows = _fixture_rows()
    service = DocumentSearchService.__new__(DocumentSearchService)
    service.repository = SimpleNamespace(
        search_by_sdo_and_display_variants=lambda _pairs: [],
    )
    service.enrichment_repository = SimpleNamespace(
        search_master_by_sdo_and_display_variants=lambda _pairs: [],
    )
    service.resolve_sdo_ids = lambda _names: {
        "ISO": 1,
        "BIS": 2,
        "IS": 2,
        "IEC": 3,
        "API": 4,
    }

    prepared_rows = []
    callback_trace = []

    original_tema_request = DocumentSearchService._is_tema_edition_request
    original_bis_revision = DocumentSearchService._is_bis_revision_edition
    original_expand_family = DocumentSearchService._should_expand_family
    original_request_key = DocumentSearchService._request_identity_key

    def is_tema_edition_request(row):
        result = original_tema_request(row)
        # During preparation this method receives the display-only probe. Its
        # earlier SDO-resolution call receives the original input row.
        if set(row) == {"displaystdno"}:
            callback_trace.append(
                {
                    "callback": "_is_tema_edition_request",
                    "args": [row["displaystdno"]],
                    "return": result,
                }
            )
        return result

    def is_bis_revision_edition(sdo_name, expression):
        result = original_bis_revision(sdo_name, expression)
        callback_trace.append(
            {
                "callback": "_is_bis_revision_edition",
                "args": [sdo_name, expression],
                "return": result,
            }
        )
        return result

    def should_expand_family(identity, include_subsections=False):
        result = original_expand_family(identity, include_subsections)
        callback_trace.append(
            {
                "callback": "_should_expand_family",
                "args": [_identity_trace(identity), include_subsections],
                "return": result,
            }
        )
        return result

    def request_identity_key(sdo_id, sdo_name, identity):
        result = original_request_key(sdo_id, sdo_name, identity)
        callback_trace.append(
            {
                "callback": "_request_identity_key",
                "args": [sdo_id, sdo_name, _identity_trace(identity)],
                "return": list(result),
            }
        )
        return result

    def infer_unique_catalog_sdo(sdo_name, displaystdno):
        result = {
            "0104": ("API", 4),
            "75": None,
        }.get(displaystdno)
        callback_trace.append(
            {
                "callback": "_infer_unique_catalog_sdo",
                "args": [sdo_name, displaystdno],
                "return": list(result) if result is not None else None,
            }
        )
        return result

    service._is_tema_edition_request = is_tema_edition_request
    service._is_bis_revision_edition = is_bis_revision_edition
    service._should_expand_family = should_expand_family
    service._request_identity_key = request_identity_key
    service._infer_unique_catalog_sdo = infer_unique_catalog_sdo

    def intercept_after_preparation(row):
        prepared_rows.append(row)
        if len(prepared_rows) == len(rows):
            raise StopAfterPreparation
        return False

    # This method is called once per prepared row while building the API
    # display-query pairs, after the complete preparation loop has finished.
    service._is_api_request = intercept_after_preparation

    try:
        service.search(rows)
    except StopAfterPreparation:
        pass
    else:
        raise AssertionError("search did not reach the post-preparation hook")

    return json.loads(
        json.dumps(
            {
                "prepared_rows": prepared_rows,
                "callback_trace": callback_trace,
            }
        )
    )


class DocumentSearchInputPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with BASELINE_PATH.open(encoding="utf-8") as baseline_file:
            cls.baseline = json.load(baseline_file)

    def test_prepared_rows_match_captured_pre_extraction_behavior(self):
        captured = capture_prepared_rows_and_callback_trace()
        self.assertEqual(captured["prepared_rows"], self.baseline["prepared_rows"])

    def test_callback_order_arguments_and_cache_behavior_match_baseline(self):
        captured = capture_prepared_rows_and_callback_trace()
        self.assertEqual(captured["callback_trace"], self.baseline["callback_trace"])

        names = [event["callback"] for event in captured["callback_trace"]]
        self.assertEqual(names.count("_infer_unique_catalog_sdo"), 2)
        self.assertEqual(names.count("_should_expand_family"), 6)
        self.assertEqual(names.count("_request_identity_key"), 6)

    def test_duplicate_requests_keep_distinct_source_row_identities(self):
        prepared = capture_prepared_rows_and_callback_trace()["prepared_rows"]
        self.assertEqual(
            prepared[0]["request_key"],
            prepared[1]["request_key"],
        )
        self.assertEqual(
            prepared[0]["source_request_identity"],
            ["sample.xlsx", 2, "ISO 17025:2017"],
        )
        self.assertEqual(
            prepared[1]["source_request_identity"],
            ["sample.xlsx", 3, "ISO 17025:2017"],
        )


if __name__ == "__main__":
    unittest.main()
