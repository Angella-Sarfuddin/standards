from sqlalchemy import or_

from app.utils.db_retry import run_with_retry

from app.models.standard_master import StandardMaster
from app.models.standard_price import StandardPrice
from app.models.currency import Currency
from app.models.standard_classification import StandardClassification
from app.models.sdo_classification import SDOClassification
from app.models.sdo import SDO
from app.utils.standard_identity import (
    identity_core_appears,
    identity_discovery_terms,
)


class EnrichmentRepository:

    def __init__(self, db):
        self.db = db

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
                StandardMaster.status == 1,
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
                StandardMaster.status == 1,
                or_(*filters)
            )
            .all()
        )

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
                            StandardMaster.status == 1,
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
                            StandardMaster.status == 1,
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

        Fast path: containment ``%{core}%`` scans batched per SDO.
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
                {"containment": {}, "bound": {}},
            )
            key = (core, year)

            if containment:
                bucket["containment"][key] = containment
            elif bound:
                bucket["bound"].setdefault(key, set()).update(bound)

        if not grouped:
            return []

        results = []
        seen = set()
        containment_chunk = 40
        bound_chunk = 5

        for sdo_id, bucket in grouped.items():
            containment_items = list(bucket["containment"].items())
            for start in range(
                0,
                len(containment_items),
                containment_chunk,
            ):
                batch = containment_items[
                    start:start + containment_chunk
                ]
                filters = []
                cores_in_batch = []
                years = {year for (_core, year), _pat in batch}

                for (core, _year), pattern in batch:
                    cores_in_batch.append(core)
                    contain = f"%{pattern}%"
                    filters.append(
                        StandardMaster.display_stdNo.like(contain)
                    )
                    filters.append(
                        StandardMaster.standardno.like(contain)
                    )

                if not filters:
                    continue

                query_filters = [
                    StandardMaster.status == 1,
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
                    StandardMaster.status == 1,
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
                StandardPrice.formate_id == 1
            )
            .order_by(
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

    # ==========================================
    # BULK PRICES
    # ==========================================

    def get_prices_for_standards(self, master_ids):
        if not master_ids:
            return []

        return run_with_retry(
            self.db,
            lambda:
                self.db.query(StandardPrice)
                .filter(
                    StandardPrice.std_id.in_(master_ids),
                    StandardPrice.status == 1,
                    StandardPrice.formate_id == 1
                )
                .order_by(
                    StandardPrice.id
                ),
        )

    # ==========================================
    # BULK CLASSIFICATIONS
    # ==========================================

    def get_classifications_for_standards(self, master_ids):
        if not master_ids:
            return []

        return run_with_retry(
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