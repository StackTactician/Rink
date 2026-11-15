"""Tiny time-to-live cache for upstream API results."""

import threading
import time


class TTLCache:
    """Thread-safe key/value cache with per-entry TTL (seconds)."""

    def __init__(self, ttl):
        self.ttl = ttl
        self._data = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._data.get(key)
        if hit is None:
            return None
        value, expires = hit
        if expires < time.monotonic():
            with self._lock:
                self._data.pop(key, None)
            return None
        return value

    def set(self, key, value, ttl=None):
        with self._lock:
            self._data[key] = (value, time.monotonic() + (self.ttl if ttl is None else ttl))

    def get_or_set(self, key, factory, empty_ttl=None):
        """The cached value, or `factory()` cached for the cache's own TTL.

        `empty_ttl` caches a falsy result for that many seconds instead: an
        upstream "nothing here" may be a momentary refusal rather than a
        fact, and holding it for the full TTL would turn a blip into five
        minutes of blank pages.
        """
        value = self.get(key)
        if value is None:
            value = factory()
            short = empty_ttl is not None and not value
            self.set(key, value, empty_ttl if short else self.ttl)
        return value

    def clear(self):
        with self._lock:
            self._data.clear()
