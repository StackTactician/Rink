"""The private JSON API: its clock token, its JWT, and one request.

Requests share a pooled connection per thread, the way nkiri's REST calls do.
The API answers a 579 KB `/home` in about 2.4 s on a fresh TLS handshake and
in about 0.3 s on a socket that is already open, so a page that makes several
calls — one per episode — pays the handshake once instead of once per call.

Requests also opt out of transfer encoding (`Accept-Encoding: identity`).
Ask for gzip and the API answers chunked, and on a slow link that stream ends
with `IncompleteRead` part-way through a 579 KB body.
"""

import hashlib
import http.client
import json
import logging
import threading
import time
import urllib.parse

from ...config import TIMEOUT, UA
from ...errors import FetchError
from . import state
from .config import API, BASE

logger = logging.getLogger(__name__)

_api_host = urllib.parse.urlparse(API).netloc
_api_prefix = urllib.parse.urlparse(API).path
_conn = threading.local()

# ------------------------------------------------------------------ plumbing

def _client_token():
    """`<unix>,<md5 of the reversed unix>` — the API's clock-based client id."""
    ts = int(time.time())
    return f"{ts}," + hashlib.md5(str(ts)[::-1].encode()).hexdigest()


def _headers(token=None, referer=None):
    h = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "X-Client-Info": json.dumps({"timezone": "Africa/Lagos"}),
        "X-Request-Lang": "en",
        "User-Agent": UA,
        "Referer": referer or (BASE + "/"),
        "Origin": BASE,
    }
    if token:
        h["Authorization"] = "Bearer " + token
        h["Cookie"] = "token=" + token
    else:
        h["X-Client-Token"] = _client_token()
    return h


def _opened():
    conn = getattr(_conn, "conn", None)
    if conn is None:
        conn = http.client.HTTPSConnection(_api_host, timeout=TIMEOUT)
        _conn.conn = conn
    return conn


def _drop():
    conn = getattr(_conn, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _conn.conn = None


def _raw(path, token=None, referer=None, body=None, timeout=TIMEOUT):
    """One request over the pooled socket. Returns (status, headers, bytes).

    A pooled socket can be closed by the server while it idles, so a failure
    on the first attempt drops it and the call is retried once on a fresh one.
    """
    data = json.dumps(body).encode() if body is not None else None
    headers = _headers(token, referer)
    if data is not None:
        headers["Content-Type"] = "application/json"
    method = "POST" if data is not None else "GET"
    for attempt in (1, 2):
        conn = _opened()
        try:
            conn.request(method, _api_prefix + path, body=data, headers=headers)
            r = conn.getresponse()
            return r.status, r.headers, r.read()
        except Exception as e:
            _drop()
            if attempt == 2:
                raise FetchError(str(e)) from e
    raise FetchError(f"unreachable: {path}")


def _token_value(force=False):
    """The anonymous JWT, minted from /home and kept for an hour."""
    now = time.time()
    if not force and state._token["value"] and now - state._token["at"] < state._TOKEN_TTL:
        return state._token["value"]
    status, headers, _ = _raw("/home")
    if status != 200:
        raise FetchError(f"movibox token: HTTP {status}")
    try:
        token = json.loads(headers.get("x-user") or "{}").get("token")
    except ValueError:
        token = None
    if not token:
        raise FetchError("movibox token: no x-user header")
    state._token["value"], state._token["at"] = token, now
    return token


def _api(path, referer=None, body=None):
    """GET/POST a JSON path, re-minting the token once if it is refused."""
    for attempt in (1, 2):
        token = _token_value(force=attempt == 2)
        status, _headers_, raw = _raw(path, token, referer, body)
        if status == 200:
            try:
                payload = json.loads(raw)
            except ValueError as e:
                raise FetchError(f"invalid JSON from {path}: {e}") from e
            if payload.get("code") in (0, None):
                return payload.get("data") or {}
            raise FetchError(f"{path}: {payload.get('message')}")
        if status in (400, 401) and attempt == 1:
            continue                      # stale token: mint a new one
        raise FetchError(f"HTTP {status} from {path}")
    raise FetchError(f"unreachable: {path}")
