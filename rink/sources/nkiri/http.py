"""The REST side: a threaded connection pool to one WordPress site."""

import http.client
import json
import logging
import threading
import urllib.parse

from ...config import FORM_TIMEOUT, TIMEOUT, UA
from ...errors import FetchError
from .config import API

logger = logging.getLogger(__name__)

_api_host = urllib.parse.urlparse(API).netloc
_api_prefix = urllib.parse.urlparse(API).path
_api_local = threading.local()

def _json_load(raw, path):
    try:
        return json.loads(raw)
    except ValueError as e:
        raise FetchError(f"invalid JSON from {path}: {e}") from e


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
