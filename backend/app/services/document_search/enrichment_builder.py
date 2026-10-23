"""Enrichment-map construction for document search results."""

import re

from app.utils.standard_identity import (
    extract_international_references,
    parse_identity,
    standard_number_year,
)


def build_enrichment_map(
    standards,
    enrichment_repository,
    price_identity_designation,
    filter_api_tc_classifications,
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
        enrichment_repository
        .get_currency_info_for_sdos(sdo_ids)
    )
    sdo_title_map = enrichment_repository.get_sdo_titles(sdo_ids)

    masters = (
        enrichment_repository
        .get_master_standards(
            standard_ids
        )
    )

    master_map = {
        master.Standard_id: master
        for master in masters
    }
    masters_by_id = {
        master.id: master
        for master in masters
    }
    edition_alias_lookup = getattr(
        enrichment_repository,
        "get_edition_price_aliases",
        None,
    )
    edition_price_aliases = (
        edition_alias_lookup(master_ids=[master.id for master in masters])
        if callable(edition_alias_lookup)
        else []
    )
    for alias in edition_price_aliases:
        masters_by_id.setdefault(alias.id, alias)
    bis_aliases = enrichment_repository.get_bis_master_aliases(
        master_ids=[master.id for master in masters]
    )
    for alias in bis_aliases:
        masters_by_id.setdefault(alias.id, alias)
    api_alias_lookup = getattr(
        enrichment_repository,
        "get_api_master_price_aliases",
        None,
    )
    api_price_aliases = (
        api_alias_lookup(master_ids=[master.id for master in masters])
        if callable(api_alias_lookup)
        else []
    )
    for alias in api_price_aliases:
        masters_by_id.setdefault(alias.id, alias)
    international_alias_lookup = getattr(
        enrichment_repository,
        "get_international_equivalent_price_aliases",
        None,
    )
    international_price_aliases = (
        international_alias_lookup(
            master_ids=[master.id for master in masters]
        )
        if callable(international_alias_lookup)
        else []
    )
    for alias in international_price_aliases:
        masters_by_id.setdefault(alias.id, alias)

    alias_sdo_ids = {
        master.sdo_id
        for master in masters_by_id.values()
        if master.sdo_id
    }
    currency_map.update(
        enrichment_repository.get_currency_info_for_sdos(alias_sdo_ids)
    )
    sdo_title_map.update(
        enrichment_repository.get_sdo_titles(alias_sdo_ids)
    )

    def price_identity(master):
        sdo_name = str(
            sdo_title_map.get(master.sdo_id) or ""
        ).strip()
        designation = price_identity_designation(
            master.display_stdNo or master.standardno or ""
        )
        identity = parse_identity(
            sdo_name,
            designation,
        )
        year = (
            identity.get("year")
            or master.standardyear
            or standard_number_year(master.display_stdNo or master.standardno or "")
        )
        return (
            master.sdo_id,
            identity.get("core_number"),
            identity.get("qualifier"),
            year,
        )

    masters_by_price_identity = {}
    for master in masters_by_id.values():
        masters_by_price_identity.setdefault(
            price_identity(master),
            [],
        ).append(master)

    master_ids = [
        master.id
        for master in masters
    ]

    # --------------------------------------------------------
    # Prices
    # --------------------------------------------------------

    prices = (
        enrichment_repository
        .get_prices_for_standards(
            master_ids,
            additional_master_ids=[
                alias.id
                for alias in (
                    *edition_price_aliases,
                    *bis_aliases,
                    *api_price_aliases,
                    *international_price_aliases,
                )
            ],
        )
    )

    prices_by_master = {}
    for price in prices:
        if price.non_member_price_rate is None:
            continue
        master = masters_by_id.get(price.std_id)
        if master is None:
            continue
        prices_by_master.setdefault(price.std_id, []).append(
            (price.formate_id, price.id, float(price.non_member_price_rate))
        )

    def preferred_price_format(entries, sdo_name):
        formats = {int(entry[0] or 0) for entry in entries}
        if str(sdo_name or "").strip().upper() == "IEEE" and 1 in formats:
            # IEEE format 1 is PDF and is the catalogue price shown in
            # results. Format 2 is PRINT, which can have a higher price.
            return 1
        if str(sdo_name or "").strip().upper() == "NEMA" and 1 in formats:
            # NEMA format 1 is the base catalogue price. Format 2 can be
            # a higher product-format price for the same standard.
            return 1
        return max(formats) if formats else None

    # First resolve each record's own price. If the record has several
    # rows, prefer a stated nonzero price; otherwise preserve its zero.
    direct_price_by_master = {}
    for master_id, entries in prices_by_master.items():
        master = masters_by_id.get(master_id)
        master_sdo = sdo_title_map.get(master.sdo_id) if master else None
        entries.sort(key=lambda item: (-int(item[0] or 0), item[1]))
        nonzero_entries = [entry for entry in entries if entry[2] != 0]
        if nonzero_entries:
            best_format = preferred_price_format(
                nonzero_entries,
                master_sdo,
            )
            best_format_prices = {
                entry[2]
                for entry in nonzero_entries
                if int(entry[0] or 0) == best_format
            }
            if len(best_format_prices) == 1:
                direct_price_by_master[master_id] = next(
                    iter(best_format_prices)
                )
        elif entries:
            # Preserve zero only for the exact master row that records it.
            direct_price_by_master[master_id] = entries[0][2]

    price_by_identity = {}
    for identity, matching_masters in masters_by_price_identity.items():
        known_entries = [
            entry
            for master in matching_masters
            for entry in prices_by_master.get(master.id, [])
            if entry[2] != 0
        ]
        if known_entries:
            # Catalog aliases may expose the same edition in multiple
            # product formats. Prefer the IEEE PDF price when present;
            # otherwise use the highest listed format. Borrow only when
            # that format gives one unambiguous non-member price.
            identity_sdo = sdo_title_map.get(
                matching_masters[0].sdo_id
            ) if matching_masters else None
            best_format = preferred_price_format(
                known_entries,
                identity_sdo,
            )
            best_format_prices = {
                entry[2]
                for entry in known_entries
                if int(entry[0] or 0) == best_format
            }
            if len(best_format_prices) == 1:
                price_by_identity[identity] = next(
                    iter(best_format_prices)
                )

    # Resolve explicit BIS adoption references against exact, available
    # ISO/IEC/IEEE catalogue editions. Unlike same-SDO aliases, these
    # identities include the referenced publisher and edition year.
    international_prices_by_identity = {}
    for master in international_price_aliases:
        if getattr(master, "DocumentAvailability", None) != 1:
            continue
        sdo_name = str(sdo_title_map.get(master.sdo_id) or "").strip()
        identity = parse_identity(
            sdo_name,
            price_identity_designation(
                master.display_stdNo or master.standardno or ""
            ),
        )
        year = (
            identity.get("year")
            or master.standardyear
            or standard_number_year(
                master.display_stdNo or master.standardno or ""
            )
        )
        key = (
            sdo_name.upper(),
            identity.get("core_number"),
            identity.get("qualifier"),
            year,
        )
        if not key[1] or not key[3]:
            continue
        known_entries = [
            entry
            for entry in prices_by_master.get(master.id, [])
            if entry[2] != 0
        ]
        if not known_entries:
            continue
        international_prices_by_identity.setdefault(key, []).extend(
            (master, entry)
            for entry in known_entries
        )

    resolved_international_prices = {}
    for identity, matching_entries in international_prices_by_identity.items():
        sdo_name = identity[0]
        best_format = preferred_price_format(
            [entry for _master, entry in matching_entries],
            sdo_name,
        )
        best_entries = [
            (master, entry)
            for master, entry in matching_entries
            if int(entry[0] or 0) == best_format
        ]
        distinct_prices = {entry[2] for _master, entry in best_entries}
        if len(distinct_prices) != 1:
            continue
        # Multiple catalogue rows for a language/format variant may be
        # used only when their SDO currency also agrees.
        source_currencies = {
            (currency_map.get(master.sdo_id) or {}).get("code")
            for master, _entry in best_entries
        }
        if len(source_currencies) != 1:
            continue
        resolved_international_prices[identity] = (
            next(iter(distinct_prices)),
            next(iter(source_currencies)),
            next(
                (
                    (currency_map.get(master.sdo_id) or {}).get("symbol")
                    for master, _entry in best_entries
                ),
                None,
            ),
        )

    international_price_by_standard = {}
    for master in masters:
        sdo_name = str(sdo_title_map.get(master.sdo_id) or "").strip()
        if sdo_name.upper() != "BIS":
            continue
        designation = " ".join(
            str(value or "")
            for value in (master.display_stdNo, master.standardno)
        )
        references = extract_international_references(designation)
        reference_prices = {
            resolved_international_prices[reference["identity"]]
            for reference in references
            if reference["identity"] in resolved_international_prices
        }
        # Only borrow when explicit references resolve unambiguously to
        # one available, priced database edition and currency.
        if len(reference_prices) == 1:
            international_price_by_standard[master.Standard_id] = next(
                iter(reference_prices)
            )

    price_map = {}
    for master in masters:
        identity = price_identity(master)
        sdo_name = str(
            sdo_title_map.get(master.sdo_id) or ""
        ).strip().upper()
        designation = str(
            " ".join(
                value
                for value in (
                    str(master.display_stdNo or "").strip(),
                    str(master.standardno or "").strip(),
                )
                if value
            )
        ).strip()
        has_international_equivalent = bool(
            re.search(r"(?i)\b(?:ISO|IEC|IEEE)\b", designation)
        )
        is_simple_is_edition = (
            sdo_name == "BIS"
            and re.match(r"^IS\b", designation, re.IGNORECASE)
            and not has_international_equivalent
        )
        exact_price = direct_price_by_master.get(master.id)
        international_price = international_price_by_standard.get(
            master.Standard_id
        )
        has_amendment_designation = bool(
            re.search(
                r"(?i)(?:\+|/|\s)\s*"
                r"(?:AMD\.?|AMEND(?:MENT)?\.?|AMENDMENT)\s*[-.:#]?\s*\d+",
                designation,
            )
        )
        if is_simple_is_edition:
            # Plain IS editions are free in the result. Do not let a
            # priced BIS/BOSS alias create a charge for them.
            value = 0
        elif sdo_name == "BIS" and exact_price not in (None, 0):
            # For paid BIS/IS adoptions, prefer the exact row's listed
            # amount; use aliases only when the exact edition has no paid
            # price recorded.
            value = exact_price
        elif sdo_name == "BIS" and international_price:
            value = international_price[0]
        elif (
            sdo_name != "BIS"
            and exact_price not in (None, 0)
        ):
            # For non-BIS SDOs, the matched catalogue record's own price
            # is authoritative. A duplicate edition/format alias can have
            # a different price and must not overwrite this exact value.
            value = exact_price
        elif (
            sdo_name != "BIS"
            and exact_price == 0
            and not has_amendment_designation
        ):
            # Preserve true zero-price records, but an amendment row can
            # carry a placeholder zero while its consolidated/base edition
            # has the actual catalogue price.
            value = 0
        elif identity in price_by_identity:
            value = price_by_identity[identity]
        else:
            # Conflicting aliases are not a safe source for an inferred
            # amount. Retain only the matched master row's own price.
            value = exact_price
        if value is not None:
            price_map[master.Standard_id] = value

    # --------------------------------------------------------
    # Classifications
    # --------------------------------------------------------

    classifications = (
        enrichment_repository
        .get_classifications_for_standards(
            master_ids
        )
    )

    classification_map = {}

    for (
        standard_classification,
        classification,
    ) in classifications:

        if isinstance(classification, dict):
            classification_id = classification.get("id")
            classification_code = classification.get("code")
            classification_description = classification.get("description")
            classification_owner_sdo = classification.get("owner_sdo")
            classification_owner_id = classification.get(
                "owner_sdo_id",
                classification.get("sdo_id"),
            )
        else:
            classification_id = classification.id
            classification_code = classification.classification_code
            classification_description = classification.description
            classification_owner_id = classification.sdo_id
            classification_owner_sdo = sdo_title_map.get(
                classification_owner_id
            )

        master = masters_by_id.get(
            standard_classification.standard_id
        )
        expected_owner_id = master.sdo_id if master else None
        assignment_owner_id = getattr(
            standard_classification,
            "sdo_id",
            None,
        )
        if (
            expected_owner_id
            and assignment_owner_id
            and str(expected_owner_id) != str(assignment_owner_id)
        ):
            continue
        if (
            expected_owner_id
            and classification_owner_id
            and str(expected_owner_id) != str(classification_owner_id)
        ):
            continue
        expected_owner_name = str(
            sdo_title_map.get(expected_owner_id) or ""
        ).strip().casefold()
        if (
            expected_owner_name
            and classification_owner_sdo
            and str(classification_owner_sdo).strip().casefold()
            != expected_owner_name
        ):
            continue

        if not classification_owner_sdo and expected_owner_name:
            classification_owner_sdo = sdo_title_map.get(expected_owner_id)

        classification_map.setdefault(
            standard_classification.standard_id,
            [],
        ).append(
            {
                "id": classification_id,
                "code": classification_code,
                "description": classification_description,
                "owner_sdo": classification_owner_sdo,
            }
        )

    # If the matched catalogue row has no TC link, recover it only from an
    # unambiguous exact duplicate or same-SDO edition family. The
    # repository returns a fallback only when all linked peers agree.
    missing_classification_masters = [
        master
        for master in masters
        if not classification_map.get(master.id)
    ]
    duplicate_classifications = (
        enrichment_repository
        .get_classifications_from_exact_catalog_duplicates(
            missing_classification_masters
        )
    )
    for master_id, values in duplicate_classifications.items():
        master = masters_by_id.get(master_id)
        expected_owner_id = master.sdo_id if master else None
        classification_map[master_id] = [
            value
            for value in values
            if isinstance(value, dict) and (
                not expected_owner_id
                or not value.get("owner_sdo_id")
                or str(value.get("owner_sdo_id"))
                == str(expected_owner_id)
            )
        ]
        for value in classification_map[master_id]:
            value.setdefault(
                "owner_sdo",
                sdo_title_map.get(
                    value.get("owner_sdo_id") or expected_owner_id
                ),
            )

    bsi_module_lookup = getattr(
        enrichment_repository,
        "get_bsi_modules_for_standards",
        None,
    )
    bsi_modules_by_standard = (
        bsi_module_lookup(master_ids)
        if callable(bsi_module_lookup)
        else {}
    )
    for master_id, modules in bsi_modules_by_standard.items():
        standard_classifications = classification_map.setdefault(
            master_id,
            [],
        )
        has_explicit_bsi_committee = any(
            str(item.get("owner_sdo") or "").strip().upper() == "BSI"
            and re.search(
                r"(?<![A-Z0-9])(?:GMB|GBM)\s*\d+[A-Z]?(?![A-Z0-9])",
                " ".join(
                    (
                        str(item.get("code") or ""),
                        str(item.get("description") or ""),
                    )
                ),
                re.IGNORECASE,
            )
            for item in standard_classifications
        )
        # ICS is a subject classification and can map to several BSI
        # modules. Use that inference only when the catalogue has no
        # explicit BSI committee for this standard.
        if has_explicit_bsi_committee:
            continue
        existing_codes = {
            str(item.get("code") or "").strip().upper()
            for item in standard_classifications
        }
        for module in modules:
            module_code = str(module or "").strip().upper()
            if not module_code or module_code in existing_codes:
                continue
            standard_classifications.append(
                {
                    "id": f"bsi-module-{module_code}",
                    "code": module_code,
                    "description": module_code,
                    "owner_sdo": "BSI",
                }
            )
            existing_codes.add(module_code)

    # --------------------------------------------------------
    # Final enrichment map
    # --------------------------------------------------------

    result = {}

    for standard in standards:
        if not standard.Standard_id:
            continue

        master = master_map.get(standard.Standard_id)
        currency = currency_map.get(standard.sdo_id, {})
        sdo_title = str(
            sdo_title_map.get(standard.sdo_id) or ""
        ).strip().casefold()
        if sdo_title == "bis":
            currency_code = "INR"
            currency_symbol = "₹"
        else:
            currency_code = currency.get("code")
            currency_symbol = currency.get("symbol")
        international_price = international_price_by_standard.get(
            standard.Standard_id
        )
        if (
            sdo_title == "bis"
            and international_price
            and price_map.get(standard.Standard_id)
            == international_price[0]
            and direct_price_by_master.get(master.id if master else None)
            in (None, 0)
        ):
            currency_code = international_price[1]
            currency_symbol = international_price[2]
        year = (
            master.standardyear
            if master
            else standard_number_year(standard.standardno)
        )
        classifications_for_standard = (
            classification_map.get(master.id, []) if master else []
        )
        if master:
            classifications_for_standard = (
                filter_api_tc_classifications(
                    master,
                    classifications_for_standard,
                )
            )
        if sdo_title == "din":
            # DIN's ICS codes are subject classifications, not TCs.
            classifications_for_standard = []
        elif sdo_title.startswith("asme"):
            # ASME's classifications identify codes/volumes, not TCs.
            classifications_for_standard = []
        elif sdo_title == "aci":
            # ACI adds the generic MCP topic code alongside its specific
            # subject classification. Keep one specific ACI classification
            # so the generic tag is not presented as a second committee.
            specific_classifications = [
                item for item in classifications_for_standard
                if str(item.get("code") or "").strip().isdigit()
                and str(item.get("description") or "").strip()
                and str(item.get("description") or "")
                .strip()
                .casefold() != "mcp"
            ]
            specific_classifications.sort(
                key=lambda item: (
                    int(str(item.get("code") or "0").strip()),
                    int(item.get("id") or 0),
                )
            )
            classifications_for_standard = specific_classifications[:1]
        elif sdo_title == "ieee":
            # IEEE's numeric classification code is an internal
            # category identifier; the committee name is the useful
            # value for the TC column. Keep only the text before any
            # parenthetical alias or abbreviation.
            ieee_classifications = []
            for item in classifications_for_standard:
                committee_name = re.sub(
                    r"\s+",
                    " ",
                    str(item.get("description") or ""),
                ).strip()
                committee_name = committee_name.split("(", 1)[0].strip()
                if not committee_name:
                    continue
                ieee_classifications.append(
                    {
                        **item,
                        "code": committee_name,
                    }
                )
            classifications_for_standard = ieee_classifications

        result[
            standard.Standard_id
        ] = {
            "year": year,
            "currency": currency_code,
            "currency_symbol": currency_symbol,
            "price": price_map.get(master.Standard_id) if master else None,
            "document_available": bool(
                master and master.DocumentAvailability == 1
            ),
            "has_database_price": bool(
                master and master.id in prices_by_master
            ),
            "classifications": classifications_for_standard,
        }

    return result
