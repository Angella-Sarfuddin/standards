
from app.core.standard_identity import parse_identity
from app.services.document_search_service import DocumentSearchService
from app.services.grouping_service import GroupingService


def refresh_official_catalog_rows(results, db):
    """
    Keep catalogue refresh generic.

    Standard-specific refresh rules belong in the catalogue/search layer,
    not in export preparation.
    """
    return list(results or [])


def _expand_series_export_rows(results, db):
    """Expand series roots while preserving already-expanded rows."""
    expanded = []
    cache = {}

    for result in results or []:
        if result.get("_seriesExpanded"):
            expanded.append(result)
            continue

        standard = result.get("standard") or {}
        requested_sdo = str(result.get("requested_sdo") or "").strip()

        requested_number = str(
            result.get("requested_standard")
            or standard.get("display_stdNo")
            or standard.get("standardno")
            or ""
        ).strip()

        matched_designations = (
            standard.get("display_stdNo"),
            standard.get("standardno"),
        )

        matched_series = next(
            (
                designation
                for designation in matched_designations
                if designation
                and parse_identity(
                    requested_sdo, designation
                ).get("qualifier") == "SERIES"
            ),
            None,
        )

        requested_is_series = (
            parse_identity(
                requested_sdo, requested_number
            ).get("qualifier") == "SERIES"
        )

        # Do not expand an already-resolved individual family member.
        if result.get("matched") and standard and not matched_series:
            expanded.append(result)
            continue

        series_designation = matched_series or (
            requested_number if requested_is_series else None
        )

        if not series_designation:
            expanded.append(result)
            continue

        cache_key = (
            requested_sdo.casefold(),
            str(series_designation).casefold(),
        )

        if cache_key not in cache:
            cache[cache_key] = DocumentSearchService(db).search(
                [{
                    "sdo_name": requested_sdo,
                    "displaystdno": series_designation,
                }]
            )

        current_results = cache[cache_key]

        current_parts = [
            item for item in current_results
            if item.get("matched")
        ]

        if current_parts:
            expanded.extend(
                {**item, "_seriesExpanded": True}
                for item in current_results
            )
        else:
            expanded.append({
                **result,
                "_seriesExpanded": True,
            })

    # Remove exact series-expansion clones, but keep distinct worksheet
    # requests so the Duplicates sheet can still report repeated searches.
    deduplicated = []
    seen = set()

    for result in expanded:
        requested_sdo = str(
            result.get("requested_sdo") or ""
        ).strip().casefold()

        requested_standard = str(
            result.get("requested_standard") or ""
        ).strip().casefold()

        standard = result.get("standard") or {}
        source_identity = result.get("source_row_identity")
        if isinstance(source_identity, list):
            source_identity = tuple(source_identity)
        elif not isinstance(source_identity, tuple):
            source_identity = None

        if result.get("matched") and standard:
            resolved = (
                standard.get("Standard_id")
                or standard.get("id")
                or standard.get("display_stdNo")
                or standard.get("standardno")
            )

            key = (
                "found",
                requested_sdo,
                requested_standard,
                str(resolved or "").casefold(),
                source_identity,
            )
        else:
            key = (
                "unmatched",
                requested_sdo,
                requested_standard,
                str(result.get("status") or "").casefold(),
                str(result.get("status_detail") or "").casefold(),
                source_identity,
            )

        if key in seen:
            continue

        seen.add(key)
        deduplicated.append(result)

    return deduplicated


def expand_series_export_rows(results, db):
    return _expand_series_export_rows(results, db)


def prepare_quotation_export(results, db):
    results = refresh_official_catalog_rows(results, db)

    return {
        "results": results,
        "grouping": GroupingService.group_results(results),
    }


def prepare_latest_year_export(results, db):
    return refresh_official_catalog_rows(results, db)


def prepare_both_export(quotation_results, latest_year_results, db):
    quotation_results = refresh_official_catalog_rows(
        quotation_results, db
    )

    latest_year_results = refresh_official_catalog_rows(
        latest_year_results, db
    )

    return (
        {
            "results": quotation_results,
            "grouping": GroupingService.group_results(
                quotation_results
            ),
        },
        latest_year_results,
    )


def prepare_found_and_not_found_export(
    quotation_results, all_results, db
):
    quotation_results = refresh_official_catalog_rows(
        quotation_results, db
    )

    all_results = refresh_official_catalog_rows(
        all_results, db
    )

    return (
        expand_series_export_rows(quotation_results, db),
        expand_series_export_rows(all_results, db),
    )
