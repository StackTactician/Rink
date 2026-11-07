"""Download engine: 2-step downloadwella resolution + file transfer.

The web UI never stores files server-side (the browser fetches and saves);
the CLI uses `download_file` (curl) to write to disk.
"""

import html as htmllib
import logging
import os
import re
import subprocess
import urllib.parse

from .config import BASE, UA
from .errors import DownloadError, NkiriError
from .net import head_size, http_get, post_form

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
           "NkiriError", "DownloadError"]
