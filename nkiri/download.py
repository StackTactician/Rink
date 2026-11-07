"""Download engine: 2-step downloadwella resolution + file transfer.

The web UI never stores files server-side (the browser fetches and saves);
the CLI uses `download_file` (curl) to write to disk.
"""

import html as htmllib
import ipaddress
import logging
import os
import re
import subprocess
import urllib.parse

from .cache import TTLCache
from .config import BASE, UA
from .errors import DownloadError, NkiriError
from .net import head_size, http_get, post_form
from .text import parse_size

logger = logging.getLogger(__name__)

_DIRECT_RE = re.compile(r'href="(https?://[^"]*?\.downloadwella\.com/d/[^"]+)"')
_FORM_RE = re.compile(r'<form[^>]*name="F1"[^>]*>(.*?)</form>', re.S)
_FIELD_RE = re.compile(r'name="([^"]+)"\s+value="([^"]*)"')

# Files arrive named like "The.Assassin.S02E01.(THENKIRI.COM).mkv".
# Strip the source-site tag and brand the file with ours instead.
BRAND = "Rink"
_SITE_TAG_RE = re.compile(
    r"[._\- ]*[\(\[\{]?\s*(?:www\.)?(?:thenkiri\.com|nkiri\.ink|nkiri\.com|"
    r"thenkiri|nkiri|dramakey\.com|dramakey)\s*[\)\]\}]?[._\- ]*",
    re.I)


# ------------------------------------------------------------ url validation
#
# /api/resolve and /api/file take a URL from the browser and make the server
# fetch it. Unvalidated, that is an open proxy: it burns the host's egress and,
# worse, lets a caller reach addresses only the server can see (loopback,
# private ranges, link-local metadata endpoints). Both endpoints now reject
# anything outside the file hosts this app actually produces.

FILE_HOST_RE = re.compile(
    r"(^|\.)(?:downloadwella\.com|mega\.nz|mega\.co\.nz|mediafire\.com|"
    r"dropbox\.com|dropboxusercontent\.com|drive\.google\.com|"
    r"googleusercontent\.com)$", re.I)

#: what downloadwella hands back once the 2-step is done
_DIRECT_PATH_RE = re.compile(r"^/d/", re.I)


def _public_host(host):
    """False for loopback, private, link-local or otherwise non-public hosts."""
    host = (host or "").lower().strip(".")
    if (not host or host == "localhost"
            or host.endswith(".local") or host.endswith(".internal")):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True                      # a name: DNS decides, not us
    return not (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def resolve_target_allowed(url):
    """Can /api/resolve be pointed at this URL?"""
    p = urllib.parse.urlparse(url or "")
    host = p.hostname or ""
    return (p.scheme in ("http", "https")
            and _public_host(host)
            and bool(FILE_HOST_RE.search(host)))


def direct_url_allowed(url):
    """Can /api/file stream this URL? Stricter: a resolved direct link."""
    p = urllib.parse.urlparse(url or "")
    host = p.hostname or ""
    return (p.scheme in ("http", "https")
            and _public_host(host)
            and bool(FILE_HOST_RE.search(host))
            and bool(_DIRECT_PATH_RE.match(p.path or "")))


def resolve_direct(url, referer=BASE + "/"):
    """Follow the downloadwella (sibsoft) 2-step to get the direct file URL."""
    cur, ref = url, referer
    for _ in range(4):
        raw, final_url = http_get(cur, referer=ref)
        page = raw.decode("utf-8", "ignore")

        m = _DIRECT_RE.search(page)
        if m:
            return htmllib.unescape(m.group(1))

        fm = _FORM_RE.search(page)
        if fm:
            fields = {htmllib.unescape(k): htmllib.unescape(v)
                      for k, v in _FIELD_RE.findall(fm.group(1))}
            raw2, cur2 = post_form(final_url, fields, referer=ref)
            m2 = _DIRECT_RE.search(raw2.decode("utf-8", "ignore"))
            if m2:
                return htmllib.unescape(m2.group(1))
            cur, ref = cur2, final_url
            continue

        # no further step: this already is the file
        return final_url
    return cur


def brand_name(name):
    """'The.Assassin.S02E01.(THENKIRI.COM).mkv' -> 'The.Assassin.S02E01.Rink.mkv'."""
    stem, ext = os.path.splitext(name)
    stem = _SITE_TAG_RE.sub(".", stem)
    stem = re.sub(r"[._\- ]{2,}", ".", stem).strip("._- ")
    if not stem:
        stem = "download"
    if BRAND.lower() not in stem.lower():
        stem = f"{stem}.{BRAND}"
    return stem + ext


def filename_for(direct):
    """Safe local filename for a direct URL, branded with our name."""
    name = os.path.basename(urllib.parse.urlparse(direct).path) or "download.mkv"
    return brand_name(htmllib.unescape(name))


def resolve_info(link_url, referer=BASE + "/"):
    """Resolve a download link to {direct, name, size}. Raises NkiriError."""
    logger.info("RESOLVE url=%s", link_url)
    direct = resolve_direct(link_url, referer=referer)
    name = filename_for(direct)
    size = head_size(direct)
    logger.info("RESOLVED direct=%s name=%s size=%s", direct, name, size or "unknown")
    return {"direct": direct, "name": name, "size": size}


#: the landing page prints the size as  <span class="statd">size</span><span>437.9 MB</span>
_SIZE_RE = re.compile(r'<span class="statd">size</span>\s*<span>([^<]+)</span>', re.I)
_size_cache = TTLCache(ttl=3600)


def landing_size(url):
    """File size from a download link's landing page.

    One GET: the size is printed on the page the link already points at, so
    this skips the 2-step postback that resolve_direct needs. Cached, because
    a detail page asks for every link at once.
    """
    def fetch():
        try:
            raw, _ = http_get(url)
        except Exception as e:
            logger.warning("size lookup failed %s: %s", url, e)
            return {"size": None, "bytes": None}
        m = _SIZE_RE.search(raw.decode("utf-8", "ignore"))
        if not m:
            return {"size": None, "bytes": None}
        text = htmllib.unescape(m.group(1)).strip()
        return {"size": text, "bytes": parse_size(text)}

    return _size_cache.get_or_set(url, fetch)


def download_file(direct, dest, referer, quiet=True):
    """Fetch direct -> dest with curl (resumable). Returns bytes written."""
    cmd = ["curl", "-sS", "-L", "-f", "-C", "-", "-A", UA, "-e", referer,
           "-o", dest, direct]
    if not quiet:
        cmd = [c for c in cmd if c != "-sS"]
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise DownloadError(f"exit {proc.returncode}")
    return os.path.getsize(dest) if os.path.exists(dest) else 0


__all__ = ["resolve_direct", "resolve_info", "filename_for", "download_file",
           "landing_size", "resolve_target_allowed", "direct_url_allowed",
           "NkiriError", "DownloadError"]
