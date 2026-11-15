"""The TTL cache, and the short life an empty answer gets.

An upstream "nothing here" can be a refused request wearing the same face as
an empty listing. Caching it for the full TTL turns a blip into minutes of
blank pages, so a falsy result is held only for the caller's short TTL.
"""

import unittest

from rink.cache import TTLCache


class EmptyResultTest(unittest.TestCase):
    def test_an_empty_answer_is_not_cached_for_the_full_ttl(self):
        cache = TTLCache(ttl=300)
        cache.set("k", [], ttl=30)
        value, expires = cache._data["k"]
        import time
        self.assertLess(expires - time.monotonic(), 31)

    def test_get_or_set_caches_a_short_answer_briefly(self):
        cache = TTLCache(ttl=300)
        cache.get_or_set("k", lambda: [], empty_ttl=5)
        import time
        _, expires = cache._data["k"]
        self.assertLess(expires - time.monotonic(), 6)

    def test_get_or_set_caches_a_real_answer_for_the_full_ttl(self):
        cache = TTLCache(ttl=300)
        cache.get_or_set("k", lambda: [{"a": 1}], empty_ttl=5)
        import time
        _, expires = cache._data["k"]
        self.assertGreater(expires - time.monotonic(), 200)

    def test_without_an_empty_ttl_nothing_changes(self):
        cache = TTLCache(ttl=300)
        cache.get_or_set("k", lambda: [])
        import time
        _, expires = cache._data["k"]
        self.assertGreater(expires - time.monotonic(), 200)

    def test_a_hit_is_not_recomputed(self):
        cache = TTLCache(ttl=300)
        calls = []
        cache.get_or_set("k", lambda: calls.append(1) or ["x"])
        self.assertEqual(cache.get_or_set("k", lambda: calls.append(2) or ["y"]),
                         ["x"])
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
