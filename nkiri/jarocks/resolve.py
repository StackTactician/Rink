"""Turning a link into a file: the three-hop token chain on loadedfiles."""

import html as htmllib
import logging
import re
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

from ..config import TIMEOUT, UA
from ..download import BRAND
from ..errors import DownloadError, FetchError, NkiriError
from ..text import parse_size, strip_tags
from . import state
from .config import BASE, _CDN_HOST_RE, _FILE_HOST_RE
from .http import _get, _unescape_js

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- resolving
#
# loadedfiles.net does not hand out a file from the landing page the way
# downloadwella does. Each request mints a new single-use `pt` token:
#
#   1. GET /<hash>/<name>.mkv      sets a `filehosting` cookie, offers a
#                                  "Proceed To Download Page" link with pt=T1
#   2. GET /<hash>?pt=T1           the real page; its Alpine data block embeds
#                                  link: 'https://loadedfiles.net/…?pt=T2'
#   3. GET /<hash>?pt=T2           302 -> https://NN.static.gfrdaseazzs.com/…
#
# The token in step 2 is JSON-escaped (\/ and \uXXXX and %253D), so it has to
# be decoded three times over before it is a URL.

_PROCEED_RE = re.compile(
    r'href="(https?://loadedfiles\.net/[0-9a-f]{8,}\?pt=[^"]+)"', re.I)
_ALPINE_LINK_RE = re.compile(r"link:\s*'((?:[^'\\]|\\.)*)'")


def _opener():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar()))


def _open(opener, url, referer=None, extra=None, timeout=TIMEOUT):
    headers = {"User-Agent": UA, "Accept": "text/html,*/*",
               "Accept-Language": "en-US,en;q=0.9"}
    if referer:
        headers["Referer"] = referer
    if extra:
        headers.update(extra)
    return opener.open(urllib.request.Request(url, headers=headers),
                       timeout=timeout)


def resolve_direct(link_url, timeout=TIMEOUT):
    """Follow the token chain. Returns (direct_url, size_bytes, name)."""
    opener = _opener()

    with _open(opener, link_url, timeout=timeout) as r:
        page = r.read().decode("utf-8", "ignore")

    hop = _PROCEED_RE.search(page)
    if not hop:
        # a direct file link, or the host changed shape under us
        return link_url, None, _filename(link_url)

    token_url = htmllib.unescape(hop.group(1))
    with _open(opener, token_url, referer=link_url, timeout=timeout) as r:
        page2 = r.read().decode("utf-8", "ignore")

    m = _ALPINE_LINK_RE.search(page2)
    if not m:
        raise DownloadError("loadedfiles: no download link on the page")
    target = _unescape_js(m.group(1))

    # the final hop answers with the file itself; one byte is enough to learn
    # the real URL and the total size, and it costs nothing on a 500 MB file
    r = _open(opener, target, referer=token_url,
              extra={"Range": "bytes=0-0"}, timeout=timeout)
    try:
        direct = r.geturl()
        total = _total_from_range(r.headers.get("Content-Range"))
        disposition = r.headers.get("Content-Disposition") or ""
    finally:
        try:
            r.close()
        except Exception:
            pass

    return direct, total, _filename(direct, disposition)


def _total_from_range(header):
    m = re.search(r"/\s*(\d+)\s*$", header or "")
    return int(m.group(1)) if m else None


def _filename(direct, disposition=""):
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disposition, re.I)
    raw = m.group(1) if m else urllib.parse.unquote(
        urllib.parse.urlparse(direct).path.rsplit("/", 1)[-1])
    raw = htmllib.unescape(raw or "") or "download.mkv"
    # 'X.(9jaRocks.Com).mkv' -> 'X.Rink.mkv'
    stem, dot, ext = raw.rpartition(".")
    stem = re.sub(r"[\[\(](?:9jarocks\.com|9ja[^\]\)]*)[\]\)]", "", stem,
                  flags=re.I)
    stem = re.sub(r"[._\- ]{2,}", ".", stem).strip("._- ") or "download"
    if BRAND.lower() not in stem.lower():
        stem = f"{stem}.{BRAND}"
    return stem + (dot + ext if dot else "")


def resolve_info(link_url):
    """{direct, name, size} for the download button, same shape as thenkiri's."""
    direct, size, name = resolve_direct(link_url)
    return {"direct": direct, "name": name, "size": size}


#: the host prints "<filename>.mkv 200.55 MB" beside its download button, and
#: the same page also advertises "upload files up to 3.79 GB", so the match is
#: anchored to the file extension rather than to the number alone
_SIZE_AFTER_FILE_RE = re.compile(
    r"\.(?:mkv|mp4|avi|mov|m4v|webm|mp3|zip|rar)\s+([0-9.]+)\s*([KMGT]i?B)", re.I)


def size_info(url):
    """Per-link size from the file host's own page: one GET, cached.

    The post page prints a size for a single file, so every episode row of a
    season goes unanswered there; this asks the host each row points at.
    """
    def fetch():
        try:
            raw, _ = _get(url)
        except NkiriError as e:
            logger.warning("9ja size lookup failed %s: %s", url, e)
            return {"size": None, "bytes": None}
        m = _SIZE_AFTER_FILE_RE.search(strip_tags(raw))
        if not m:
            return {"size": None, "bytes": None}
        text = f"{m.group(1)} {m.group(2).upper()}"
        return {"size": text, "bytes": parse_size(text)}

    return state._size_cache.get_or_set(url, fetch)


# ----------------------------------------------------------------- allowlist

def file_host_allowed(url):
    """May the proxy stream this URL? Direct file host or the CDN only."""
    p = urllib.parse.urlparse(url or "")
    host = p.hostname or ""
    return (p.scheme in ("http", "https")
            and bool(_FILE_HOST_RE.search(host) or _CDN_HOST_RE.search(host)))


def resolve_host_allowed(url):
    """May /api/resolve be pointed here? A landing page, not the CDN."""
    p = urllib.parse.urlparse(url or "")
    host = p.hostname or ""
    return p.scheme in ("http", "https") and bool(_FILE_HOST_RE.search(host))


