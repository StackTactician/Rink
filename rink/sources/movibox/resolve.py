"""A movibox link is already the file: no chain, but a referer."""

import urllib.parse

from ...errors import FetchError
from .config import _FILE_HOST_RE, _FILE_REFERER

# ---------------------------------------------------------------- allowlists

def file_host_allowed(url):
    host = urllib.parse.urlparse(url or "").hostname or ""
    return bool(_FILE_HOST_RE.search(host))


def file_referer(url):
    """The referer the CDN insists on, or None for a host that wants none."""
    return _FILE_REFERER if file_host_allowed(url) else None


def resolve_host_allowed(url):
    """movibox hands out the file itself: there is no chain to walk."""
    return False


def resolve_info(url):
    """A movibox link is already the file, so resolving is a rename."""
    if not file_host_allowed(url):
        raise FetchError("not a movibox file")
    name = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1] or "download.mp4"
    return {"direct": url, "name": name}


def size_info(url):
    """Sizes arrive with the link, so there is nothing to look up."""
    return {"size": None, "bytes": None}


