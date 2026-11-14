"""Caches, one place, so `clear_cache()` cannot miss one."""

from ...cache import TTLCache

#: the site's own taxonomy: genre table, format table, and a category's page
_genres_cache = TTLCache(ttl=3600)
_formats_cache = TTLCache(ttl=3600)
_browse_cache = TTLCache(ttl=120)

#: listings, and one post
_latest_cache = TTLCache(ttl=120)
_search_cache = TTLCache(ttl=300)
_post_cache = TTLCache(ttl=600)

#: the media batch that fills a page of posters
_media_cache = TTLCache(ttl=1800)

#: a landing page's stated size
_size_cache = TTLCache(ttl=3600)


def clear_cache():
    """Every cache this source keeps."""
    for c in (_genres_cache, _formats_cache, _browse_cache, _latest_cache,
              _search_cache, _post_cache, _media_cache, _size_cache):
        c.clear()
