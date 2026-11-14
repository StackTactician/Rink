"""Search: REST decides the matches, the search page supplies the posters."""

import logging
import urllib.parse

from ...errors import RinkError
from ...page import page_payload
from . import state
from .config import BASE
from .filters import _listed_flags
from .http import _api, _get
from .listing import _cards

logger = logging.getLogger(__name__)

def search(query, limit=24, page=1):
    """Search. REST decides *which* posts match and in what order; the search
    page supplies the posters for those ids, because the REST search result
    carries no media. Neither of those states a category, so each hit's own
    record is asked (`_listed_flags`).

    Filtering after REST means a page can come back short of `limit`. That is
    left alone on purpose: over-fetching to refill it would shift the offset
    REST pages by, and results would fall down the gap between two pages.
    """
    query = (query or "").strip()
    if not query:
        return page_payload([], page, limit)

    def fetch():
        q = urllib.parse.quote(query)
        try:
            rows = _api(f"/search?search={q}&per_page={limit}"
                        f"&subtype=post&page={page}")
        except RinkError as e:
            logger.warning("9ja search failed %r: %s", query, e)
            return page_payload([], page, limit)
        order = [r["id"] for r in rows if r.get("subtype", "post") == "post"]

        try:
            text, _ = _get(f"{BASE}/?s={q}&paged={page}")
            cards = {c["id"]: c for c in _cards(text)}
        except RinkError:
            cards = {}

        listed = _listed_flags(order, cards)
        # a hit REST matched but the page rendered no card for used to become a
        # blank row: no title, no poster, and now no category to judge either,
        # so it is left out rather than drawn as a titleless tile
        items = [cards[pid] for pid in order
                 if listed.get(pid) and pid in cards]
        return page_payload(items, page, limit, total=None,
                            total_pages=(page + 1) if len(rows) >= limit else page)

    return state._search_cache.get_or_set((query.lower(), limit, page), fetch)
