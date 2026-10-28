import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

MYSQL_DISCONNECT_CODES = {2006, 2013}


def _mysql_error_code(exc: OperationalError) -> int | None:
    try:
        code = exc.orig.args[0]
    except Exception:
        return None
    return code if isinstance(code, int) else None


def run_with_retry(
    db: Session,
    query_factory: Callable[[], Any],
    retries: int = 1,
) -> list:
    """Execute a SELECT and retry once after a MySQL disconnect.

    Only server-gone (2006) and lost-connection (2013) errors are retried.
    """
    last_error: OperationalError | None = None

    for attempt in range(retries + 1):
        try:
            return query_factory().all()

        except OperationalError as exc:
            last_error = exc
            code = _mysql_error_code(exc)

            if code not in MYSQL_DISCONNECT_CODES or attempt >= retries:
                raise

            logger.warning(
                "MySQL disconnect code=%s attempt=%s/%s; retrying",
                code,
                attempt + 1,
                retries + 1,
            )
            try:
                db.rollback()
            except Exception:
                logger.exception("Database rollback failed before retry")

    raise last_error
