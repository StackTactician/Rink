"""HTML and text helpers."""

import html as htmllib
import re


def strip_tags(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return htmllib.unescape(s).strip()


def clean_title(title):
    """'Resident Evil (2026) | Download Hollywood Movie' -> 'Resident Evil (2026)'"""
    t = re.split(r"\s*\|\s*", title or "")[0]
    return htmllib.unescape(strip_tags(t)).strip()


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024.0


_SIZE_TEXT_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGTP]?B)\s*$", re.I)
_SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024 ** 2,
               "GB": 1024 ** 3, "TB": 1024 ** 4, "PB": 1024 ** 5}


def parse_size(text):
    """'437.9 MB' -> 459223859. None when the string is not a size."""
    m = _SIZE_TEXT_RE.match(text or "")
    if not m:
        return None
    return int(float(m.group(1)) * _SIZE_UNITS[m.group(2).upper()])
