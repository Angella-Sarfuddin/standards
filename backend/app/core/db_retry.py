from sqlalchemy.exc import OperationalError


MYSQL_DISCONNECT_CODES = {2006, 2013}


def _mysql_error_code(exc):
    try:
        return exc.orig.args[0]
    except Exception:
        return None


def run_with_retry(db, query_factory, retries=1):
    """
    Execute a SQLAlchemy SELECT query and retry once if MySQL
    disconnects during the query.
    """

    last_error = None

    for attempt in range(retries + 1):
        try:
            return query_factory().all()

        except OperationalError as exc:
            last_error = exc

            code = _mysql_error_code(exc)

            if code not in MYSQL_DISCONNECT_CODES:
                raise

            if attempt >= retries:
                raise

            # The connection/transaction is broken.
            # SQLAlchemy requires rollback before the Session can
            # obtain another connection.
            try:
                db.rollback()
            except Exception:
                pass

            continue

    raise last_error