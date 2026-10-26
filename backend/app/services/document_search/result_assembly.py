"""Result assembly for document search."""

import re
import time

from app.services.document_search.selection_context import use_candidate_status_map

from app.services.ieee_official_metadata import IEEEOfficialMetadataService
from app.utils.standard_identity import (
    normalize_identity_core,
    normalize_tokens,
    parse_identity,
    reaffirmation_year,
)


def candidate_has_database_document(candidate, enrichment_map):
    """Require an available database master with an active price row."""
    standard_id = getattr(candidate, "Standard_id", None)
    if hasattr(candidate, "DocumentAvailability"):
        if getattr(candidate, "DocumentAvailability", None) != 1:
            return False
    enrichment = (enrichment_map or {}).get(standard_id) or {}
    return (
        enrichment.get("document_available") is True
        and enrichment.get("has_database_price") is True
    )


def assemble_results(
    service,
    started,
    prepared_rows,
    unique_prepared_rows,
    local_matches,
    master_matches,
):
    """Collect enrichments and build ordered result templates."""
    # --------------------------------------------------------
    # 8. COLLECT MATCHED STANDARDS
    # --------------------------------------------------------

    stage_started = time.perf_counter()

    matched_standards = []

    seen = set()

    matched_candidates = [
        standard
        for row in unique_prepared_rows.values()
        for standard in (
            local_matches.get(row["request_key"], [])
            + master_matches.get(row["request_key"], [])
        )
        if getattr(standard, "sdo_id", None) == row["sdo_id"]
    ]

    nace_mr0103_overrides = {}
    for row in unique_prepared_rows.values():
        official_candidate = service._official_nace_mr0103_edition(row)
        if official_candidate is None:
            continue
        nace_mr0103_overrides[row["request_key"]] = official_candidate
        matched_candidates.append(official_candidate)

    for row in unique_prepared_rows.values():
        hi_replacement = service._official_hi_replacement(row)
        if hi_replacement is not None:
            matched_candidates.append(hi_replacement)

    ieee_replacements = {}
    for row in unique_prepared_rows.values():
        ieee_metadata = IEEEOfficialMetadataService.lookup(
            row.get("search_sdo_name") or row.get("sdo_name"),
            row.get("result_displaystdno") or row.get("displaystdno"),
        )
        if ieee_metadata is None:
            continue
        replacement = service._official_ieee_replacement(
            row,
            ieee_metadata,
        )
        ieee_replacements[row["request_key"]] = (
            ieee_metadata,
            replacement,
        )
        if replacement is not None:
            matched_candidates.append(replacement)

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
        service.build_enrichment_map(
            matched_standards
        )
    )
    status_map = service.enrichment_repository.get_standard_status_map(
        {
            getattr(standard, "status_id", None)
            for standard in matched_standards
        }
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

        # Standalone revision/amendment requests stay out of the found
        # results. COR/AMD suffix forms are normalized to their base
        # designation during row preparation and continue below.
        if row.get("has_revision_or_amendment"):
            template = {
                "requested_sdo": row["sdo_name"],
                "requested_standard": row["result_displaystdno"],
                "matched": False,
                "status": "NOT FOUND",
                "status_detail": (
                    "Revision/amendment requests are excluded from "
                    "standard matching."
                ),
                "standard": None,
                "actions": {"manual_search": True},
                "_source_request_identity": row.get(
                    "source_request_identity"
                ),
            }
            results.append(template)
            continue

        cached_templates = result_templates.get(key)
        if cached_templates is not None:
            results.extend(
                {
                    **template,
                    "requested_sdo": row["sdo_name"],
                    "requested_standard": row["result_displaystdno"],
                    "_source_request_identity": row.get(
                        "source_request_identity"
                    ),
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
                "requested_standard": row["result_displaystdno"],
                "matched": False,
                "status": "SDO NOT FOUND",
                "standard": None,
                "actions": {"manual_search": True},
                "_source_request_identity": row.get(
                    "source_request_identity"
                ),
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

        # SDO + standard number form one identity. Keep this guard at the
        # result boundary as well as in the partitioned queries so a
        # candidate from another catalogue can never be surfaced.
        request_candidates = [
            candidate
            for candidate in request_candidates
            if getattr(candidate, "sdo_id", None) == row["sdo_id"]
        ]

        official_nace_candidate = nace_mr0103_overrides.get(
            row["request_key"]
        )
        if official_nace_candidate is not None:
            # Prefer AMPP's canonical ANSI-NACE catalogue entry over the
            # duplicate legacy NACE row for this same 2023 publication.
            # The canonical record carries the SC 08 assignment and its
            # active/reaffirmed catalogue status.
            request_candidates = [official_nace_candidate]

        hi_replacement = service._official_hi_replacement(
            row,
        )
        if hi_replacement is not None:
            # HI 2.6 was replaced by HI 14.6. Match the exact obsolete
            # designation and return the active replacement already in
            # the catalogue instead of surfacing the 2000 edition.
            request_candidates = [hi_replacement]

        # Discard unavailable records before edition selection.
        request_candidates = [
            candidate
            for candidate in request_candidates
            if service._candidate_has_database_document(
                candidate,
                enrichment_map,
            )
        ]

        if service._is_tema_edition_request(row):
            request_candidates = service._select_latest_tema_edition(
                request_candidates,
                row,
                status_map,
            )

        if row.get("expand_family"):
            with use_candidate_status_map(status_map):
                request_candidates = service._select_candidates(
                    request_candidates,
                    row,
                )
        else:
            request_candidates = service._select_best_current_candidate(
                request_candidates,
                row,
                status_map,
            )

        if row.get("expand_family"):
            requested_qualifier = row["identity"].get("qualifier")
            requested_family = (
                requested_qualifier
                if requested_qualifier in {"PART", "SECTION", "CHAPTER", "SERIES"}
                else "PART"
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
                if candidate_qualifier and (
                    candidate_qualifier.startswith(
                        f"{requested_family}:"
                    )
                    or (
                        row["identity"].get("family_lookup")
                        and candidate_qualifier.startswith("SECTION:")
                    )
                ):
                    family_members.append(candidate)

            if family_members and requested_family != "SERIES":
                request_candidates = family_members

        ieee_resolution = ieee_replacements.get(key)
        if ieee_resolution is not None:
            ieee_metadata, ieee_replacement = ieee_resolution
            # IEEE's legacy records are incorrectly marked ACTIVE in the
            # mirror. Use the official successor's real catalogue row so
            # year, price, title, and committee all belong to that edition.
            request_candidates = (
                [ieee_replacement]
                if ieee_replacement is not None
                else []
            )

        # Reapply the availability gate after all replacement paths so
        # none can bypass the database document and price requirements.
        request_candidates = [
            candidate
            for candidate in request_candidates
            if service._candidate_has_database_document(
                candidate,
                enrichment_map,
            )
        ]

        standards_by_id = {}
        for standard in request_candidates:
            standard_id = standard.Standard_id or standard.id
            standards_by_id.setdefault(standard_id, standard)

        if standards_by_id:
            templates = []
            for standard in standards_by_id.values():
                is_master = hasattr(standard, "standardyear")
                requested_year = row["identity"].get("year")
                is_match = True
                if is_master:
                    data = service.format_master_standard(standard)
                    status_info = status_map.get(standard.status_id)
                    status, is_match = service._master_result_status(
                        status_info,
                        standard,
                    )
                    data["catalog_status"] = (
                        status_info.get("name")
                        if status_info
                        else None
                    )
                    actual_year = standard.standardyear
                else:
                    data = service.search_service.format_standard(standard)
                    status = service.search_service.validate_standard(standard)
                    is_match = status == "AVAILABLE"
                    status_info = status_map.get(
                        getattr(standard, "status_id", None)
                    )
                    if not status_info:
                        status = "STATUS UNKNOWN"
                        is_match = False
                    elif (
                            int(status_info.get("cart_show") or 0) != 1
                            or int(status_info.get("std_show") or 0) != 1
                            or service._status_label_is_unavailable(
                                status_info.get("name")
                            )
                    ):
                        status = str(
                            status_info.get("name") or "UNAVAILABLE"
                        ).upper()
                        is_match = False
                    actual_year = service._candidate_year(
                        standard,
                        row["sdo_name"],
                    )

                tema_designation = service._official_tema_edition_designation(
                    row,
                    actual_year,
                )
                if tema_designation:
                    # TEMA replaced numbered editions with year-based
                    # editions in 2026. The catalogue still labels this
                    # record "Twelfth Edition", which TEMA explicitly
                    # says is not the publication name.
                    data["standardno"] = tema_designation
                    data["display_stdNo"] = tema_designation
                requested_tema_is_historical = (
                    service._tema_request_is_historical(
                        row,
                        actual_year,
                    )
                )

                requested_lifecycle_status = str(
                    row.get("requested_edition_status") or ""
                ).strip().upper()
                if service._requested_edition_lifecycle_status(row, actual_year):
                    # A duplicated catalogue record can be incorrectly
                    # marked ACTIVE even when the same requested edition
                    # has an explicit Historical/Withdrawn lifecycle row.
                    # Apply that lifecycle only to the exact requested
                    # year; a newer active edition remains eligible.
                    status = service._requested_edition_lifecycle_status(
                        row,
                        actual_year,
                    )
                    is_match = False
                embedded_lifecycle_status = (
                    service._candidate_embedded_lifecycle_status(standard)
                )
                if embedded_lifecycle_status:
                    status = embedded_lifecycle_status
                    is_match = False
                    data["catalog_status"] = embedded_lifecycle_status
                if service._is_api_request(row):
                    api_status_info = status_map.get(
                        getattr(standard, "status_id", None)
                    ) or {}
                    api_lifecycle = str(
                        api_status_info.get("name") or ""
                    ).strip()
                    if service._status_label_is_unavailable(api_lifecycle):
                        status = (
                            "WITHDRAWN"
                            if re.search(
                                r"(?i)\bDO\s+NOT\s+USE\b",
                                api_lifecycle,
                            )
                            else api_lifecycle.upper()
                        )
                        is_match = False

                # The BIS catalogue sometimes stores BIS-prefixed display
                # numbers for standards requested under the IS designation.
                # Preserve the catalogue identity, but present the requested
                # SDO's designation consistently in search/export results.
                if str(
                    row.get("requested_sdo_name") or ""
                ).strip().upper() in {"IS", "BIS"}:
                    service._normalize_bis_standard_designation(data)

                requested_year_is_newer_than_database = bool(
                    requested_year is not None
                    and actual_year is not None
                    and int(actual_year) < int(requested_year)
                )
                if is_match and requested_year_is_newer_than_database:
                    # Never present an older database edition as a match
                    # for a newer, explicitly requested edition.
                    is_match = False
                    status = "NOT FOUND"

                status_detail = (
                    (
                        f"No database edition is available for requested "
                        f"year {requested_year}; latest available database "
                        f"edition is {actual_year}."
                        if requested_year_is_newer_than_database
                        else f"Requested year {requested_year}; returned latest available edition {actual_year}."
                    )
                    if requested_year is not None
                    and actual_year is not None
                    and int(requested_year) != int(actual_year)
                    and not requested_tema_is_historical
                    else None
                )
                if requested_tema_is_historical and not status_detail:
                    status_detail = (
                        "Requested TEMA edition is superseded; "
                        f"latest available edition is {actual_year}."
                    )
                if (
                    not is_match
                    and requested_lifecycle_status
                    and requested_year is not None
                    and actual_year is not None
                    and int(requested_year) == int(actual_year)
                    and service._status_label_is_unavailable(
                        requested_lifecycle_status
                    )
                ):
                    status_detail = (
                        f"Requested edition is marked "
                        f"{requested_lifecycle_status} in the catalogue "
                        "and is not available."
                    )
                reaffirmed_year = (
                    reaffirmation_year(row["displaystdno"])
                    or reaffirmation_year(standard.Standard_id or "")
                    or reaffirmation_year(standard.display_stdNo or "")
                    or reaffirmation_year(standard.standardno or "")
                )
                if is_match and actual_year is not None:
                    if requested_year is None:
                        status_detail = (
                            f"Current available version: {actual_year}."
                        )
                    elif actual_year == requested_year and reaffirmed_year is not None:
                        status_detail = (
                            f"Edition {actual_year}; reaffirmed in "
                            f"{reaffirmed_year}."
                        )

                    if reaffirmed_year is not None:
                        reaffirmation_note = (
                            f"Reaffirmed in {reaffirmed_year}."
                        )
                        if (
                            status_detail
                            and reaffirmation_note not in status_detail
                        ):
                            status_detail = (
                                f"{status_detail.rstrip()} "
                                f"{reaffirmation_note}"
                            )
                        elif not status_detail:
                            status_detail = reaffirmation_note

                    # Keep an existing catalogue reaffirmation note in the
                    # details once. Repeated rows should not look like
                    # separate standards merely because the note is
                    # duplicated in the worksheet's two detail columns.
                    if status_detail:
                        status_detail = re.sub(
                            r"(?i)(Reaffirmed in \\d{4}\\.)(?:\\s*\\1)+",
                            r"\\1",
                            status_detail,
                        )

                if reaffirmed_year is not None:
                    data["reaffirmation_year"] = reaffirmed_year

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
                    "requested_standard": (
                        str(
                            data.get("display_stdNo")
                            or standard.display_stdNo
                            or standard.standardno
                            or row["result_displaystdno"]
                        )
                        if (
                            row["identity"].get("qualifier") == "SERIES"
                            and not is_match
                        ) or (
                            is_match
                            and requested_year is not None
                            and actual_year is not None
                            and int(requested_year) != int(actual_year)
                            and not requested_tema_is_historical
                        ) or (
                            is_match
                            and requested_tema_is_historical
                        )
                        else row["result_displaystdno"]
                    ),
                    "matched": is_match,
                    "status": (
                        "NOT FOUND"
                        if row["identity"].get("qualifier") == "SERIES"
                        and not is_match
                        else status
                    ),
                    "status_detail": (
                        "No current available edition was found for this series part."
                        if row["identity"].get("qualifier") == "SERIES"
                        and not is_match
                        else status_detail
                    ),
                    "replacement_standard": (
                        service._bis_replacement_standard(
                            row.get("requested_sdo_name"),
                            standard,
                            status,
                        )
                        if not is_match
                        else None
                    ),
                    "superseded_by": (
                        service._bis_superseded_by_note(status_detail)
                        if not is_match
                        and str(row.get("requested_sdo_name") or "")
                        .strip()
                        .upper()
                        in {"BIS", "IS"}
                        and "WITHDRAWN" in str(status or "").upper()
                        else None
                    ),
                    "standard": data if is_match else None,
                    "actions": {},
                    "_source_request_identity": row.get(
                        "source_request_identity"
                    ),
                }
                templates.append(template)
                results.append(template)

                # If the request names a different year, retain the exact
                # requested edition as not found. A year difference alone
                # does not establish that the available edition supersedes it.
                if (
                    is_match
                    and requested_year is not None
                    and actual_year is not None
                    and int(requested_year) != int(actual_year)
                    and not requested_tema_is_historical
                ) or (
                    is_match
                    and requested_tema_is_historical
                ):
                    has_explicit_replacement = bool(
                        hi_replacement is not None
                        or (
                            ieee_resolution is not None
                            and ieee_resolution[1] is not None
                        )
                        or requested_tema_is_historical
                    )
                    ieee_relationship_type = (
                        getattr(ieee_resolution[0], "relationship_type", None)
                        if ieee_resolution is not None
                        else None
                    )
                    historical_template = {
                        "requested_sdo": row["sdo_name"],
                        "requested_standard": row["result_displaystdno"],
                        "matched": False,
                        "status": "NOT FOUND",
                        "status_detail": (
                            (
                                (
                                    f"Requested edition {requested_year} was "
                                    "incorporated into the current consolidated "
                                    f"edition {actual_year}."
                                    if ieee_relationship_type
                                    == "INCORPORATED_INTO"
                                    else (
                                        f"Requested edition {requested_year} is "
                                        "superseded; latest available edition is "
                                        f"{actual_year}."
                                    )
                                )
                                if has_explicit_replacement
                                else (
                                    f"Requested edition {requested_year} does not "
                                    f"match the available edition {actual_year}."
                                )
                            )
                            if requested_year is not None
                            and int(requested_year) != int(actual_year)
                            and not requested_tema_is_historical
                            else (
                                "Requested TEMA edition is superseded; "
                                f"latest available edition is {actual_year}."
                            )
                        ),
                        "replacement_standard": (
                            str(
                                data.get("display_stdNo")
                                or standard.display_stdNo
                                or standard.standardno
                                or ""
                            )
                            if has_explicit_replacement
                            else None
                        ),
                        "superseded_by": (
                            str(
                                data.get("display_stdNo")
                                or standard.display_stdNo
                                or standard.standardno
                                or ""
                            )
                            if has_explicit_replacement
                            and ieee_relationship_type
                            != "INCORPORATED_INTO"
                            else None
                        ),
                        "standard": None,
                        "actions": {"manual_search": True},
                        "_source_request_identity": row.get(
                            "source_request_identity"
                        ),
                    }
                    templates.append(historical_template)
                    results.append(historical_template)
            result_templates[key] = templates
            continue

        # ----------------------------------------------------
        # NOT FOUND
        # ----------------------------------------------------

        ieee_resolution = ieee_replacements.get(key)
        ieee_metadata = (
            ieee_resolution[0] if ieee_resolution else None
        )
        requested_edition_status = str(
            row.get("requested_edition_status") or ""
        ).strip().upper()
        if re.search(r"(?i)\bDO\s+NOT\s+USE\b", requested_edition_status):
            requested_edition_status = "WITHDRAWN"
        unavailable_edition_status = (
            requested_edition_status
            if service._status_label_is_unavailable(
                requested_edition_status
            )
            else None
        )
        if ieee_metadata:
            ieee_relationship_type = getattr(
                ieee_metadata,
                "relationship_type",
                "SUPERSEDED_BY",
            )
            if ieee_relationship_type == "INCORPORATED_INTO":
                not_found_detail = (
                    "IEEE SA lists this amendment edition as superseded and "
                    "incorporated into the IEEE 802.1Q consolidated family; "
                    f"the current consolidated edition is "
                    f"{ieee_metadata.replacement_designation}, but that "
                    "edition is not available in the local catalogue."
                )
            else:
                not_found_detail = (
                    "IEEE SA lists this edition as superseded; current "
                    f"successor is {ieee_metadata.replacement_designation}, "
                    "but that successor is not available in the local "
                    "catalogue."
                )
        elif unavailable_edition_status:
            not_found_detail = (
                f"Requested edition is marked "
                f"{unavailable_edition_status} in the catalogue "
                "and is not available."
            )
        else:
            not_found_detail = None
        template = {
            "requested_sdo": row["sdo_name"],
            "requested_standard": row["result_displaystdno"],
            "matched": False,
            "status": (
                unavailable_edition_status
                or "NOT FOUND"
            ),
            "status_detail": not_found_detail,
            "replacement_standard": (
                ieee_metadata.replacement_designation
                if ieee_metadata
                else None
            ),
            "superseded_by": (
                ieee_metadata.replacement_designation
                if ieee_metadata
                and getattr(
                    ieee_metadata,
                    "relationship_type",
                    "SUPERSEDED_BY",
                )
                != "INCORPORATED_INTO"
                else None
            ),
            "standard": None,
            "actions": {"manual_search": True},
            "_source_request_identity": row.get(
                "source_request_identity"
            ),
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

    # A series row is a request to expand the family, not a catalogue
    # part to include alongside the expanded rows. Once current parts
    # were found, drop an unmatched placeholder for the series root.
    series_rows = [
        row for row in prepared_rows
        if row.get("identity", {}).get("qualifier") == "SERIES"
    ]
    for row in series_rows:
        root = normalize_identity_core(
            row.get("identity", {}).get("core_number") or ""
        )
        has_found_part = any(
            result.get("matched")
            and str(result.get("requested_sdo") or "").casefold()
            == str(row.get("sdo_name") or "").casefold()
            and (
                (part_identity := parse_identity(
                    row.get("search_sdo_name") or row.get("sdo_name"),
                    result.get("requested_standard") or "",
                )).get("qualifier")
                not in {None, "SERIES"}
            )
            and normalize_identity_core(
                part_identity.get("core_number") or ""
            ).startswith(root)
            for result in results
        )
        if has_found_part:
            results = [
                result for result in results
                if not (
                    not result.get("matched")
                    and str(result.get("requested_sdo") or "").casefold()
                    == str(row.get("sdo_name") or "").casefold()
                    and normalize_tokens(
                        result.get("requested_standard") or ""
                    ) == normalize_tokens(
                        row.get("result_displaystdno") or ""
                    )
                )
            ]

    return service._deduplicate_results(results)
