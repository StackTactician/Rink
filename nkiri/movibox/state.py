"""Caches and the token, one place, so `clear_cache()` cannot miss one."""

from ..cache import TTLCache

_home_cache = TTLCache(ttl=300)
_menu_cache = TTLCache(ttl=3600)
_search_cache = TTLCache(ttl=300)
_enum_cache = TTLCache(ttl=300)
_detail_cache = TTLCache(ttl=600)
_files_cache = TTLCache(ttl=300)


_token = {"value": None, "at": 0.0}
_TOKEN_TTL = 3600

def clear_cache():
    """Every cache, and the JWT: the next call mints a fresh one."""
    for cache in (_home_cache, _menu_cache, _search_cache, _enum_cache,
                  _detail_cache, _files_cache):
        cache.clear()
    _token["value"], _token["at"] = None, 0.0
