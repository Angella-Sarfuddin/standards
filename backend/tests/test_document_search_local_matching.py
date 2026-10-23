"""Characterize the local-matching workflow before extraction."""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.document_search import input_preparation
from app.services.document_search_service import DocumentSearchService
from app.utils.standard_identity import parse_identity


class StopBeforeMasterFallback(Exception):
    pass


def _prepared_row(sdo_name, sdo_id, designation, source_row):
    identity = parse_identity(sdo_name, designation)
    return {
        "sdo_name": sdo_name,
        "search_sdo_name": sdo_name,
        "sdo_id": sdo_id,
        "identity": identity,
        "displaystdno": designation,
        "result_displaystdno": designation,
        "full_display_number": designation,
        "request_key": (sdo_id or sdo_name, identity.get("core_number"), source_row),
        "source_row": source_row,
        "source_location": f"row {source_row}",
        "source_request_identity": ["local.xlsx", source_row, designation],
    }


def _standard(record_id, designation, status_id):
    return SimpleNamespace(
        id=record_id,
        Standard_id=f"STD-{record_id}",
        sdo_id=1,
        status_id=status_id,
        standardno=designation,
        display_stdNo=designation,
        stdNo_normalized=designation,
        standardyear=None,
        recent=0,
    )


def _capture_local_matching(rows, display_records, identity_records):
    trace = []
    prepared_rows = list(rows)

    class Repository:
        def search_by_sdo_and_display_variants(self, pairs):
            trace.append(("repository", "search_by_sdo_and_display_variants", list(pairs)))
            return list(display_records)

        def search_by_sdo_and_display_numbers(self, pairs):
            trace.append(("repository", "search_by_sdo_and_display_numbers", list(pairs)))
            return []

        def search_by_sdo_and_normalized_numbers(self, pairs):
            trace.append(("repository", "search_by_sdo_and_normalized_numbers", list(pairs)))
            return []

        def search_by_sdo_and_standard_numbers(self, pairs):
            trace.append(("repository", "search_by_sdo_and_standard_numbers", list(pairs)))
            return []

        def search_by_sdo_and_identity_hints(self, hints):
            trace.append(("repository", "search_by_sdo_and_identity_hints", list(hints)))
            return list(identity_records)

    class EnrichmentRepository:
        def search_master_by_sdo_and_display_variants(self, pairs):
            trace.append(("enrichment_repository", "search_master_by_sdo_and_display_variants", list(pairs)))
            return []

        def get_standard_status_map(self, status_ids):
            normalized = set(status_ids)
            trace.append(("enrichment_repository", "get_standard_status_map", normalized))
            return {}

    service = DocumentSearchService.__new__(DocumentSearchService)
    service.repository = Repository()
    service.enrichment_repository = EnrichmentRepository()
    service.resolve_sdo_ids = lambda _names: {"ISO": 1}

    callback_trace = []
    for method_name in (
        "_direct_candidate_lists",
        "_unique_standards",
        "_select_candidate",
        "_row_needs_identity_discovery",
        "_candidate_matches_identity",
        "_candidate_is_part_of_root",
        "_select_candidates",
        "_is_bare_qualifier_request",
    ):
        original = getattr(service, method_name)

        def make_spy(name, callback):
            if name in {"_select_candidate", "_select_candidates"}:
                def spy(candidates, row):
                    args = (candidates, row)
                    result = callback(candidates, row)
                    capture(name, callback, args, result)
                    return result

                return spy

            def spy(*args, **kwargs):
                result = callback(*args, **kwargs)
                capture(name, callback, args, result)
                return result
            return spy

        def capture(name, callback, args, result):
            if name in {"_direct_candidate_lists", "_unique_standards"}:
                values = result
                if name == "_direct_candidate_lists":
                    values = [
                        [getattr(item, "id", item) for item in group]
                        for group in result
                    ]
                else:
                    values = [getattr(item, "id", item) for item in result]
                callback_trace.append((name, "return", values))
            elif name in {"_select_candidate", "_select_candidates"}:
                callback_trace.append(
                    (
                        name,
                        "args",
                        [getattr(item, "id", item) for item in args[0]],
                        args[1]["request_key"],
                    )
                )
                callback_trace.append(
                    (
                        name,
                        "return",
                        getattr(result, "id", None)
                        if name == "_select_candidate"
                        else [getattr(item, "id", item) for item in result],
                    )
                )
            elif name == "_row_needs_identity_discovery":
                callback_trace.append((name, args[0]["request_key"], result))
            elif name == "_is_bare_qualifier_request":
                callback_trace.append((name, args[0]["request_key"], result))
            else:
                callback_trace.append((name, args[0].id, args[1]["request_key"], result))

        setattr(service, method_name, make_spy(method_name, original))

    captured = {}

    def stop_at_master(unresolved):
        frame = sys._getframe(1)
        captured["unique_rows"] = list(frame.f_locals["unique_prepared_rows"].values())
        captured["local_matches"] = frame.f_locals["local_matches"]
        captured["unresolved"] = unresolved
        raise StopBeforeMasterFallback

    service.find_master_matches = stop_at_master

    with patch.object(input_preparation, "prepare_input_rows", return_value=prepared_rows):
        try:
            service.search(
                [{"sdo_name": row["sdo_name"], "displaystdno": row["displaystdno"]} for row in prepared_rows]
            )
        except StopBeforeMasterFallback:
            pass
        else:
            raise AssertionError("search did not reach the master-fallback boundary")

    captured["trace"] = trace
    captured["callback_trace"] = callback_trace
    return captured


class DocumentSearchLocalMatchingTests(unittest.TestCase):
    def test_local_matching_trace_and_unresolved_rows(self):
        rows = [
            _prepared_row("ISO", 1, "ISO 1", 2),
            _prepared_row("ISO", 1, "ISO 2", 3),
            _prepared_row("UNKNOWN", None, "UNKNOWN 3", 4),
            _prepared_row("ISO", 1, "ISO 4 Part 1", 5),
            _prepared_row("ISO", 1, "ISO 1", 6),
        ]
        rows[3]["identity"]["qualifier"] = "PART"
        rows[3]["identity"]["family_lookup"] = True
        # The last request deliberately shares the first request key to verify
        # first-row identity. The prepared row's source row is excluded from
        # the key in that duplicate case.
        rows[-1]["request_key"] = rows[0]["request_key"]
        direct = _standard("direct-1", "ISO 1", 10)
        identity = _standard("identity-2", "ISO 2", 20)
        family = _standard("identity-4-part", "ISO 4 Part 1", 30)

        captured = _capture_local_matching(rows, [direct], [identity, family])

        self.assertEqual(
            captured["trace"],
            [
                (
                    "repository",
                    "search_by_sdo_and_display_variants",
                    [
                        (1, "1"), (1, "ISO 1"), (1, "ISO/IEC 1"),
                        (1, "ISO/TS 1"), (1, "ISO/TR 1"),
                        (1, "2"), (1, "ISO 2"), (1, "ISO/IEC 2"),
                        (1, "ISO/TS 2"), (1, "ISO/TR 2"),
                        (1, "4 PART 1"), (1, "ISO 4 PART 1"),
                        (1, "ISO/IEC 4 PART 1"), (1, "ISO/TS 4 PART 1"),
                        (1, "ISO/TR 4 PART 1"), (1, "4 PART1"),
                        (1, "ISO 4 PART1"), (1, "ISO/IEC 4 PART1"),
                        (1, "ISO/TS 4 PART1"), (1, "ISO/TR 4 PART1"),
                        (1, "4-1"), (1, "ISO 4-1"), (1, "ISO/IEC 4-1"),
                        (1, "ISO/TS 4-1"), (1, "ISO/TR 4-1"),
                        (1, "4 1"), (1, "ISO 4 1"), (1, "ISO/IEC 4 1"),
                        (1, "ISO/TS 4 1"), (1, "ISO/TR 4 1"),
                        (1, "4.1"), (1, "ISO 4.1"), (1, "ISO/IEC 4.1"),
                        (1, "ISO/TS 4.1"), (1, "ISO/TR 4.1"),
                    ],
                ),
                (
                    "repository",
                    "search_by_sdo_and_display_numbers",
                    [(1, "ISO 2"), (1, "ISO 4 Part 1")],
                ),
                (
                    "repository",
                    "search_by_sdo_and_normalized_numbers",
                    [(1, "ISO2"), (1, "ISO4PART1")],
                ),
                (
                    "repository",
                    "search_by_sdo_and_standard_numbers",
                    [(1, "ISO 2"), (1, "ISO 4 Part 1")],
                ),
                ("enrichment_repository", "get_standard_status_map", {10}),
                (
                    "repository",
                    "search_by_sdo_and_identity_hints",
                    [(1, "ISO", "2"), (1, "ISO", "4")],
                ),
                ("enrichment_repository", "get_standard_status_map", {20, 30}),
            ],
        )
        selection_trace = [
            event
            for event in captured["callback_trace"]
            if event[0] in {"_select_candidate", "_select_candidates"}
        ]
        self.assertEqual(
            selection_trace,
            [
                ("_select_candidate", "args", ["direct-1"], rows[0]["request_key"]),
                ("_select_candidate", "return", "direct-1"),
                ("_select_candidate", "args", [], rows[1]["request_key"]),
                ("_select_candidate", "return", None),
                ("_select_candidate", "args", [], rows[3]["request_key"]),
                ("_select_candidate", "return", None),
                ("_select_candidates", "args", ["direct-1"], rows[0]["request_key"]),
                ("_select_candidates", "return", ["direct-1"]),
                ("_select_candidates", "args", ["identity-2"], rows[1]["request_key"]),
                ("_select_candidates", "return", ["identity-2"]),
                ("_select_candidates", "args", ["identity-4-part"], rows[3]["request_key"]),
                ("_select_candidates", "return", ["identity-4-part"]),
            ],
        )
        self.assertEqual(
            [row["source_row"] for row in captured["unique_rows"]],
            [2, 3, 4, 5],
        )
        self.assertEqual(
            {key: [item.id for item in value] for key, value in captured["local_matches"].items()},
            {
                rows[0]["request_key"]: ["direct-1"],
                rows[1]["request_key"]: ["identity-2"],
                rows[3]["request_key"]: ["identity-4-part"],
            },
        )
        self.assertEqual(
            [(row["source_row"], row.get("skip_master_identity")) for row in captured["unresolved"]],
            [(2, None), (3, None), (5, True)],
        )
        self.assertIs(captured["unresolved"][0], captured["unique_rows"][0])
        self.assertIsNot(captured["unresolved"][2], captured["unique_rows"][3])
        self.assertIs(captured["unresolved"][2]["identity"], captured["unique_rows"][3]["identity"])

    def test_first_status_lookup_runs_empty_and_second_lookup_is_skipped(self):
        row = _prepared_row("ISO", 1, "ISO 9", 9)
        captured = _capture_local_matching([row], [], [])
        status_calls = [entry for entry in captured["trace"] if entry[1] == "get_standard_status_map"]
        self.assertEqual(status_calls, [("enrichment_repository", "get_standard_status_map", set())])
        self.assertEqual(captured["local_matches"], {})
        self.assertEqual([row["source_row"] for row in captured["unresolved"]], [9])


if __name__ == "__main__":
    unittest.main()
