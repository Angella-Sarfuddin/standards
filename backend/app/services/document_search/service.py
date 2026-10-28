"""Search orchestration. The other class methods live in service_methods.py."""

import logging
import time

logger = logging.getLogger(__name__)

from app.repositories.enrichment_repository import EnrichmentRepository
from app.repositories.standards_repository import StandardsRepository
from app.services.document_search import input_preparation
from app.services.document_search import local_matching
from app.services.document_search import lookup_indexes
from app.services.document_search import repository_lookup
from app.services.document_search import result_assembly
from app.services.document_search.service_methods import (
    DocumentSearchServiceMethods,
)
from app.services.search_service import SearchService
import app.services.document_search.service_methods as service_methods


class DocumentSearchService(DocumentSearchServiceMethods):

    def __init__(self, db):
        # Single-DB architecture:
        # search, master fallback, pricing, and classifications
        # all use the same application DB session.
        self.repository = StandardsRepository(db)
        self.search_service = SearchService(self.repository)
        self.enrichment_repository = EnrichmentRepository(db)
        self._search_memos = {}

    # ============================================================
    # MAIN SEARCH
    # ============================================================

    def search(self, rows):
        started = time.perf_counter()

        if not rows:
            return []

        logger.info(
            f"[SEARCH TIMING] START | rows={len(rows)}"
        )

        # --------------------------------------------------------
        # 1. RESOLVE SDO IDS
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        sdo_names = []
        requested_names = []
        for row in rows:
            sdo_name = str(row.get("sdo_name") or "").strip()
            displaystdno = str(row.get("displaystdno") or "").strip()
            if sdo_name:
                requested_names.append(sdo_name)
            if not sdo_name and not displaystdno:
                continue
            sdo_names.extend(
                self._candidate_sdo_names(
                    sdo_name,
                    displaystdno,
                )
            )

        sdo_map = self.resolve_sdo_ids(
            sdo_names,
            fallback_names=requested_names,
        )
        if any(
            self._is_tema_edition_request(row)
            and not str(row.get("sdo_name") or "").strip()
            for row in rows
        ):
            tema_id = self.resolve_sdo_ids(
                ["TEMA"],
                fallback_names=["TEMA"],
            ).get("TEMA")
            if tema_id:
                sdo_map["TEMA"] = tema_id

        logger.info(
            f"[SEARCH TIMING] SDO resolution: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        # --------------------------------------------------------
        # 2. PREPARE INPUT ROWS
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        prepared_rows = input_preparation.prepare_input_rows(
            rows,
            sdo_map,
            is_tema_edition_request=self._is_tema_edition_request,
            is_bis_revision_edition=self._is_bis_revision_edition,
            infer_unique_catalog_sdo=self._infer_unique_catalog_sdo,
            should_expand_family=self._should_expand_family,
            request_identity_key=self._request_identity_key,
        )

        logger.info(
            f"[SEARCH TIMING] Row preparation: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        # --------------------------------------------------------
        # 3. PRIMARY DISPLAY NUMBER LOOKUP
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        display_candidates, candidate_map = (
            repository_lookup.lookup_display_candidates(
                prepared_rows,
                self.repository,
                self.enrichment_repository,
                self._is_api_request,
            )
        )

        logger.info(
            f"[SEARCH TIMING] Display lookup: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        # --------------------------------------------------------
        # 4. EXACT / NORMALIZED / STANDARD NUMBER LOOKUPS
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        (
            exact_results,
            normalized_results,
            standard_number_results,
        ) = repository_lookup.lookup_number_candidates(
            prepared_rows,
            candidate_map,
            self.repository,
            self._row_has_display_candidates,
        )

        logger.info(
            f"[SEARCH TIMING] Exact/normalized lookup: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        # --------------------------------------------------------
        # BUILD LOOKUP MAPS
        # --------------------------------------------------------

        (
            exact_result_map,
            normalized_result_map,
            standard_number_map,
        ) = lookup_indexes.build_lookup_indexes(
            exact_results,
            normalized_results,
            standard_number_results,
        )

        # --------------------------------------------------------
        # 5–6. LOCAL CANDIDATE DISCOVERY AND MATCHING
        # --------------------------------------------------------

        (
            unique_prepared_rows,
            local_matches,
            unresolved,
        ) = local_matching.match_local_standards(
            prepared_rows,
            display_candidates,
            exact_results,
            normalized_results,
            standard_number_results,
            candidate_map,
            exact_result_map,
            normalized_result_map,
            standard_number_map,
            self.repository,
            self.enrichment_repository,
            self._unique_standards,
            self._direct_candidate_lists,
            self._select_candidate,
            self._row_needs_identity_discovery,
            self._candidate_matches_identity,
            self._candidate_is_part_of_root,
            self._select_candidates,
            self._is_bare_qualifier_request,
        )

        # --------------------------------------------------------
        # 7. MASTER FALLBACK
        # --------------------------------------------------------

        stage_started = time.perf_counter()

        master_matches = self.find_master_matches(
            unresolved
        )

        logger.info(
            f"[SEARCH TIMING] Master fallback: "
            f"{time.perf_counter() - stage_started:.3f}s"
        )

        return result_assembly.assemble_results(
            self,
            started,
            prepared_rows,
            unique_prepared_rows,
            local_matches,
            master_matches,
        )


for _name, _value in vars(DocumentSearchServiceMethods).items():
    if _name.startswith("__") and _name.endswith("__"):
        continue
    setattr(DocumentSearchService, _name, _value)

service_methods.DocumentSearchService = DocumentSearchService
