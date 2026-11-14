"""Caches, one place, so `clear_cache()` cannot miss one."""

from ..cache import TTLCache

_menu_cache = TTLCache(ttl=3600)
_latest_cache = TTLCache(ttl=120)
_search_cache = TTLCache(ttl=300)
_post_cache = TTLCache(ttl=600)
_browse_cache = TTLCache(ttl=120)
_size_cache = TTLCache(ttl=3600)

#: the category table, and one post's categories
_cat_slug_cache = TTLCache(ttl=3600)
_post_cat_cache = TTLCache(ttl=3600)

def clear_cache():
    """Every cache this source keeps, including the two category ones."""
    for c in (_menu_cache, _latest_cache, _search_cache, _post_cache,
              _browse_cache, _size_cache, _cat_slug_cache, _post_cat_cache):
        c.clear()
