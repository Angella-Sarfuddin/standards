"""DocumentSearchService methods other than search().

Method bodies are unchanged. service.py assigns DocumentSearchService
after that class exists so name lookups and test patches stay on it.
"""


import re
import time

from app.repositories.standards_repository import StandardsRepository
from app.repositories.enrichment_repository import EnrichmentRepository
from app.models.standard_master import StandardMaster
from app.services.search_service import SearchService
from app.services.ieee_official_metadata import IEEEOfficialMetadataService
from app.services.document_search import candidate_resolution
from app.services.document_search import candidate_filtering
from app.services.document_search import family_paths
from app.services.document_search import family_revisions
from app.services.document_search import candidate_selection
from app.services.document_search import lifecycle_status
from app.services.document_search import result_helpers
from app.services.document_search import enrichment_builder
from app.services.document_search import identity_discovery
from app.services.document_search import lookup_indexes
from app.services.document_search import input_preparation
from app.services.document_search import repository_lookup
from app.services.document_search import local_matching
from app.services.document_search import master_fallback
from app.services.document_search import result_assembly
from app.services.document_search.selection_context import current_candidate_status_map

from app.core.standard_formatter import (
    build_full_display_number,
    remove_draft_marker,
)

from app.core.standard_expression_parser import StandardExpressionParser
from app.core.standard_identity import (
    parse_identity,
    extract_international_references,
    standard_number_year,
    normalize_tokens,
    normalize_identity_core,
    sdo_identifier_prefixes,
    identity_matches,
    identity_index_cores,
    identity_lookup_core_tokens,
    reaffirmation_year,
)
from app.core.api_classification_filter import filter_api_classifications


class DocumentSearchServiceMethods:
    @staticmethod
    def _deduplicate_results(results):
        return result_helpers.deduplicate_results(
            results,
            DocumentSearchService,
        )

    @staticmethod
    def _not_found_reason(result):
        return result_helpers.not_found_reason(result)

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
    def _candidate_sdo_names(sdo_name, displaystdno):
        return identity_discovery.candidate_sdo_names(
            sdo_name,
            displaystdno,
            service_class=DocumentSearchService,
        )

    def _infer_unique_catalog_sdo(self, sdo_name, displaystdno):
        """Use catalog identity as a fallback only when it points to one SDO."""
        sdo_name = str(sdo_name or "").strip()
        displaystdno = str(displaystdno or "").strip()
        identity_value = displaystdno
        if sdo_name.upper() in {"SP", "SPECIAL PUBLICATION"}:
            identity_value = f"SP {displaystdno}".strip()

        requested_identity = parse_identity(sdo_name, identity_value)
        core = requested_identity.get("core_number")
        if not core or len(core) < 3:
            return None

        candidates = self.enrichment_repository.search_master_candidates_across_sdos(
            core
        )
        if len(candidates) >= 501:
            return None

        matching = []
        matched_sdo_ids = set()
        for candidate, catalog_sdo_name in candidates:
            candidate_number = (
                candidate.standardno
                or candidate.display_stdNo
                or ""
            )
            candidate_sdo, _candidate_body = (
                StandardExpressionParser.infer_sdo_and_body(
                    candidate_number
                )
            )
            if not candidate_sdo:
                candidate_sdo = {
                    "AMPPNACE": "NACE",
                    "AMPPSSPC": "SSPC",
                }.get(
                    normalize_tokens(catalog_sdo_name),
                    catalog_sdo_name,
                )
            if not candidate_sdo:
                continue
            candidate_identity = parse_identity(
                candidate_sdo,
                candidate_number,
            )
            candidate_identity["sdo_name"] = requested_identity["sdo_name"]
            if not identity_matches(
                requested_identity,
                candidate_identity,
                check_year=False,
            ):
                continue
            matching.append((candidate, candidate_sdo))
            matched_sdo_ids.add(candidate.sdo_id)

        if len(matched_sdo_ids) != 1:
            return None

        sdo_counts = {}
        for _candidate, candidate_sdo in matching:
            sdo_counts[candidate_sdo] = sdo_counts.get(candidate_sdo, 0) + 1
        identity_sdo = max(sdo_counts, key=sdo_counts.get)
        selected_sdo_id = next(iter(matched_sdo_ids))
        return identity_sdo, selected_sdo_id

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
        return repository_lookup.direct_candidate_lists(
            row,
            candidate_map,
            exact_result_map,
            normalized_result_map,
            standard_number_map,
        )

    @staticmethod
    def _build_identity_candidate_index(candidates, rows):
        return identity_discovery.build_identity_candidate_index(
            candidates,
            rows,
        )

    # ============================================================
    # IDENTITY VALIDATION
    # ============================================================

    @staticmethod
    def _candidate_matches_identity(
        candidate,
        row,
    ):

        return candidate_resolution._candidate_matches_identity(candidate, row)

    @staticmethod
    def _candidate_year(candidate, sdo_name):
        return candidate_resolution._candidate_year(candidate, sdo_name)

    def _official_nace_mr0103_edition(self, row):
        """Prefer AMPP's canonical 2023 MR0103/ISO 17945 catalogue record."""
        requested = " ".join(
            str(value or "")
            for value in (
                row.get("displaystdno"),
                row.get("result_displaystdno"),
                row.get("standardno"),
            )
        )
        normalized = re.sub(r"[^A-Z0-9]", "", requested.upper())
        if "MR0103" not in normalized or "ISO17945" not in normalized:
            return None

        candidates = (
            self.repository.db.query(StandardMaster)
            .filter(
                StandardMaster.sdo_id == row.get("sdo_id"),
                StandardMaster.standardno.ilike("%MR0103%"),
                StandardMaster.standardno.ilike("%17945%"),
                StandardMaster.status == 1,
            )
            .all()
        )
        candidates = [
            candidate
            for candidate in candidates
            if re.sub(
                r"[^A-Z0-9]",
                "",
                str(candidate.standardno or "").upper(),
            ).startswith("ANSINACE")
        ]
        return max(
            candidates,
            key=lambda candidate: (
                int(getattr(candidate, "standardyear", 0) or 0),
                int(getattr(candidate, "id", 0) or 0),
            ),
            default=None,
        )

    def _official_hi_replacement(self, row):
        """Resolve superseded HI 2.6 hydraulic tests to current HI 14.6."""
        if str(
            row.get("search_sdo_name") or row.get("sdo_name") or ""
        ).strip().upper() not in {"HI", "HYDRAULIC INSTITUTE"}:
            return None

        requested = str(
            row.get("displaystdno") or row.get("result_displaystdno") or ""
        ).strip().upper()
        if not re.search(
            r"(?<![A-Z0-9])(?:ANSI\s*/\s*HI|HI)\s*2\.6(?!\d)", requested
        ):
            return None

        candidates = self.repository.db.query(StandardMaster).filter(
            StandardMaster.sdo_id == row.get("sdo_id"),
            StandardMaster.standardno.in_(["ANSI/HI 14.6", "HI 14.6"]),
            StandardMaster.status == 1,
        ).all()
        for candidate in candidates:
            number = str(
                getattr(candidate, "standardno", "")
                or getattr(candidate, "display_stdNo", "")
            ).upper()
            title = str(getattr(candidate, "title", "") or "").upper()
            if (
                re.search(r"\b14\.6\b", number)
                and "HYDRAULIC PERFORMANCE ACCEPTANCE TEST" in title
                and getattr(candidate, "status", None) == 1
            ):
                return candidate

        return None

    def _official_ieee_replacement(self, row, metadata=None):
        """Return the active catalogue row for a verified IEEE target."""
        metadata = metadata or IEEEOfficialMetadataService.lookup(
            row.get("search_sdo_name") or row.get("sdo_name"),
            row.get("result_displaystdno") or row.get("displaystdno"),
        )
        if metadata is None or not row.get("sdo_id"):
            return None

        candidates = self.repository.db.query(StandardMaster).filter(
            StandardMaster.sdo_id == row["sdo_id"],
            StandardMaster.standardno == metadata.replacement_standardno,
            StandardMaster.standardyear == metadata.replacement_year,
            StandardMaster.status == 1,
        ).order_by(StandardMaster.id.asc()).all()
        return candidates[0] if candidates else None

    @staticmethod
    def _normalized_identifier_prefix(value):
        return candidate_resolution._normalized_identifier_prefix(value)

    @staticmethod
    def _select_best_current_candidate(candidates, row, status_map=None):
        return candidate_resolution._select_best_current_candidate(candidates, row, status_map, service_class=DocumentSearchService)

    @staticmethod
    def _is_api_request(row):
        return str(
            (row or {}).get("search_sdo_name")
            or (row or {}).get("sdo_name")
            or ""
        ).strip().upper() == "API"

    @staticmethod
    def _filter_api_unavailable_candidates(candidates, status_map, row):
        return candidate_resolution._filter_api_unavailable_candidates(candidates, status_map, row, service_class=DocumentSearchService)

    @staticmethod
    def _candidate_is_part_of_root(candidate, row):
        return family_paths._candidate_is_part_of_root(
            candidate,
            row,
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
    def _should_expand_family(identity, include_subsections=False):
        qualifier = str(identity.get("qualifier") or "")
        return (
            include_subsections
            or qualifier in {"PART", "SECTION", "CHAPTER", "SERIES"}
            or bool(
                re.fullmatch(
                    r"(?:PART|SECTION|CHAPTER):\d+-\d+",
                    qualifier,
                )
            )
        )

    @staticmethod
    def _part_family_path(candidate_identity, requested_identity):
        return family_paths._part_family_path(
            candidate_identity,
            requested_identity,
        )

    @staticmethod
    def _requested_part_matches_path(row, part_path):
        return family_paths._requested_part_matches_path(row, part_path)

    @staticmethod
    def _candidate_revision_suffix(candidate):
        return candidate_filtering._candidate_revision_suffix(candidate)

    @staticmethod
    def _candidate_is_amendment(candidate):
        return candidate_filtering._candidate_is_amendment(candidate)

    @staticmethod
    def _candidate_is_draft_stage(candidate):
        return candidate_filtering._candidate_is_draft_stage(candidate)

    @staticmethod
    def _candidate_is_proposal(candidate):
        return candidate_filtering._candidate_is_proposal(candidate)

    @staticmethod
    def _candidate_is_ul_supplemental_publication(candidate):
        return candidate_filtering._candidate_is_ul_supplemental_publication(
            candidate
        )

    @staticmethod
    def _candidate_should_be_excluded(candidate):
        return candidate_filtering._candidate_should_be_excluded(
            candidate,
            service_class=DocumentSearchService,
        )

    @staticmethod
    def _candidate_base_edition_year(candidate):
        return family_revisions._candidate_base_edition_year(candidate)

    @staticmethod
    def _select_current_family_revisions(latest_by_part, requested_qualifier):
        return family_revisions._select_current_family_revisions(
            latest_by_part,
            requested_qualifier,
            service_class=DocumentSearchService,
        )

    @staticmethod
    def _series_member_key(candidate, row):
        return candidate_selection._series_member_key(candidate, row)

    @staticmethod
    def _series_language_marker(value):
        return candidate_selection._series_language_marker(value)

    @staticmethod
    def _select_series_candidates(candidates, row, status_map=None):
        return candidate_selection._select_series_candidates(
            candidates, row, status_map, service_class=DocumentSearchService
        )

    @staticmethod
    def _select_candidates(candidates, row):
        return candidate_selection._select_candidates(
            candidates, row, current_candidate_status_map(), service_class=DocumentSearchService
        )

    # ============================================================
    # SELECT LOCAL CANDIDATE
    # ============================================================

    @staticmethod
    def _select_candidate(
        candidates,
        row,
    ):

        return candidate_resolution._select_candidate(candidates, row, current_candidate_status_map(), service_class=DocumentSearchService)

    # ============================================================
    # MASTER MATCHING
    # ============================================================

    @staticmethod
    def _row_has_display_candidates(row, candidate_map):
        return repository_lookup.row_has_display_candidates(
            row,
            candidate_map,
        )

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
    def _display_masters_satisfy(row, display_grouped, status_map=None):
        # A direct display-number match may be an older edition. Always run
        # identity discovery to collect candidates before choosing the newest.
        return False

    @staticmethod
    def _masters_satisfy_row(row, masters, status_map=None):
        """Exact edition matches cannot prove no newer edition exists."""
        return False

    def find_master_matches(
        self,
        unresolved_rows,
    ):
        return master_fallback.find_master_matches(
            unresolved_rows,
            self.enrichment_repository,
            self._is_tema_edition_request,
            self._masters_satisfy_row,
            self._display_masters_satisfy,
            self._unique_standards,
            self._build_identity_candidate_index,
            self._master_candidate_matches_identity,
            self._candidate_is_part_of_root,
            self._select_master_candidates,
        )

    # ============================================================
    # MASTER IDENTITY VALIDATION
    # ============================================================

    @staticmethod
    def _master_candidate_matches_identity(
        candidate,
        row,
    ):

        if DocumentSearchService._candidate_should_be_excluded(candidate):
            return False

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
    def _select_master_candidate(candidates, row):
        return candidate_selection._select_master_candidate(
            candidates, row, current_candidate_status_map(), service_class=DocumentSearchService
        )

    @staticmethod
    def _is_tema_edition_request(row):
        sdo_name = str(
            row.get("search_sdo_name") or row.get("sdo_name") or ""
        ).strip().upper()
        designation = str(row.get("displaystdno") or "").strip()
        # Quick search accepts a bare edition phrase with no publisher
        # prefix. The edition family is distinctive to TEMA in this catalogue.
        if not sdo_name and re.match(
            r"(?i)^(?:\w+|\d+(?:st|nd|rd|th)?)\s+Edition"
            r"(?:\s*:\s*(?:19|20)\d{2})?\s*$",
            designation,
        ):
            sdo_name = "TEMA"
        if sdo_name != "TEMA":
            return False
        # Spreadsheet inputs often store the publisher in its own SDO column,
        # leaving only "Eleventh Edition : 2023" in the designation column.
        designation = re.sub(r"(?i)^TEMA\s+", "", designation).strip()
        return bool(
            re.match(
                r"(?i)^(?:\w+|\d+(?:st|nd|rd|th)?)\s+Edition"
                r"(?:\s*:\s*(?:19|20)\d{2})?\s*$",
                designation,
            )
        )

    @staticmethod
    def _tema_request_is_historical(row, actual_year):
        """Recognize old numbered TEMA editions even when year is omitted."""
        if not DocumentSearchService._is_tema_edition_request(row):
            return False
        try:
            current_year = int(actual_year)
        except (TypeError, ValueError):
            return False

        designation = str(row.get("displaystdno") or "").strip()
        year_matches = re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", designation)
        if year_matches:
            return int(year_matches[-1]) != current_year

        designation = re.sub(r"(?i)^TEMA\s+", "", designation).strip()
        edition_match = re.match(r"(?i)^(\w+)\s+Edition", designation)
        if not edition_match:
            return False
        edition = edition_match.group(1)
        if edition.isdigit() and len(edition) == 4:
            return int(edition) != current_year

        # TEMA ended ordinal numbering with the 2026 year-based edition.
        return current_year >= 2026

    @staticmethod
    def _official_tema_edition_designation(row, actual_year):
        """Use TEMA's year-based designation from the 2026 edition onward."""
        sdo_name = str(
            row.get("search_sdo_name") or row.get("sdo_name") or ""
        ).strip().upper()
        try:
            year = int(actual_year)
        except (TypeError, ValueError):
            return None
        if sdo_name != "TEMA" or year < 2026:
            return None
        return f"TEMA {year} Edition : {year}"

    @staticmethod
    def _is_tema_edition_family_candidate(candidate, row):
        if not DocumentSearchService._is_tema_edition_request(row):
            return False
        designation = str(
            getattr(candidate, "display_stdNo", "")
            or getattr(candidate, "standardno", "")
            or ""
        ).strip()
        return bool(
            re.match(
                r"(?i)^TEMA\s+\w+\s+Edition\s*:\s*(?:19|20)\d{2}\s*$",
                designation,
            )
        )

    @staticmethod
    def _select_latest_tema_edition(candidates, row, status_map=None):
        """Select the newest visible numbered TEMA edition, ignoring input year."""
        editions = [
            candidate
            for candidate in candidates or []
            if DocumentSearchService._is_tema_edition_family_candidate(
                candidate,
                row,
            )
            and not DocumentSearchService._candidate_should_be_excluded(
                candidate
            )
        ]
        visible = [
            candidate
            for candidate in editions
            if DocumentSearchService._candidate_catalog_visibility(
                candidate,
                status_map or {},
            ) is True
        ]
        if visible:
            editions = visible
        else:
            unknown = [
                candidate
                for candidate in editions
                if DocumentSearchService._candidate_catalog_visibility(
                    candidate,
                    status_map or {},
                ) is None
            ]
            editions = unknown
        if not editions:
            return []

        latest = max(
            editions,
            key=lambda candidate: (
                DocumentSearchService._candidate_year(
                    candidate,
                    row.get("search_sdo_name") or row.get("sdo_name") or "TEMA",
                ) or 0,
                int(getattr(candidate, "recent", 0) == 1),
                int(hasattr(candidate, "standardyear")),
            ),
        )
        return [latest]

    @staticmethod
    def _prefer_exact_designation(candidates, row):
        requested = row.get("identity") or {}
        requested_designation = requested.get("designation")
        if (
            not candidates
            or not requested_designation
            or requested.get("year") is not None
            or requested.get("qualifier")
            or requested.get("family_lookup")
        ):
            return candidates

        sdo_name = row.get("search_sdo_name") or row.get("sdo_name")
        exact = [
            candidate
            for candidate in candidates
            if any(
                parse_identity(sdo_name, value).get("designation")
                == requested_designation
                for value in (
                    candidate.display_stdNo or "",
                    candidate.standardno or "",
                )
                if value
            )
        ]
        return exact or candidates

    @staticmethod
    def _select_master_candidates(candidates, row):
        return candidate_selection._select_master_candidates(
            candidates, row, current_candidate_status_map(), service_class=DocumentSearchService
        )

    # ============================================================
    # MASTER FORMATTER
    # ============================================================

    @staticmethod
    def _record_requested_edition_status(candidates, row, status_map=None):
        requested_year = (row.get("identity") or {}).get("year")
        if not status_map or str(
            row.get("requested_sdo_name") or row.get("sdo_name") or ""
        ).strip().upper() in {"BIS", "IS"}:
            return
        identity_candidates = [
            candidate for candidate in candidates or []
            and DocumentSearchService._candidate_matches_identity(
                candidate,
                row,
            )
        ]
        if requested_year is not None:
            exact_candidates = [
                candidate
                for candidate in identity_candidates
                if DocumentSearchService._candidate_year(
                    candidate,
                    row.get("search_sdo_name") or row.get("sdo_name") or "",
                ) == requested_year
            ]
        else:
            # An unversioned request should only inherit a lifecycle status
            # when no edition for that identity is currently visible. This
            # catches standards whose catalog records are all withdrawn while
            # avoiding a withdrawn label when an active edition exists.
            if any(
                DocumentSearchService._candidate_catalog_visibility(
                    candidate,
                    status_map,
                ) is not False
                for candidate in identity_candidates
            ):
                return
            if identity_candidates:
                latest_year = max(
                    (
                        DocumentSearchService._candidate_year(
                            candidate,
                            row.get("search_sdo_name") or row.get("sdo_name") or "",
                        )
                        or 0
                    )
                    for candidate in identity_candidates
                )
                exact_candidates = [
                    candidate
                    for candidate in identity_candidates
                    if (
                        DocumentSearchService._candidate_year(
                            candidate,
                            row.get("search_sdo_name") or row.get("sdo_name") or "",
                        )
                        or 0
                    ) == latest_year
                ]
            else:
                exact_candidates = []

        for candidate in exact_candidates:
            if DocumentSearchService._candidate_catalog_visibility(
                candidate,
                status_map,
            ) is False:
                status_info = status_map.get(
                    getattr(candidate, "status_id", None)
                ) or {}
                status_name = str(
                    DocumentSearchService._candidate_embedded_lifecycle_status(
                        candidate
                    )
                    or status_info.get("name")
                    or ""
                ).strip()
                if DocumentSearchService._status_label_is_unavailable(
                    status_name
                ):
                    row["requested_edition_status"] = (
                        "WITHDRAWN"
                        if re.search(
                            r"(?i)\bDO\s+NOT\s+USE\b",
                            status_name,
                        )
                        else status_name.upper()
                    )
                else:
                    row["requested_edition_status"] = "NOT AVAILABLE"
                return

    @staticmethod
    def _candidate_catalog_visibility(candidate, status_map):
        embedded_status = (
            DocumentSearchService._candidate_embedded_lifecycle_status(
                candidate
            )
        )
        if embedded_status:
            return False
        if not status_map:
            return None
        status_info = status_map.get(getattr(candidate, "status_id", None))
        if not status_info:
            return None
        status_name = str(status_info.get("name") or "").strip()
        if not status_name:
            return None
        if (
            int(status_info.get("cart_show") or 0) != 1
            or int(status_info.get("std_show") or 0) != 1
            or DocumentSearchService._status_label_is_unavailable(status_name)
        ):
            return False
        return True

    @staticmethod
    def _current_edition_request_requires_active_status(row, status_map):
        """Whether an unversioned request needs active-lifecycle filtering."""
        identity = row.get("identity") or {}
        return bool(status_map)

    @staticmethod
    def _prefer_catalog_visible_candidates(candidates, status_map=None, row=None):
        candidates = list(candidates or [])
        if not candidates or not status_map:
            return candidates

        candidates = DocumentSearchService._suppress_stale_active_lifecycle_duplicates(
            candidates,
            status_map,
            row,
        )
        if not candidates:
            return []

        visible = [
            candidate for candidate in candidates
            if DocumentSearchService._candidate_catalog_visibility(
                candidate,
                status_map,
            ) is True
        ]
        if visible:
            return visible
        unknown = [
            candidate for candidate in candidates
            if DocumentSearchService._candidate_catalog_visibility(
                candidate,
                status_map,
            ) is None
        ]
        return unknown or candidates

    @staticmethod
    def _suppress_stale_active_lifecycle_duplicates(
        candidates,
        status_map,
        row=None,
    ):
        """Do not let a bad ACTIVE duplicate hide an exact withdrawn edition."""
        requested_sdo = str(
            (row or {}).get("requested_sdo_name")
            or (row or {}).get("search_sdo_name")
            or (row or {}).get("sdo_name")
            or ""
        ).strip().upper()
        # BIS/IS lifecycle is checked against the official BIS catalogue and
        # is handled by that dedicated verification path.
        if requested_sdo in {"BIS", "IS"}:
            return list(candidates or [])

        unavailable_editions = set()
        for candidate in candidates or []:
            status_info = status_map.get(
                getattr(candidate, "status_id", None)
            ) or {}
            status_name = str(
                DocumentSearchService._candidate_embedded_lifecycle_status(
                    candidate
                )
                or status_info.get("name")
                or ""
            ).strip()
            if (
                DocumentSearchService._candidate_catalog_visibility(
                    candidate,
                    status_map,
                ) is not False
                or not DocumentSearchService._status_label_is_unavailable(
                    status_name
                )
            ):
                continue
            identity = parse_identity(
                requested_sdo,
                getattr(candidate, "display_stdNo", "")
                or getattr(candidate, "standardno", ""),
            )
            core = normalize_identity_core(
                identity.get("core_number") or identity.get("core") or ""
            )
            year = DocumentSearchService._candidate_year(
                candidate,
                requested_sdo,
            )
            if core and year is not None:
                unavailable_editions.add(
                    (
                        getattr(candidate, "sdo_id", None),
                        core,
                        identity.get("qualifier"),
                        int(year),
                    )
                )

        if not unavailable_editions:
            return list(candidates or [])

        filtered = []
        for candidate in candidates or []:
            embedded_status = (
                DocumentSearchService._candidate_embedded_lifecycle_status(
                    candidate
                )
            )
            candidate_status_info = status_map.get(
                getattr(candidate, "status_id", None)
            ) or {}
            candidate_lifecycle_status = str(
                embedded_status
                or candidate_status_info.get("name")
                or ""
            )
            if DocumentSearchService._candidate_catalog_visibility(
                candidate,
                status_map,
            ) is True:
                filtered.append(candidate)
                continue
            if DocumentSearchService._status_label_is_unavailable(
                candidate_lifecycle_status
            ):
                filtered.append(candidate)
                continue
            identity = parse_identity(
                requested_sdo,
                getattr(candidate, "display_stdNo", "")
                or getattr(candidate, "standardno", ""),
            )
            core = normalize_identity_core(
                identity.get("core_number") or identity.get("core") or ""
            )
            year = DocumentSearchService._candidate_year(
                candidate,
                requested_sdo,
            )
            edition_key = (
                getattr(candidate, "sdo_id", None),
                core,
                identity.get("qualifier"),
                int(year) if year is not None else None,
            )
            if edition_key not in unavailable_editions:
                filtered.append(candidate)
        return filtered

    @staticmethod
    def _status_label_is_unavailable(status_name):
        return lifecycle_status._status_label_is_unavailable(
            status_name
        )

    @staticmethod
    def _candidate_embedded_lifecycle_status(candidate):
        return lifecycle_status._candidate_embedded_lifecycle_status(
            candidate
        )

    @staticmethod
    def _is_bis_revision_edition(requested_sdo, expression):
        """Recognize BIS/IS ``Rev N, YYYY`` catalog edition notation."""
        return bool(
            str(requested_sdo or "").strip().upper() in {"BIS", "IS"}
            and re.search(
                r"(?i)\bREV(?:ISION)?\.?\s*[-.:#]?\s*\d+\s*,\s*(?:19|20)\d{2}\b",
                str(expression or ""),
            )
        )

    @staticmethod
    def _bis_replacement_standard(requested_sdo, standard, status):
        """Return a verified replacement for a withdrawn BIS standard."""
        if str(requested_sdo or "").strip().upper() != "BIS":
            return None
        if "WITHDRAWN" not in str(status or "").upper():
            return None
        designation = str(
            getattr(standard, "display_stdNo", "")
            or getattr(standard, "standardno", "")
            or ""
        )
        identity = parse_identity("BIS", designation)
        key = (
            identity.get("core_number"),
            identity.get("year")
            or getattr(standard, "standardyear", None)
            or standard_number_year(designation),
        )
        verified_replacements = {
            ("2099", 1986): "IS/IEC 60137 : 2017",
        }
        return verified_replacements.get(key)

    @staticmethod
    def _bis_superseded_by_note(status_detail):
        """Extract a BIS supersession note when the source includes one."""
        text = str(status_detail or "").strip()
        match = re.search(
            r"(?is)\bSuperseded\s+by\s*:\s*(.+?)(?=\s+(?:Status|Price|Technical\s+Committee)\s*:|$)",
            text,
        )
        if not match:
            return None
        value = re.sub(r"\s+", " ", match.group(1)).strip(" \t\r\n:;,.|")
        return value or None

    @staticmethod
    def _is_bsb_internal_only(standard):
        """True when the row is stocked only for BSB Internal use."""
        if int(getattr(standard, "BSBInternal", 0) or 0) != 1:
            return False
        return not any(
            int(getattr(standard, flag, 0) or 0) == 1
            for flag in (
                "BSBESales",
                "BSBSubscription",
                "DocumentAvailability",
            )
        )

    @staticmethod
    def _prefer_externally_available_candidates(candidates):
        """Keep a sellable row ahead of a BSB Internal-only duplicate."""
        candidates = list(candidates or [])
        sellable = [
            candidate
            for candidate in candidates
            if not DocumentSearchService._is_bsb_internal_only(candidate)
        ]
        return sellable or candidates

    @staticmethod
    def _master_result_status(status_info, standard):
        """A current catalogue row is found. Withdrawn and historical are not."""
        if not status_info:
            return "STATUS UNKNOWN", False

        status_name = str(status_info.get("name") or "").strip()
        if not status_name:
            return "STATUS UNKNOWN", False
        if (
            int(status_info.get("cart_show") or 0) != 1
            or int(status_info.get("std_show") or 0) != 1
            or DocumentSearchService._status_label_is_unavailable(status_name)
        ):
            return status_name.upper(), False
        if DocumentSearchService._is_bsb_internal_only(standard):
            return "NOT FOUND", False
        return "AVAILABLE", True

    @staticmethod
    def _candidate_has_database_document(candidate, enrichment_map):
        return result_assembly.candidate_has_database_document(
            candidate,
            enrichment_map,
        )

    @staticmethod
    def _requested_edition_lifecycle_status(row, actual_year):
        """Return a known unavailable status only for the requested edition."""
        requested_year = (row.get("identity") or {}).get("year")
        if requested_year is None or actual_year is None:
            return None
        try:
            if int(requested_year) != int(actual_year):
                return None
        except (TypeError, ValueError):
            return None
        status = str(row.get("requested_edition_status") or "").strip().upper()
        return (
            status
            if DocumentSearchService._status_label_is_unavailable(status)
            else None
        )

    @staticmethod
    def format_master_standard(
        standard,
    ):
        return result_helpers.format_master_standard(standard)

    @staticmethod
    def _normalize_bis_standard_designation(standard_data):
        """Present BIS catalog identifiers with the IS designation prefix."""
        for field in ("display_stdNo", "standardno"):
            value = str(standard_data.get(field) or "")
            if value.upper().startswith("BIS "):
                standard_data[field] = "IS " + value[4:]

    # ============================================================
    # ENRICHMENT
    # ============================================================

    @staticmethod
    def _price_identity_designation(value):
        """Return the base-edition designation used to join amendment prices.

        Some SDO catalogues price a consolidated amendment publication on its
        base edition record. Keep edition identity (including the base year),
        while removing amendment/corrigendum suffixes and IEC's trailing CSV
        format marker so those records can share that exact edition price.
        """
        designation = str(value or "").strip()
        designation = re.sub(
            r"(?i)(?:\+|/|\s)\s*"
            r"(?:CORR(?:IGENDUM)?\.?|COR\.?|AMD\.?|AMEND(?:MENT)?\.?)"
            r"\s*(?:NO\.?\s*)?\d+[A-Z]?"
            r"(?::(?:19|20)\d{2})?.*$",
            "",
            designation,
        )
        designation = re.sub(r"(?i)\s+CSV\s*$", "", designation)
        return designation.strip()

    def build_enrichment_map(
        self,
        standards,
        adoption_text_by_standard_id=None,
    ):
        return enrichment_builder.build_enrichment_map(
            standards,
            self.enrichment_repository,
            self._price_identity_designation,
            self._filter_api_tc_classifications,
            adoption_text_by_standard_id,
        )

    @staticmethod
    def _filter_api_tc_classifications(master, classifications):
        """Select the relevant API catalogue category for known standards."""
        return filter_api_classifications(
            getattr(master, "standardno", None),
            classifications,
        )

    @staticmethod
    def _format_iso_committee(value):
        """Ensure ISO committee codes retain their ISO namespace prefix."""
        committee = re.sub(r"\s+", " ", str(value or "")).strip()
        if not committee:
            return ""
        if re.match(r"(?i)^ISO\s*/\s*TC\b", committee):
            return re.sub(r"(?i)^ISO\s*/\s*TC", "ISO/TC", committee)
        if re.match(r"(?i)^TC\b", committee):
            return "ISO/" + committee
        return committee

    # ============================================================
    # SDO RESOLUTION
    # ============================================================

    def resolve_sdo_ids(
        self,
        sdo_names,
        fallback_names=None,
    ):

        """
        Resolve SDO IDs from the SDO table.

        Guessed aliases are not scanned against the catalogue.
        ``fallback_names`` are the caller's own SDO texts, and each
        missing one gets a single prefix lookup.
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

        missing = []
        for prefix in fallback_names or []:
            key = str(prefix).upper().strip()
            if key and key not in result and key not in missing:
                missing.append(key)

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
