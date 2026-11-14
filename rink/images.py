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

#: hosts whose images we will fetch on the browser's behalf
IMAGE_HOSTS = frozenset({"thenkiri.com", "www.thenkiri.com",
                         "9jarocks.net", "www.9jarocks.net"})

#: a source whose artwork lives on a family of CDN subdomains: movibox serves
#: covers from pbcdn / pbcdnw / h5-static, and the exact host changes per image
IMAGE_HOST_SUFFIXES = (".aoneroom.com",)

_MAX_IMAGE_BYTES = 40 * 1024 * 1024
_images = OrderedDict()       # url -> (bytes, ctype), LRU
_image_bytes = [0]
_MAX_ENTRY = 3 * 1024 * 1024  # ignore absurd originals
_lock = threading.Lock()


def _known_image_host(host):
    host = (host or "").lower()
    return host in IMAGE_HOSTS or host.endswith(IMAGE_HOST_SUFFIXES)


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
