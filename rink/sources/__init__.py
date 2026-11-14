"""Source registry: more than one site behind the same JSON shapes.

Everything the web layer and the CLI ask for goes through here, so a new site
means one module and one entry in `_MODULES` — no endpoint changes, and no
branch anywhere else.

Three sources exist today:

  nkiri     thenkiri.com    1080p MKV on downloadwella, 2-step resolve
  9ja       9jarocks.net    540p x265 MKV on loadedfiles, 3-hop token chain
  movibox   movibox.net     signed MP4 on hakunaymatata, no chain at all

All three are peers under `sources/`, each a package with the same shape:
config, state, its own http or api, listing, post, resolve. Nothing about one
lives above or beside the others; what they share is in `rink/` itself.

**What a source has to provide.** Each package exports a `META` dict and the
same handful of functions, and this module never asks which one it is talking
to:

    META            id, label, site, kind, aliases, can_size, has_formats,
                    poster_aspect, image_hosts
    chips()         the chip row, in this source's own taxonomy
    formats()       the second axis, or [] when the site has only one
    latest()        newest uploads
    browse()        one page of a category
    search()        one page of hits
    parse_ref()     a post id from a number or a URL
    post_view()     the detail view model
    resolve_info()  a download link -> {direct, name, size}
    size_info()     {size, bytes} for one link
    file_host_allowed() / resolve_host_allowed() / file_referer()
    clear_cache()

Post ids are per-site and can collide, so every id and every cache key that
carries one is namespaced by source upstream of this module.
"""

import ipaddress
import logging
import urllib.parse

from ..net import open_stream
from ..page import page_payload
from . import jarocks, movibox, nkiri

logger = logging.getLogger(__name__)

#: display order, and the only place a source is named. Adding one is a line
#: here plus its package; nothing below this line knows any of them by name.
_MODULES = (nkiri, jarocks, movibox)

SOURCES = tuple((m.META["id"], m.META) for m in _MODULES)
_IDS = tuple(src for src, _meta in SOURCES)
DEFAULT = _MODULES[0].META["id"]

#: every id and alias a client might send, mapped to the id it means
_ALIASES = {alias: m.META["id"] for m in _MODULES for alias in m.META["aliases"]}
_ALIASES.update({src: src for src in _IDS})

#: the old constants, kept because the web layer and the tests name them
NKIRI, JAROCKS, MOVIBOX = _IDS


def norm(src):
    """Only a known source id or alias passes; anything else is the default."""
    return _ALIASES.get((src or "").strip().lower(), DEFAULT)


def mod(src):
    """The package behind a source id."""
    wanted = norm(src)
    for m in _MODULES:
        if m.META["id"] == wanted:
            return m
    return _MODULES[0]


def meta(src):
    return dict(mod(src).META)


def source_list():
    """For the toggle: everything the browser needs to draw a source."""
    return [{"id": m.META["id"], "label": m.META["label"],
             "site": m.META["site"], "kind": m.META["kind"],
             "can_size": m.META["can_size"],
             "has_formats": m.META["has_formats"],
             "poster_aspect": m.META["poster_aspect"]}
            for m in _MODULES]


# ------------------------------------------------------------------ listing

def menu(src):
    """Chip row for one source: its own taxonomy, nothing merged."""
    m = mod(src)
    return {"id": m.META["id"], "kind": m.META["kind"],
            "chips": m.chips(), "formats": m.formats()}


def latest(src, limit=24, page=1):
    return mod(src).latest(limit, page)


def browse(src, slug="", cat="", limit=24, page=1):
    """One page of one category, and nothing else.

    These sites answer a category that does not exist by serving their
    homepage — a 200 with somebody else's posts in it. Passed through, a
    request for a gone category would quietly return an unrelated page, so
    the slug is checked against the source's own taxonomy first and anything
    it does not list comes back empty. An empty taxonomy means the lookup
    failed rather than that nothing matches, so the source still answers.
    """
    m = mod(src)
    if slug:
        known = {c.get("slug") for c in m.chips()}
        if known and slug not in known:
            logger.info("browse: %s has no category %r", m.META["id"], slug)
            return page_payload([], page, limit)
    if cat:
        known = {f.get("slug") for f in m.formats()}
        if known and cat not in known:
            logger.info("browse: %s has no format %r", m.META["id"], cat)
            return page_payload([], page, limit)
    return m.browse(slug, limit, page, cat)


def search(src, query, limit=24, page=1):
    if not (query or "").strip():
        return page_payload([], page, limit, 0, 0)
    return mod(src).search(query, limit, page)


# --------------------------------------------------------------------- post

def parse_ref(src, ref):
    return mod(src).parse_ref(ref)


def post(src, ref):
    """Detail view model. Posters are upstream URLs: turning one into a
    same-origin /api/img link is the web layer's job, not the engine's."""
    m = mod(src)
    view = m.post_view(ref)
    # the card/star machinery keys watchlist entries by src, so carry it back
    view["src"] = m.META["id"]
    return view


# ---------------------------------------------------------------- resolving
#
# A link always points at one site's file host, so the host decides which
# source answers — a link pasted from the wrong tab still works.

def _owner(url):
    """The source whose file hosts include this URL, or None."""
    for m in _MODULES:
        if m.file_host_allowed(url) or m.resolve_host_allowed(url):
            return m
    return None


def resolve(url, referer=None):
    """Resolve a download link from any site."""
    owner = _owner(url)
    if owner is not None:
        return owner.resolve_info(url)
    if not (urllib.parse.urlparse(url or "").hostname or ""):
        raise ValueError("missing url")
    # an unknown host: the default source's chain is the only one that takes a
    # referer, and it is the one a bare link has always meant
    return _MODULES[0].resolve_info(url, referer or (_MODULES[0].META["site"] + "/"))


def size(src, url):
    """{size, bytes} for one link, when the source can answer cheaply.

    The host decides first and the tab second: a link always points at one
    site's file host, so a client that forgets ?src — an old cached asset, a
    page opened from the watchlist — still gets the size it asked for instead
    of an empty answer from the wrong resolver.
    """
    owner = _owner(url)
    if owner is not None and not owner.META["can_size"]:
        # the size came with the link; its file page has nothing to add
        return {"size": None, "bytes": None}
    order = ([owner] if owner is not None else []) + [m for m in _MODULES
                                                      if m is not owner]
    for m in order:
        if not m.META["can_size"]:
            continue
        found = m.size_info(url)
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


def _url_ok(url):
    p = urllib.parse.urlparse(url or "")
    return p.scheme in ("http", "https") and _public_host(p.hostname or "")


def file_allowed(url):
    return _url_ok(url) and any(m.file_host_allowed(url) for m in _MODULES)


def resolve_allowed(url):
    """Can /api/resolve be pointed at this URL?

    `_owner` is the allowlist: a source that walks a chain says so with
    resolve_host_allowed, and one that hands out the file itself — movibox —
    answers with file_host_allowed. Asking only the first rejected every link
    that needed no chain.
    """
    return _url_ok(url) and _owner(url) is not None


def file_referer(url, fallback=None):
    """The referer a file host demands, or `fallback` for one that wants none.

    A downloader that shells out to curl needs this: the movibox CDN answers
    429 to a request that arrives without a movibox referer.
    """
    for m in _MODULES:
        referer = m.file_referer(url)
        if referer:
            return referer
    return fallback


def stream(url, headers=None):
    """Open a direct file for proxying, with whatever its host insists on.

    movibox's CDN answers 429 to a request that arrives without a movibox
    referer, so the referer travels with the stream rather than with the
    browser — the phone never talks to the CDN itself.
    """
    extra = dict(headers or {})
    referer = file_referer(url)
    if referer:
        extra.setdefault("Referer", referer)
    return open_stream(url, headers=extra)


def clear_cache():
    for m in _MODULES:
        m.clear_cache()
