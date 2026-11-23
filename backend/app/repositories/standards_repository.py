from sqlalchemy import or_

from app.repositories.identity_lookup import (
    BOUND_PATTERN_BATCH,
    IN_BATCH_SIZE,
    fetch_long_core_candidates,
    iter_batches,
    keep_rows_containing_core,
    unique_rows_by_id,
)
from app.repositories.query_columns import standard_search_options
from app.core.db_retry import run_with_retry
from app.core.ttl_cache import BindTtlCache

from app.models.standard import Standard
from app.models.sdo import SDO
from app.core.standard_identity import (
    identity_discovery_terms,
    normalize_tokens,
)


_SDO_ROWS_CACHE = BindTtlCache(ttl_seconds=60)


class StandardsRepository:

    def __init__(self, db):
        self.db = db

    def _standard_query(self):
        return self.db.query(Standard).options(standard_search_options())

    def _session_bind(self):
        get_bind = getattr(self.db, "get_bind", None)
        return get_bind() if callable(get_bind) else None

    # ==========================================
    # BASIC STANDARD SEARCH
    # ==========================================

    def search_by_display_number(self, display_number: str):
        return (
            self._standard_query()
            .filter(
                Standard.display_stdNo == display_number
            )
            .all()
        )

    def search_by_normalized_number(self, normalized_number: str):
        return (
            self._standard_query()
            .filter(
                Standard.stdNo_normalized == normalized_number
            )
            .all()
        )

    def search_by_standard_number(self, standard_number: str):
        return (
            self._standard_query()
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
            self._standard_query()
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
            self._standard_query()
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
            self._standard_query()
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
            self._standard_query()
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

        for sdo_id, display_numbers in grouped.items():
            for batch in iter_batches(display_numbers, IN_BATCH_SIZE):
                rows = run_with_retry(
                    self.db,
                    lambda sdo_id=sdo_id, batch=batch:
                        self._standard_query()
                        .filter(
                            Standard.sdo_id == sdo_id,
                            Standard.display_stdNo.in_(batch),
                        ),
                )
                results.extend(unique_rows_by_id(rows, seen))

        return results

    def search_by_sdo_display_and_standard_numbers(self, pairs):
        """One round trip covering display_stdNo and standardno IN lookups.

        Splits rows the same way separate display and standard-number queries
        would, so lookup indexes and match logic stay unchanged.
        """
        if not pairs:
            return [], []

        grouped = {}
        for sdo_id, value in pairs:
            if not sdo_id or not value:
                continue
            text = str(value).strip()
            if not text:
                continue
            grouped.setdefault(int(sdo_id), set()).add(text)

        exact_results = []
        standard_number_results = []
        exact_seen = set()
        standard_seen = set()

        for sdo_id, values in grouped.items():
            for batch in iter_batches(values, IN_BATCH_SIZE):
                batch_set = set(batch)
                rows = run_with_retry(
                    self.db,
                    lambda sdo_id=sdo_id, batch=batch:
                        self._standard_query()
                        .filter(
                            Standard.sdo_id == sdo_id,
                            or_(
                                Standard.display_stdNo.in_(batch),
                                Standard.standardno.in_(batch),
                            ),
                        ),
                )
                for row in rows:
                    display = str(row.display_stdNo or "").strip()
                    standardno = str(row.standardno or "").strip()
                    if display in batch_set and row.id not in exact_seen:
                        exact_seen.add(row.id)
                        exact_results.append(row)
                    if standardno in batch_set and row.id not in standard_seen:
                        standard_seen.add(row.id)
                        standard_number_results.append(row)

        return exact_results, standard_number_results

    # ==========================================
    # SDO + IDENTITY HINTS
    # ==========================================

    def search_by_sdo_and_identity_hints(self, hints):
        """Find local candidates via designation-neutral identity hints.

        Long cores use an index prefix plus a fulltext lookup. Short cores
        keep selective prefix-bound patterns. Final accuracy is always
        ``identity_core_appears`` in Python.
        """
        if not hints:
            return []

        # sdo_id -> {"containment": {core: pattern}, "bound": {}, "prefixes": set}
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
                (int(sdo_id), sdo_prefix),
                {"containment": {}, "bound": {}, "prefixes": {sdo_prefix}},
            )

            if containment:
                bucket["containment"][core] = containment
            # Separator-preserving patterns (``ASME B36.19%``) are bound even
            # when a long-core containment key is also present.
            if bound:
                bucket["bound"].setdefault(core, set()).update(bound)

        if not grouped:
            return []

        # Always use the request session so candidates stay attached and match
        # selection can read loaded columns without re-querying after close().
        results = []
        seen = set()
        text_columns = ("display_stdNo", "standardno")

        for (sdo_id, _prefix), bucket in grouped.items():
            cores_in_batch = list(bucket["containment"])
            rows = fetch_long_core_candidates(
                self.db,
                model=Standard,
                sdo_id=sdo_id,
                cores=cores_in_batch,
                sdo_prefixes=bucket["prefixes"],
                text_columns=(
                    Standard.display_stdNo,
                    Standard.standardno,
                ),
                fulltext_column=Standard.display_stdNo,
                normalized_column=Standard.stdNo_normalized,
                query_options=standard_search_options(),
            )
            results.extend(
                keep_rows_containing_core(
                    rows,
                    cores_in_batch,
                    (*text_columns, "stdNo_normalized"),
                    seen,
                )
            )

            bound_items = list(bucket["bound"].items())
            for batch in iter_batches(bound_items, BOUND_PATTERN_BATCH):
                filters = []
                cores_in_batch = []

                for core, pattern_set in batch:
                    cores_in_batch.append(core)
                    for pattern in pattern_set:
                        filters.append(Standard.display_stdNo.like(pattern))
                        filters.append(Standard.standardno.like(pattern))

                if not filters:
                    continue

                rows = run_with_retry(
                    self.db,
                    lambda sdo_id=sdo_id, filters=filters: (
                        self._standard_query()
                        .filter(
                            Standard.sdo_id == sdo_id,
                            or_(*filters),
                        )
                    ),
                )
                results.extend(
                    keep_rows_containing_core(
                        rows,
                        cores_in_batch,
                        text_columns,
                        seen,
                    )
                )

        return results

    # ==========================================
    # STANDARD IDs
    # ==========================================

    def search_by_standard_ids(self, standard_ids):
        if not standard_ids:
            return []

        return (
            self._standard_query()
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

        # SDO names and aliases change infrequently. Reuse the small active
        # SDO table snapshot briefly so repeated one-row searches do not pay
        # for a database round trip each time.
        def _load_sdo_rows():
            return run_with_retry(
                self.db,
                lambda: self.db.query(
                    SDO.id,
                    SDO.sdo_title,
                    SDO.sdo_fullname,
                    SDO.sdo_shortdesc,
                    SDO.designation,
                ).filter(SDO.status == 1),
            )

        rows = _SDO_ROWS_CACHE.get_or_load(self._session_bind(), _load_sdo_rows)

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
            self._standard_query()
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
            for batch in iter_batches(values, IN_BATCH_SIZE):
                rows = run_with_retry(
                    self.db,
                    lambda sdo_id=sdo_id, batch=batch:
                        self._standard_query()
                        .filter(
                            Standard.sdo_id == sdo_id,
                            Standard.stdNo_normalized.in_(batch),
                        ),
                )
                results.extend(unique_rows_by_id(rows, seen))

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
            for batch in iter_batches(values, IN_BATCH_SIZE):
                rows = run_with_retry(
                    self.db,
                    lambda sdo_id=sdo_id, batch=batch:
                        self._standard_query()
                        .filter(
                            Standard.sdo_id == sdo_id,
                            Standard.standardno.in_(batch),
                        ),
                )
                results.extend(unique_rows_by_id(rows, seen))

        return results
