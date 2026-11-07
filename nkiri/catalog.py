"""Browse by genre and format.

The site files genres as WordPress tags and origin/format as categories.
Tag filters accept ids only, and the tag table carries years of spelling
variants ("comdey", "Fanatsy", "documentry"), so this module maps a short
canonical genre list onto whichever ids actually exist and folds the variants
into one genre. Anything unresolved is simply left out.
"""

import logging
import urllib.parse

from .cache import TTLCache
from .posts import _FIELDS, _collection, _summaries, latest, page_payload
from .net import api_get

logger = logging.getLogger(__name__)

#: display name -> tag slugs that mean it (first existing one wins per id)
GENRES = (
    ("Drama", ("drama", "drrama")),
    ("Comedy", ("comedy", "comdey", "comdy", "coemdy")),
    ("Action", ("action", "actioin", "actoin")),
    ("Thriller", ("thriller", "thrilller")),
    ("Crime", ("crime",)),
    ("Adventure", ("adventure",)),
    ("Sci-fi", ("sci-fi", "science-fiction")),
    ("Fantasy", ("fantasy", "fanatsy", "fantacy")),
    ("Mystery", ("mystery", "mysterr")),
    ("Horror", ("horror",)),
    ("Romance", ("romance",)),
    ("Animation", ("animation",)),
    ("Family", ("family",)),
    ("History", ("history",)),
    ("War", ("war",)),
    ("Documentary", ("documentary", "documentry")),
    ("Reality", ("reality",)),
    ("Western", ("western",)),
    ("Biography", ("biography",)),
    ("Sport", ("sport", "sports")),
    ("Music", ("music",)),
    ("Kids", ("kids",)),
)

_genres_cache = TTLCache(ttl=3600)
_formats_cache = TTLCache(ttl=3600)
_browse_cache = TTLCache(ttl=120)


def _slug(name):
    return "-".join(name.lower().replace("&", "").split())


def genres():
    """Canonical genres with the tag ids behind them, biggest first."""
    def fetch():
        slugs = [s for _name, aliases in GENRES for s in aliases]
        try:
            rows = api_get("/tags?slug="
                           + urllib.parse.quote(",".join(slugs), safe=",")
                           + "&per_page=100&_fields=id,name,slug,count")
        except Exception as e:
            logger.warning("genre lookup failed: %s", e)
            return []
        by_slug = {r["slug"].lower(): r for r in rows}
        out = []
        for name, aliases in GENRES:
            found = [by_slug[a] for a in aliases if a in by_slug]
            if not found:
                continue
            out.append({
                "slug": _slug(name),
                "name": name,
                "count": sum(f.get("count", 0) for f in found),
                "ids": [f["id"] for f in found],
            })
        out.sort(key=lambda g: -g["count"])
        return out

    return _genres_cache.get_or_set("all", fetch)


def formats():
    """Origin/format categories, biggest first."""
    def fetch():
        try:
            rows = api_get("/categories?per_page=100&_fields=id,name,slug,count")
        except Exception as e:
            logger.warning("format lookup failed: %s", e)
            return []
        rows = [r for r in rows
                if r.get("count", 0) > 0 and r["slug"] != "important-information"]
        rows.sort(key=lambda r: -r["count"])
        return [{"id": r["id"], "slug": r["slug"], "name": r["name"],
                 "count": r["count"]} for r in rows]

    return _formats_cache.get_or_set("all", fetch)


def public(rows):
    """Drop the internal ids before anything leaves the process."""
    return [{k: v for k, v in r.items() if k != "id" and k != "ids"} for r in rows]


def find(rows, slug):
    for row in rows:
        if row["slug"] == slug:
            return row
    return None


def browse(tag="", cat="", limit=24, page=1):
    """One page of posts filtered by genre slug and/or format slug."""
    key = (tag, cat, limit, page)

    def fetch():
        if not tag and not cat:
            return latest(limit, page)

        params = [f"per_page={limit}", f"page={page}",
                  f"_fields={_FIELDS}", "orderby=date"]
        if tag:
            genre = find(genres(), tag)
            if not genre:
                return page_payload([], page, limit)
            params.append("tags=" + ",".join(str(i) for i in genre["ids"]))
        if cat:
            fmt = find(formats(), cat)
            if not fmt:
                return page_payload([], page, limit)
            params.append("categories=" + str(fmt["id"]))
        return _collection("/posts?" + "&".join(params),
                           page, limit, _summaries)

    return _browse_cache.get_or_set(key, fetch)


def clear_cache():
    _genres_cache.clear()
    _formats_cache.clear()
    _browse_cache.clear()
