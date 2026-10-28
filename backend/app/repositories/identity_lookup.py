"""Index-friendly retrieval for long identity cores.

A leading-wildcard ``LIKE '%9001%'`` scan of one publisher takes about a
second and a half. The same cores sought with a left-anchored prefix use
the existing designation index in a few hundredths of a second, and a
fulltext query finds a core buried in a longer title such as
``ANSI-NACE MR0175-2021``. Callers still accept a row only when
``identity_core_appears`` says the requested number is actually present.
"""

from collections.abc import Iterable, Iterator
from typing import Any

from sqlalchemy import or_
from sqlalchemy.dialects.mysql import match
from sqlalchemy.orm import Session

from app.core.db_retry import run_with_retry
from app.core.standard_identity import (
    identity_core_appears,
    identity_fulltext_terms,
    identity_indexable_like_patterns,
)

IN_BATCH_SIZE = 400
BOUND_PATTERN_BATCH = 5
LIKE_BATCH_SIZE = 200
FULLTEXT_CORE_BATCH = 200


def iter_batches(values: Iterable[Any], size: int) -> Iterator[list[Any]]:
    """Yield successive slices without changing item order."""
    items = list(values)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def unique_rows_by_id(rows: Iterable[Any], seen: set | None = None) -> list[Any]:
    """Keep the first row for each primary key."""
    if seen is None:
        seen = set()
    kept = []
    for row in rows:
        row_id = row.id
        if row_id in seen:
            continue
        seen.add(row_id)
        kept.append(row)
    return kept


def keep_rows_containing_core(
    rows: Iterable[Any],
    cores: Iterable[str],
    column_names: Iterable[str],
    seen: set,
) -> list[Any]:
    """Accept a row only when one of ``cores`` is present in its text columns."""
    cores = [core for core in cores if core]
    names = tuple(column_names)
    kept = []
    for row in rows:
        if row.id in seen:
            continue
        values = [
            str(getattr(row, name) or "").strip()
            for name in names
        ]
        if any(
            identity_core_appears(value, core)
            for value in values
            for core in cores
        ):
            seen.add(row.id)
            kept.append(row)
    return kept


def fetch_long_core_candidates(
    db: Session,
    *,
    model: Any,
    sdo_id: int,
    cores: Iterable[str],
    sdo_prefixes: Iterable[str],
    text_columns: Iterable[Any],
    fulltext_column: Any,
    normalized_column: Any = None,
    extra_filters: tuple = (),
) -> list[Any]:
    """Return catalogue rows that might contain one of ``cores``.

    Rows are not identity-checked here. The repository applies
    ``identity_core_appears`` before a row can become a match.
    """
    cores = [str(core) for core in dict.fromkeys(cores) if core]
    if not cores:
        return []

    rows = prefix_index_candidates(
        db,
        model=model,
        sdo_id=sdo_id,
        cores=cores,
        sdo_prefixes=sdo_prefixes,
        text_columns=text_columns,
        normalized_column=normalized_column,
        extra_filters=extra_filters,
    )
    missing = [
        core
        for core in cores
        if not row_contains_core(rows, core, text_columns, normalized_column)
    ]
    seen: set = set()
    unique = unique_rows_by_id(rows, seen)
    if missing:
        unique.extend(
            unique_rows_by_id(
                fulltext_candidates(
                    db,
                    model=model,
                    sdo_id=sdo_id,
                    cores=missing,
                    fulltext_column=fulltext_column,
                    extra_filters=extra_filters,
                ),
                seen,
            )
        )
    return unique


def row_contains_core(rows, core, text_columns, normalized_column):
    columns = list(text_columns)
    if normalized_column is not None:
        columns.append(normalized_column)
    for row in rows:
        for column in columns:
            value = getattr(row, column.key, None)
            if value and identity_core_appears(value, core):
                return True
    return False


def prefix_index_candidates(
    db,
    *,
    model,
    sdo_id,
    cores,
    sdo_prefixes,
    text_columns,
    normalized_column,
    extra_filters,
):
    pending_likes = []
    rows = []

    def run():
        if not pending_likes:
            return
        likes = list(pending_likes)
        pending_likes.clear()
        rows.extend(
            run_with_retry(
                db,
                lambda likes=likes: (
                    db.query(model)
                    .filter(
                        model.sdo_id == sdo_id,
                        or_(*likes),
                        *extra_filters,
                    )
                ),
            )
        )

    for core in cores:
        patterns = []
        for prefix in sdo_prefixes:
            patterns.extend(identity_indexable_like_patterns(prefix, core))
        patterns = list(dict.fromkeys(patterns))
        likes = []
        for pattern in patterns:
            for column in text_columns:
                likes.append(column.like(pattern))
            if normalized_column is not None and " " not in pattern:
                likes.append(normalized_column.like(pattern))
        if not likes:
            continue
        if pending_likes and len(pending_likes) + len(likes) > LIKE_BATCH_SIZE:
            run()
        pending_likes.extend(likes)
    run()
    return rows


def fulltext_candidates(
    db,
    *,
    model,
    sdo_id,
    cores,
    fulltext_column,
    extra_filters,
):
    rows = []
    for batch in iter_batches(cores, FULLTEXT_CORE_BATCH):
        terms = []
        for core in batch:
            terms.extend(identity_fulltext_terms(core))
        terms = list(dict.fromkeys(terms))
        if not terms:
            continue
        against = " ".join(terms)
        rows.extend(
            run_with_retry(
                db,
                lambda against=against: (
                    db.query(model)
                    .filter(
                        model.sdo_id == sdo_id,
                        match(
                            fulltext_column,
                            against=against,
                        ).in_boolean_mode(),
                        *extra_filters,
                    )
                ),
            )
        )
    return rows
