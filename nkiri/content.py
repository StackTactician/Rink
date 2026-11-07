"""Scrape a post's rendered HTML: download links, synopsis, view model."""

import html as htmllib
import re
import urllib.parse

from .config import OWN_HOSTS
from .text import strip_tags

_LINK_RE = re.compile(
    r'<h[1-4][^>]*>(.*?)</h[1-4]>|<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_HEADING_HINT_RE = re.compile(r"episode|quality|server|mirror|\d+", re.I)
_DL_HOST_RE = re.compile(
    r"download|files?\.|mega\.nz|mega\.co|mediafire|dropbox|gdrive|google\.", re.I)
_SELF_LINK_RE = re.compile(r"thenkiri\.com|nkiri\.ink")

# Upstream headings are written for a blog post, not for a file list:
#   "Download links Heart of the Beast (2026)\n(Hollywood Movie)"
#   "Download links for Sigma (2026) (Foreign Movie)"
#   "Episode 6(End)"     "Episode  1"
# Rink shows plain names: "Episode 6 (End)" or, for a film, "Movie".
_WS_RE = re.compile(r"\s+")
_BOILER_RE = re.compile(r"^download\s+links?\b", re.I)
_CATEGORY_RE = re.compile(r"\((?:hollywood|korean|foreign|nollywood|anime)\s+\w+\)", re.I)
_EPISODE_RE = re.compile(r"\bepisode\s*(\d+)\b", re.I)


def clean_label(raw):
    """Heading text -> plain file name. "" when the heading is site boilerplate."""
    t = _WS_RE.sub(" ", (raw or "").strip())
    if not t or _BOILER_RE.match(t) or re.fullmatch(r"download", t, re.I):
        return ""
    t = re.sub(r"\s*\(\s*end\s*\)", " (End)", t, flags=re.I)
    t = _EPISODE_RE.sub(lambda m: "Episode " + m.group(1), t)
    t = _CATEGORY_RE.sub("", t)
    return _WS_RE.sub(" ", t).strip(" -:")


def clean_text(raw):
    """Anchor text -> plain name ("Download Episode" -> "Episode")."""
    t = _WS_RE.sub(" ", (raw or "").strip())
    t = re.sub(r"^download\s+", "", t, flags=re.I)
    return t.strip() or "Download"


def find_download_links(content_html):
    """Extract download targets as [{label, text, url}].

    `label` is the nearest preceding heading, cleaned to a plain name
    ("Episode 3"); `text` is the anchor text without its "Download" prefix.
    """
    items = []
    seen = set()
    current_label = ""
    for m in _LINK_RE.finditer(content_html):
        if m.group(1) is not None:
            heading = strip_tags(m.group(1))
            if heading and _HEADING_HINT_RE.search(heading) and len(heading) < 60:
                current_label = heading
            continue

        href = htmllib.unescape(m.group(2) or "")
        text = strip_tags(m.group(3) or "")
        if not href or href.startswith(("#", "javascript:")):
            continue
        if urllib.parse.urlparse(href).netloc in OWN_HOSTS:
            continue
        if _SELF_LINK_RE.search(href) or not _DL_HOST_RE.search(href):
            continue
        if href in seen:
            continue
        seen.add(href)
        items.append({"label": clean_label(current_label),
                      "text": clean_text(text), "url": href})
    return items


def display_label(item):
    """Human-facing name for a download item."""
    label = item.get("label") or "Download"
    return label if label != "Download" else (item.get("text") or "Download")


def extract_synopsis(content_html):
    """First paragraph after the 'Synopsis' heading, or ""."""
    i = content_html.find("Synopsis")
    if i == -1:
        return ""
    block = content_html[i:i + 4000]
    pm = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
    if pm:
        txt = strip_tags(pm.group(1))
        if txt:
            return txt[:800]
    return ""


def parse_post_view(post):
    """Wire view model for the web UI."""
    content = post["content"]["rendered"]
    return {
        "id": post["id"],
        "title": post["title"],
        "url": post["link"],
        "date": post.get("date", "")[:10],
        "poster": post.get("poster"),
        "synopsis": extract_synopsis(content),
        "links": find_download_links(content),
    }
