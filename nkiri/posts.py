"""Post, search and browse service layer. Returns plain dicts.

Every list result has the shape:
    {"items": [...], "page": n, "per_page": m, "total": T, "total_pages": P}

Upstream latency dominates every request, so:
  * posters are resolved in one batched media call per page, not per post
  * pages are TTL-cached for repeat views
"""

import difflib
import logging
import re
import urllib.parse

from .cache import TTLCache
from .media import LARGE, media_url, media_urls, proxy_url
from .net import api_get, api_get_page
from .text import clean_title

logger = logging.getLogger(__name__)

_latest_cache = TTLCache(ttl=60)
_search_cache = TTLCache(ttl=300)
_post_cache = TTLCache(ttl=600)

_FIELDS = "id,title,link,featured_media,date"
_RAW_FIELDS = "id,title,link,date"


def page_payload(items, page, per_page, total=None, total_pages=None):
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }


def get_post(post_id):
    """Full post record, including the resolved poster URL."""
    def fetch():
        data = api_get(f"/posts/{post_id}?_fields=id,title,link,content,date,featured_media")
        data["title"] = clean_title(data["title"]["rendered"])
        data["poster"] = media_url(data.get("featured_media"), LARGE)
        return data
    return _post_cache.get_or_set(int(post_id), fetch)


def _summaries(posts):
    """Post records -> view items, with all posters in a single media call."""
    posters = media_urls([p.get("featured_media") for p in posts])
    return [{
        "id": p["id"],
        "title": clean_title(p["title"]["rendered"]),
        "url": p["link"],
        "date": p.get("date", "")[:10],
        "poster": proxy_url(posters.get(p.get("featured_media"))),
    } for p in posts]


def _collection(path, page, per_page, transform):
    """Fetch one page of a WP collection; tolerate out-of-range pages."""
    try:
        rows, total, total_pages = api_get_page(path)
    except Exception:
        # 400 rest_post_invalid_page_number lands here: past the last page
        return page_payload([], page, per_page)
    return page_payload(transform(rows), page, per_page, total, total_pages)


# --------------------------------------------------------------- raw (CLI)

def raw_search(query, limit=15, page=1):
    """Site-wide search (pages + posts), one page, raw WP records."""
    q = urllib.parse.quote(query)
    return _collection(f"/search?search={q}&per_page={limit}&page={page}",
                       page, limit, lambda rows: rows)


def raw_posts(limit=20, page=1):
    """Most recent posts, one page, raw WP records."""
    return _collection(f"/posts?per_page={limit}&page={page}&_fields={_RAW_FIELDS}",
                       page, limit, lambda rows: rows)


# ------------------------------------------------------------ web (views)

_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)


def _terms(query):
    return [t for t in _WORD_RE.split(query.lower()) if len(t) > 1]


def _title_has(title, term):
    """Whole-word-ish match: "love" must not fire inside "clover"."""
    return re.search(r"(?<![a-z0-9])" + re.escape(term), title.lower()) is not None


def _split_title_hits(query, items):
    """(titles carrying every term, then any term, then the rest), order kept."""
    terms = _terms(query)
    if not terms:
        return items, [], []
    all_hits = [i for i in items if all(_title_has(i["title"], t) for t in terms)]
    any_hits = [i for i in items if any(_title_has(i["title"], t) for t in terms)
                and i not in all_hits]
    return all_hits, any_hits, [i for i in items
                                if i not in all_hits and i not in any_hits]


#: posts pulled per search; WP caps per_page at 100
_SEARCH_POOL = 100


def _fetch_posts(search):
    rows = api_get(f"/posts?search={urllib.parse.quote(search)}&orderby=relevance"
                   f"&per_page={_SEARCH_POOL}&_fields={_FIELDS}")
    return _summaries(rows)


def _fuzzy(query):
    """Last resort for typos: shorten the longest word and keep near-titles."""
    words = sorted(_terms(query), key=len, reverse=True)
    if not words or len(words[0]) < 5:
        return []
    word = words[0]
    # short prefixes matter: "invoncible" only matches "Invincible" from "invo"
    cuts = [len(word) - 1, len(word) - 2, max(5, len(word) // 2), 4, 3]
    for keep in dict.fromkeys(c for c in cuts if c >= 3):
        try:
            candidates = _fetch_posts(word[:keep])
        except Exception:
            return []
        close = [i for i in candidates if _similar(word, i["title"]) >= .75]
        if close:
            return close
    return []


def _similar(word, title):
    best = 0.0
    for w in _WORD_RE.split(title.lower()):
        if abs(len(w) - len(word)) > 2:
            continue
        best = max(best, difflib.SequenceMatcher(None, word, w).ratio())
    return best


def search_pool(query):
    """Ranked list of posts for a query, cached per query (not per page)."""
    def build():
        try:
            items = _fetch_posts(query)
        except Exception as error:
            logger.warning("search %r failed: %s", query, error)
            return []
        all_hits, any_hits, rest = _split_title_hits(query, items)
        return all_hits or any_hits or rest or _fuzzy(query)

    return _search_cache.get_or_set(query.strip().lower(), build)


def search_results(query, limit=24, page=1):
    """Search posts: title matches lead, paged over our own ranked list.

    Three upstream quirks are corrected here:
      * without orderby=relevance WP returns hits newest-first
      * relevance scores body text, so "love" surfaced "Black Clover"
      * its paging would describe WP's list, not the ranked one we show
    """
    pool = search_pool(query)
    total = len(pool)
    pages = max(1, (total + limit - 1) // limit)
    start = (page - 1) * limit
    return page_payload(pool[start:start + limit], page, limit, total, pages)


def latest(limit=24, page=1):
    """Most recent uploads with poster URLs."""
    def fetch():
        return _collection(f"/posts?per_page={limit}&page={page}&_fields={_FIELDS}",
                           page, limit, _summaries)
    return _latest_cache.get_or_set((limit, page), fetch)
