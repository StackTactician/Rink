"""Fetching an upstream image through this server.

Pointing <img> straight at a source's CDN makes every poster a separate
cross-site request that fails quietly (hotlink rules, Cloudflare, VPN, flaky
mobile DNS) — the card then shows its placeholder forever. Serving the bytes
from /api/img keeps the page same-origin and lets decoded posters be cached in
front of the phone.

The host list covers every source, so this stays outside the adapters: a
source that adds a host adds it here, and nothing else changes.
"""

import logging
import threading
import urllib.parse
from collections import OrderedDict

from .net import open_stream

logger = logging.getLogger(__name__)

#: hosts whose images we will fetch on the browser's behalf, taken from the
#: sources themselves: a new source declares its hosts in its META and this
#: list follows. Built on first use, because the sources import this module.
_HOSTS = None


def _hosts():
    """(exact hosts, CDN suffixes), read from every registered source."""
    global _HOSTS
    if _HOSTS is None:
        from .sources import SOURCES
        exact, suffixes = set(), set()
        for _src, meta in SOURCES:
            for host in meta.get("image_hosts", ()):
                (suffixes if host.startswith(".") else exact).add(host)
        _HOSTS = (frozenset(exact), tuple(sorted(suffixes)))
    return _HOSTS


def __getattr__(name):
    """IMAGE_HOSTS / IMAGE_HOST_SUFFIXES on demand, so importing this module
    early cannot deadlock against the sources that import it back."""
    if name == "IMAGE_HOSTS":
        return _hosts()[0]
    if name == "IMAGE_HOST_SUFFIXES":
        return _hosts()[1]
    raise AttributeError(name)


_MAX_IMAGE_BYTES = 40 * 1024 * 1024
_images = OrderedDict()       # url -> (bytes, ctype), LRU
_image_bytes = [0]
_MAX_ENTRY = 3 * 1024 * 1024  # ignore absurd originals
_lock = threading.Lock()


def https_only(url):
    """Upgrade an http image URL on a host we already proxy.

    Older uploads still carry http:// in their markup. The proxy speaks both,
    but a browser on an https page treats a plain-http subresource as mixed
    content and refuses it, so the scheme is settled here once rather than in
    every parser that reads a poster.
    """
    if (url or "").startswith("http://"):
        host = urllib.parse.urlparse(url).hostname or ""
        if _known_image_host(host):
            return "https://" + url[len("http://"):]
    return url


def _known_image_host(host):
    host = (host or "").lower()
    exact, suffixes = _hosts()
    return host in exact or host.endswith(suffixes)


def image_allowed(url):
    p = urllib.parse.urlparse(url or "")
    return (p.scheme in ("http", "https")
            and _known_image_host(p.netloc.split(":")[0]))


def fetch_image(url):
    """Cached bytes for an upstream image. Returns (bytes, ctype) or None."""
    with _lock:
        hit = _images.get(url)
        if hit is not None:
            _images.move_to_end(url)
            return hit

    try:
        with open_stream(url) as r:
            ctype = r.headers.get("Content-Type") or "application/octet-stream"
            data = r.read(_MAX_ENTRY + 1)
    except Exception as e:
        logger.warning("image fetch failed %s: %s", url, e)
        return None

    if not data:
        return None
    result = (data, ctype.split(";")[0].strip())
    if len(data) <= _MAX_ENTRY:
        with _lock:
            _images[url] = result
            _image_bytes[0] += len(data)
            while _image_bytes[0] > _MAX_IMAGE_BYTES and len(_images) > 1:
                _, (old, _ct) = _images.popitem(last=False)
                _image_bytes[0] -= len(old)
    return result
