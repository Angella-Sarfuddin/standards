"""Index-friendly retrieval for long identity cores.

A leading-wildcard ``LIKE '%9001%'`` scan of one publisher takes about a
second and a half. The same cores sought with a left-anchored prefix use
the existing designation index in a few hundredths of a second, and a
fulltext query finds a core buried in a longer title such as
``ANSI-NACE MR0175-2021``. Callers still accept a row only when
``identity_core_appears`` says the requested number is actually present.
"""

from sqlalchemy import or_
from sqlalchemy.dialects.mysql import match

from app.utils.db_retry import run_with_retry
from app.utils.standard_identity import (
    identity_core_appears,
    identity_fulltext_terms,
    identity_indexable_like_patterns,
)

_MAX_LIKES_PER_QUERY = 200
_MAX_FULLTEXT_CORES = 200


def fetch_long_core_candidates(
    db,
    *,
    model,
    sdo_id,
    cores,
    sdo_prefixes,
    text_columns,
    fulltext_column,
    normalized_column=None,
    extra_filters=(),
):
    """Return catalogue rows that might contain one of ``cores``.

    Rows are not identity-checked here. The repository applies
    ``identity_core_appears`` before a row can become a match.
    """
    cores = [str(core) for core in dict.fromkeys(cores) if core]
    if not cores:
        return []

    rows = _prefix_candidates(
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
        if not _core_appears(rows, core, text_columns, normalized_column)
    ]
    if missing:
        rows.extend(
            _fulltext_candidates(
                db,
                model=model,
                sdo_id=sdo_id,
                cores=missing,
                fulltext_column=fulltext_column,
                extra_filters=extra_filters,
            )
        )
    return rows


def _core_appears(rows, core, text_columns, normalized_column):
    columns = list(text_columns)
    if normalized_column is not None:
        columns.append(normalized_column)
    for row in rows:
        for column in columns:
            value = getattr(row, column.key, None)
            if value and identity_core_appears(value, core):
                return True
    return False


def _prefix_candidates(
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
        if pending_likes and len(pending_likes) + len(likes) > _MAX_LIKES_PER_QUERY:
            run()
        pending_likes.extend(likes)
    run()
    return rows


def _fulltext_candidates(
    db,
    *,
    model,
    sdo_id,
    cores,
    fulltext_column,
    extra_filters,
):
    rows = []
    for start in range(0, len(cores), _MAX_FULLTEXT_CORES):
        terms = []
        for core in cores[start:start + _MAX_FULLTEXT_CORES]:
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
