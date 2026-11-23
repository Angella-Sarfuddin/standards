"""Small process-level TTL caches keyed by SQLAlchemy engine bind."""

from __future__ import annotations

import threading
import time
import weakref
from collections.abc import Callable
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class BindTtlCache(Generic[T]):
    """Cache one value per DB bind for a short TTL.

    Used for small, slowly changing catalogue tables (status codes, SDO
    snapshots) so repeated searches avoid identical round trips without
    changing which rows those helpers return.
    """

    def __init__(self, ttl_seconds: float):
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._store: weakref.WeakKeyDictionary[Any, tuple[float, T]] = (
            weakref.WeakKeyDictionary()
        )

    def get_or_load(self, bind: Any | None, loader: Callable[[], T]) -> T:
        if bind is None:
            return loader()

        now = time.monotonic()
        with self._lock:
            cached = self._store.get(bind)
            if cached and now - cached[0] < self._ttl_seconds:
                return cached[1]

        value = loader()
        with self._lock:
            self._store[bind] = (time.monotonic(), value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
