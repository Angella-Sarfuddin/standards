"""Input-row preparation for document search."""

import re

from app.core.standard_formatter import build_full_display_number, remove_draft_marker
from app.core.standard_expression_parser import StandardExpressionParser
from app.core.standard_identity import (
    canonicalize_search_request,
    normalize_identity_core,
    normalize_tokens,
    parse_identity,
    split_stated_replacement,
)


def prepare_input_rows(
    rows,
    sdo_map,
    *,
    is_tema_edition_request,
    is_bis_revision_edition,
    infer_unique_catalog_sdo,
    should_expand_family,
    request_identity_key,
):
    """Prepare ordered request rows using service-provided decisions."""
    prepared_rows = []

    parsed_request_cache = {}
    catalog_sdo_cache = {}

    for row_index, row in enumerate(rows, start=1):

        sdo_name = str(
            row.get("sdo_name") or ""
        ).strip()
        requested_sdo_name = sdo_name

        displaystdno = str(
            row.get("displaystdno") or ""
        ).strip()
        displaystdno = remove_draft_marker(displaystdno)
        stated_replacement = split_stated_replacement(displaystdno)
        if stated_replacement:
            displaystdno = stated_replacement["replacement"]
        if not requested_sdo_name and is_tema_edition_request(
            {"displaystdno": displaystdno}
        ):
            sdo_name = requested_sdo_name = "TEMA"

        raw_request_key = (
            sdo_name.upper(),
            displaystdno.upper(),
            str(
                row.get("raw_standard_expression") or displaystdno
            ).strip().upper(),
            bool(row.get("include_subsections")),
        )
        raw_expression = str(
            row.get("raw_standard_expression") or displaystdno
        ).strip()
        revision_suffix_request = bool(
            re.search(
                r"(?i)(?:/|\+|\s)\s*(?:CORR(?:IGENDUM)?\.?|COR\.?|AMD\.?|AMEND(?:MENT)?\.?)"
                r"\s*(?:NO\.?\s*)?\d+[A-Z]?\b",
                displaystdno,
            )
        )
        # BIS/IS source lists use "Rev N, YYYY" as a legacy edition
        # designation (for example, "IS 2099 Rev 2, 1986"). It is part
        # of the standard identity and must reach catalogue lookup so its
        # actual lifecycle status (including WITHDRAWN) can be reported.
        bis_revision_edition = is_bis_revision_edition(
            requested_sdo_name,
            raw_expression,
        )
        has_revision_or_amendment = bool(
            re.search(
                r"(?i)(?:^|[\s,:/+(])"
                r"(?:REV(?:ISION)?|AMEND(?:MENT)?|AMD)"
                r"\s*[-.:#]?\s*\d+\b",
                raw_expression,
            )
        ) and not revision_suffix_request and not bis_revision_edition
        inferred_sdo, _ = StandardExpressionParser.infer_sdo_and_body(
            displaystdno,
        )
        generic_sdo = requested_sdo_name.upper() in {
            "SP",
            "SPECIAL PUBLICATION",
        }
        explicit_sdo = (
            bool(sdo_name)
            and StandardExpressionParser.is_plausible_sdo(sdo_name)
            and not generic_sdo
        )
        if not explicit_sdo:
            sdo_name = inferred_sdo or sdo_name

        lookup_displaystdno = (
            re.sub(
                r"(?i)(?:/|\+|\s)\s*(?:CORR(?:IGENDUM)?\.?|COR\.?|AMD\.?|AMEND(?:MENT)?\.?)"
                r"\s*(?:NO\.?\s*)?\d+[A-Z]?\b.*$",
                "",
                displaystdno,
            ).rstrip(" :/+")
            if revision_suffix_request
            else displaystdno
        )
        lookup_sdo, lookup_standard, id_name = (
            canonicalize_search_request(
                sdo_name,
                lookup_displaystdno,
            )
        )
        search_sdo_name = (
            lookup_sdo
            or inferred_sdo
            or sdo_name
        )
        resolved_sdo_id = (
            sdo_map.get((id_name or "").upper())
            or sdo_map.get((search_sdo_name or sdo_name).upper())
            or sdo_map.get((lookup_sdo or sdo_name).upper())
            or sdo_map.get(sdo_name.upper())
            or (
                None
                if explicit_sdo
                else sdo_map.get((inferred_sdo or "").upper())
            )
        )
        needs_catalog_inference = (
            generic_sdo
            or (not explicit_sdo and not inferred_sdo)
        )
        if needs_catalog_inference:
            catalog_key = (
                requested_sdo_name.upper(),
                displaystdno.upper(),
            )
            if catalog_key not in catalog_sdo_cache:
                catalog_sdo_cache[catalog_key] = (
                    infer_unique_catalog_sdo(
                        requested_sdo_name,
                        displaystdno,
                    )
                )
            inferred_catalog_sdo = catalog_sdo_cache[catalog_key]
            if inferred_catalog_sdo and not explicit_sdo:
                search_sdo_name, resolved_sdo_id = inferred_catalog_sdo
                if generic_sdo:
                    lookup_standard = (
                        f"SP {displaystdno}".strip()
                    )
            elif not explicit_sdo and generic_sdo:
                resolved_sdo_id = None
        parsed_request = parsed_request_cache.get(raw_request_key)

        if parsed_request is None:
            identity = parse_identity(
                search_sdo_name,
                lookup_standard or lookup_displaystdno,
            )
            if raw_expression:
                raw_identity = parse_identity(
                    requested_sdo_name or search_sdo_name,
                    raw_expression,
                )
                if (
                    normalize_identity_core(
                        raw_identity.get("core_number") or ""
                    )
                    == normalize_identity_core(
                        identity.get("core_number") or ""
                    )
                    and raw_identity.get("identifier_prefix")
                ):
                    identity = {
                        **identity,
                        "identifier_prefix": raw_identity[
                            "identifier_prefix"
                        ],
                    }
            include_subsections = bool(row.get("include_subsections"))
            expand_family = should_expand_family(
                identity,
                include_subsections,
            )
            if (
                include_subsections
                and str(identity.get("qualifier") or "").startswith("PART:")
            ):
                identity = {
                    **identity,
                    "family_lookup": True,
                }
            sdo_id = resolved_sdo_id
            if search_sdo_name != (lookup_sdo or inferred_sdo or sdo_name):
                full_display_number = build_full_display_number(
                    search_sdo_name,
                    lookup_standard or displaystdno,
                )
            else:
                full_display_number = build_full_display_number(
                    sdo_name,
                    displaystdno,
                )
            request_key = request_identity_key(
                sdo_id,
                search_sdo_name,
                identity,
            )
            request_key = (*request_key, expand_family)
            parsed_request = (
                identity,
                sdo_id,
                full_display_number,
                request_key,
                expand_family,
            )
            parsed_request_cache[raw_request_key] = parsed_request
        else:
            (
                identity,
                sdo_id,
                full_display_number,
                request_key,
                expand_family,
            ) = parsed_request

        prepared_rows.append(
            {
                "sdo_name": sdo_name,
                "requested_sdo_name": requested_sdo_name,
                "search_sdo_name": search_sdo_name,
                "displaystdno": displaystdno,
                "result_displaystdno": lookup_displaystdno,
                "stated_original": (
                    stated_replacement["original"]
                    if stated_replacement
                    else None
                ),
                "stated_replacement": (
                    stated_replacement["replacement"]
                    if stated_replacement
                    else None
                ),
                "has_revision_or_amendment": has_revision_or_amendment,
                "full_display_number": full_display_number,
                "sdo_id": sdo_id,
                "identity": identity,
                "include_subsections": bool(
                    row.get("include_subsections")
                ),
                "expand_family": expand_family,
                "request_key": request_key,
                "normalized_variants": [
                    normalize_tokens(variant)
                    for variant in identity.get("variants", [])
                ],
                # Preserve separate Excel line items through the final
                # response even when they resolve to one catalog record.
                "source_request_identity": (
                    (
                        str(
                            row.get("source_file")
                            or row.get("source_sheet")
                            or ""
                        ),
                        row.get("source_row"),
                        normalize_tokens(displaystdno),
                    )
                    if (
                        row.get("source_file")
                        or row.get("source_sheet")
                    )
                    and row.get("source_row") is not None
                    else None
                ),
            }
        )

    return prepared_rows
