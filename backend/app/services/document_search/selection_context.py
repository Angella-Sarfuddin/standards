"""Per-call selection context for compatibility callbacks."""

from contextvars import ContextVar
from contextlib import contextmanager


_candidate_status_map = ContextVar("candidate_status_map", default=None)


@contextmanager
def use_candidate_status_map(status_map):
    token = _candidate_status_map.set(status_map)
    try:
        yield
    finally:
        _candidate_status_map.reset(token)


def current_candidate_status_map():
    return _candidate_status_map.get()
