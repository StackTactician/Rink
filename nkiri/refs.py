"""Resolve a post id or a thenkiri.com URL to a numeric post id."""

import re
import urllib.parse

from .config import BASE
from .net import api_get, http_get


def parse_ref(ref):
    """Accept a post id or a full thenkiri.com URL. Returns post id or None."""
    ref = (ref or "").strip()
    if ref.isdigit():
        return int(ref)

    m = re.search(r"thenkiri\.com/([^/]+)/?", ref)
    if not m:
        return None

    slug = m.group(1)
    # 1. resolve slug -> id via the search endpoint
    try:
        for r in api_get(f"/search?search={urllib.parse.quote(slug)}"):
            if r.get("url", "").rstrip("/").endswith("/" + slug):
                return r["id"]
    except Exception:
        pass

    # 2. fallback: fetch the page itself and read the embedded id
    try:
        raw, _ = http_get(f"{BASE}/{slug}/")
        m2 = re.search(r'"id":(\d+)', raw.decode("utf-8", "ignore"))
        if m2:
            return int(m2.group(1))
    except Exception:
        pass

    return None
