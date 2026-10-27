import re

from sqlalchemy import and_, bindparam, or_, select, text

from app.repositories.identity_lookup import fetch_long_core_candidates
from app.utils.db_retry import run_with_retry

from app.models.standard_master import StandardMaster
from app.models.standard_status import StandardStatus
from app.models.standard_price import StandardPrice
from app.models.currency import Currency
from app.models.standard_classification import StandardClassification
from app.models.sdo_classification import SDOClassification
from app.models.sdo import SDO
from app.utils.standard_identity import (
    identity_core_appears,
    identity_discovery_terms,
    normalize_identity_core,
    parse_identity,
    extract_international_references,
)


class EnrichmentRepository:

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _master_searchable_filter():
        """Include historical BIS catalog rows; status_id governs visibility."""
        return or_(
            StandardMaster.status == 1,
            StandardMaster.sdo_id.in_(
                select(SDO.id).where(
                    SDO.sdo_title == "BIS"
                )
            ),
        )

    # ==========================================
    # SINGLE MASTER STANDARD
    # ==========================================

    def get_master_standard(self, standard_id):
        return (
            self.db.query(StandardMaster)
            .filter(
                StandardMaster.Standard_id == standard_id
            )
            .first()
        )

    # ==========================================
    # MASTER SDO RESOLUTION - BULK
    # ==========================================

    def find_sdo_ids_by_prefixes(self, prefixes):
        if not prefixes:
            return []

        filters = []

        for prefix in prefixes:
            prefix = str(prefix or "").strip()

            if not prefix:
                continue

            filters.append(
                StandardMaster.standardno.ilike(
                    f"{prefix} %"
                )
            )

        if not filters:
            return []

        return (
            self.db.query(
                StandardMaster.standardno,
                StandardMaster.sdo_id
            )
            .filter(
                self._master_searchable_filter(),
                or_(*filters)
            )
            .all()
        )

    # ==========================================
    # MASTER STANDARD SEARCH - BULK
    # ==========================================

    def search_master_by_numbers(self, standard_numbers):
        if not standard_numbers:
            return []

        filters = [
            StandardMaster.standardno.in_(standard_numbers),
            StandardMaster.display_stdNo.in_(standard_numbers)
        ]

        return (
            self.db.query(StandardMaster)
            .filter(
                    self._master_searchable_filter(),
                or_(*filters)
            )
            .all()
        )

    def search_master_candidates_across_sdos(self, core):
        if not core:
            return []

        pattern = f"%{core}%"
        return (
            self.db.query(StandardMaster, SDO.sdo_title)
            .join(SDO, SDO.id == StandardMaster.sdo_id)
            .filter(
                StandardMaster.status == 1,
                SDO.status == 1,
                or_(
                    StandardMaster.standardno.ilike(pattern),
                    StandardMaster.display_stdNo.ilike(pattern),
                ),
            )
            .limit(501)
            .all()
        )

    def get_latest_tema_edition(self, sdo_id):
        """Return the newest visible TEMA numbered edition in the catalogue."""
        if not sdo_id:
            return None

        candidates = (
            self.db.query(StandardMaster)
            .join(SDO, SDO.id == StandardMaster.sdo_id)
            .join(StandardStatus, StandardStatus.id == StandardMaster.status_id)
            .filter(
                StandardMaster.sdo_id == sdo_id,
                SDO.sdo_title == "TEMA",
                SDO.status == 1,
                StandardMaster.status == 1,
                StandardMaster.display_stdNo.ilike("TEMA % Edition %"),
                StandardStatus.cart_show == 1,
            )
            .order_by(StandardMaster.standardyear.desc(), StandardMaster.id.desc())
            .all()
        )
        for candidate in candidates:
            designation = str(candidate.display_stdNo or "").strip()
            if re.match(
                r"(?i)^TEMA\s+\w+\s+Edition\s*:\s*(?:19|20)\d{2}\s*$",
                designation,
            ):
                return candidate
        return None

    # ==========================================
    # MASTER SEARCH BY SDO + DISPLAY VARIANTS
    # ==========================================

    def search_master_by_sdo_and_display_variants(self, pairs):
        """
        Resolve exact master candidates using grouped
        SDO + display-number IN lookups.

        Uses bounded batches to avoid one query per pair.
        """

        if not pairs:
            return []

        grouped = {}

        for sdo_id, display_number in pairs:

            if not sdo_id or not display_number:
                continue

            value = str(display_number).strip()

            if not value:
                continue

            grouped.setdefault(
                int(sdo_id),
                set()
            ).add(value)

        if not grouped:
            return []

        results = []
        seen = set()

        chunk_size = 400

        for sdo_id, display_numbers in grouped.items():

            values = list(display_numbers)

            for start in range(
                0,
                len(values),
                chunk_size
            ):

                batch = values[
                    start:start + chunk_size
                ]

                rows = run_with_retry(
                    self.db,
                    lambda sdo_id=sdo_id, batch=batch:
                        self.db.query(StandardMaster)
                        .filter(
                            self._master_searchable_filter(),
                            StandardMaster.sdo_id == sdo_id,
                            StandardMaster.display_stdNo.in_(batch),
                        ),
                )

                for row in rows:

                    if row.id in seen:
                        continue

                    seen.add(row.id)
                    results.append(row)

        return results

    # ==========================================
    # MASTER SEARCH BY SDO + STANDARD NUMBERS
    # ==========================================

    def search_master_by_sdo_and_standard_numbers(self, pairs):
        """Exact standardno IN lookups grouped by SDO."""

        if not pairs:
            return []

        grouped = {}

        for sdo_id, standard_number in pairs:

            if not sdo_id or not standard_number:
                continue

            value = str(standard_number).strip()

            if not value:
                continue

            grouped.setdefault(
                int(sdo_id),
                set()
            ).add(value)

        if not grouped:
            return []

        results = []
        seen = set()

        chunk_size = 400

        for sdo_id, standard_numbers in grouped.items():

            values = list(standard_numbers)

            for start in range(
                0,
                len(values),
                chunk_size
            ):

                batch = values[
                    start:start + chunk_size
                ]

                rows = run_with_retry(
                    self.db,
                    lambda sdo_id=sdo_id, batch=batch:
                        self.db.query(StandardMaster)
                        .filter(
                            self._master_searchable_filter(),
                            StandardMaster.sdo_id == sdo_id,
                            StandardMaster.standardno.in_(batch),
                        ),
                )

                for row in rows:

                    if row.id in seen:
                        continue

                    seen.add(row.id)
                    results.append(row)

        return results

    # ==========================================
    # MASTER SEARCH BY SDO + IDENTITY HINTS
    # ==========================================

    def search_master_by_sdo_and_identity_hints(self, hints):
        """
        Find master candidates using designation-neutral
        identity hints.

        Long cores use an index prefix plus a fulltext lookup.
        Short cores keep selective prefix-bound patterns.
        Python ``identity_core_appears`` is the accuracy gate.

        Final year / qualifier validation remains in
        DocumentSearchService.
        """

        if not hints:
            return []

        # {
        #   sdo_id: {
        #     "containment": {(core, year): pattern},
        #     "bound": {(core, year): {patterns}},
        #   }
        # }
        grouped = {}

        for sdo_id, sdo_prefix, core_token, year in hints:

            if (
                not sdo_id
                or not sdo_prefix
                or not core_token
            ):
                continue

            core, containment, bound = identity_discovery_terms(
                sdo_prefix,
                core_token,
            )

            if not core:
                continue

            bucket = grouped.setdefault(
                int(sdo_id),
                {"containment": {}, "bound": {}, "prefixes": set()},
            )
            bucket["prefixes"].add(sdo_prefix)
            key = (core, year)

            if containment:
                bucket["containment"][key] = containment
            elif bound:
                bucket["bound"].setdefault(key, set()).update(bound)

        if not grouped:
            return []

        results = []
        seen = set()
        bound_chunk = 5

        for sdo_id, bucket in grouped.items():
            cores_in_batch = list(
                dict.fromkeys(core for (core, _year) in bucket["containment"])
            )
            years = {year for (_core, year) in bucket["containment"]}
            extra_filters = [self._master_searchable_filter()]
            if len(years) == 1:
                shared_year = next(iter(years))
                if shared_year is not None:
                    extra_filters.append(
                        StandardMaster.standardyear == shared_year
                    )
            rows = fetch_long_core_candidates(
                self.db,
                model=StandardMaster,
                sdo_id=sdo_id,
                cores=cores_in_batch,
                sdo_prefixes=bucket["prefixes"],
                text_columns=(
                    StandardMaster.display_stdNo,
                    StandardMaster.standardno,
                ),
                fulltext_column=StandardMaster.display_stdNo,
                extra_filters=tuple(extra_filters),
            )

            for row in rows:
                if row.id in seen:
                    continue

                display_value = str(
                    row.display_stdNo or ""
                ).strip()
                standard_value = str(
                    row.standardno or ""
                ).strip()

                if not display_value and not standard_value:
                    continue

                if not any(
                    identity_core_appears(display_value, core)
                    or identity_core_appears(
                        standard_value,
                        core,
                    )
                    for core in cores_in_batch
                ):
                    continue

                seen.add(row.id)
                results.append(row)

            bound_items = list(bucket["bound"].items())
            for start in range(0, len(bound_items), bound_chunk):
                batch = bound_items[start:start + bound_chunk]
                filters = []
                cores_in_batch = []
                years = {year for (_core, year), _pats in batch}

                for (core, _year), pattern_set in batch:
                    cores_in_batch.append(core)
                    for pattern in pattern_set:
                        filters.append(
                            StandardMaster.display_stdNo.like(
                                pattern
                            )
                        )
                        filters.append(
                            StandardMaster.standardno.like(
                                pattern
                            )
                        )

                if not filters:
                    continue

                query_filters = [
                    self._master_searchable_filter(),
                    StandardMaster.sdo_id == sdo_id,
                    or_(*filters),
                ]
                if len(years) == 1:
                    shared_year = next(iter(years))
                    if shared_year is not None:
                        query_filters.insert(
                            2,
                            StandardMaster.standardyear == shared_year,
                        )

                rows = run_with_retry(
                    self.db,
                    lambda query_filters=query_filters: (
                        self.db.query(StandardMaster)
                        .filter(*query_filters)
                    ),
                )

                for row in rows:
                    if row.id in seen:
                        continue

                    display_value = str(
                        row.display_stdNo or ""
                    ).strip()
                    standard_value = str(
                        row.standardno or ""
                    ).strip()

                    if not display_value and not standard_value:
                        continue

                    if not any(
                        identity_core_appears(display_value, core)
                        or identity_core_appears(
                            standard_value,
                            core,
                        )
                        for core in cores_in_batch
                    ):
                        continue

                    seen.add(row.id)
                    results.append(row)

        return results

    # ==========================================
    # SINGLE MASTER SEARCH
    # ==========================================

    def search_master_by_sdo_and_standard(
        self,
        sdo_id,
        standard_number
    ):
        if not sdo_id or not standard_number:
            return []

        return (
            self.db.query(StandardMaster)
            .filter(
                StandardMaster.sdo_id == sdo_id,
                StandardMaster.standardno == standard_number,
                StandardMaster.status == 1
            )
            .all()
        )

    # ==========================================
    # MASTER DISPLAY SEARCH
    # ==========================================

    def search_master_by_sdo_and_display(
        self,
        sdo_id,
        display_number
    ):
        if not sdo_id or not display_number:
            return []

        return (
            self.db.query(StandardMaster)
            .filter(
                StandardMaster.sdo_id == sdo_id,
                StandardMaster.display_stdNo == display_number,
                StandardMaster.status == 1
            )
            .all()
        )

    # ==========================================
    # PRICES
    # ==========================================

    def get_prices(self, master_id):
        return (
            self.db.query(StandardPrice)
            .filter(
                StandardPrice.std_id == master_id,
                StandardPrice.status == 1,
                StandardPrice.formate_id.in_((1, 2))
            )
            .order_by(
                StandardPrice.formate_id,
                StandardPrice.id
            )
            .all()
        )

    # ==========================================
    # CLASSIFICATIONS
    # ==========================================

    def get_classifications(self, master_id):
        return (
            self.db.query(
                StandardClassification,
                SDOClassification
            )
            .join(
                SDOClassification,
                StandardClassification.classfication_id
                == SDOClassification.id
            )
            .filter(
                StandardClassification.standard_id == master_id,
                StandardClassification.status == 1,
                SDOClassification.status == 1
            )
            .all()
        )

    # ==========================================
    # BULK MASTER STANDARDS
    # ==========================================

    def get_master_standards(self, standard_ids):
        if not standard_ids:
            return []

        return run_with_retry(
            self.db,
            lambda:
                self.db.query(StandardMaster)
                .filter(
                    StandardMaster.Standard_id.in_(standard_ids)
                ),
        )

    def get_bis_master_aliases(self, master_ids):
        """Load BIS IS/BIS aliases for the same base designation and edition."""
        if not master_ids:
            return []
        matched = run_with_retry(
            self.db,
            lambda: self.db.query(
                StandardMaster.id,
                StandardMaster.sdo_id,
                StandardMaster.standardno,
                StandardMaster.display_stdNo,
                StandardMaster.standardyear,
            ).filter(StandardMaster.id.in_(master_ids)),
        )
        prefixes = set()
        for row in matched:
            for value in (row.standardno, row.display_stdNo):
                text = str(value or "").strip()
                match = re.search(
                    r"(?i)(?:IS|BIS)\s*([0-9]+)",
                    text,
                )
                if match:
                    prefixes.add(match.group(1))
        if not prefixes:
            return []
        aliases = run_with_retry(
            self.db,
            lambda: self.db.query(StandardMaster)
            .join(SDO, SDO.id == StandardMaster.sdo_id)
            .filter(
                SDO.sdo_title == "BIS",
                or_(
                    *[
                        StandardMaster.standardno.ilike(f"%{prefix}%")
                        for prefix in prefixes
                    ]
                ),
            ),
        )
        return [
            alias
            for alias in aliases
            if any(
                re.search(
                    rf"(?i)(?:IS|BIS)\s*{re.escape(prefix)}(?!\d)",
                    f"{alias.standardno or ''} {alias.display_stdNo or ''}",
                )
                for prefix in prefixes
            )
        ]

    def get_international_equivalent_price_aliases(
        self,
        master_ids,
        extra_designations=None,
    ):
        """Fetch catalogue rows for an edition named by a BIS adoption.

        The named publisher can be any catalogue publisher. The caller checks
        the parsed identity and edition year before borrowing a price.
        """
        if not master_ids:
            return []

        source_rows = run_with_retry(
            self.db,
            lambda: self.db.query(
                StandardMaster.standardno,
                StandardMaster.display_stdNo,
            )
            .join(SDO, SDO.id == StandardMaster.sdo_id)
            .filter(
                StandardMaster.id.in_(master_ids),
                SDO.sdo_title == "BIS",
            ),
        )
        references = {}
        reference_texts = [
            *(value for row in source_rows for value in (
                row.display_stdNo,
                row.standardno,
            )),
            *(extra_designations or []),
        ]
        for value in reference_texts:
            for reference in extract_international_references(value):
                references.setdefault(
                    reference["identity"],
                    reference,
                )
        if not references:
            return []

        requested_sdos = {
            reference["sdo_name"]
            for reference in references.values()
        }
        sdo_rows = run_with_retry(
            self.db,
            lambda: self.db.query(SDO.id, SDO.sdo_title)
            .filter(SDO.sdo_title.in_(requested_sdos)),
        )
        sdo_ids_by_name = {}
        for row in sdo_rows:
            sdo_ids_by_name.setdefault(
                str(row.sdo_title or "").strip().upper(),
                set(),
            ).add(row.id)

        filters = []
        for reference in references.values():
            sdo_ids = sdo_ids_by_name.get(reference["sdo_name"], set())
            if not sdo_ids:
                continue
            identity = parse_identity(
                reference["sdo_name"],
                reference["designation"],
            )
            core = str(identity.get("core") or "").strip()
            parts = re.findall(r"[A-Z]+|\d+", core, re.IGNORECASE)
            patterns = {f"%{core}%"} if core else set()
            if len(parts) > 1:
                patterns.add("%" + "%".join(parts) + "%")
            if not patterns:
                continue
            filters.append(
                and_(
                    StandardMaster.sdo_id.in_(sdo_ids),
                    or_(
                        *(
                            field.ilike(pattern)
                            for field in (
                                StandardMaster.standardno,
                                StandardMaster.display_stdNo,
                            )
                            for pattern in patterns
                        )
                    ),
                )
            )

        if not filters:
            return []

        aliases_by_id = {}
        for offset in range(0, len(filters), 200):
            batch = filters[offset:offset + 200]
            aliases = run_with_retry(
                self.db,
                lambda batch=batch: self.db.query(StandardMaster)
                .filter(or_(*batch)),
            )
            aliases_by_id.update((alias.id, alias) for alias in aliases)
        return list(aliases_by_id.values())

    def get_api_master_price_aliases(self, master_ids):
        """Load API catalog aliases for the exact standard number and edition."""
        if not master_ids:
            return []

        matched = run_with_retry(
            self.db,
            lambda: self.db.query(
                StandardMaster.sdo_id,
                StandardMaster.standardno,
                StandardMaster.standardyear,
            )
            .join(SDO, SDO.id == StandardMaster.sdo_id)
            .filter(
                StandardMaster.id.in_(master_ids),
                SDO.sdo_title == "API",
            ),
        )
        identities = {
            (row.sdo_id, row.standardno, row.standardyear)
            for row in matched
            if row.standardno and row.standardyear is not None
        }
        if not identities:
            return []

        aliases_by_id = {}
        identity_list = list(identities)
        for offset in range(0, len(identity_list), 200):
            batch = identity_list[offset:offset + 200]
            filters = [
                and_(
                    StandardMaster.sdo_id == sdo_id,
                    StandardMaster.standardno == standardno,
                    StandardMaster.standardyear == standardyear,
                )
                for sdo_id, standardno, standardyear in batch
            ]
            aliases = run_with_retry(
                self.db,
                lambda filters=filters: self.db.query(StandardMaster)
                .filter(or_(*filters)),
            )
            aliases_by_id.update(
                (alias.id, alias)
                for alias in aliases
            )

        return list(aliases_by_id.values())

    def get_edition_price_aliases(self, master_ids):
        """Load same-SDO edition rows, including consolidated AMD records.

        Some catalogues attach a price to a consolidated amendment record,
        while search resolves the request to the base-edition record (or the
        reverse). Fetch likely same-SDO designation siblings by normalized
        core number. Enrichment performs the stricter core/year check before
        borrowing a price, so this lookup can safely include multiple editions.
        """
        master_ids = {value for value in master_ids or [] if value is not None}
        if not master_ids:
            return []

        matched = run_with_retry(
            self.db,
            lambda: self.db.query(
                StandardMaster.id,
                StandardMaster.sdo_id,
                StandardMaster.standardno,
                StandardMaster.display_stdNo,
            ).filter(StandardMaster.id.in_(master_ids)),
        )
        if not matched:
            return []

        sdo_titles = self.get_sdo_titles(
            {row.sdo_id for row in matched if row.sdo_id is not None}
        )
        aliases_by_id = {}
        grouped = {}
        for row in matched:
            if row.sdo_id is None:
                continue
            sdo_name = str(sdo_titles.get(row.sdo_id) or "").strip()
            designation = row.display_stdNo or row.standardno or ""
            identity = parse_identity(sdo_name, designation)
            core = str(
                identity.get("core_number") or identity.get("core") or ""
            ).strip()
            if not core:
                continue
            bucket = grouped.setdefault(
                row.sdo_id,
                {"prefix": sdo_name, "cores": []},
            )
            bucket["cores"].append(core)

        for sdo_id, bucket in grouped.items():
            rows = fetch_long_core_candidates(
                self.db,
                model=StandardMaster,
                sdo_id=sdo_id,
                cores=bucket["cores"],
                sdo_prefixes={bucket["prefix"]} if bucket["prefix"] else set(),
                text_columns=(
                    StandardMaster.display_stdNo,
                    StandardMaster.standardno,
                ),
                fulltext_column=StandardMaster.display_stdNo,
            )
            for alias in rows:
                if any(
                    identity_core_appears(value, core)
                    for value in (alias.display_stdNo, alias.standardno)
                    for core in bucket["cores"]
                ):
                    aliases_by_id[alias.id] = alias
        return list(aliases_by_id.values())

    def get_standard_status_map(self, status_ids):
        """Load display and cart visibility for detailed standard statuses."""
        status_ids = {
            int(status_id)
            for status_id in status_ids or []
            if status_id is not None
        }
        if not status_ids:
            return {}

        rows = run_with_retry(
            self.db,
            lambda: self.db.query(
                StandardStatus.id,
                StandardStatus.status,
                StandardStatus.std_show,
                StandardStatus.cart_show,
            ).filter(StandardStatus.id.in_(status_ids)),
        )
        return {
            row.id: {
                "name": row.status,
                "std_show": row.std_show,
                "cart_show": row.cart_show,
            }
            for row in rows
        }

    def get_currency_info_for_sdos(self, sdo_ids):
        if not sdo_ids:
            return {}

        rows = run_with_retry(
            self.db,
            lambda:
                self.db.query(
                    SDO.id,
                    Currency.currency_code,
                    Currency.currency_symbol,
                )
                .join(
                    Currency,
                    SDO.currency_id == Currency.id,
                )
                .filter(SDO.id.in_(sdo_ids)),
        )

        return {
            row.id: {
                "code": row.currency_code,
                "symbol": row.currency_symbol,
            }
            for row in rows
        }

    def get_sdo_metadata_for_sdos(self, sdo_ids):
        """Fetch SDO titles and currency details in one database round trip."""
        if not sdo_ids:
            return {"titles": {}, "currencies": {}}

        rows = run_with_retry(
            self.db,
            lambda: self.db.query(
                SDO.id,
                SDO.sdo_title,
                Currency.currency_code,
                Currency.currency_symbol,
            )
            .outerjoin(
                Currency,
                SDO.currency_id == Currency.id,
            )
            .filter(SDO.id.in_(sdo_ids)),
        )

        return {
            "titles": {row.id: row.sdo_title for row in rows},
            "currencies": {
                row.id: {
                    "code": row.currency_code,
                    "symbol": row.currency_symbol,
                }
                for row in rows
            },
        }

    def get_sdo_titles(self, sdo_ids):
        """Return canonical SDO names for currency-specific export rules."""
        if not sdo_ids:
            return {}

        rows = run_with_retry(
            self.db,
            lambda: self.db.query(SDO.id, SDO.sdo_title)
            .filter(SDO.id.in_(sdo_ids)),
        )
        return {row.id: row.sdo_title for row in rows}

    # ==========================================
    # BULK PRICES
    # ==========================================

    def get_prices_for_standards(self, master_ids, additional_master_ids=None):
        master_ids = set(master_ids or []) | set(additional_master_ids or [])
        if not master_ids:
            return []

        return run_with_retry(
            self.db,
            lambda:
                self.db.query(StandardPrice)
                .filter(
                    StandardPrice.std_id.in_(master_ids),
                    StandardPrice.status == 1,
                    StandardPrice.formate_id.in_((1, 2))
                )
                .order_by(
                    # BIS format 1 can be a placeholder zero while format 2
                    # carries the published India price.
                    StandardPrice.formate_id.desc(),
                    StandardPrice.id
                ),
        )

    # ==========================================
    # BULK CLASSIFICATIONS
    # ==========================================

    def get_classifications_for_standards(self, master_ids):
        if not master_ids:
            return []

        assignments = run_with_retry(
            self.db,
            lambda:
                self.db.query(
                    StandardClassification,
                    SDOClassification
                )
                .join(
                    SDOClassification,
                    StandardClassification.classfication_id
                    == SDOClassification.id
                )
                .filter(
                    StandardClassification.standard_id.in_(master_ids),
                    StandardClassification.status == 1,
                    SDOClassification.status == 1
                ),
        )
        if not assignments:
            return []

        # Classification tables often store ISO TC and SC as a parent/child
        # hierarchy (e.g. TC 67 -> SC 2). Return the full committee path with
        # each assignment so consumers never have to infer it from a bare SC.
        classification_ids = {
            classification.id
            for _assignment, classification in assignments
        }
        nodes = {
            classification.id: classification
            for _assignment, classification in assignments
        }
        owner_ids = {
            classification.sdo_id
            for _assignment, classification in assignments
            if classification.sdo_id
        }
        frontier = {
            classification.parent_id
            for _assignment, classification in assignments
            if classification.parent_id
        } - classification_ids
        while frontier:
            parents = run_with_retry(
                self.db,
                lambda frontier=frontier: self.db.query(SDOClassification)
                .filter(
                    SDOClassification.id.in_(frontier),
                    SDOClassification.status == 1,
                ),
            )
            if not parents:
                break
            for parent in parents:
                nodes[parent.id] = parent
                if parent.sdo_id:
                    owner_ids.add(parent.sdo_id)
            loaded_ids = {parent.id for parent in parents}
            frontier = {
                parent.parent_id
                for parent in parents
                if parent.parent_id
            } - set(nodes)

        owners = {}
        if owner_ids:
            owner_rows = run_with_retry(
                self.db,
                lambda: self.db.query(SDO.id, SDO.sdo_title)
                .filter(SDO.id.in_(owner_ids)),
            )
            owners = {owner_id: title for owner_id, title in owner_rows}

        enriched = []
        for assignment, classification in assignments:
            chain = []
            current = classification
            seen = set()
            while current and current.id not in seen:
                seen.add(current.id)
                code = str(current.classification_code or "").strip()
                if code:
                    chain.append(code)
                current = nodes.get(current.parent_id)
            chain.reverse()
            enriched_classification = {
                "id": classification.id,
                "code": "/".join(chain) if chain else classification.classification_code,
                "description": classification.description,
                "owner_sdo": owners.get(classification.sdo_id),
            }
            enriched.append((assignment, enriched_classification))
        return enriched

    def get_bsi_modules_for_standards(self, master_ids):
        """Resolve BSI module codes from each standard's most specific ICS."""
        if not master_ids:
            return {}

        result = {}
        statement = text(
            """
            SELECT si.standard_id, TRIM(si.org_ics_id) AS standard_ics,
                   TRIM(bm.module) AS module, TRIM(bm.ics_code) AS module_ics
            FROM bsbe_std_ics AS si
            JOIN standards AS st ON st.id = si.standard_id
            JOIN sdos AS d ON d.id = st.sdo_id AND d.sdo_title = 'BSI'
            JOIN bsi_module AS bm
              ON TRIM(si.org_ics_id) = TRIM(bm.ics_code)
              OR TRIM(si.org_ics_id) LIKE CONCAT(TRIM(bm.ics_code), '.%')
            WHERE si.standard_id IN :standard_ids
              AND si.status = 1
              AND si.org_ics_id IS NOT NULL
              AND TRIM(si.org_ics_id) <> ''
            """
        ).bindparams(bindparam("standard_ids", expanding=True))

        for start in range(0, len(master_ids), 400):
            batch_ids = list(master_ids[start:start + 400])
            rows = self.db.execute(
                statement,
                {"standard_ids": batch_ids},
            ).fetchall()
            best_by_ics = {}
            for standard_id, standard_ics, module, module_ics in rows:
                if not module or not standard_ics or not module_ics:
                    continue
                current = best_by_ics.setdefault(
                    (standard_id, standard_ics),
                    {"specificity": -1, "modules": set()},
                )
                specificity = len(module_ics)
                if specificity > current["specificity"]:
                    current["specificity"] = specificity
                    current["modules"] = {module}
                elif specificity == current["specificity"]:
                    current["modules"].add(module)

            for (standard_id, _ics), values in best_by_ics.items():
                result.setdefault(standard_id, set()).update(values["modules"])

        return {
            standard_id: sorted(modules)
            for standard_id, modules in result.items()
        }

    def get_classifications_from_exact_catalog_duplicates(self, standards):
        """Find TC metadata on exact duplicate catalogue records.

        Some catalogues publish duplicate records or editions without a TC
        link, even though another copy has one. Prefer same-SDO records with
        the same standard number across editions. If none exist, allow an
        exact content duplicate across SDO entries. In either case, every
        classified peer must agree on the same TC set.
        """
        standards = [
            standard
            for standard in standards or []
            if standard.standardno
            and standard.standardyear is not None
            and standard.title
        ]
        if not standards:
            return {}

        sdo_titles = {
            title_id: title
            for title_id, title in run_with_retry(
                self.db,
                lambda: self.db.query(SDO.id, SDO.sdo_title).filter(
                    SDO.id.in_({standard.sdo_id for standard in standards})
                ),
            )
        }

        def identity(standard):
            title = " ".join(str(standard.title or "").split()).casefold()
            sdo_title = str(sdo_titles.get(standard.sdo_id) or "")
            if "NACE" in sdo_title.upper():
                sdo_title = "NACE"
            parsed = parse_identity(
                sdo_title,
                standard.display_stdNo or standard.standardno or "",
            )
            core = normalize_identity_core(
                parsed.get("core_number") or parsed.get("core") or ""
            )
            return (
                standard.sdo_id,
                parsed.get("designation"),
                core,
                parsed.get("qualifier"),
                int(standard.standardyear),
                title,
            )

        target_by_identity = {}
        for standard in standards:
            target_by_identity.setdefault(identity(standard), []).append(standard)

        numbers = sorted({
            str(standard.standardno).strip()
            for standard in standards
            if str(standard.standardno or "").strip()
        })
        core_filters = []
        for standard in standards:
            sdo_title = str(sdo_titles.get(standard.sdo_id) or "")
            if "NACE" in sdo_title.upper():
                sdo_title = "NACE"
            parsed = parse_identity(
                sdo_title,
                standard.display_stdNo or standard.standardno or "",
            )
            core = normalize_identity_core(
                parsed.get("core_number") or parsed.get("core") or ""
            )
            if not core or standard.standardyear is None:
                continue
            pattern = f"%{core}%"
            core_filters.append(
                and_(
                    StandardMaster.sdo_id == standard.sdo_id,
                    StandardMaster.standardyear == standard.standardyear,
                    or_(
                        StandardMaster.standardno.ilike(pattern),
                        StandardMaster.display_stdNo.ilike(pattern),
                    ),
                )
            )
        peer_rows = []
        for offset in range(0, len(numbers), 500):
            batch = numbers[offset:offset + 500]
            peer_rows.extend(
                run_with_retry(
                    self.db,
                    lambda batch=batch:
                        self.db.query(
                            StandardMaster,
                            StandardClassification,
                            SDOClassification,
                        )
                        .join(
                            StandardClassification,
                            StandardClassification.standard_id == StandardMaster.id,
                        )
                        .join(
                            SDOClassification,
                            StandardClassification.classfication_id == SDOClassification.id,
                        )
                        .filter(
                            StandardMaster.standardno.in_(batch),
                            StandardMaster.status == 1,
                            StandardClassification.status == 1,
                            SDOClassification.status == 1,
                        ),
                )
            )
        if core_filters:
            peer_rows.extend(
                run_with_retry(
                    self.db,
                    lambda: self.db.query(
                        StandardMaster,
                        StandardClassification,
                        SDOClassification,
                    )
                    .join(
                        StandardClassification,
                        StandardClassification.standard_id == StandardMaster.id,
                    )
                    .join(
                        SDOClassification,
                        StandardClassification.classfication_id == SDOClassification.id,
                    )
                    .filter(
                        or_(*core_filters),
                        StandardMaster.status == 1,
                        StandardClassification.status == 1,
                        SDOClassification.status == 1,
                    ),
                )
            )

        assignments_by_identity_and_record = {}
        assignments_by_family_and_record = {}
        assignment_metadata = {}
        for master, standard_classification, classification in peer_rows:
            key = identity(master)
            if key not in target_by_identity:
                continue
            assignment_key = (
                str(classification.classification_code or "").strip().casefold(),
                " ".join(str(classification.description or "").split()).casefold(),
            )
            assignments_by_identity_and_record.setdefault(key, {}).setdefault(
                master.id, set()
            ).add(assignment_key)
            family = key[:4]
            assignments_by_family_and_record.setdefault(
                family, {}
            ).setdefault(master.id, set()).add(assignment_key)
            metadata = {
                "id": classification.id,
                "code": classification.classification_code,
                "description": classification.description,
                "owner_sdo_id": classification.sdo_id,
            }
            assignment_metadata.setdefault(
                (("identity", key), assignment_key), metadata
            )
            assignment_metadata.setdefault(
                (("family", family), assignment_key), metadata
            )

        def agreed_classifications(record_sets, metadata_key):
            distinct_sets = {frozenset(items) for items in record_sets}
            if len(distinct_sets) != 1:
                return None
            agreed_assignments = next(iter(distinct_sets))
            return [
                assignment_metadata[(metadata_key, assignment_key)]
                for assignment_key in sorted(
                    agreed_assignments,
                    key=lambda item: item[0],
                )
            ]

        result = {}
        for standard in standards:
            family = identity(standard)[:4]
            family_records = assignments_by_family_and_record.get(family, {})
            classifications = None
            if family_records:
                classifications = agreed_classifications(
                    family_records.values(),
                    ("family", family),
                )
            else:
                key = identity(standard)
                duplicate_records = assignments_by_identity_and_record.get(
                    key, {}
                )
                if duplicate_records:
                    classifications = agreed_classifications(
                        duplicate_records.values(),
                        ("identity", key),
                    )
            if classifications:
                result[standard.id] = classifications

        return result
