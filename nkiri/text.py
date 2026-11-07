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
