"""WordPress media id -> image URL, resolved in batches and cached.

One WP API call resolves up to 100 ids (`?include=1,2,3`), so a page of
24 posters costs one request instead of 24.

Successful lookups are cached for the process lifetime. Misses are cached
briefly (some media genuinely 401 / do not exist), while a *failed* batch is
never cached: a flaky upstream request must not blank a whole page of posters
until the server restarts.
"""

import logging
import threading
import urllib.parse
from collections import OrderedDict

from .cache import TTLCache
from .net import api_get, open_stream

logger = logging.getLogger(__name__)

_BATCH = 100

_hits = {}                    # (media_id, prefer) -> url
_misses = TTLCache(ttl=300)   # (media_id, prefer) -> True when known missing
_lock = threading.Lock()


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


SMALL = ("medium", "thumbnail")
LARGE = ("ocean-thumb-l", "large", "ocean-thumb-ml", "full")


def _pick_url(media, prefer=SMALL):
    """Prefer a chosen rendition: a 200x300 poster costs ~14KB against ~140KB."""
    sizes = (media.get("media_details") or {}).get("sizes") or {}
    for key in prefer:
        url = (sizes.get(key) or {}).get("source_url")
        if url:
            return url
    return media.get("source_url")


def _fetch_batch(ids, prefer=SMALL):
    """One API call for a group of ids. None means the call itself failed."""
    query = ",".join(str(i) for i in ids)
    try:
        data = api_get(f"/media?include={query}&per_page={_BATCH}"
                       f"&_fields=id,source_url,media_details")
    except Exception as e:
        logger.warning("media batch failed (%d ids): %s", len(ids), e)
        return None
    return {d["id"]: _pick_url(d, prefer) for d in data}


def media_urls(media_ids, prefer=SMALL):
    """Resolve many media ids at once. Returns {id: url or None}.

    Cache keys include the rendition, so a list view's 200x300 poster never
    shadows the larger detail-page request for the same media id.
    """
    ids = [i for i in dict.fromkeys(media_ids) if i]
    key = lambda i: (i, prefer)
    with _lock:
        missing = [i for i in ids if key(i) not in _hits and not _misses.get(key(i))]

    if missing:
        for chunk in _chunks(missing, _BATCH):
            found = _fetch_batch(chunk, prefer)
            if found is None:
                continue                      # transient: retry next request
            with _lock:
                for i in chunk:
                    url = found.get(i)
                    if url:
                        _hits[key(i)] = url
                        _misses.set(key(i), False)
                    else:
                        _misses.set(key(i), True)   # known missing / 401
                        _hits.pop(key(i), None)

    with _lock:
        return {i: _hits.get(key(i)) for i in ids}


def media_url(media_id, prefer=SMALL):
    """Resolve a single media id. None when unknown."""
    if not media_id:
        return None
    return media_urls([media_id], prefer).get(media_id)


def clear_cache():
    with _lock:
        _hits.clear()
        _misses.clear()
        _images.clear()
        _image_bytes.clear()


# ---------------------------------------------------------------- proxying
#
# The browser is a phone on the LAN talking plain HTTP to us. Pointing <img>
# at thenkiri.com makes every poster a separate cross-site request that fails
# quietly (hotlink rules, Cloudflare, VPN, flaky mobile DNS) — the card then
# shows its placeholder forever. Serving bytes from /api/img keeps the page
# same-origin and lets us cache decoded posters in front of the phone.

#: hosts whose images we will fetch on the browser's behalf
IMAGE_HOSTS = frozenset({"thenkiri.com", "www.thenkiri.com",
                         "9jarocks.net", "www.9jarocks.net"})

_MAX_IMAGE_BYTES = 40 * 1024 * 1024
_images = OrderedDict()       # url -> (bytes, ctype), LRU
_image_bytes = [0]
_MAX_ENTRY = 3 * 1024 * 1024  # ignore absurd originals


def proxy_url(url):
    """Local /api/img URL for an upstream image, or url unchanged."""
    if not url:
        return url
    host = urllib.parse.urlparse(url).netloc
    if host not in IMAGE_HOSTS:
        return url
    return "/api/img?u=" + urllib.parse.quote(url, safe="")


def image_allowed(url):
    p = urllib.parse.urlparse(url or "")
    return p.scheme in ("http", "https") and p.netloc in IMAGE_HOSTS


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
