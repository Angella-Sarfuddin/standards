
import time

from app.repositories.standards_repository import StandardsRepository
from app.repositories.enrichment_repository import EnrichmentRepository
from app.services.search_service import SearchService

from app.utils.standard_formatter import (
    normalize_display_number,
    build_full_display_number,
)

from app.utils.standard_identity import (
    parse_identity,
    standard_number_year,
    normalize_tokens,
    normalize_identity_core,
    sdo_identifier_prefixes,
    identity_matches,
    identity_index_cores,
)


class DocumentSearchService:

    def __init__(self, db):
        # Single-DB architecture:
        # search, master fallback, pricing, and classifications
        # all use the same application DB session.
        self.repository = StandardsRepository(db)
        self.search_service = SearchService(self.repository)
        self.enrichment_repository = EnrichmentRepository(db)

    # ============================================================
    # MAIN SEARCH
    # ============================================================

    def search(self, rows):
        started = time.perf_counter()

        if not rows:
            return []

        print(
            f"[SEARCH TIMING] START | rows={len(rows)}"
        )

        # --------------------------------------------------------
        # 1. RESOLVE SDO IDS
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        sdo_names = [
            row.get("sdo_name", "")
            for row in rows
            if row.get("sdo_name")
        ]

        sdo_map = self.resolve_sdo_ids(sdo_names)

        print(
            f"[SEARCH TIMING] SDO resolution: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        # --------------------------------------------------------
        # 2. PREPARE INPUT ROWS
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        prepared_rows = []

        first_row_by_request = {}
        parsed_request_cache = {}

        for row_index, row in enumerate(rows, start=1):

            sdo_name = str(
                row.get("sdo_name") or ""
            ).strip()

            displaystdno = str(
                row.get("displaystdno") or ""
            ).strip()

            raw_request_key = (
                sdo_name.upper(),
                displaystdno.upper(),
            )
            parsed_request = parsed_request_cache.get(raw_request_key)

            if parsed_request is None:
                identity = parse_identity(
                    sdo_name,
                    displaystdno,
                )
                sdo_id = sdo_map.get(sdo_name.upper())
                full_display_number = build_full_display_number(
                    sdo_name,
                    displaystdno,
                )
                request_key = self._request_identity_key(
                    sdo_id,
                    sdo_name,
                    identity,
                )
                parsed_request = (
                    identity,
                    sdo_id,
                    full_display_number,
                    request_key,
                )
                parsed_request_cache[raw_request_key] = parsed_request
            else:
                (
                    identity,
                    sdo_id,
                    full_display_number,
                    request_key,
                ) = parsed_request

            source_row = row.get("source_row", row_index)
            source_sheet = row.get("source_sheet")
            source_location = (
                f"{source_sheet} row {source_row}"
                if source_sheet
                else f"row {source_row}"
            )
            duplicate_of = first_row_by_request.get(request_key)
            first_row_by_request.setdefault(
                request_key,
                source_location,
            )

            prepared_rows.append(
                {
                    "sdo_name": sdo_name,
                    "displaystdno": displaystdno,
                    "full_display_number": full_display_number,
                    "sdo_id": sdo_id,
                    "identity": identity,
                    "request_key": request_key,
                    "source_location": source_location,
                    "duplicate_of": duplicate_of,
                }
            )

        print(
            f"[SEARCH TIMING] Row preparation: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        # --------------------------------------------------------
        # 3. PRIMARY DISPLAY NUMBER LOOKUP
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        display_pairs = []

        for row in prepared_rows:

            if not row["sdo_id"]:
                continue

            for variant in row["identity"].get(
                "variants",
                [],
            ):
                display_pairs.append(
                    (
                        row["sdo_id"],
                        variant,
                    )
                )

        display_pairs = list(
            dict.fromkeys(display_pairs)
        )

        display_candidates = (
            self.repository
            .search_by_sdo_and_display_variants(
                display_pairs
            )
        )

        candidate_map = {}

        for standard in display_candidates:

            key = (
                standard.sdo_id,
                normalize_tokens(
                    standard.display_stdNo or ""
                ),
            )

            candidate_map.setdefault(
                key,
                [],
            ).append(standard)

        print(
            f"[SEARCH TIMING] Display lookup: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        # --------------------------------------------------------
        # 4. EXACT / NORMALIZED / STANDARD NUMBER LOOKUPS
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        exact_pairs = []
        normalized_pairs = []

        for row in prepared_rows:

            if not row["sdo_id"]:
                continue

            if self._row_has_display_candidates(row, candidate_map):
                continue

            full = row[
                "full_display_number"
            ]

            exact_pairs.append(
                (
                    row["sdo_id"],
                    full,
                )
            )

            normalized_pairs.append(
                (
                    row["sdo_id"],
                    normalize_tokens(
                        full
                    ).replace(" ", ""),
                )
            )

        exact_pairs = list(
            dict.fromkeys(exact_pairs)
        )

        normalized_pairs = list(
            dict.fromkeys(normalized_pairs)
        )

        exact_results = (
            self.repository
            .search_by_sdo_and_display_numbers(
                exact_pairs
            )
        )

        normalized_results = (
            self.repository
            .search_by_sdo_and_normalized_numbers(
                normalized_pairs
            )
        )

        standard_number_results = (
            self.repository
            .search_by_sdo_and_standard_numbers(
                exact_pairs
            )
        )

        print(
            f"[SEARCH TIMING] Exact/normalized lookup: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        # --------------------------------------------------------
        # BUILD LOOKUP MAPS
        # --------------------------------------------------------

        exact_result_map = {}

        for standard in exact_results:

            key = (
                standard.sdo_id,
                normalize_display_number(
                    standard.display_stdNo or ""
                ),
            )

            exact_result_map.setdefault(
                key,
                [],
            ).append(standard)

        normalized_result_map = {}

        for standard in normalized_results:

            key = (
                standard.sdo_id,
                normalize_tokens(
                    standard.stdNo_normalized or ""
                ).replace(" ", ""),
            )

            normalized_result_map.setdefault(
                key,
                [],
            ).append(standard)

        standard_number_map = {}

        for standard in standard_number_results:

            key = (
                standard.sdo_id,
                normalize_display_number(
                    standard.standardno or ""
                ),
            )

            standard_number_map.setdefault(
                key,
                [],
            ).append(standard)

        # --------------------------------------------------------
        # 5. DESIGNATION-NEUTRAL CANDIDATE DISCOVERY
        # --------------------------------------------------------

        unique_prepared_rows = {}

        for row in prepared_rows:
            unique_prepared_rows.setdefault(
                row["request_key"],
                row,
            )

        identity_lookup_rows = []

        for row in unique_prepared_rows.values():
            if not row["sdo_id"]:
                continue

            direct_candidate_lists = self._direct_candidate_lists(
                row,
                candidate_map,
                exact_result_map,
                normalized_result_map,
                standard_number_map,
            )
            direct_candidates = self._unique_standards(
                [
                    candidate
                    for candidates in direct_candidate_lists
                    for candidate in candidates
                ]
            )
            selected_direct = self._select_candidate(
                direct_candidates,
                row,
            )

            # Designation-neutral LIKE is only for rows that still lack a
            # usable local match, or that need family/bare-qualifier
            # expansion from additional identity candidates.
            if self._row_needs_identity_discovery(row, selected_direct):
                identity_lookup_rows.append(row)

        identity_hints = []

        for row in identity_lookup_rows:
            identity = row["identity"]
            core = (
                identity.get("core_number_pattern")
                or identity.get("core_number")
            )

            if not core:
                continue

            if "SERIES" in identity.get("body", ""):
                continue

            identity_hints.append(
                (
                    row["sdo_id"],
                    row["sdo_name"],
                    core,
                )
            )

        identity_hints = list(dict.fromkeys(identity_hints))
        stage_started = time.perf_counter()
        identity_candidates = (
            self.repository
            .search_by_sdo_and_identity_hints(identity_hints)
        )
        identity_candidate_index = (
            self._build_identity_candidate_index(
                identity_candidates,
                identity_lookup_rows,
            )
        )

        print(
            f"[SEARCH TIMING] Identity lookup: "
            f"{time.perf_counter() - stage_started:.3f}s | "
            f"hints={len(identity_hints)} | "
            f"candidates={len(identity_candidates)}"
        )

        # --------------------------------------------------------
        # 6. LOCAL MATCHING
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        local_matches = {}
        unresolved = []

        for row in unique_prepared_rows.values():

            key = row["request_key"]

            if not row["sdo_id"]:
                continue

            display_candidates, exact_candidates, normalized_candidates, standard_candidates = (
                self._direct_candidate_lists(
                    row,
                    candidate_map,
                    exact_result_map,
                    normalized_result_map,
                    standard_number_map,
                )
            )

            candidates = list(display_candidates)

            # ----------------------------------------------------
            # Designation-neutral candidates
            # ----------------------------------------------------

            identity = row["identity"]

            core = identity.get(
                "core_number"
            )

            if core:

                normalized_core = normalize_identity_core(
                    core
                )

                possible_identity_candidates = (
                    identity_candidate_index.get(
                        (
                            row["sdo_id"],
                            normalize_tokens(row["sdo_name"]),
                            normalized_core,
                        ),
                        {},
                    ).values()
                )

                for candidate in possible_identity_candidates:

                    if (
                        candidate.sdo_id
                        != row["sdo_id"]
                    ):
                        continue

                    if (
                        self._candidate_matches_identity(candidate, row)
                        or self._candidate_is_part_of_root(candidate, row)
                    ):
                        candidates.append(
                            candidate
                        )

            candidates.extend(exact_candidates)
            candidates.extend(normalized_candidates)
            candidates.extend(standard_candidates)

            # ----------------------------------------------------
            # Remove duplicates
            # ----------------------------------------------------

            candidates = self._unique_standards(
                candidates
            )

            selected = self._select_candidates(
                candidates,
                row,
            )

            if selected:
                local_matches[key] = selected
                if self._is_bare_qualifier_request(row):
                    # Local family/bare-qualifier match is already
                    # authoritative for the response. Still consult master
                    # via cheap display/standardno IN lookups for edition
                    # enrichment, but skip the expensive identity LIKE scan.
                    unresolved.append(
                        {
                            **row,
                            "skip_master_identity": True,
                        }
                    )
            else:
                unresolved.append(row)

        print(
            f"[SEARCH TIMING] Local matching: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        # --------------------------------------------------------
        # 7. MASTER FALLBACK
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        master_matches = self.find_master_matches(
            unresolved
        )

        print(
            f"[SEARCH TIMING] Master fallback: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        # --------------------------------------------------------
        # 8. COLLECT MATCHED STANDARDS
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        matched_standards = []

        seen = set()

        matched_candidates = [
            standard
            for matches in (
                list(local_matches.values())
                + list(master_matches.values())
            )
            for standard in matches
        ]

        for standard in matched_candidates:

            standard_id = standard.Standard_id or standard.id

            if standard_id in seen:
                continue

            seen.add(
                standard_id
            )

            matched_standards.append(
                standard
            )

        enrichment_map = (
            self.build_enrichment_map(
                matched_standards
            )
        )

        print(
            f"[SEARCH TIMING] Enrichment: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        # --------------------------------------------------------
        # 9. BUILD FINAL RESULTS
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        results = []
        result_templates = {}

        for row in prepared_rows:

            key = row["request_key"]
            duplicate_metadata = {
                "is_duplicate": row["duplicate_of"] is not None,
                "duplicate_of": row["duplicate_of"],
            }

            cached_templates = result_templates.get(key)
            if cached_templates is not None:
                results.extend(
                    {
                        **template,
                        "requested_sdo": row["sdo_name"],
                        "requested_standard": row["displaystdno"],
                        **duplicate_metadata,
                    }
                    for template in cached_templates
                )
                continue

            # ----------------------------------------------------
            # SDO NOT FOUND
            # ----------------------------------------------------

            if not row["sdo_id"]:

                template = {
                    "requested_sdo": row["sdo_name"],
                    "requested_standard": row["displaystdno"],
                    "matched": False,
                    "status": "SDO NOT FOUND",
                    "standard": None,
                    **duplicate_metadata,
                    "actions": {"manual_search": True},
                }
                result_templates[key] = [template]
                results.append(template)

                continue

            # ----------------------------------------------------
            # NORMAL STANDARDS SEARCH MATCH
            # ----------------------------------------------------

            local_standards = local_matches.get(key, [])
            master_standards = master_matches.get(key, [])

            request_candidates = local_standards + master_standards

            if self._is_bare_qualifier_request(row):
                requested_family = (
                    "PART"
                    if row["identity"].get("family_lookup")
                    else row["identity"].get("qualifier")
                )
                family_members = []

                for candidate in request_candidates:
                    candidate_identity = parse_identity(
                        row["sdo_name"],
                        candidate.display_stdNo
                        or candidate.standardno
                        or "",
                    )
                    candidate_qualifier = candidate_identity.get(
                        "qualifier"
                    )
                    if candidate_qualifier and candidate_qualifier.startswith(
                        f"{requested_family}:"
                    ):
                        family_members.append(candidate)

                if family_members:
                    request_candidates = family_members

            standards_by_id = {}
            for standard in request_candidates:
                standard_id = standard.Standard_id or standard.id
                standards_by_id.setdefault(standard_id, standard)

            if standards_by_id:
                templates = []
                for standard in standards_by_id.values():
                    is_master = hasattr(standard, "standardyear")
                    requested_year = row["identity"].get("year")

                    if is_master:
                        data = self.format_master_standard(standard)
                        status = "AVAILABLE"
                        actual_year = standard.standardyear
                    else:
                        data = self.search_service.format_standard(standard)
                        status = self.search_service.validate_standard(standard)
                        actual_year = self._candidate_year(
                            standard,
                            row["sdo_name"],
                        )

                    status_detail = None
                    if requested_year is not None and actual_year != requested_year:
                        status = "EDITION MISMATCH"
                        status_detail = (
                            f"Requested edition {requested_year}; "
                            f"showing {actual_year or 'an undated'} catalogue record."
                        )

                    data["enrichment"] = enrichment_map.get(
                        standard.Standard_id,
                        {
                            "price": None,
                            "currency": None,
                            "year": None,
                            "classifications": [],
                        },
                    )
                    template = {
                        "requested_sdo": row["sdo_name"],
                        "requested_standard": row["displaystdno"],
                        "matched": True,
                        "status": status,
                        "status_detail": status_detail,
                        "standard": data,
                        **duplicate_metadata,
                        "actions": {},
                    }
                    templates.append(template)
                    results.append(template)
                result_templates[key] = templates
                continue

            # ----------------------------------------------------
            # NOT FOUND
            # ----------------------------------------------------

            template = {
                "requested_sdo": row["sdo_name"],
                "requested_standard": row["displaystdno"],
                "matched": False,
                "status": "NOT FOUND",
                "standard": None,
                **duplicate_metadata,
                "actions": {"manual_search": True},
            }
            result_templates[key] = [template]
            results.append(template)

        print(
            f"[SEARCH TIMING] Result building: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        print(
            f"[SEARCH TIMING] END | "
            f"total={time.perf_counter() - started:.3f}s | "
            f"matched={sum(1 for r in results if r['matched'])} | "
            f"not_found={sum(1 for r in results if not r['matched'] and r['status'] == 'NOT FOUND')} | "
            f"sdo_missing={sum(1 for r in results if r['status'] == 'SDO NOT FOUND')}"
        )

        return results

    # ============================================================
    # UNIQUE STANDARDS
    # ============================================================

    @staticmethod
    def _unique_standards(candidates):

        seen = set()
        result = []

        for candidate in candidates:

            if candidate.id in seen:
                continue

            seen.add(
                candidate.id
            )

            result.append(
                candidate
            )

        return result

    @staticmethod
    def _request_identity_key(sdo_id, sdo_name, identity):
        return (
            sdo_id or normalize_tokens(sdo_name),
            normalize_identity_core(
                identity.get("core_number")
                or identity.get("core")
                or identity.get("body")
                or ""
            ),
            identity.get("qualifier"),
            identity.get("year"),
            bool(identity.get("family_lookup")),
        )

    @staticmethod
    def _direct_candidate_lists(
        row,
        candidate_map,
        exact_result_map,
        normalized_result_map,
        standard_number_map,
    ):
        display_candidates = []

        for variant in row["identity"].get("variants", []):
            candidate_key = (
                row["sdo_id"],
                normalize_tokens(variant),
            )
            display_candidates.extend(
                candidate_map.get(candidate_key, [])
            )

        full_display_number = row["full_display_number"]

        exact_key = (
            row["sdo_id"],
            normalize_display_number(full_display_number),
        )
        normalized_key = (
            row["sdo_id"],
            normalize_tokens(full_display_number).replace(" ", ""),
        )
        standard_number_key = (
            row["sdo_id"],
            normalize_display_number(full_display_number),
        )

        return (
            display_candidates,
            exact_result_map.get(exact_key, []),
            normalized_result_map.get(normalized_key, []),
            standard_number_map.get(standard_number_key, []),
        )

    @staticmethod
    def _build_identity_candidate_index(candidates, rows):
        sdo_names_by_id = {}

        for row in rows:
            sdo_id = row.get("sdo_id")
            sdo_name = row.get("sdo_name")

            if sdo_id and sdo_name:
                sdo_names_by_id.setdefault(
                    sdo_id,
                    set(),
                ).add(sdo_name)

        index = {}

        for candidate in candidates:
            sdo_names = sdo_names_by_id.get(
                candidate.sdo_id,
                (),
            )

            for sdo_name in sdo_names:
                for value in (
                    candidate.display_stdNo or "",
                    candidate.standardno or "",
                ):
                    if not value:
                        continue

                    candidate_identity = parse_identity(
                        sdo_name,
                        value,
                    )
                    candidate_core = normalize_identity_core(
                        candidate_identity.get("core_number")
                        or candidate_identity.get("core")
                        or ""
                    )

                    if not candidate_core:
                        continue

                    for index_core in identity_index_cores(
                        sdo_name,
                        candidate_core,
                    ):
                        key = (
                            candidate.sdo_id,
                            normalize_tokens(sdo_name),
                            index_core,
                        )
                        index.setdefault(key, {})[
                            candidate.id
                        ] = candidate

        return index

    # ============================================================
    # IDENTITY VALIDATION
    # ============================================================

    @staticmethod
    def _candidate_matches_identity(
        candidate,
        row,
    ):

        requested = row[
            "identity"
        ]

        candidate_values = [
            candidate.display_stdNo or "",
            candidate.standardno or "",
        ]

        for value in candidate_values:

            if not value:
                continue

            candidate_identity = parse_identity(
                requested[
                    "sdo_name"
                ],
                value,
            )

            if not identity_matches(
                requested,
                candidate_identity,
                check_year=False,
            ):
                continue

            return True

        return False

    @staticmethod
    def _candidate_year(candidate, sdo_name):
        if getattr(candidate, "standardyear", None) is not None:
            return candidate.standardyear

        candidate_identity = parse_identity(
            sdo_name,
            candidate.display_stdNo or candidate.standardno or "",
        )
        return (
            candidate_identity.get("year")
            or standard_number_year(candidate.standardno)
        )

    @staticmethod
    def _candidate_is_part_of_root(candidate, row):
        requested = row["identity"]
        if requested.get("qualifier") or requested.get("family_lookup"):
            return False

        candidate_identity = parse_identity(
            row["sdo_name"],
            candidate.display_stdNo or candidate.standardno or "",
        )
        return (
            (candidate_identity.get("qualifier") or "").startswith("PART:")
            and candidate_identity.get("core_number")
            == requested.get("core_number")
        )

    @staticmethod
    def _is_bare_qualifier_request(row):
        return row["identity"].get("family_lookup") or row["identity"].get("qualifier") in {
            "PART",
            "SECTION",
            "CHAPTER",
            "SERIES",
        }

    @staticmethod
    def _select_candidates(candidates, row):
        selected = DocumentSearchService._select_candidate(
            candidates,
            row,
        )

        if not DocumentSearchService._is_bare_qualifier_request(row):
            if selected:
                return [selected]

            requested_core = row["identity"].get("core_number")
            part_candidates = []

            for candidate in DocumentSearchService._unique_standards(candidates):
                candidate_identity = parse_identity(
                    row["sdo_name"],
                    candidate.display_stdNo or candidate.standardno or "",
                )
                if (
                    (candidate_identity.get("qualifier") or "").startswith("PART:")
                    and candidate_identity.get("core_number") == requested_core
                ):
                    part_candidates.append(candidate)

            if not part_candidates:
                return []

            family_row = {
                **row,
                "identity": {
                    **row["identity"],
                    "family_lookup": True,
                    "qualifier": "PART",
                },
            }
            return DocumentSearchService._select_candidates(
                part_candidates,
                family_row,
            )

        requested_qualifier = (
            "PART"
            if (
                row["identity"].get("family_lookup")
                or row["identity"].get("qualifier") == "SERIES"
            )
            else row["identity"]["qualifier"]
        )
        validated = [
            candidate
            for candidate in DocumentSearchService._unique_standards(candidates)
            if DocumentSearchService._candidate_matches_identity(
                candidate,
                row,
            )
        ]
        latest_by_part = {}
        root_candidate = None
        root_score = (-1, -1)
        requested_year = row["identity"].get("year")

        for candidate in validated:
            candidate_identity = parse_identity(
                row["sdo_name"],
                candidate.display_stdNo or candidate.standardno or "",
            )
            part_qualifier = candidate_identity.get("qualifier")
            year = (
                DocumentSearchService._candidate_year(
                    candidate,
                    row["sdo_name"],
                )
                or 0
            )
            score = (year == requested_year, year) if requested_year else (False, year)

            if not part_qualifier or part_qualifier == "SERIES":
                if score > root_score:
                    root_candidate = candidate
                    root_score = score
                continue

            if not part_qualifier.startswith(f"{requested_qualifier}:"):
                continue

            current = latest_by_part.get(part_qualifier)
            if current is None or score > current[0]:
                latest_by_part[part_qualifier] = (score, candidate)

        if latest_by_part:
            return [
                latest_by_part[qualifier][1]
                for qualifier in sorted(latest_by_part)
            ]
        return [root_candidate] if root_candidate else []

    # ============================================================
    # SELECT LOCAL CANDIDATE
    # ============================================================

    @staticmethod
    def _select_candidate(
        candidates,
        row,
    ):

        if not candidates:
            return None

        requested_year = row["identity"].get("year")

        validated = [
            candidate
            for candidate in candidates
            if DocumentSearchService
            ._candidate_matches_identity(
                candidate,
                row,
            )
        ]

        # --------------------------------------------------------
        # Explicit year requested
        # --------------------------------------------------------

        if requested_year is not None:
            exact = [
                candidate
                for candidate in validated
                if DocumentSearchService._candidate_year(
                    candidate,
                    row["sdo_name"],
                )
                == requested_year
            ]

            if exact:
                return exact[0]

            return max(
                validated,
                key=lambda candidate: DocumentSearchService._candidate_year(
                    candidate,
                    row["sdo_name"],
                ) or 0,
                default=None,
            )

        # --------------------------------------------------------
        # No explicit year
        # --------------------------------------------------------

        if validated:

            versioned = [
                candidate
                for candidate in validated
                if standard_number_year(
                    candidate.standardno
                ) is not None
            ]

            if versioned:
                return versioned[0]

            return validated[0]

        return None

    # ============================================================
    # MASTER MATCHING
    # ============================================================

    @staticmethod
    def _row_has_display_candidates(row, candidate_map):
        sdo_id = row.get("sdo_id")

        if not sdo_id:
            return False

        for variant in row["identity"].get("variants", []):
            if candidate_map.get(
                (sdo_id, normalize_tokens(variant))
            ):
                return True

        return False

    @staticmethod
    def _row_needs_identity_discovery(row, selected_direct):
        """Return True when designation-neutral LIKE may still find matches.

        Skip the wide identity scan when a strong local display/exact/
        normalized/standard match already exists, unless the request needs
        family or bare-qualifier expansion from additional candidates.
        """
        if selected_direct is None:
            return True

        identity = row.get("identity") or {}
        if identity.get("family_lookup"):
            return True

        qualifier = identity.get("qualifier")
        if qualifier in {"PART", "SECTION", "CHAPTER", "SERIES"}:
            return True

        return False

    @staticmethod
    def _display_masters_satisfy(row, display_grouped):
        requested_year = row["identity"].get("year")
        found = False

        for variant in row["identity"].get("variants", []):
            masters = list(
                display_grouped.get(
                    (
                        row["sdo_id"],
                        normalize_tokens(variant),
                    ),
                    [],
                )
            )

            for master in masters:
                if not DocumentSearchService._master_candidate_matches_identity(
                    master,
                    row,
                ):
                    continue

                found = True

                if (
                    requested_year is None
                    or master.standardyear == requested_year
                ):
                    return True

        return found and requested_year is None

    @staticmethod
    def _masters_satisfy_row(row, masters):
        """True when exact/display master candidates already cover the row."""
        if not masters:
            return False

        requested_year = row["identity"].get("year")
        found = False

        for master in masters:
            if not DocumentSearchService._master_candidate_matches_identity(
                master,
                row,
            ):
                continue

            found = True

            if (
                requested_year is None
                or master.standardyear == requested_year
            ):
                return True

        identity = row.get("identity") or {}
        if identity.get("family_lookup"):
            return False
        if identity.get("qualifier") in {
            "PART",
            "SECTION",
            "CHAPTER",
            "SERIES",
        }:
            return False

        return found and requested_year is None

    def find_master_matches(
        self,
        unresolved_rows,
    ):

        if not unresolved_rows:
            return {}

        # --------------------------------------------------------
        # Display-number candidates
        # --------------------------------------------------------

        pairs = []

        for row in unresolved_rows:

            for variant in row[
                "identity"
            ].get(
                "variants",
                [],
            ):

                pairs.append(
                    (
                        row["sdo_id"],
                        variant,
                    )
                )

        pairs = list(
            dict.fromkeys(pairs)
        )

        stage_started = time.perf_counter()
        masters = (
            self.enrichment_repository
            .search_master_by_sdo_and_display_variants(
                pairs
            )
        )
        print(
            f"[SEARCH TIMING] Master display query: "
            f"{time.perf_counter() - stage_started:.3f}s | "
            f"pairs={len(pairs)} candidates={len(masters)}"
        )

        # --------------------------------------------------------
        # Exact standardno candidates (narrower than identity LIKE)
        # --------------------------------------------------------

        standard_pairs = list(pairs)
        for row in unresolved_rows:
            full = row.get("full_display_number")
            if row.get("sdo_id") and full:
                standard_pairs.append((row["sdo_id"], full))

        standard_pairs = list(dict.fromkeys(standard_pairs))

        stage_started = time.perf_counter()
        standard_masters = (
            self.enrichment_repository
            .search_master_by_sdo_and_standard_numbers(
                standard_pairs
            )
        )
        masters.extend(standard_masters)
        print(
            f"[SEARCH TIMING] Master standardno query: "
            f"{time.perf_counter() - stage_started:.3f}s | "
            f"pairs={len(standard_pairs)} candidates={len(standard_masters)}"
        )

        # --------------------------------------------------------
        # Identity-hint candidates (only rows still unresolved)
        # --------------------------------------------------------

        identity_hints = []

        display_grouped = {}

        for master in masters:
            display_grouped.setdefault(
                (
                    master.sdo_id,
                    normalize_tokens(master.display_stdNo or ""),
                ),
                [],
            ).append(master)
            display_grouped.setdefault(
                (
                    master.sdo_id,
                    normalize_tokens(master.standardno or ""),
                ),
                [],
            ).append(master)

        for row in unresolved_rows:
            row_masters = []
            for variant in row["identity"].get("variants", []):
                row_masters.extend(
                    display_grouped.get(
                        (
                            row["sdo_id"],
                            normalize_tokens(variant),
                        ),
                        [],
                    )
                )
            full = row.get("full_display_number")
            if full:
                row_masters.extend(
                    display_grouped.get(
                        (
                            row["sdo_id"],
                            normalize_tokens(full),
                        ),
                        [],
                    )
                )
            row_masters = self._unique_standards(row_masters)

            if row.get("skip_master_identity"):
                # Local match already covers the response; keep only the
                # cheap display/standardno masters gathered above.
                continue

            if self._masters_satisfy_row(row, row_masters):
                continue

            if self._display_masters_satisfy(row, display_grouped):
                continue

            core = row[
                "identity"
            ].get(
                "core_number_pattern"
            ) or row[
                "identity"
            ].get(
                "core_number"
            )

            if not core:
                continue

            if "SERIES" in row[
                "identity"
            ].get(
                "body",
                "",
            ):
                continue

            # Query without a year filter once; edition selection stays in
            # Python. This replaces the previous year-pass + year-stripped
            # second LIKE scan with a single identity lookup per core.
            identity_hints.append(
                (
                    row["sdo_id"],
                    row["sdo_name"],
                    core,
                    None,
                )
            )

        identity_hints = list(
            dict.fromkeys(
                identity_hints
            )
        )

        stage_started = time.perf_counter()
        if identity_hints:
            identity_masters = (
                self.enrichment_repository
                .search_master_by_sdo_and_identity_hints(
                    identity_hints
                )
            )
        else:
            identity_masters = []

        masters.extend(identity_masters)
        print(
            f"[SEARCH TIMING] Master identity query: "
            f"{time.perf_counter() - stage_started:.3f}s | "
            f"hints={len(identity_hints)} candidates={len(identity_masters)}"
        )

        # --------------------------------------------------------
        # Group master candidates
        # --------------------------------------------------------

        grouped = {}

        for master in masters:

            key = (
                master.sdo_id,
                normalize_tokens(
                    master.display_stdNo or ""
                ),
            )

            grouped.setdefault(
                key,
                [],
            ).append(master)

        # --------------------------------------------------------
        # Select master for each unresolved row
        # --------------------------------------------------------

        matches = {}
        master_identity_index = (
            self._build_identity_candidate_index(
                masters,
                unresolved_rows,
            )
        )
        stage_started = time.perf_counter()

        for row in unresolved_rows:

            candidates = []

            # ----------------------------------------------------
            # Display variants
            # ----------------------------------------------------

            for variant in row[
                "identity"
            ].get(
                "variants",
                [],
            ):

                candidates.extend(
                    grouped.get(
                        (
                            row["sdo_id"],
                            normalize_tokens(
                                variant
                            ),
                        ),
                        [],
                    )
                )

            # ----------------------------------------------------
            # Designation-neutral candidates
            # ----------------------------------------------------

            core = row[
                "identity"
            ].get(
                "core_number"
            )

            if core:

                normalized_core = normalize_identity_core(
                    core
                )

                possible_masters = (
                    master_identity_index.get(
                        (
                            row["sdo_id"],
                            normalize_tokens(row["sdo_name"]),
                            normalized_core,
                        ),
                        {},
                    ).values()
                )

                for master in possible_masters:

                    if (
                        self._master_candidate_matches_identity(master, row)
                        or self._candidate_is_part_of_root(master, row)
                    ):
                        candidates.append(
                            master
                        )

            selected = (
                self._select_master_candidates(
                    candidates,
                    row,
                )
            )

            if selected:
                matches[row["request_key"]] = selected

        print(
            f"[SEARCH TIMING] Master candidate selection: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        return matches

    # ============================================================
    # MASTER IDENTITY VALIDATION
    # ============================================================

    @staticmethod
    def _master_candidate_matches_identity(
        candidate,
        row,
    ):

        requested = row[
            "identity"
        ]

        candidate_values = [
            candidate.display_stdNo or "",
            candidate.standardno or "",
        ]

        for value in candidate_values:

            if not value:
                continue

            candidate_identity = parse_identity(
                requested[
                    "sdo_name"
                ],
                value,
            )

            if not identity_matches(
                requested,
                candidate_identity,
                check_year=False,
            ):
                continue

            return True

        return False

    # ============================================================
    # SELECT MASTER CANDIDATE
    # ============================================================

    @staticmethod
    def _select_master_candidate(
        candidates,
        row,
    ):

        candidates = list(
            {
                candidate.id: candidate
                for candidate in candidates
            }.values()
        )

        if not candidates:
            return None

        requested_year = (
            row["identity"].get(
                "year"
            )
        )

        # --------------------------------------------------------
        # Explicit edition/year
        # --------------------------------------------------------

        if requested_year is not None:

            exact = [
                candidate
                for candidate in candidates
                if candidate.standardyear
                == requested_year
            ]

            if exact:
                return exact[0]

            return max(
                candidates,
                key=lambda candidate: candidate.standardyear or 0,
                default=None,
            )

        # --------------------------------------------------------
        # No explicit edition
        # --------------------------------------------------------

        current = [
            candidate
            for candidate in candidates
            if getattr(
                candidate,
                "recent",
                None,
            ) == 1
        ]

        if current:

            return sorted(
                current,
                key=lambda candidate:
                    candidate.standardyear or 0,
                reverse=True,
            )[0]

        return sorted(
            candidates,
            key=lambda candidate:
                candidate.standardyear or 0,
            reverse=True,
        )[0]

    @staticmethod
    def _select_master_candidates(candidates, row):
        if not DocumentSearchService._is_bare_qualifier_request(row):
            root_candidates = [
                candidate
                for candidate in candidates
                if DocumentSearchService._master_candidate_matches_identity(
                    candidate,
                    row,
                )
            ]
            selected = DocumentSearchService._select_master_candidate(
                root_candidates,
                row,
            )
            if selected:
                return [selected]

            requested_core = row["identity"].get("core_number")
            part_candidates = []

            for candidate in {
                candidate.id: candidate
                for candidate in candidates
            }.values():
                candidate_identity = parse_identity(
                    row["sdo_name"],
                    candidate.display_stdNo or candidate.standardno or "",
                )
                if (
                    (candidate_identity.get("qualifier") or "").startswith("PART:")
                    and candidate_identity.get("core_number") == requested_core
                ):
                    part_candidates.append(candidate)

            if not part_candidates:
                return []

            family_row = {
                **row,
                "identity": {
                    **row["identity"],
                    "family_lookup": True,
                    "qualifier": "PART",
                },
            }
            return DocumentSearchService._select_master_candidates(
                part_candidates,
                family_row,
            )

        requested_qualifier = (
            "PART"
            if (
                row["identity"].get("family_lookup")
                or row["identity"].get("qualifier") == "SERIES"
            )
            else row["identity"]["qualifier"]
        )
        latest_by_part = {}
        root_candidate = None
        root_score = (-1, -1)
        requested_year = row["identity"].get("year")

        for candidate in {
            candidate.id: candidate
            for candidate in candidates
        }.values():
            if not DocumentSearchService._master_candidate_matches_identity(
                candidate,
                row,
            ):
                continue

            candidate_identity = parse_identity(
                row["sdo_name"],
                candidate.display_stdNo or candidate.standardno,
            )
            part_qualifier = candidate_identity.get("qualifier")
            year = candidate.standardyear or standard_number_year(
                candidate.standardno
            ) or 0
            score = (year == requested_year, year) if requested_year else (False, year)

            if not part_qualifier or part_qualifier == "SERIES":
                if score > root_score:
                    root_candidate = candidate
                    root_score = score
                continue

            if not part_qualifier.startswith(f"{requested_qualifier}:"):
                continue

            current = latest_by_part.get(part_qualifier)
            if current is None or score > current[0]:
                latest_by_part[part_qualifier] = (score, candidate)

        if latest_by_part:
            return [
                latest_by_part[qualifier][1]
                for qualifier in sorted(latest_by_part)
            ]
        return [root_candidate] if root_candidate else []

    # ============================================================
    # MASTER FORMATTER
    # ============================================================

    @staticmethod
    def format_master_standard(
        standard,
    ):

        return {
            "Standard_id": standard.Standard_id,
            "standardno": standard.standardno,
            "display_stdNo": standard.display_stdNo,
            "title": standard.title,
            "url": standard.url,
            "sdo_id": standard.sdo_id,
            "standardyear": standard.standardyear,
        }

    # ============================================================
    # ENRICHMENT
    # ============================================================

    def build_enrichment_map(
        self,
        standards,
    ):

        if not standards:
            return {}

        standard_ids = list(
            {
                standard.Standard_id
                for standard in standards
                if standard.Standard_id
            }
        )

        sdo_ids = {
            standard.sdo_id
            for standard in standards
            if standard.sdo_id
        }

        currency_map = (
            self.enrichment_repository
            .get_currency_info_for_sdos(sdo_ids)
        )

        masters = (
            self.enrichment_repository
            .get_master_standards(
                standard_ids
            )
        )

        master_map = {
            master.Standard_id: master
            for master in masters
        }

        master_ids = [
            master.id
            for master in masters
        ]

        # --------------------------------------------------------
        # Prices
        # --------------------------------------------------------

        prices = (
            self.enrichment_repository
            .get_prices_for_standards(
                master_ids
            )
        )

        price_map = {}

        for price in prices:

            price_map.setdefault(
                price.std_id,
                (
                    float(
                        price.non_member_price_rate
                    )
                    if price.non_member_price_rate
                    is not None
                    else None
                ),
            )

        # --------------------------------------------------------
        # Classifications
        # --------------------------------------------------------

        classifications = (
            self.enrichment_repository
            .get_classifications_for_standards(
                master_ids
            )
        )

        classification_map = {}

        for (
            standard_classification,
            classification,
        ) in classifications:

            classification_map.setdefault(
                standard_classification.standard_id,
                [],
            ).append(
                {
                    "id": classification.id,
                    "code": classification.classification_code,
                    "description": classification.description,
                }
            )

        # --------------------------------------------------------
        # Final enrichment map
        # --------------------------------------------------------

        result = {}

        for standard in standards:
            if not standard.Standard_id:
                continue

            master = master_map.get(standard.Standard_id)
            currency = currency_map.get(standard.sdo_id, {})
            year = (
                master.standardyear
                if master
                else standard_number_year(standard.standardno)
            )

            result[
                standard.Standard_id
            ] = {
                "year": year,
                "currency": currency.get("code"),
                "currency_symbol": currency.get("symbol"),
                "price": price_map.get(master.id) if master else None,
                "classifications": (
                    classification_map.get(master.id, [])
                    if master
                    else []
                ),
            }

        return result

    # ============================================================
    # SDO RESOLUTION
    # ============================================================

    def resolve_sdo_ids(
        self,
        sdo_names,
    ):

        """
        Resolve SDO IDs without scanning the large
        standards tables.

        The dedicated SDO table is used first.
        The standards-prefix lookup is only used
        as a compatibility fallback.
        """

        prefixes = {
            str(value).upper().strip()
            for value in sdo_names
            if value
            and str(value).strip()
        }

        if not prefixes:
            return {}

        result = {}

        # --------------------------------------------------------
        # Primary SDO table lookup
        # --------------------------------------------------------

        sdo_rows = (
            self.repository
            .find_sdo_ids_from_sdo_table(
                prefixes
            )
        )

        normalized_requested = {
            normalize_tokens(prefix): prefix
            for prefix in prefixes
        }

        for row in sdo_rows:

            values = [
                row.sdo_title,
                row.sdo_fullname,
                row.sdo_shortdesc,
                row.designation,
            ]

            for value in values:

                key = normalize_tokens(
                    value
                )

                requested = (
                    normalized_requested.get(
                        key
                    )
                )

                if requested:
                    result[
                        requested
                    ] = row.id

        # --------------------------------------------------------
        # Compatibility fallback
        # --------------------------------------------------------

        missing = [
            prefix
            for prefix in prefixes
            if prefix not in result
        ]

        for prefix in missing:

            rows = (
                self.repository
                .find_sdo_ids_by_prefixes(
                    [prefix]
                )
            )

            for (
                _standardno,
                sdo_id,
            ) in rows:

                result[
                    prefix
                ] = sdo_id

                break

        return result

