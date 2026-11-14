"""What the site shows: its home rows, their pages, and search."""

import logging
from concurrent.futures import ThreadPoolExecutor

from ...errors import RinkError
from ...page import page_payload
from ...text import clean_title
from . import api, config, state

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ mapping

def _poster(cover):
    """The full-size cover. The API also serves resized copies; the original
    is what keeps a portrait poster from being cropped to a landscape box."""
    if isinstance(cover, dict):
        return cover.get("url") or ""
    return cover or ""


def _item(subject):
    """One card, in the shape every other source produces."""
    path = subject.get("detailPath") or ""
    return {
        "id": path,
        "title": clean_title(subject.get("title") or ""),
        "url": f"{config.BASE}/movies/{path}" if path else config.BASE,
        "date": (subject.get("releaseDate") or "")[:10],
        "poster": _poster(subject.get("cover")),
    }


def _wanted(subject):
    """Films and series only: the feed also carries music and stage shows."""
    if subject.get("subjectType") not in config._FILM_TYPES:
        return False
    if subject.get("isPornographic"):
        return False
    return bool(subject.get("detailPath"))


def _home():
    return state._home_cache.get_or_set("home", lambda: api._api("/home"))


def _sections():
    """The site's own home rows, in the order it shows them.

    This is the taxonomy: movibox has no genre endpoint, and its filter
    endpoint ignores every field it is given, so the rows it publishes are the
    only real categorisation it exposes.
    """
    out, seen = [], set()
    for row in _home().get("operatingList") or ():
        if row.get("type") != "SUBJECTS_MOVIE":
            continue
        subjects = [s for s in (row.get("subjects") or ()) if _wanted(s)]
        if not subjects:
            continue
        name = (row.get("title") or "").strip()
        slug = str(row.get("opId") or "")
        if not name or not slug or name in seen:
            continue
        seen.add(name)
        out.append({"slug": slug, "name": name, "count": len(subjects),
                    "subjects": subjects})
    return out


# ------------------------------------------------------------------ listing

def menu():
    """Chip row: the home rows, as the site itself orders them."""
    def fetch():
        return [{"slug": s["slug"], "name": s["name"], "count": s["count"]}
                for s in _sections()]

    return state._menu_cache.get_or_set("all", fetch)


def _flatten():
    """Every section's subjects, deduped, in home order."""
    seen, out = set(), []
    for section in _sections():
        for subject in section["subjects"]:
            item = _item(subject)
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            out.append(item)
    return out


def latest(limit=24, page=1):
    """The home feed: the site's rows flattened, paged locally."""
    def fetch():
        items = _flatten()
        start = max(0, (page - 1) * limit)
        window = items[start:start + limit]
        pages = max(1, (len(items) + limit - 1) // limit)
        return page_payload(window, page, limit, total=len(items),
                            total_pages=pages)

    return state._home_cache.get_or_set(("latest", limit, page), fetch)


def browse(slug="", limit=24, page=1, cat=""):
    """One home row. Rows are fixed-length, so there is only ever one page."""
    if not slug:
        return latest(limit, page)

    def fetch():
        for section in _sections():
            if section["slug"] == str(slug):
                items = [_item(s) for s in section["subjects"]][:limit]
                return page_payload(items, 1, limit, total=len(items),
                                    total_pages=1)
        return page_payload([], page, limit, total=0, total_pages=1)

    return state._menu_cache.get_or_set(("browse", str(slug), limit), fetch)




def _search_page(query, page):
    """One page of hits, as cards. Returns (items, has_more, total_hint)."""
    try:
        data = api._api("/subject/search",
                    body={"keyword": query, "page": page,
                          "perPage": config._PAGE_SIZE})
    except RinkError as e:
        logger.warning("movibox search failed %r p%d: %s", query, page, e)
        return [], False, 0
    items = []
    for subject in data.get("items") or ():
        if _wanted(subject):
            items.append(_item(subject))
    pager = data.get("pager") or {}
    try:
        hint = int(pager.get("totalCount") or 0)
    except (TypeError, ValueError):
        hint = 0
    return items, bool(pager.get("hasMore")), hint


def _enumerate(query):
    """Every hit for a query, deduped, in the API's order.

    Returns (items, complete). `complete` is False when the cap was reached,
    which is the only case where the count is a lower bound rather than a
    number.
    """
    return state._enum_cache.get_or_set(query.lower(),
                                  lambda: _enumerate_uncached(query))


def _enumerate_uncached(query):
    items, seen = [], set()

    def absorb(found):
        for item in found:
            # a series comes back once per season, all sharing one detailPath,
            # so the card is the same card: keep the first
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            items.append(item)

    first, more, hint = _search_page(query, 1)
    absorb(first)
    if not more:
        return items, True

    # The API caps a page at 30 but usually returns fewer, so its totalCount
    # overstates how many pages there are. What one page actually held is the
    # better divisor, and it turns the whole read into a single parallel wave
    # for a typical query instead of one round trip per page.
    per_page = max(1, len(first))
    estimate = min(config._MAX_PAGES, max(2, -(-hint // per_page) if hint else config._WAVE))
    page = 2
    while page <= config._MAX_PAGES:
        wave = list(range(page, min(page + estimate, config._MAX_PAGES + 1)))
        if not wave:
            break
        with ThreadPoolExecutor(max_workers=len(wave)) as pool:
            results = list(pool.map(lambda p: _search_page(query, p), wave))
        for found, _has_more, _hint in results:
            absorb(found)
        # only the last page of the wave says whether there is more: an
        # earlier page's hasMore is about pages already fetched
        more = results[-1][1]
        if not more:
            return items, True
        page += len(wave)
    return items, False


def search(query, limit=24, page=1):
    """Search, paged from one cached enumeration.

    The API's own paging is not trustworthy — it reports more pages than it
    will serve, and its total is not the number of rows — so the whole result
    set is read once and sliced here. That is what makes the count exact and
    the page numbers honest.
    """
    query = (query or "").strip()
    if not query:
        return page_payload([], page, limit)

    def fetch():
        items, complete = _enumerate(query)
        start = max(0, (page - 1) * limit)
        window = items[start:start + limit]
        if complete:
            pages = max(1, (len(items) + limit - 1) // limit)
            return page_payload(window, page, limit, total=len(items),
                                total_pages=pages)
        # the cap was hit: say how many pages are known, not how many exist
        return page_payload(window, page, limit, total=None,
                            total_pages=page + 1)

    return state._search_cache.get_or_set((query.lower(), limit, page), fetch)
