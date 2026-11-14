"""The private JSON API: its clock token, its JWT, and one request."""

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request

from ..config import TIMEOUT, UA
from ..errors import FetchError
from . import state
from .config import API, BASE

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ plumbing

def _client_token():
    """`<unix>,<md5 of the reversed unix>` — the API's clock-based client id."""
    ts = int(time.time())
    return f"{ts}," + hashlib.md5(str(ts)[::-1].encode()).hexdigest()


def _headers(token=None, referer=None):
    h = {
        "Accept": "application/json",
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


def _raw(path, token=None, referer=None, body=None, timeout=TIMEOUT):
    """One request. Returns (status, headers, bytes)."""
    data = json.dumps(body).encode() if body is not None else None
    headers = _headers(token, referer)
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except Exception as e:
        raise FetchError(str(e)) from e


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
