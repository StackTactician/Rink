"""Saving a file: the name it gets, and the fetch that writes it.

Nothing here knows which source a link came from — that is the whole point of
it living outside the adapters. The site tag in a filename is stripped by a
pattern that covers every source this app has, so a file from any of them
comes out branded the same way.
"""

import html as htmllib
import logging
import os
import re
import subprocess
import urllib.parse

from .config import UA
from .errors import DownloadError

logger = logging.getLogger(__name__)

# Files arrive named like "The.Assassin.S02E01.(THENKIRI.COM).mkv".
# Strip the source-site tag and brand the file with ours instead.
BRAND = "Rink"


def _site_tag_names():
    """Every name a filename might carry, taken from the sources themselves.

    A new source adds its names to its META and the downloader strips them
    with no change here.
    """
    from .sources import SOURCES
    names = set()
    for _src, meta in SOURCES:
        names.add(meta["site"].split("//", 1)[-1].split("/")[0])
        names.add(meta["label"])
        names.update(meta.get("file_tags", ()))
    # longest first, so "thenkiri.com" is tried before "thenkiri"
    return sorted((n for n in names if n), key=len, reverse=True)


_TAG_RE = None


def _site_tag_re():
    """Built on first use, not at import: the sources import this module."""
    global _TAG_RE
    if _TAG_RE is None:
        _TAG_RE = re.compile(
            r"[._\- ]*[\(\[\{]?\s*(?:www\.)?(?:"
            + "|".join(re.escape(n) for n in _site_tag_names())
            + r")\s*[\)\]\}]?[._\- ]*",
            re.I)
    return _TAG_RE


def brand_name(name):
    """'The.Assassin.S02E01.(THENKIRI.COM).mkv' -> 'The.Assassin.S02E01.Rink.mkv'."""
    stem, ext = os.path.splitext(name)
    stem = _site_tag_re().sub(".", stem)
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


def download_file(direct, dest, referer, quiet=True):
    """Fetch direct -> dest with curl (resumable). Returns bytes written."""
    # `-g` keeps curl from reading [..] in a file name as a URL glob
    cmd = ["curl", "-g", "-sS", "-L", "-f", "-C", "-", "-A", UA, "-e",
           referer, "-o", dest, direct]
    if not quiet:
        cmd = [c for c in cmd if c != "-sS"]
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        raise DownloadError(f"exit {proc.returncode}")
    return os.path.getsize(dest) if os.path.exists(dest) else 0
