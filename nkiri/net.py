"""HTTP primitives. Every network call in the project goes through here."""

import http.client
import json
import logging
import threading
import urllib.parse
import urllib.request

from .config import API, FORM_TIMEOUT, HEAD_TIMEOUT, STREAM_TIMEOUT, TIMEOUT, UA
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


def _json_load(raw, path):
    try:
        return json.loads(raw)
    except ValueError as e:
        raise FetchError(f"invalid JSON from {path}: {e}") from e


# The WP API lives on one host, so each worker thread keeps one HTTPS
# connection alive instead of paying a TLS handshake per call.
_api_host = urllib.parse.urlparse(API).netloc
_api_prefix = urllib.parse.urlparse(API).path
_api_local = threading.local()


def _api_conn():
    conn = getattr(_api_local, "conn", None)
    if conn is None:
        conn = http.client.HTTPSConnection(_api_host, timeout=TIMEOUT)
        _api_local.conn = conn
    return conn


def _api_drop():
    conn = getattr(_api_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _api_local.conn = None


def _api_raw(path):
    """GET {API}{path} over a pooled connection. Returns (body, headers)."""
    headers = {"User-Agent": UA, "Accept": "*/*",
               "Accept-Language": "en-US,en;q=0.9"}
    for attempt in (1, 2):
        conn = _api_conn()
        try:
            conn.request("GET", _api_prefix + path, headers=headers)
            resp = conn.getresponse()
            body = resp.read()
            if resp.status >= 400:
                raise FetchError(f"HTTP {resp.status} from {path}")
            return body, resp.headers
        except FetchError:
            raise
        except Exception as e:
            # a pooled socket may have been closed by the server while idle
            _api_drop()
            if attempt == 2:
                raise FetchError(str(e)) from e
    raise FetchError(f"unreachable: {path}")


def api_get(path):
    """GET a WP-JSON path (appended to API) and decode it."""
    raw, _ = _api_raw(path)
    return _json_load(raw, path)


def api_get_page(path):
    """GET a WP-JSON collection path.

    Returns (items, total, total_pages) reading the X-WP-Total and
    X-WP-TotalPages headers WP sends for paginated collections.
    """
    raw, headers = _api_raw(path)
    data = _json_load(raw, path)
    return data, _int_header(headers, "X-WP-Total"), _int_header(headers, "X-WP-TotalPages")


def _int_header(headers, name):
    try:
        return int(headers.get(name) or 0) or None
    except (TypeError, ValueError):
        return None


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


def open_stream(url, timeout=STREAM_TIMEOUT):
    """Open a text/file URL for chunked reading. Caller closes."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
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
