"""Films and shows only: what the site files under music, gist and news."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from ...errors import RinkError
from . import state
from .config import _is_film_or_show
from .http import _api

logger = logging.getLogger(__name__)

#: music and gist posts share the /videodownload/ path, so a URL cannot tell
#: them apart. Search cannot ask the site to filter by category either — both
#: `?cat=` on the search page and `categories=` on the REST search are ignored
#: (verified). The search page does not print a category on its cards either,
#: so the only place a hit states its category is the post's own REST record;
#: `_post_cats` goes and reads it. The title screen below is what is left when
#: even that is unavailable.
_NON_FILM_PREFIX_RE = re.compile(
    r"^\s*(?:video|music(?:\s*box)?|audio|mp3|lyrics?)\s*:", re.I)
_NON_FILM_HINT_RE = re.compile(
    r"\s(?:ft\.|feat\.)\s|\bremix\b|\bgospel\b|\blyrics?\b|"
    r"\bas\s+he\s+talks\b|\breveals?\b", re.I)
_HAS_YEAR_RE = re.compile(r"\(\s*(?:19|20)\d{2}\s*\)")


def _looks_like_film(title, url=""):
    """Loose, cheap screen for a search hit: films and shows carry a (year).

    Only used when a hit's category cannot be read, so it leans towards
    keeping the post: a wrong drop hides something the listing still shows,
    which is the disagreement this whole filter exists to prevent.
    """
    if "/uncategorized/" in (url or ""):
        return False
    t = title or ""
    # a year is the site's own mark of a film or show, and it outranks both
    # screens: "Music (2021)" is a film, "Music: Burna Boy - City Boys" is not
    if _HAS_YEAR_RE.search(t):
        return True
    if _NON_FILM_PREFIX_RE.search(t):
        return False
    return not _NON_FILM_HINT_RE.search(t)


def _cat_slugs():
    """{category id: slug} for the whole table, so a post's ids become names."""
    def fetch():
        try:
            rows = _api("/categories?per_page=100&_fields=id,slug")
        except RinkError as e:
            logger.warning("9ja category id lookup failed: %s", e)
            return {}
        return {r["id"]: (r.get("slug") or "").lower() for r in rows}

    return state._cat_slug_cache.get_or_set("all", fetch)


def _post_cats(pid):
    """Category slugs behind one post id; () when the site will not say.

    One request per id, which is why the caller runs these concurrently and
    keeps the answers for an hour: a post's categories do not change.
    """
    def fetch():
        try:
            row = _api(f"/posts/{pid}?_fields=id,categories")
        except RinkError as e:
            logger.warning("9ja post %s categories failed: %s", pid, e)
            return ()
        slugs = _cat_slugs()
        return tuple(s for s in (slugs.get(c) for c in row.get("categories") or ())
                     if s)

    return state._post_cat_cache.get_or_set(pid, fetch)


def _listed_flags(order, cards):
    """{post id: is it a film or show}, in one batch of parallel lookups.

    Browse gets its answer from the category in its URL; search has to ask per
    post, or the two screens disagree about what exists. A post whose category
    cannot be read falls back to the title screen rather than disappearing.
    """
    def verdict(pid):
        cats = _post_cats(pid)
        if cats:
            return any(_is_film_or_show(c) for c in cats)
        card = cards.get(pid) or {}
        return _looks_like_film(card.get("title"), card.get("url"))

    if not order:
        return {}
    # One connection opens per call, so these are mostly handshake: 12 at a
    # time turns a page of hits into about two rounds instead of one per hit.
    # Capped rather than matched to the page because this is not our site.
    with ThreadPoolExecutor(max_workers=min(12, len(order))) as pool:
        return dict(zip(order, pool.map(verdict, order)))
