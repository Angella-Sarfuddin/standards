"""Characterize result assembly through the current DocumentSearchService.search."""

import unittest
import copy
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import patch

from app.services.document_search import input_preparation, local_matching, lookup_indexes, repository_lookup
from app.services.document_search_service import DocumentSearchService
from app.services.ieee_official_metadata import IEEEOfficialMetadataService
from app.utils.standard_identity import parse_identity


def _prepared(sdo, sdo_id, designation, key, source_identity, *, expand=False):
    identity = parse_identity(sdo, designation)
    if expand and identity.get("qualifier") == "SERIES":
        identity["family_lookup"] = True
    return {
        "sdo_name": sdo,
        "search_sdo_name": sdo,
        "requested_sdo_name": sdo,
        "sdo_id": sdo_id,
        "identity": identity,
        "displaystdno": designation,
        "result_displaystdno": designation,
        "full_display_number": designation,
        "request_key": key,
        "source_request_identity": source_identity,
        "requested_edition_status": None,
        "expand_family": expand,
    }


def _local(record_id, standard_id, sdo_id, status_id, standardno, display):
    # Local records deliberately have no ``standardyear`` attribute; search()
    # uses that distinction to choose the local formatting/status path.
    return SimpleNamespace(
        id=record_id,
        Standard_id=standard_id,
        sdo_id=sdo_id,
        status_id=status_id,
        standardno=standardno,
        display_stdNo=display,
        title=f"Title {standard_id}",
    )


def _master(record_id, standard_id, sdo_id, status_id, designation, year):
    return SimpleNamespace(
        id=record_id,
        Standard_id=standard_id,
        sdo_id=sdo_id,
        status_id=status_id,
        standardno=designation,
        display_stdNo=designation,
        standardyear=year,
        recent=0,
        title=f"Title {standard_id}",
        DocumentAvailability=1,
    )


class DocumentSearchResultAssemblyTests(unittest.TestCase):
    def _run_special_search(self):
        trace = []
        nace_key = (6, "mr010317945", None, 2023, False)
        hi_key = (7, "26", None, 2000, False)
        tema_key = (8, "twelfth edition", None, None, False)
        revision_key = (1, "9001", None, 2020, False)
        rows = [
            _prepared("NACE", 6, "NACE MR0103 (ISO 17945) : 2023", nace_key, ("special.xlsx", 2)),
            _prepared("HI", 7, "HI 2.6 : 2000", hi_key, ("special.xlsx", 3)),
            _prepared("TEMA", 8, "TEMA Twelfth Edition", tema_key, ("special.xlsx", 4)),
            _prepared("ISO", 1, "ISO 9001 AMD 1", revision_key, ("special.xlsx", 5)),
        ]
        rows[0]["identity"]["year"] = 2023
        rows[1]["identity"]["year"] = 2000
        rows[3]["identity"]["year"] = 2020
        rows[3]["has_revision_or_amendment"] = True

        nace_old = _local(71, "NACE-LEGACY-2023", 6, 6, "NACE MR0103", "NACE MR0103 : 2023")
        nace_official = _local(77, "NACE-OFFICIAL-2023", 6, 6, "ANSI NACE MR0103", "ANSI NACE MR0103 : 2023")
        hi_old = _local(81, "HI-2.6-2000", 7, 7, "HI 2.6", "HI 2.6 : 2000")
        hi_current = _local(88, "HI-14.6-2016", 7, 7, "HI 14.6", "HI 14.6 : 2016")
        tema_current = _local(99, "TEMA-2026", 8, 8, "TEMA Twelfth Edition", "TEMA Twelfth Edition")
        revision_record = _local(100, "ISO-9001-2020", 1, 1, "ISO 9001", "ISO 9001 : 2020")
        candidates = [nace_old, hi_old, tema_current, revision_record]
        unique_rows = OrderedDict((row["request_key"], row) for row in rows)
        local_matches = {
            nace_key: [nace_old],
            hi_key: [hi_old],
            tema_key: [tema_current],
            revision_key: [revision_record],
        }

        class StatusRepository:
            def get_standard_status_map(self, status_ids):
                trace.append(("status", tuple(sorted(status_ids))))
                return {
                    status_id: {"name": "ACTIVE", "cart_show": 1, "std_show": 1}
                    for status_id in status_ids
                }

        service = DocumentSearchService.__new__(DocumentSearchService)
        service.repository = SimpleNamespace()
        service.enrichment_repository = StatusRepository()
        service.resolve_sdo_ids = lambda _names: {"NACE": 6, "HI": 7, "TEMA": 8, "ISO": 1}
        service.find_master_matches = lambda _unresolved: {}
        service._official_nace_mr0103_edition = lambda row: trace.append(("nace", row["request_key"])) or (nace_official if row["request_key"] == nace_key else None)
        service._official_hi_replacement = lambda row: trace.append(("hi", row["request_key"])) or (hi_current if row["request_key"] == hi_key else None)
        service._official_ieee_replacement = lambda row, metadata=None: None
        service._candidate_has_database_document = lambda candidate, _enrichment: True
        service._select_best_current_candidate = lambda candidates, row, _status: trace.append(("select_current", row["request_key"], tuple(candidate.id for candidate in candidates))) or list(candidates)
        service._select_candidates = lambda candidates, row: trace.append(("select_family", row["request_key"], tuple(candidate.id for candidate in candidates))) or list(candidates)
        service._select_latest_tema_edition = lambda candidates, row, _status: trace.append(("select_tema", row["request_key"], tuple(candidate.id for candidate in candidates))) or list(candidates)
        service._candidate_year = lambda candidate, _sdo: {71: 2023, 77: 2023, 81: 2000, 88: 2016, 99: 2026, 100: 2020}[candidate.id]
        service.build_enrichment_map = lambda standards: {
            standard.Standard_id: {
                "price": standard.id,
                "currency": "USD",
                "currency_symbol": "$",
                "year": None,
                "document_available": True,
                "has_database_price": True,
                "classifications": [],
            }
            for standard in standards
        }
        service.search_service = SimpleNamespace(
            format_standard=lambda standard: {"Standard_id": standard.Standard_id, "standardno": standard.standardno, "display_stdNo": standard.display_stdNo, "title": standard.title},
            validate_standard=lambda _standard: "AVAILABLE",
        )
        patchers = [
            patch.object(input_preparation, "prepare_input_rows", return_value=rows),
            patch.object(repository_lookup, "lookup_display_candidates", return_value=([], {})),
            patch.object(repository_lookup, "lookup_number_candidates", return_value=([], [], [])),
            patch.object(lookup_indexes, "build_lookup_indexes", return_value=({}, {}, {})),
            patch.object(local_matching, "match_local_standards", return_value=(unique_rows, local_matches, [])),
            patch.object(IEEEOfficialMetadataService, "lookup", return_value=None),
        ]
        with patchers[0], patchers[1], patchers[2], patchers[3], patchers[4], patchers[5]:
            results = service.search([{"sdo_name": row["sdo_name"], "displaystdno": row["displaystdno"]} for row in rows])
        return results, trace, {
            "nace": nace_key,
            "hi": hi_key,
            "tema": tema_key,
            "revision": revision_key,
        }

    def _run_search(self):
        trace = []
        local_candidate = _local(
            11, "ISO-9001-2022", 1, 1, "ISO 9001", "ISO 9001 : 2022"
        )
        master_candidate = _master(
            22, "ISO-14001-2022", 1, 2, "ISO 14001 : 2022", 2022
        )
        api_candidate = _local(
            33, "API-570-2019", 2, 3, "API 570", "API 570 : 2019"
        )
        bis_candidate = _local(
            44, "BIS-2099-1986", 3, 4, "IS 2099", "IS 2099 : 1986"
        )
        family_candidate = _local(
            55,
            "ISO-3000-PART1-2020",
            1,
            1,
            "ISO 3000 Part 1",
            "ISO 3000 : Part 1 : 2020",
        )
        ieee_replacement = _local(
            66, "IEEE-802.11-2024", 5, 5,
            "IEEE 802.11", "IEEE 802.11 : 2024",
        )

        duplicate_key = (1, "9001", None, 2015, False)
        master_key = (1, "14001", None, 2020, False)
        api_key = (2, "570", None, 2019, False)
        bis_key = (3, "2099", None, 1986, False)
        unmatched_key = (4, "777", None, None, False)
        missing_sdo_key = (None, "9", None, None, False)
        series_key = (1, "3000", "SERIES", None, True)
        ieee_key = (5, "80211", None, 2016, False)
        rows = [
            _prepared("ISO", 1, "ISO 9001 : 2015", duplicate_key, ("a.xlsx", 2)),
            _prepared("ISO", 1, "ISO 9001 : 2015", duplicate_key, ("a.xlsx", 3)),
            _prepared("ISO", 1, "ISO 14001 : 2020", master_key, ("a.xlsx", 4)),
            _prepared("API", 2, "API 570 : 2019", api_key, ("a.xlsx", 5)),
            _prepared("BIS", 3, "IS 2099 : 1986", bis_key, ("a.xlsx", 6)),
            _prepared("IEC", 4, "IEC 777", unmatched_key, ("a.xlsx", 7)),
            _prepared("UNKNOWN", None, "UNKNOWN 9", missing_sdo_key, ("a.xlsx", 8)),
            _prepared("ISO", 1, "ISO 3000 SERIES", series_key, ("a.xlsx", 9), expand=True),
            _prepared("IEEE", 5, "IEEE 802.11 : 2016", ieee_key, ("a.xlsx", 10)),
        ]
        rows[0]["identity"]["year"] = 2015
        rows[1]["identity"]["year"] = 2015
        rows[2]["identity"]["year"] = 2020
        rows[3]["identity"]["year"] = 2019
        rows[4]["identity"]["year"] = 1986
        rows[8]["identity"]["year"] = 2016

        unique_rows = OrderedDict()
        for row in rows:
            unique_rows.setdefault(row["request_key"], row)
        local_matches = {
            duplicate_key: [local_candidate],
            api_key: [api_candidate],
            bis_key: [bis_candidate],
            series_key: [family_candidate],
        }
        master_matches = {master_key: [master_candidate]}

        class StatusRepository:
            def get_standard_status_map(self, status_ids):
                trace.append(("status", tuple(sorted(status_ids))))
                return {
                    1: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
                    2: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
                    3: {"name": "WITHDRAWN", "cart_show": 0, "std_show": 1},
                    4: {"name": "WITHDRAWN", "cart_show": 0, "std_show": 1},
                    5: {"name": "ACTIVE", "cart_show": 1, "std_show": 1},
                }

        service = DocumentSearchService.__new__(DocumentSearchService)
        service.repository = SimpleNamespace()
        service.enrichment_repository = StatusRepository()
        service.resolve_sdo_ids = lambda names: {"ISO": 1, "API": 2, "BIS": 3, "IEC": 4, "UNKNOWN": None}
        service.find_master_matches = lambda unresolved: trace.append(("master_fallback", tuple(row["request_key"] for row in unresolved))) or master_matches
        service.build_enrichment_map = lambda standards: {
            (standard.Standard_id): {
                "price": 100 + standard.id,
                "currency": "USD",
                "currency_symbol": "$",
                "year": getattr(standard, "standardyear", None),
                "document_available": True,
                "has_database_price": True,
                "classifications": [],
            }
            for standard in standards
        }
        service._official_nace_mr0103_edition = lambda row: trace.append(("nace", row["request_key"])) or None
        service._official_hi_replacement = lambda row: trace.append(("hi", row["request_key"])) or None
        service._official_ieee_replacement = lambda row, metadata=None: trace.append(("ieee_replacement", row["request_key"], metadata.replacement_designation if metadata else None)) or (ieee_replacement if metadata else None)
        service._candidate_has_database_document = lambda candidate, enrichment: trace.append(("availability", candidate.id)) or True
        service._select_best_current_candidate = lambda candidates, row, status_map: trace.append(("select_current", row["request_key"], tuple(c.id for c in candidates))) or list(candidates)
        service._select_candidates = lambda candidates, row: trace.append(("select_family", row["request_key"], tuple(c.id for c in candidates))) or list(candidates)
        service._candidate_year = lambda candidate, sdo: getattr(candidate, "standardyear", None) or parse_identity(sdo, candidate.display_stdNo).get("year")
        original_bis_replacement = DocumentSearchService._bis_replacement_standard
        service._bis_replacement_standard = lambda requested_sdo, standard, status: trace.append(("bis_replacement", requested_sdo, standard.id, status)) or original_bis_replacement(requested_sdo, standard, status)
        service._bis_superseded_by_note = lambda detail: trace.append(("bis_superseded_note", detail)) or DocumentSearchService._bis_superseded_by_note(detail)

        formatting = SimpleNamespace(
            format_standard=lambda standard: trace.append(("format_local", standard.id)) or {
                "Standard_id": standard.Standard_id,
                "standardno": standard.standardno,
                "display_stdNo": standard.display_stdNo,
                "title": standard.title,
            },
            validate_standard=lambda standard: trace.append(("validate_local", standard.id)) or "AVAILABLE",
        )
        service.search_service = formatting
        service.format_master_standard = lambda standard: trace.append(("format_master", standard.id)) or {
            "Standard_id": standard.Standard_id,
            "standardno": standard.standardno,
            "display_stdNo": standard.display_stdNo,
            "title": standard.title,
        }

        enrichment_calls = []
        def build_enrichment(standards):
            enrichment_calls.append(tuple(standard.id for standard in standards))
            trace.append(("enrichment", tuple(standard.id for standard in standards)))
            return {
                standard.Standard_id: {
                    "price": 100 + standard.id,
                    "currency": "USD",
                    "currency_symbol": "$",
                    "year": getattr(standard, "standardyear", None),
                    "document_available": True,
                    "has_database_price": True,
                    "classifications": [],
                }
                for standard in standards
            }
        service.build_enrichment_map = build_enrichment

        # Capture the terminal deduplication callback while retaining its real behavior.
        original_deduplicate = service._deduplicate_results
        def deduplicate(results):
            trace.append(("deduplicate", len(results)))
            return original_deduplicate(results)
        service._deduplicate_results = deduplicate

        # Preparation and discovery are controlled so these tests isolate the
        # existing result-assembly block while still calling search() end to end.
        patchers = [
            patch.object(input_preparation, "prepare_input_rows", return_value=rows),
            patch.object(repository_lookup, "lookup_display_candidates", return_value=([], {})),
            patch.object(repository_lookup, "lookup_number_candidates", return_value=([], [], [])),
            patch.object(lookup_indexes, "build_lookup_indexes", return_value=({}, {}, {})),
            patch.object(local_matching, "match_local_standards", return_value=(unique_rows, local_matches, [])),
            patch.object(IEEEOfficialMetadataService, "lookup", side_effect=lambda *args: trace.append(("ieee_lookup", *args)) or (SimpleNamespace(replacement_designation="IEEE 802.11 : 2024") if args[0] == "IEEE" else None)),
        ]
        prepared_snapshots = copy.deepcopy(rows)
        with patchers[0], patchers[1], patchers[2], patchers[3], patchers[4], patchers[5]:
            results = service.search(
                [{"sdo_name": row["sdo_name"], "displaystdno": row["displaystdno"]} for row in rows]
            )
        self.assertEqual(rows, prepared_snapshots)
        return results, trace, enrichment_calls, rows

    def test_result_templates_order_callbacks_replacements_and_source_identity(self):
        results, trace, enrichment_calls, rows = self._run_search()
        self.assertEqual(
            [
                (result["requested_sdo"], result["requested_standard"], result["matched"], result["status"])
                for result in results
            ],
            [
                ("ISO", "ISO 9001 : 2022", True, "AVAILABLE"),
                ("ISO", "ISO 9001 : 2015", False, "NOT FOUND"),
                ("ISO", "ISO 9001 : 2015", True, "AVAILABLE"),
                ("ISO", "ISO 9001 : 2015", False, "NOT FOUND"),
                ("ISO", "ISO 14001 : 2022", True, "AVAILABLE"),
                ("ISO", "ISO 14001 : 2020", False, "NOT FOUND"),
                ("API", "API 570 : 2019", False, "WITHDRAWN"),
                ("BIS", "IS 2099 : 1986", False, "WITHDRAWN"),
                ("IEC", "IEC 777", False, "NOT FOUND"),
                ("UNKNOWN", "UNKNOWN 9", False, "SDO NOT FOUND"),
                ("ISO", "ISO 3000 SERIES", True, "AVAILABLE"),
                ("IEEE", "IEEE 802.11 : 2024", True, "AVAILABLE"),
                ("IEEE", "IEEE 802.11 : 2016", False, "NOT FOUND"),
            ],
        )
        self.assertEqual(
            [result["source_row_identity"] for result in results],
            [["a.xlsx", 2], ["a.xlsx", 2], ["a.xlsx", 3], ["a.xlsx", 3],
             ["a.xlsx", 4], ["a.xlsx", 4], ["a.xlsx", 5], ["a.xlsx", 6],
             ["a.xlsx", 7], ["a.xlsx", 8], ["a.xlsx", 9], ["a.xlsx", 10], ["a.xlsx", 10]],
        )
        self.assertEqual(results[0]["standard"], {
            "Standard_id": "ISO-9001-2022",
            "standardno": "ISO 9001",
            "display_stdNo": "ISO 9001 : 2022",
            "title": "Title ISO-9001-2022",
            "enrichment": {"price": 111, "currency": "USD", "currency_symbol": "$", "year": None,
                           "document_available": True, "has_database_price": True, "classifications": []},
        })
        self.assertEqual(results[0]["status_detail"], "Requested year 2015; returned latest available edition 2022.")
        self.assertEqual(results[0], {
            "requested_sdo": "ISO",
            "requested_standard": "ISO 9001 : 2022",
            "matched": True,
            "status": "AVAILABLE",
            "status_detail": "Requested year 2015; returned latest available edition 2022.",
            "replacement_standard": None,
            "superseded_by": None,
            "standard": {
                "Standard_id": "ISO-9001-2022",
                "standardno": "ISO 9001",
                "display_stdNo": "ISO 9001 : 2022",
                "title": "Title ISO-9001-2022",
                "enrichment": {
                    "price": 111, "currency": "USD", "currency_symbol": "$", "year": None,
                    "document_available": True, "has_database_price": True, "classifications": [],
                },
            },
            "actions": {},
            "source_row_identity": ["a.xlsx", 2],
        })
        self.assertEqual(results[1]["replacement_standard"], "ISO 9001 : 2022")
        self.assertEqual(results[4]["standard"]["catalog_status"], "ACTIVE")
        self.assertEqual(results[5]["standard"], None)
        self.assertEqual(results[5]["status_detail"], "Requested edition 2020 is superseded; latest available edition is 2022.")
        self.assertEqual(results[6]["standard"], None)
        self.assertEqual(results[7]["replacement_standard"], "IS/IEC 60137 : 2017")
        self.assertEqual(results[8]["standard"], None)
        self.assertEqual(results[9], {
            "requested_sdo": "UNKNOWN", "requested_standard": "UNKNOWN 9", "matched": False,
            "status": "SDO NOT FOUND", "standard": None, "actions": {"manual_search": True},
            "not_found_reason": "SDO not found", "status_detail": "The requested SDO was not found in the catalog.",
            "source_row_identity": ["a.xlsx", 8],
        })
        self.assertEqual(results[10]["standard"]["display_stdNo"], "ISO 3000 : Part 1 : 2020")
        self.assertEqual(results[11]["standard"]["display_stdNo"], "IEEE 802.11 : 2024")
        self.assertEqual(results[11]["status_detail"], "Requested year 2016; returned latest available edition 2024.")
        self.assertEqual(results[12]["replacement_standard"], "IEEE 802.11 : 2024")
        self.assertEqual(enrichment_calls, [(11, 22, 33, 44, 55, 66)])
        self.assertEqual(
            [event for event in trace if event[0] in {"nace", "hi", "ieee_lookup", "ieee_replacement"}],
            [
                *(('nace', rows[index]['request_key']) for index in (0, 2, 3, 4, 5, 6, 7, 8)),
                *(('hi', rows[index]['request_key']) for index in (0, 2, 3, 4, 5, 6, 7, 8)),
                *(('ieee_lookup', rows[index]['search_sdo_name'], rows[index]['result_displaystdno']) for index in (0, 2, 3, 4, 5, 6, 7, 8)),
                ("ieee_replacement", rows[8]["request_key"], "IEEE 802.11 : 2024"),
                *(('hi', row['request_key']) for row in (rows[0], rows[2], rows[3], rows[4], rows[5], rows[7], rows[8])),
            ],
        )
        self.assertEqual(
            [event for event in trace if event[0] in {"master_fallback", "select_current", "select_family", "format_local", "validate_local", "format_master", "bis_replacement", "bis_superseded_note", "deduplicate"}],
            [
                ("master_fallback", ()),
                ("select_current", rows[0]["request_key"], (11,)),
                ("format_local", 11), ("validate_local", 11),
                ("select_current", rows[2]["request_key"], (22,)),
                ("format_master", 22),
                ("select_current", rows[3]["request_key"], (33,)),
                ("format_local", 33), ("validate_local", 33),
                ("bis_replacement", "API", 33, "WITHDRAWN"),
                ("select_current", rows[4]["request_key"], (44,)),
                ("format_local", 44), ("validate_local", 44),
                ("bis_replacement", "BIS", 44, "WITHDRAWN"),
                ("bis_superseded_note", None),
                ("select_current", rows[5]["request_key"], ()),
                ("select_family", rows[7]["request_key"], (55,)),
                ("format_local", 55), ("validate_local", 55),
                ("select_current", rows[8]["request_key"], ()),
                ("format_local", 66), ("validate_local", 66),
                ("deduplicate", 13),
            ],
        )
        self.assertEqual([row.get("requested_edition_status") for row in rows], [None] * len(rows))

    def test_positive_nace_hi_tema_and_standalone_revision_assembly(self):
        results, trace, keys = self._run_special_search()
        self.assertEqual(
            [(result["requested_sdo"], result["requested_standard"], result["matched"], result["status"]) for result in results],
            [
                ("NACE", "NACE MR0103 (ISO 17945) : 2023", True, "AVAILABLE"),
                ("HI", "HI 14.6 : 2016", True, "AVAILABLE"),
                ("HI", "HI 2.6 : 2000", False, "NOT FOUND"),
                ("TEMA", "TEMA 2026 Edition : 2026", True, "AVAILABLE"),
                ("TEMA", "TEMA Twelfth Edition", False, "NOT FOUND"),
                ("ISO", "ISO 9001 AMD 1", False, "NOT FOUND"),
            ],
        )
        self.assertEqual(results[0]["standard"]["Standard_id"], "NACE-OFFICIAL-2023")
        self.assertEqual(results[1]["standard"]["Standard_id"], "HI-14.6-2016")
        self.assertEqual(results[2]["replacement_standard"], "HI 14.6 : 2016")
        self.assertEqual(results[3]["standard"]["display_stdNo"], "TEMA 2026 Edition : 2026")
        self.assertEqual(results[4]["replacement_standard"], "TEMA 2026 Edition : 2026")
        self.assertEqual(results[5]["status_detail"], "Revision/amendment requests are excluded from standard matching.")
        self.assertEqual(
            [event for event in trace if event[0] in {"nace", "hi", "select_tema", "select_current"}],
            [
                *(('nace', keys[name]) for name in ("nace", "hi", "tema", "revision")),
                *(('hi', keys[name]) for name in ("nace", "hi", "tema", "revision")),
                ("hi", keys["nace"]),
                ("select_current", keys["nace"], (77,)),
                ("hi", keys["hi"]),
                ("select_current", keys["hi"], (88,)),
                ("hi", keys["tema"]),
                ("select_tema", keys["tema"], (99,)),
                ("select_current", keys["tema"], (99,)),
            ],
        )


if __name__ == "__main__":
    unittest.main()
