from sqlalchemy import or_

from app.utils.db_retry import run_with_retry

from app.models.standard import Standard
from app.models.sdo import SDO
from app.utils.standard_identity import (
    identity_core_appears,
    identity_discovery_terms,
    normalize_tokens,
)


class StandardsRepository:

    def __init__(self, db):
        self.db = db

    # ==========================================
    # BASIC STANDARD SEARCH
    # ==========================================

    def search_by_display_number(self, display_number: str):
        return (
            self.db.query(Standard)
            .filter(
                Standard.display_stdNo == display_number
            )
            .all()
        )

    def search_by_normalized_number(self, normalized_number: str):
        return (
            self.db.query(Standard)
            .filter(
                Standard.stdNo_normalized == normalized_number
            )
            .all()
        )

    def search_by_standard_number(self, standard_number: str):
        return (
            self.db.query(Standard)
            .filter(
                Standard.standardno == standard_number
            )
            .all()
        )

    # ==========================================
    # BULK STANDARD SEARCH
    # ==========================================

    def search_by_display_numbers(self, display_numbers: list[str]):
        if not display_numbers:
            return []

        return (
            self.db.query(Standard)
            .filter(
                Standard.display_stdNo.in_(display_numbers)
            )
            .all()
        )

    def search_by_normalized_numbers(
        self,
        normalized_numbers: list[str]
    ):
        if not normalized_numbers:
            return []

        return (
            self.db.query(Standard)
            .filter(
                Standard.stdNo_normalized.in_(normalized_numbers)
            )
            .all()
        )

    def search_by_standard_numbers(
        self,
        standard_numbers: list[str]
    ):
        if not standard_numbers:
            return []

        return (
            self.db.query(Standard)
            .filter(
                Standard.standardno.in_(standard_numbers)
            )
            .all()
        )

    # ==========================================
    # SDO + DISPLAY NUMBER
    # ==========================================

    def search_by_sdo_and_display_number(
        self,
        sdo_id: int,
        display_number: str
    ):
        return (
            self.db.query(Standard)
            .filter(
                Standard.sdo_id == sdo_id,
                Standard.display_stdNo == display_number
            )
            .all()
        )

    # ==========================================
    # SDO + DISPLAY VARIANTS
    # ==========================================

    def search_by_sdo_and_display_variants(self, pairs):
        """
        Resolve exact display-number candidates without
        a large OR tree.

        Groups requested display numbers by SDO and uses
        display_stdNo IN (...) so MySQL can use the
        SDO/display indexes more effectively.
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
                        self.db.query(Standard)
                        .filter(
                            Standard.sdo_id == sdo_id,
                            Standard.display_stdNo.in_(batch),
                        ),
                )

                for row in rows:

                    if row.id in seen:
                        continue

                    seen.add(row.id)
                    results.append(row)

        return results

    # ==========================================
    # SDO + IDENTITY HINTS
    # ==========================================

    def search_by_sdo_and_identity_hints(self, hints):
        """Find local candidates via designation-neutral identity hints.

        Fast path: one (or few) containment scans per SDO using
        ``%{core_pattern}%`` on display/standardno/normalized. Short cores
        keep selective prefix-bound patterns. Final accuracy is always
        ``identity_core_appears`` in Python.
        """
        if not hints:
            return []

        # sdo_id -> {"containment": {core: pattern}, "bound": {core: patterns}}
        grouped = {}

        for sdo_id, sdo_prefix, core_token in hints:

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

            if containment:
                bucket["containment"][core] = containment
            elif bound:
                bucket["bound"].setdefault(core, set()).update(bound)

        if not grouped:
            return []

        results = []
        seen = set()
        # Containment uses 3 predicates per core; large batches are fine.
        containment_chunk = 40
        bound_chunk = 5

        for sdo_id, bucket in grouped.items():
            containment_items = list(bucket["containment"].items())
            for start in range(0, len(containment_items), containment_chunk):
                batch = containment_items[start:start + containment_chunk]
                filters = []
                cores_in_batch = []

                for core, pattern in batch:
                    cores_in_batch.append(core)
                    contain = f"%{pattern}%"
                    filters.append(Standard.display_stdNo.like(contain))
                    filters.append(Standard.standardno.like(contain))
                    filters.append(
                        Standard.stdNo_normalized.like(f"%{core}%")
                    )

                if not filters:
                    continue

                rows = run_with_retry(
                    self.db,
                    lambda sdo_id=sdo_id, filters=filters: (
                        self.db.query(Standard)
                        .filter(
                            Standard.sdo_id == sdo_id,
                            or_(*filters),
                        )
                    ),
                )

                for row in rows:
                    if row.id in seen:
                        continue

                    display_value = str(row.display_stdNo or "").strip()
                    standard_value = str(row.standardno or "").strip()
                    normalized_value = str(
                        row.stdNo_normalized or ""
                    ).strip()
                    if not any(
                        identity_core_appears(display_value, core)
                        or identity_core_appears(standard_value, core)
                        or identity_core_appears(normalized_value, core)
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

                for core, pattern_set in batch:
                    cores_in_batch.append(core)
                    for pattern in pattern_set:
                        filters.append(
                            Standard.display_stdNo.like(pattern)
                        )
                        filters.append(
                            Standard.standardno.like(pattern)
                        )

                if not filters:
                    continue

                rows = run_with_retry(
                    self.db,
                    lambda sdo_id=sdo_id, filters=filters: (
                        self.db.query(Standard)
                        .filter(
                            Standard.sdo_id == sdo_id,
                            or_(*filters),
                        )
                    ),
                )

                for row in rows:
                    if row.id in seen:
                        continue

                    display_value = str(row.display_stdNo or "").strip()
                    standard_value = str(row.standardno or "").strip()
                    if not any(
                        identity_core_appears(display_value, core)
                        or identity_core_appears(standard_value, core)
                        for core in cores_in_batch
                    ):
                        continue

                    seen.add(row.id)
                    results.append(row)

        return results

    # ==========================================
    # STANDARD IDs
    # ==========================================

    def search_by_standard_ids(self, standard_ids):
        if not standard_ids:
            return []

        return (
            self.db.query(Standard)
            .filter(
                Standard.Standard_id.in_(standard_ids)
            )
            .all()
        )

    # ==========================================
    # FIND SDO BY STANDARD PREFIX
    # ==========================================

    def find_sdo_id_by_standard_prefix(
        self,
        prefix: str
    ):
        return (
            self.db.query(Standard.sdo_id)
            .filter(
                Standard.standardno.like(
                    f"{prefix}%"
                )
            )
            .distinct()
            .all()
        )

    # ==========================================
    # COMPATIBILITY METHOD
    # ==========================================

    def search_by_sdo_and_display_numbers(self, pairs):
        if not pairs:
            return []

        return self.search_by_sdo_and_display_variants(
            pairs
        )

    # ==========================================
    # LEGACY SDO PREFIX LOOKUP
    # ==========================================

    def find_sdo_ids_by_prefixes(self, prefixes):
        """
        Legacy compatibility only.

        SDO resolution should use the dedicated SDO
        table whenever possible.

        This method is retained for callers outside
        the document-search flow.
        """

        if not prefixes:
            return []

        results = []

        for prefix in prefixes:

            prefix = str(
                prefix or ""
            ).strip()

            if not prefix:
                continue

            results.extend(
                self.db.query(
                    Standard.standardno,
                    Standard.sdo_id
                )
                .filter(
                    Standard.standardno.like(
                        f"{prefix} %"
                    )
                )
                .limit(1)
                .all()
            )

        return results

    # ==========================================
    # SDO TABLE LOOKUP
    # ==========================================

    def find_sdo_ids_from_sdo_table(self, names):
        """
        Resolve SDO names from the dedicated SDO table.

        The SDO table is small, so we load the active SDO
        rows once and perform the final normalized-name
        comparison in Python.
        """

        requested = {
            normalize_tokens(name)
            for name in names
            if name and str(name).strip()
        }

        if not requested:
            return []

        # Use retry handling here as well so an expired/
        # disconnected MySQL connection can recover.
        rows = run_with_retry(
            self.db,
            lambda:
                self.db.query(
                    SDO.id,
                    SDO.sdo_title,
                    SDO.sdo_fullname,
                    SDO.sdo_shortdesc,
                    SDO.designation,
                )
                .filter(
                    SDO.status == 1
                ),
        )

        matches = []

        for row in rows:

            values = {
                normalize_tokens(row.sdo_title),
                normalize_tokens(row.sdo_fullname),
                normalize_tokens(row.sdo_shortdesc),
                normalize_tokens(row.designation),
            }

            values.discard("")

            if requested.intersection(values):
                matches.append(row)

        return matches

    # ==========================================
    # GET STANDARDS BY INTERNAL IDs
    # ==========================================

    def get_by_ids(self, ids):
        if not ids:
            return []

        return (
            self.db.query(Standard)
            .filter(
                Standard.id.in_(ids)
            )
            .all()
        )

    # ==========================================
    # SDO + NORMALIZED NUMBER
    # ==========================================

    def search_by_sdo_and_normalized_numbers(
        self,
        pairs
    ):
        """
        Search standards using SDO + normalized number.

        Requests are grouped by SDO and processed in
        batches so the database does not receive one
        query per Excel row.
        """

        if not pairs:
            return []

        grouped = {}

        for sdo_id, value in pairs:

            if sdo_id and value:

                grouped.setdefault(
                    int(sdo_id),
                    set()
                ).add(
                    str(value).strip()
                )

        results = []
        seen = set()

        for sdo_id, values in grouped.items():

            values = list(values)

            for start in range(
                0,
                len(values),
                400
            ):

                batch = values[
                    start:start + 400
                ]

                rows = run_with_retry(
                    self.db,
                    lambda sdo_id=sdo_id, batch=batch:
                        self.db.query(Standard)
                        .filter(
                            Standard.sdo_id == sdo_id,
                            Standard.stdNo_normalized.in_(batch),
                        ),
                )

                for row in rows:

                    if row.id in seen:
                        continue

                    seen.add(row.id)
                    results.append(row)

        return results

    # ==========================================
    # SDO + STANDARD NUMBER
    # ==========================================

    def search_by_sdo_and_standard_numbers(
        self,
        pairs
    ):
        """
        Search standards using SDO + exact standard
        number.

        Requests are grouped by SDO and processed
        in batches.
        """

        if not pairs:
            return []

        grouped = {}

        for sdo_id, value in pairs:

            if sdo_id and value:

                grouped.setdefault(
                    int(sdo_id),
                    set()
                ).add(
                    str(value).strip()
                )

        results = []
        seen = set()

        for sdo_id, values in grouped.items():

            values = list(values)

            for start in range(
                0,
                len(values),
                400
            ):

                batch = values[
                    start:start + 400
                ]

                rows = run_with_retry(
                    self.db,
                    lambda sdo_id=sdo_id, batch=batch:
                        self.db.query(Standard)
                        .filter(
                            Standard.sdo_id == sdo_id,
                            Standard.standardno.in_(batch),
                        ),
                )

                for row in rows:

                    if row.id in seen:
                        continue

                    seen.add(row.id)
                    results.append(row)

        return results