"""The two ways this site answers: an HTML page, and a REST body."""

import html as htmllib
import json
import logging
import re
import urllib.request

from ..config import TIMEOUT, UA
from ..errors import FetchError
from .config import API

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ plumbing

def _get(url, timeout=TIMEOUT):
    """GET a page as text. Returns (text, final_url)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore"), r.geturl()
    except Exception as e:
        raise FetchError(str(e)) from e


def _api(path):
    """GET a WP REST path on this site. Returns the decoded body."""
    req = urllib.request.Request(API + path, headers={
        "User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read())
    except Exception as e:
        raise FetchError(str(e)) from e


def _unescape_js(s):
    """Undo the JSON escaping inside an Alpine x-data attribute."""
    s = s.replace("\\/", "/")
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    return htmllib.unescape(s)
