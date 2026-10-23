"""Characterize master-fallback orchestration before extraction."""

import unittest
from types import SimpleNamespace

from app.services.document_search_service import DocumentSearchService
from app.utils.standard_identity import parse_identity


def _row(sdo_name, sdo_id, designation, key, source_row, **extra):
    row = {
        "sdo_name": sdo_name,
        "search_sdo_name": sdo_name,
        "sdo_id": sdo_id,
        "displaystdno": designation,
        "full_display_number": designation,
        "identity": parse_identity(sdo_name, designation),
        "request_key": key,
        "source_row": source_row,
    }
    row.update(extra)
    return row


def _master(record_id, sdo_id, designation, status_id, year):
    return SimpleNamespace(
        id=record_id,
        Standard_id=f"STD-{record_id}",
        sdo_id=sdo_id,
        status_id=status_id,
        display_stdNo=designation,
        standardno=designation,
        standardyear=year,
        recent=0,
    )


class DocumentSearchMasterFallbackTests(unittest.TestCase):
    def test_withdrawn_bis_duplicate_master_rows_do_not_create_two_matches(self):
        first = SimpleNamespace(
            id=492833,
            Standard_id="BIS-Boss-27432",
            sdo_id=77,
            status_id=10,
            status=0,
            standardno="BIS 2099",
            display_stdNo="BIS 2099 : 1986",
            standardyear=1986,
            recent=0,
            DocumentAvailability=0,
            url="",
        )
        second = SimpleNamespace(
            id=492834,
            Standard_id="BIS-Boss-29634",
            sdo_id=77,
            status_id=10,
            status=0,
            standardno="BIS 2099",
            display_stdNo="BIS 2099 : 1986",
            standardyear=1986,
            recent=0,
            DocumentAvailability=0,
            url="",
        )
        master_rows = [first, second]
        queried_master_ids = []

        class LocalRepository:
            def __getattr__(self, name):
                if name.startswith("search_by_sdo_and_"):
                    return lambda *_args: []
                raise AttributeError(name)

        class EnrichmentRepository:
            def search_master_by_sdo_and_display_variants(self, _pairs):
                queried_master_ids.extend(row.id for row in master_rows)
                return list(master_rows)

            def search_master_by_sdo_and_standard_numbers(self, _pairs):
                return []

            def search_master_by_sdo_and_identity_hints(self, _hints):
                return list(master_rows)

            def get_standard_status_map(self, status_ids):
                if 10 in status_ids:
                    return {
                        10: {
                            "name": "WITHDRAWN",
                            "cart_show": 0,
                            "std_show": 0,
                        },
                    }
                return {}

        service = DocumentSearchService.__new__(DocumentSearchService)
        service.repository = LocalRepository()
        service.enrichment_repository = EnrichmentRepository()
        service.resolve_sdo_ids = lambda names: {
            str(name).upper(): 77 for name in names
        }

        selection_trace = []
        original_select_master_candidates = service._select_master_candidates

        def capture_master_selection(candidates, row):
            selected = original_select_master_candidates(candidates, row)
            selection_trace.append(
                (
                    {candidate.id for candidate in candidates},
                    [candidate.id for candidate in selected],
                )
            )
            return selected

        service._select_master_candidates = capture_master_selection

        results = service.search(
            [{"displaystdno": "BIS 2099 : 1986"}]
        )

        self.assertEqual(set(queried_master_ids), {492833, 492834})
        self.assertTrue(
            any(candidate_ids == {492833, 492834} and not selected_ids
                for candidate_ids, selected_ids in selection_trace)
        )
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["matched"])
        self.assertIsNone(results[0]["standard"])

    def test_empty_input_returns_without_repository_or_callback_calls(self):
        trace = []

        class EnrichmentRepository:
            def __getattr__(self, name):
                def unexpected(*args):
                    trace.append((name, args))
                    raise AssertionError("empty fallback must not query")
                return unexpected

        service = DocumentSearchService.__new__(DocumentSearchService)
        service.enrichment_repository = EnrichmentRepository()
        service.assertion_trace = trace
        self.assertEqual(service.find_master_matches([]), {})
        self.assertEqual(trace, [])

    def test_repository_and_callback_traces_candidate_order_and_row_mutation(self):
        calls = []
        callbacks = []
        direct = _master("iso-1", 1, "ISO 1", 10, 2020)
        direct_duplicate = _master("iso-1", 1, "ISO 1", 10, 2020)
        latest_tema = _master("tema-latest", 9, "TEMA Twelfth Edition : 2026", 40, 2026)
        identity_iso2 = _master("iso-2", 1, "ISO 2:2022", 30, 2022)

        class EnrichmentRepository:
            def search_master_by_sdo_and_display_variants(self, pairs):
                calls.append(("display", list(pairs)))
                return [direct]

            def search_master_by_sdo_and_standard_numbers(self, pairs):
                calls.append(("standard", list(pairs)))
                return [direct_duplicate]

            def get_latest_tema_edition(self, sdo_id):
                calls.append(("tema_latest", sdo_id))
                return latest_tema

            def get_standard_status_map(self, status_ids):
                ids = set(status_ids)
                calls.append(("status", ids))
                if ids == {10, 40}:
                    return {
                        10: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
                        40: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
                    }
                if ids == {30}:
                    return {30: {"name": "WITHDRAWN", "cart_show": 0, "std_show": 0}}
                raise AssertionError(f"unexpected status IDs: {ids}")

            def search_master_by_sdo_and_identity_hints(self, hints):
                calls.append(("identity", list(hints)))
                return [identity_iso2]

        service = DocumentSearchService.__new__(DocumentSearchService)
        service.enrichment_repository = EnrichmentRepository()

        def spy_callback(name, original, capture):
            if name == "_select_master_candidates":
                def spy(candidates, row):
                    args = (candidates, row)
                    result = original(candidates, row)
                    capture(name, args, result)
                    return result
                return spy

            def spy(*args, **kwargs):
                result = original(*args, **kwargs)
                capture(name, args, result)
                return result
            return spy

        for name in (
            "_is_tema_edition_request",
            "_masters_satisfy_row",
            "_display_masters_satisfy",
            "_unique_standards",
            "_build_identity_candidate_index",
            "_master_candidate_matches_identity",
            "_candidate_is_part_of_root",
            "_select_master_candidates",
        ):
            original = getattr(service, name)

            def capture(callback_name, args, result):
                if callback_name == "_is_tema_edition_request":
                    callbacks.append((callback_name, args[0]["source_row"], result))
                elif callback_name in {"_masters_satisfy_row", "_display_masters_satisfy"}:
                    callbacks.append(
                        (
                            callback_name,
                            args[0]["source_row"],
                            (
                                [
                                    (key, [value.id for value in group])
                                    for key, group in args[1].items()
                                ]
                                if callback_name == "_display_masters_satisfy"
                                else [getattr(value, "id", value) for value in args[1]]
                            ),
                            {
                                key: value.get("name")
                                for key, value in args[2].items()
                            },
                            result,
                        )
                    )
                elif callback_name == "_unique_standards":
                    callbacks.append(
                        (
                            callback_name,
                            [getattr(value, "id", value) for value in args[0]],
                            [value.id for value in result],
                        )
                    )
                elif callback_name == "_select_master_candidates":
                    callbacks.append(
                        (
                            callback_name,
                            [getattr(value, "id", value) for value in args[0]],
                            args[1]["source_row"],
                            [getattr(value, "id", value) for value in result],
                        )
                    )
                elif callback_name == "_build_identity_candidate_index":
                    callbacks.append(
                        (
                            callback_name,
                            [value.id for value in args[0]],
                            [row["source_row"] for row in args[1]],
                            list(result.keys()),
                        )
                    )
                elif callback_name == "_master_candidate_matches_identity":
                    callbacks.append(
                        (callback_name, args[0].id, args[1]["source_row"], result)
                    )
                elif callback_name == "_candidate_is_part_of_root":
                    callbacks.append(
                        (callback_name, args[0].id, args[1]["source_row"], result)
                    )
                else:
                    callbacks.append(
                        (
                            callback_name,
                            [value.id for value in args[0]],
                            args[1]["source_row"],
                            {key: value.get("name") for key, value in args[2].items()},
                            [value.id for value in result],
                        )
                    )

            setattr(service, name, spy_callback(name, original, capture))

        rows = [
            _row("ISO", 1, "ISO 1", "iso-1-a", 1, skip_master_identity=True),
            _row("ISO", 1, "ISO 1", "iso-1-b", 2, skip_master_identity=True),
            _row("ISO", 1, "ISO 2:2022", "iso-2", 3),
            _row("TEMA", 9, "TEMA Twelfth Edition : 2026", "tema-a", 4, skip_master_identity=True),
            _row("TEMA", 9, "TEMA Twelfth Edition : 2026", "tema-b", 5, skip_master_identity=True),
        ]

        matches = service.find_master_matches(rows)

        self.assertEqual(
            calls,
            [
                (
                    "display",
                    [
                        (1, "1"), (1, "ISO 1"), (1, "ISO/IEC 1"),
                        (1, "ISO/TS 1"), (1, "ISO/TR 1"),
                        (1, "2"), (1, "ISO 2"), (1, "ISO/IEC 2"),
                        (1, "ISO/TS 2"), (1, "ISO/TR 2"),
                        (9, "TWELFTH EDITION"), (9, "TEMA TWELFTH EDITION"),
                    ],
                ),
                (
                    "standard",
                    [
                        (1, "1"), (1, "ISO 1"), (1, "ISO/IEC 1"),
                        (1, "ISO/TS 1"), (1, "ISO/TR 1"),
                        (1, "2"), (1, "ISO 2"), (1, "ISO/IEC 2"),
                        (1, "ISO/TS 2"), (1, "ISO/TR 2"),
                        (9, "TWELFTH EDITION"), (9, "TEMA TWELFTH EDITION"),
                        (1, "ISO 2:2022"),
                        (9, "TEMA Twelfth Edition : 2026"),
                    ],
                ),
                ("tema_latest", 9),
                ("status", {10, 40}),
                ("identity", [(1, "ISO", "2", None)]),
                ("status", {30}),
            ],
        )
        self.assertEqual(
            list(matches),
            ["iso-1-a", "iso-1-b", "tema-a", "tema-b"],
        )
        self.assertEqual(
            [[candidate.id for candidate in values] for values in matches.values()],
            [["iso-1"], ["iso-1"], ["tema-latest"], ["tema-latest"]],
        )
        self.assertEqual(rows[2].get("requested_edition_status"), "WITHDRAWN")
        self.assertTrue(all("requested_edition_status" not in row for row in rows[:2] + rows[3:]))
        self.assertEqual(
            [event[0] for event in callbacks],
            [
                "_is_tema_edition_request", "_is_tema_edition_request",
                "_is_tema_edition_request", "_is_tema_edition_request",
                "_is_tema_edition_request", "_unique_standards",
                "_unique_standards", "_unique_standards",
                "_masters_satisfy_row",
                "_display_masters_satisfy", "_unique_standards",
                "_unique_standards", "_build_identity_candidate_index",
                "_master_candidate_matches_identity", "_is_tema_edition_request",
                "_select_master_candidates", "_master_candidate_matches_identity",
                "_is_tema_edition_request", "_select_master_candidates",
                "_master_candidate_matches_identity", "_is_tema_edition_request",
                "_select_master_candidates", "_master_candidate_matches_identity",
                "_is_tema_edition_request", "_select_master_candidates",
                "_master_candidate_matches_identity", "_is_tema_edition_request",
                "_select_master_candidates",
            ],
        )
        self.assertEqual(
            [event for event in callbacks if event[0] == "_is_tema_edition_request"],
            [
                ("_is_tema_edition_request", 1, False),
                ("_is_tema_edition_request", 2, False),
                ("_is_tema_edition_request", 3, False),
                ("_is_tema_edition_request", 4, True),
                ("_is_tema_edition_request", 5, True),
                ("_is_tema_edition_request", 1, False),
                ("_is_tema_edition_request", 2, False),
                ("_is_tema_edition_request", 3, False),
                ("_is_tema_edition_request", 4, True),
                ("_is_tema_edition_request", 5, True),
            ],
        )
        self.assertEqual(
            [event for event in callbacks if event[0] == "_unique_standards"],
            [
                ("_unique_standards", ["iso-1"] * 8, ["iso-1"]),
                ("_unique_standards", ["iso-1"] * 8, ["iso-1"]),
                ("_unique_standards", [], []),
                ("_unique_standards", ["tema-latest"] * 2, ["tema-latest"]),
                ("_unique_standards", ["tema-latest"] * 2, ["tema-latest"]),
            ],
        )
        self.assertEqual(
            [event for event in callbacks if event[0] == "_masters_satisfy_row"],
            [("_masters_satisfy_row", 3, [], {10: "ACTIVE", 40: "ACTIVE"}, False)],
        )
        self.assertEqual(
            [event for event in callbacks if event[0] == "_display_masters_satisfy"],
            [
                (
                    "_display_masters_satisfy",
                    3,
                    [
                        ((1, "ISO 1"), ["iso-1"] * 4),
                        ((9, "TEMA TWELFTH EDITION:2026"), ["tema-latest"] * 2),
                    ],
                    {10: "ACTIVE", 40: "ACTIVE"},
                    False,
                )
            ],
        )
        self.assertEqual(
            [event for event in callbacks if event[0] == "_master_candidate_matches_identity"],
            [
                ("_master_candidate_matches_identity", "iso-1", 1, True),
                ("_master_candidate_matches_identity", "iso-1", 2, True),
                ("_master_candidate_matches_identity", "iso-2", 3, True),
                ("_master_candidate_matches_identity", "tema-latest", 4, True),
                ("_master_candidate_matches_identity", "tema-latest", 5, True),
            ],
        )
        self.assertEqual(
            [event for event in callbacks if event[0] == "_build_identity_candidate_index"],
            [
                (
                    "_build_identity_candidate_index",
                    ["iso-1", "iso-1", "tema-latest", "iso-2"],
                    [1, 2, 3, 4, 5],
                    [(1, "ISO", "1"), (9, "TEMA", "TWELFTHEDITION"), (1, "ISO", "2")],
                )
            ],
        )
        self.assertEqual(
            [event for event in callbacks if event[0] == "_select_master_candidates"],
            [
                ("_select_master_candidates", ["iso-1", "iso-1", "iso-1"], 1, ["iso-1"]),
                ("_select_master_candidates", ["iso-1", "iso-1", "iso-1"], 2, ["iso-1"]),
                ("_select_master_candidates", ["iso-2"], 3, []),
                ("_select_master_candidates", ["tema-latest", "tema-latest"], 4, ["tema-latest"]),
                ("_select_master_candidates", ["tema-latest", "tema-latest"], 5, ["tema-latest"]),
            ],
        )


if __name__ == "__main__":
    unittest.main()
