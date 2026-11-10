"""Source registry: more than one site behind the same JSON shapes.

Everything the web layer and the CLI ask for goes through here, so a new site
means one module and one entry in SOURCES — no endpoint changes.

Two sources exist today:

  nkiri     thenkiri.com    1080p MKV on downloadwella, 2-step resolve
  9ja       9jarocks.net    540p x265 MKV on loadedfiles, 3-hop token chain

Post ids are per-site and can collide, so every id and every cache key that
carries one is namespaced by source upstream of this module.
"""

import ipaddress
import logging
import urllib.parse

from . import jarocks
from .catalog import browse as _nkiri_browse
from .config import BASE
from .catalog import format_names, formats, genre_names, genres, public
from .content import parse_post_view
from .download import (direct_url_allowed, landing_size, resolve_info,
                       resolve_target_allowed)
from .media import proxy_url
from .posts import get_post, latest as _nkiri_latest, page_payload
from .posts import search_results
from .refs import parse_ref as _nkiri_ref

logger = logging.getLogger(__name__)

NKIRI = "nkiri"
JAROCKS = "9ja"
DEFAULT = NKIRI

#: ordered: the toggle renders in this order
SOURCES = (
    (NKIRI, {"label": "Nkiri", "site": "https://thenkiri.com",
             "kind": "genre"}),
    (JAROCKS, {"label": "9jarocks", "site": "https://9jarocks.net",
               "kind": "category"}),
)
_IDS = tuple(src for src, _meta in SOURCES)


def norm(src):
    """Only a known source id passes; anything else is the default."""
    src = (src or "").strip().lower()
    if src in ("jarocks", "9jarocks"):
        return JAROCKS
    return src if src in _IDS else DEFAULT


def meta(src):
    src = norm(src)
    return dict(next(m for s, m in SOURCES if s == src), id=src)


def source_list():
    """For the toggle: [{id, label}] in display order."""
    return [{"id": src, "label": m["label"]} for src, m in SOURCES]


# ------------------------------------------------------------------ listing

def menu(src):
    """Chip row for one source: its own taxonomy, nothing merged.

    nkiri files genres as tags and origin as categories, so it gets both.
    jarocks only has real categories, and those are the chips.
    """
    src = norm(src)
    if src == JAROCKS:
        return {"id": src, "kind": "category",
                "chips": [{k: c[k] for k in ("slug", "name", "count")}
                          for c in jarocks.menu()],
                "formats": []}
    return {"id": src, "kind": "genre",
            "chips": public(genres()), "formats": public(formats())}


def _proxy_list(payload):
    """Point every poster at the local image proxy, as thenkiri's lists do.

    Same-origin keeps the phone off the other site's CDN, and the proxy
    already caps and caches what it holds."""
    for item in payload.get("items") or ():
        item["poster"] = proxy_url(item.get("poster"))
    return payload


def latest(src, limit=24, page=1):
    src = norm(src)
    if src == JAROCKS:
        return _proxy_list(jarocks.latest(limit, page))
    return _nkiri_latest(limit, page)


def browse(src, slug="", cat="", limit=24, page=1):
    src = norm(src)
    if src == JAROCKS:
        # jarocks has one axis: slug is a category
        return _proxy_list(jarocks.browse(slug, limit, page))
    return _nkiri_browse(slug, cat, limit, page)


def search(src, query, limit=24, page=1):
    src = norm(src)
    if not (query or "").strip():
        return page_payload([], page, limit, 0, 0)
    if src == JAROCKS:
        return _proxy_list(jarocks.search(query, limit, page))
    return search_results(query, limit, page)


# --------------------------------------------------------------------- post

def parse_ref(src, ref):
    src = norm(src)
    if src == JAROCKS:
        return jarocks.parse_ref(ref)
    return _nkiri_ref(ref)


def post(src, ref):
    """Detail view model, posters already pointed at the local proxy."""
    src = norm(src)
    if src == JAROCKS:
        view = jarocks.post_view(int(ref))
    else:
        view = parse_post_view(get_post(int(ref)))
        view["genres"] = genre_names(view.pop("tag_ids", []))
        view["formats"] = format_names(view.pop("cat_ids", []))
    view["poster"] = proxy_url(view.get("poster"))
    # the card/star machinery keys watchlist entries by src, so carry it back
    view["src"] = src
    return view


# ---------------------------------------------------------------- resolving

def resolve(url, referer=None):
    """Resolve a download link from either site. The host decides, so a link
    pasted from the wrong tab still works."""
    host = urllib.parse.urlparse(url or "").hostname or ""
    if jarocks.resolve_host_allowed(url) or jarocks.file_host_allowed(url):
        return jarocks.resolve_info(url)
    if not host:
        raise ValueError("missing url")
    # thenkiri's 2-step form expects the post page as its referer
    return resolve_info(url, referer or (BASE + "/"))


def size(src, url):
    """{size, bytes} for one link, when the source can answer cheaply.

    The host decides first and the tab second: a link always points at one
    site's file host, so a client that forgets ?src — an old cached asset, a
    page opened from the watchlist — still gets the size it asked for instead
    of an empty answer from the wrong resolver.
    """
    lookups = ((jarocks.size_info, landing_size)
               if jarocks.resolve_host_allowed(url)
               else (landing_size, jarocks.size_info))
    for lookup in lookups:
        found = lookup(url)
        if found.get("size"):
            return found
    return {"size": None, "bytes": None}


# ---------------------------------------------------------------- allowlists
#
# The proxy fetches whatever URL it is handed, so both endpoints are strict:
# a known file host (or the CDN it redirects to), and never a literal private
# address. One shared check, because a new source must not widen the SSRF hole.

def _public_host(host):
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def file_allowed(url):
    p = urllib.parse.urlparse(url or "")
    if p.scheme not in ("http", "https") or not _public_host(p.hostname or ""):
        return False
    return direct_url_allowed(url) or jarocks.file_host_allowed(url)


def resolve_allowed(url):
    p = urllib.parse.urlparse(url or "")
    if p.scheme not in ("http", "https") or not _public_host(p.hostname or ""):
        return False
    return resolve_target_allowed(url) or jarocks.resolve_host_allowed(url)


def clear_cache():
    jarocks.clear_cache()
