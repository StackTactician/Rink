"""One post: its links, its labels, and the rows they become."""

import html as htmllib
import logging
import re
import urllib.parse

from ...text import clean_title, parse_size, strip_tags
from . import state
from .config import BASE, _FILE_HOST_RE, _SKIP_RE, _id_from_url
from .http import _api
from .listing import menu

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------- post



def parse_ref(ref):
    """Post id from a number or a 9jarocks URL. None when neither."""
    ref = (ref or "").strip()
    if ref.isdigit():
        return int(ref)
    if "9jarocks.net" not in ref:
        return None
    return _id_from_url(ref)


def _raw_post(pid):
    return _api(f"/posts/{int(pid)}")


_EM_RE = re.compile(r"<em[^>]*>(.*?)</em>", re.I | re.S)
_STRONG_RE = re.compile(r"<strong[^>]*>(.*?)</strong>", re.I | re.S)
_PARA_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)
_ANCHOR_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
_SIZE_IN_BLOCK_RE = re.compile(r"Size:\s*([0-9.]+\s*[KMG]B)", re.I)
_EPISODE_RE = re.compile(r"\bepisode\s*(\d+)\b", re.I)


def _clean_label(raw):
    t = re.sub(r"\s+", " ", strip_tags(raw or "")).strip()
    if not t:
        return ""
    t = re.sub(r"\s*\(\s*end\s*\)", " (End)", t, flags=re.I)
    t = _EPISODE_RE.sub(lambda m: "Episode " + m.group(1), t)
    return t


_SXXEXX_RE = re.compile(r"\bS(\d{1,2})E(\d{1,3})\b", re.I)
_EPISODE_WORD_RE = re.compile(r"\bepisode\b", re.I)


def _label_for(label, href):
    """A season header is not an episode name.

    Some posts mark every row <em>EPISODE 3</em>. Others print one
    <em>SEASON 6</em> above rows whose only identifier is S06E03 inside the
    filename, so a header yields to that token and every row keeps a name.
    """
    if label and _EPISODE_WORD_RE.search(label):
        return label
    found = _SXXEXX_RE.search(urllib.parse.unquote(href))
    if found:
        return f"S{int(found.group(1)):02d}E{int(found.group(2)):02d}"
    return label


def find_links(content_html):
    """Download targets as [{label, text, url}].

    This site marks each row with <em>EPISODE n</em> inside the same <p> as
    its anchor, and the anchor text is always just "DOWNLOAD", so the label
    has to be read from the paragraph, not from a heading.
    """
    items, seen = [], set()
    for para in _PARA_RE.findall(content_html):
        em = _EM_RE.search(para) or _STRONG_RE.search(para)
        heading = _clean_label(em.group(1)) if em else ""
        for href, text in _ANCHOR_RE.findall(para):
            href = htmllib.unescape(href)
            if not href.startswith("http") or href in seen:
                continue
            if _SKIP_RE.search(href):
                continue
            host = urllib.parse.urlparse(href).hostname or ""
            if not _FILE_HOST_RE.search(host):
                continue
            seen.add(href)
            items.append({"label": _label_for(heading, href),
                          "text": strip_tags(text) or "Download",
                          "url": href})
    return items


def _synopsis(content_html):
    """First real paragraph: the opening <p> usually holds only the poster."""
    for para in _PARA_RE.findall(content_html):
        text = strip_tags(para)
        if len(text) >= 60 and "themoviedb" not in para and "imdb.com" not in para:
            return text[:800]
    return ""


def _poster(content_html):
    m = _IMG_RE.search(content_html)
    return htmllib.unescape(m.group(1)) if m else ""


def _category_chips(ids):
    by_id = {c["id"]: c for c in menu()}
    out, seen = [], set()
    for i in ids or ():
        c = by_id.get(i)
        if c and c["slug"] not in seen:
            seen.add(c["slug"])
            out.append({"slug": c["slug"], "name": c["name"]})
    return out


def post_view(pid):
    """Wire view model, same keys the thenkiri source produces."""
    def fetch():
        raw = _raw_post(pid)
        content = (raw.get("content") or {}).get("rendered", "")
        links = find_links(content)
        if links and not any(link["label"] for link in links):
            # a film: one file, no episode marker anywhere
            for i, link in enumerate(links):
                link["label"] = "Movie" if len(links) == 1 else f"File {i + 1}"
        size = _SIZE_IN_BLOCK_RE.search(strip_tags(content))
        if size and len(links) == 1:
            # the stats block describes this single file, so the row can show
            # its size without a round trip to the file host
            links[0]["size"] = re.sub(r"\s+", " ", size.group(1)).upper()
            links[0]["bytes"] = parse_size(links[0]["size"])
        return {
            "id": raw.get("id", pid),
            "title": clean_title(htmllib.unescape(
                ((raw.get("title") or {}).get("rendered")) or "")),
            "url": raw.get("link") or f"{BASE}/videodownload/x-id{pid}.html",
            "date": (raw.get("date") or "")[:10],
            "poster": _poster(content),
            "synopsis": _synopsis(content),
            "links": links,
            "genres": _category_chips(raw.get("categories")),
            "formats": [],
        }

    return state._post_cache.get_or_set(int(pid), fetch)
