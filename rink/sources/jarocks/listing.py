"""What the site shows: cards, the feed, categories, and their pages."""

import html as htmllib
import logging
import re
import urllib.parse

from ...errors import RinkError
from ...page import page_payload
from ...text import clean_title
from . import state
from .config import BASE, _id_from_url, _is_film_or_show
from .http import _api, _get

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ listing

#: a card is one <li class="post-item">; the attrs inside it carry everything
_CARD_SPLIT_RE = re.compile(r'<li[^>]*class="[^"]*\bpost-item\b', re.I)
_POST_HREF_RE = re.compile(
    r'href="(https://9jarocks\.net/videodownload/[^"]*?-id(\d+)\.html)"', re.I)
_ARIA_RE = re.compile(r'aria-label="([^"]*)"')
#: WordPress lists a resized copy beside the real file: a poster that is
#: 666x1000 becomes -390x220 on the way out, and that is a center crop, so the
#: bottom of the artwork (usually the title) is cut off
_WP_THUMB_SUFFIX_RE = re.compile(r"-\d+x\d+(?=\.[A-Za-z]{2,4}$)")


def _full_poster(url):
    """The uncropped original behind a resized listing thumbnail."""
    return _WP_THUMB_SUFFIX_RE.sub("", url or "")
_THUMB_RE = re.compile(
    r'(?:data-src|src)="(https://9jarocks\.net/wp-content/uploads/[^"]+)"', re.I)

_FEED_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
_FEED_DATE_RE = re.compile(r"<pubDate>(.*?)</pubDate>", re.S)


def _cards(page):
    """Post cards in document order: id, title, url, poster."""
    blocks = _CARD_SPLIT_RE.split(page)[1:]
    out, seen = [], set()
    for block in blocks:
        href = _POST_HREF_RE.search(block)
        if not href:
            continue
        pid = int(href.group(2))
        if pid in seen:
            continue
        seen.add(pid)
        title = _ARIA_RE.search(block)
        poster = _THUMB_RE.search(block)
        out.append({
            "id": pid,
            # card labels carry the rating widget's numbers too: "Title 4 (4)"
            "title": clean_title(_strip_feed_junk(
                htmllib.unescape(title.group(1)) if title else "")),
            "url": href.group(1),
            "date": "",
            "poster": _full_poster(
                htmllib.unescape(poster.group(1))) if poster else "",
        })
    return out


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        out.append(it)
    return out


def menu():
    """Categories to show as chips, biggest first."""
    def fetch():
        try:
            rows = _api("/categories?per_page=100&_fields=id,name,slug,count")
        except Exception as e:
            logger.warning("9ja category lookup failed: %s", e)
            return []
        out = [{"id": r["id"], "slug": r["slug"],
                "name": htmllib.unescape(r.get("name") or r["slug"]),
                "count": r.get("count", 0)}
               for r in rows
               if _is_film_or_show(r.get("slug")) and r.get("count", 0) > 0]
        out.sort(key=lambda c: -c["count"])
        return out

    return state._menu_cache.get_or_set("all", fetch)


def _feed_page(page):
    """Newest uploads, restricted to the film/show categories.

    WordPress honours `cat=<ids>` on a feed, so one request replaces a merge
    of sixteen category feeds. Without the ids (the category table failed)
    the site-wide feed is the fallback, and the title filter still drops the
    obvious music.
    """
    cats = [str(c["id"]) for c in menu()]
    if cats:
        text, _ = _get(f"{BASE}/feed?cat={','.join(cats)}&paged={page}")
    else:
        logger.warning("9ja feed: no categories, falling back to all posts")
        text, _ = _get(f"{BASE}/feed?paged={page}")
    items = []
    for raw in _FEED_ITEM_RE.findall(text):
        link = re.search(r"<link>(https://9jarocks\.net/videodownload/[^<]+)</link>",
                         raw)
        if not link:
            continue
        href = link.group(1)
        pid = _id_from_url(href)
        if not pid:
            continue
        title = re.search(r"<title>(.*?)</title>", raw, re.S)
        date = _FEED_DATE_RE.search(raw)
        poster = re.search(
            r'<img[^>]+src="(https://9jarocks\.net/wp-content/uploads/[^"]+)"',
            raw, re.I)
        items.append({
            "id": pid,
            "title": clean_title(_strip_feed_junk(htmllib.unescape(
                title.group(1))) if title else ""),
            "url": href,
            "date": _rfc822(date.group(1)) if date else "",
            "poster": _full_poster(
                htmllib.unescape(poster.group(1))) if poster else "",
        })
    # a feed page is always the same size, so a full one means there is a next
    return _dedupe(items), len(items) >= 20


_MONTHS = {m: i + 1 for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}
_RFC822_RE = re.compile(r",\s*(\d{1,2})\s+(\w{3})\s+(\d{4})")


def _rfc822(text):
    """'Tue, 10 Nov 2026 08:16:34 +0000' -> '2026-11-10'."""
    m = _RFC822_RE.search(text or "")
    if not m:
        return ""
    day, mon, year = m.groups()
    month = _MONTHS.get(mon[:3].title())
    if not month:
        return ""
    return f"{year}-{month:02d}-{int(day):02d}"


def _strip_feed_junk(title):
    """Feeds and cards append the rating widget and comment count, and the
    rating is sometimes a decimal: 'Title (2025) 4.6 (9)'."""
    return re.sub(r"\s+\d+(?:\.\d+)?\s*\(\d+\)\s*$", "", title or "").strip()


def latest(limit=24, page=1):
    """Newest uploads. One feed page holds 22 items, so a page is one request."""
    def fetch():
        items, more = _feed_page(page)
        items = items[:limit]
        return page_payload(items, page, limit,
                            total=None,
                            total_pages=(page + 1) if more else page)

    return state._latest_cache.get_or_set((limit, page), fetch)


def _category_url(slug, page):
    path = f"/category/videodownload/{urllib.parse.quote(slug)}"
    if page > 1:
        path += f"/page/{page}"
    return BASE + path + "/"


def browse(slug="", limit=24, page=1):
    """One page of a category, or the newest uploads when no category given."""
    if not slug:
        return latest(limit, page)

    def fetch():
        try:
            text, _ = _get(_category_url(slug, page))
        except RinkError:
            # the nested taxonomy path is the site's own menu link; a flat
            # /category/<slug>/ is what older permalinks still use
            try:
                text, _ = _get(f"{BASE}/category/{urllib.parse.quote(slug)}/"
                               + (f"page/{page}/" if page > 1 else ""))
            except RinkError as e:
                logger.warning("9ja browse failed %s p%d: %s", slug, page, e)
                return page_payload([], page, limit)
        items = _cards(text)[:limit]
        more = len(items) >= min(limit, 20)
        return page_payload(items, page, limit, total=None,
                            total_pages=(page + 1) if more else page)

    return state._browse_cache.get_or_set((slug, limit, page), fetch)
