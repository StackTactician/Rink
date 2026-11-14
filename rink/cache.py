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

    def set(self, key, value):
        with self._lock:
            self._data[key] = (value, time.monotonic() + self.ttl)

    def get_or_set(self, key, factory):
        value = self.get(key)
        if value is None:
            value = factory()
            self.set(key, value)
        return value

    def clear(self):
        with self._lock:
            self._data.clear()
