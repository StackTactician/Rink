"""HTTP verbs, with no idea which site they are talking to.

The REST pool that used to live here belongs to thenkiri, so it moved into
that source; what is left is what every source and the web layer share.
"""

import logging
import urllib.parse
import urllib.request

from .config import FORM_TIMEOUT, HEAD_TIMEOUT, STREAM_TIMEOUT, TIMEOUT, UA
from .errors import FetchError

logger = logging.getLogger(__name__)

def http_get_with_headers(url, referer=None, timeout=TIMEOUT):
    """GET url. Returns (body_bytes, final_url, headers)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    if referer:
        req.add_header("Referer", referer)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.geturl(), r.headers
    except Exception as e:
        raise FetchError(str(e)) from e


def http_get(url, referer=None, timeout=TIMEOUT):
    """GET url. Returns (body_bytes, final_url)."""
    body, final_url, _ = http_get_with_headers(url, referer, timeout)
    return body, final_url


def post_form(url, fields, referer=None, timeout=FORM_TIMEOUT):
    """URL-encoded POST. Returns (body_bytes, final_url)."""
    body = urllib.parse.urlencode(fields).encode()
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.geturl()
    except Exception as e:
        raise FetchError(str(e)) from e


def open_stream(url, timeout=STREAM_TIMEOUT, headers=None):
    """Open a text/file URL for chunked reading. Caller closes.

    `headers` carries what a host demands before it serves bytes — a referer
    for movibox's CDN, a Range for a seek in the player.
    """
    hdrs = {"User-Agent": UA}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, headers=hdrs)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except Exception as e:
        raise FetchError(str(e)) from e


def head_size(url, timeout=HEAD_TIMEOUT):
    """Content-Length of url via HEAD, or None when unavailable."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(r.headers.get("Content-Length") or 0) or None
    except Exception as e:
        logger.warning("HEAD size lookup failed for %s: %s", url, e)
        return None
