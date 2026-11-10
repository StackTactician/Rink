"""9jarocks.net: a second source whose files live on loadedfiles.net.

It is WordPress like thenkiri, but its REST posts *collection* is switched off
(GET /wp-json/wp/v2/posts answers 404 rest_no_route), so there is no way to ask
for "the newest 24 posts". Listing therefore comes from two places that do
carry id, title and poster in a single response:

  * category archives as HTML  (/category/videodownload/<slug>/page/N/)
  * the site RSS feed          (/feed?paged=N)   for the newest uploads

The REST API is still used for search ranking (the HTML search page carries
sidebar cards that are not results), for one post, and for the category table.

Files are 540p x265 MKV behind a three-hop token chain on loadedfiles.net:
file page -> "proceed" token -> page embedding the real link -> CDN. The CDN
answers Range requests properly, so the file can be streamed or resumed.
"""

import html as htmllib
import json
import logging
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar

from .cache import TTLCache
from .config import TIMEOUT, UA
from .download import BRAND
from .errors import DownloadError, FetchError, NkiriError
from .posts import page_payload
from .text import clean_title, parse_size, strip_tags

BASE = "https://9jarocks.net"
API = BASE + "/wp-json/wp/v2"

logger = logging.getLogger(__name__)

_menu_cache = TTLCache(ttl=3600)
_latest_cache = TTLCache(ttl=120)
_search_cache = TTLCache(ttl=300)
_post_cache = TTLCache(ttl=600)
_browse_cache = TTLCache(ttl=120)

#: Rink shows films and shows. This site also files music, gist, news, sport
#: highlights and "Whatsapp Stories" in the same table, so the filter is an
#: allowlist: an unknown category is left out unless its name says what it is.
#:
#: Nkiri is a film-and-show source, and this list is what the app advertises as
#: its catalogue, so adult titles are out of it. That covers the "Adult" chip
#: and the same posts in the newest-uploads feed and in search. Those posts are
#: still on the site: "18-section" (which this list never included) and "adult"
#: stay reachable only through an explicit category URL, since `browse()` takes
#: a slug without checking it.
_FILM_SHOW_SLUGS = frozenset({
    "hollywood-movie", "hollywood-tv-series", "foreign-movies", "anime",
    "ongoing", "chinese-drama", "korean-drama", "other-foreign-series",
    "thai-drama", "japanese-drama", "turkish-drama", "nollywood-movie",
    "nollywood-tv-series", "spanish-drama-telenovela", "filipino-drama",
})

#: "-movie", "-drama", "-series", "-telenovela" cover a language added later
#: without another code change; "-music", "-stories" and the rest never match
_FILM_SHOW_RE = re.compile(r"-(?:movies?|dramas?|series|telenovela)$", re.I)


def _is_film_or_show(slug):
    slug = (slug or "").lower()
    return slug in _FILM_SHOW_SLUGS or bool(_FILM_SHOW_RE.search(slug))

#: hosts a download link may point at, and the CDN the chain lands on
_FILE_HOST_RE = re.compile(r"(^|\.)(loadedfiles\.net)$", re.I)
_CDN_HOST_RE = re.compile(r"(^|\.)static\.gfrdaseazzs\.com$", re.I)

#: never a download: the site itself, metadata sites, trailers
_SKIP_RE = re.compile(
    r"9jarocks\.net|themoviedb\.org|imdb\.com|youtube\.com|youtu\.be|"
    r"facebook\.com|t\.me|whatsapp\.com", re.I)


# ------------------------------------------------------------------ plumbing

def _get(url, timeout=TIMEOUT):
    """GET a page as text. Returns (text, final_url)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore"), r.geturl()
    except Exception as e:
        raise FetchError(str(e)) from e


def _api(path):
    """GET a WP REST path on this site. Returns the decoded body."""
    req = urllib.request.Request(API + path, headers={
        "User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read())
    except Exception as e:
        raise FetchError(str(e)) from e


def _unescape_js(s):
    """Undo the JSON escaping inside an Alpine x-data attribute."""
    s = s.replace("\\/", "/")
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    return htmllib.unescape(s)


# ------------------------------------------------------------------ listing

#: a card is one <li class="post-item">; the attrs inside it carry everything
_CARD_SPLIT_RE = re.compile(r'<li[^>]*class="[^"]*\bpost-item\b', re.I)
_POST_HREF_RE = re.compile(
    r'href="(https://9jarocks\.net/videodownload/[^"]*?-id(\d+)\.html)"', re.I)
_ARIA_RE = re.compile(r'aria-label="([^"]*)"')
_THUMB_RE = re.compile(
    r'(?:data-src|src)="(https://9jarocks\.net/wp-content/uploads/[^"]+)"', re.I)

_FEED_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
_FEED_DATE_RE = re.compile(r"<pubDate>(.*?)</pubDate>", re.S)


def _cards(page):
    """Post cards in document order: id, title, url, poster."""
    blocks = _CARD_SPLIT_RE.split(page)[1:]
    out, seen = [], set()
    for block in blocks:
        href = _POST_HREF_RE.search(block)
        if not href:
            continue
        pid = int(href.group(2))
        if pid in seen:
            continue
        seen.add(pid)
        title = _ARIA_RE.search(block)
        poster = _THUMB_RE.search(block)
        out.append({
            "id": pid,
            # card labels carry the rating widget's numbers too: "Title 4 (4)"
            "title": clean_title(_strip_feed_junk(
                htmllib.unescape(title.group(1)) if title else "")),
            "url": href.group(1),
            "date": "",
            "poster": htmllib.unescape(poster.group(1)) if poster else "",
        })
    return out


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        out.append(it)
    return out


def menu():
    """Categories to show as chips, biggest first."""
    def fetch():
        try:
            rows = _api("/categories?per_page=100&_fields=id,name,slug,count")
        except Exception as e:
            logger.warning("9ja category lookup failed: %s", e)
            return []
        out = [{"id": r["id"], "slug": r["slug"],
                "name": htmllib.unescape(r.get("name") or r["slug"]),
                "count": r.get("count", 0)}
               for r in rows
               if _is_film_or_show(r.get("slug")) and r.get("count", 0) > 0]
        out.sort(key=lambda c: -c["count"])
        return out

    return _menu_cache.get_or_set("all", fetch)


def _feed_page(page):
    """Newest uploads, restricted to the film/show categories.

    WordPress honours `cat=<ids>` on a feed, so one request replaces a merge
    of sixteen category feeds. Without the ids (the category table failed)
    the site-wide feed is the fallback, and the title filter still drops the
    obvious music.
    """
    cats = [str(c["id"]) for c in menu()]
    if cats:
        text, _ = _get(f"{BASE}/feed?cat={','.join(cats)}&paged={page}")
    else:
        logger.warning("9ja feed: no categories, falling back to all posts")
        text, _ = _get(f"{BASE}/feed?paged={page}")
    items = []
    for raw in _FEED_ITEM_RE.findall(text):
        link = re.search(r"<link>(https://9jarocks\.net/videodownload/[^<]+)</link>",
                         raw)
        if not link:
            continue
        href = link.group(1)
        pid = _id_from_url(href)
        if not pid:
            continue
        title = re.search(r"<title>(.*?)</title>", raw, re.S)
        date = _FEED_DATE_RE.search(raw)
        poster = re.search(
            r'<img[^>]+src="(https://9jarocks\.net/wp-content/uploads/[^"]+)"',
            raw, re.I)
        items.append({
            "id": pid,
            "title": clean_title(_strip_feed_junk(htmllib.unescape(
                title.group(1))) if title else ""),
            "url": href,
            "date": _rfc822(date.group(1)) if date else "",
            "poster": htmllib.unescape(poster.group(1)) if poster else "",
        })
    # a feed page is always the same size, so a full one means there is a next
    return _dedupe(items), len(items) >= 20


_MONTHS = {m: i + 1 for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}
_RFC822_RE = re.compile(r",\s*(\d{1,2})\s+(\w{3})\s+(\d{4})")


def _rfc822(text):
    """'Tue, 10 Nov 2026 08:16:34 +0000' -> '2026-11-10'."""
    m = _RFC822_RE.search(text or "")
    if not m:
        return ""
    day, mon, year = m.groups()
    month = _MONTHS.get(mon[:3].title())
    if not month:
        return ""
    return f"{year}-{month:02d}-{int(day):02d}"


def _strip_feed_junk(title):
    """Feeds and cards append the rating widget and comment count, and the
    rating is sometimes a decimal: 'Title (2025) 4.6 (9)'."""
    return re.sub(r"\s+\d+(?:\.\d+)?\s*\(\d+\)\s*$", "", title or "").strip()


#: music and gist posts share the /videodownload/ path, so a URL cannot tell
#: them apart. Search cannot ask the site to filter by category either — both
#: `?cat=` on the search page and `categories=` on the REST search are ignored
#: (verified). The search page does not print a category on its cards either,
#: so the only place a hit states its category is the post's own REST record;
#: `_post_cats` goes and reads it. The title screen below is what is left when
#: even that is unavailable.
_NON_FILM_PREFIX_RE = re.compile(
    r"^\s*(?:video|music(?:\s*box)?|audio|mp3|lyrics?)\s*:", re.I)
_NON_FILM_HINT_RE = re.compile(
    r"\s(?:ft\.|feat\.)\s|\bremix\b|\bgospel\b|\blyrics?\b|"
    r"\bas\s+he\s+talks\b|\breveals?\b", re.I)
_HAS_YEAR_RE = re.compile(r"\(\s*(?:19|20)\d{2}\s*\)")


def _looks_like_film(title, url=""):
    """Loose, cheap screen for a search hit: films and shows carry a (year).

    Only used when a hit's category cannot be read, so it leans towards
    keeping the post: a wrong drop hides something the listing still shows,
    which is the disagreement this whole filter exists to prevent.
    """
    if "/uncategorized/" in (url or ""):
        return False
    t = title or ""
    # a year is the site's own mark of a film or show, and it outranks both
    # screens: "Music (2021)" is a film, "Music: Burna Boy - City Boys" is not
    if _HAS_YEAR_RE.search(t):
        return True
    if _NON_FILM_PREFIX_RE.search(t):
        return False
    return not _NON_FILM_HINT_RE.search(t)


_cat_slug_cache = TTLCache(ttl=3600)
_post_cat_cache = TTLCache(ttl=3600)


def _cat_slugs():
    """{category id: slug} for the whole table, so a post's ids become names."""
    def fetch():
        try:
            rows = _api("/categories?per_page=100&_fields=id,slug")
        except NkiriError as e:
            logger.warning("9ja category id lookup failed: %s", e)
            return {}
        return {r["id"]: (r.get("slug") or "").lower() for r in rows}

    return _cat_slug_cache.get_or_set("all", fetch)


def _post_cats(pid):
    """Category slugs behind one post id; () when the site will not say.

    One request per id, which is why the caller runs these concurrently and
    keeps the answers for an hour: a post's categories do not change.
    """
    def fetch():
        try:
            row = _api(f"/posts/{pid}?_fields=id,categories")
        except NkiriError as e:
            logger.warning("9ja post %s categories failed: %s", pid, e)
            return ()
        slugs = _cat_slugs()
        return tuple(s for s in (slugs.get(c) for c in row.get("categories") or ())
                     if s)

    return _post_cat_cache.get_or_set(pid, fetch)


def _listed_flags(order, cards):
    """{post id: is it a film or show}, in one batch of parallel lookups.

    Browse gets its answer from the category in its URL; search has to ask per
    post, or the two screens disagree about what exists. A post whose category
    cannot be read falls back to the title screen rather than disappearing.
    """
    def verdict(pid):
        cats = _post_cats(pid)
        if cats:
            return any(_is_film_or_show(c) for c in cats)
        card = cards.get(pid) or {}
        return _looks_like_film(card.get("title"), card.get("url"))

    if not order:
        return {}
    # One connection opens per call, so these are mostly handshake: 12 at a
    # time turns a page of hits into about two rounds instead of one per hit.
    # Capped rather than matched to the page because this is not our site.
    with ThreadPoolExecutor(max_workers=min(12, len(order))) as pool:
        return dict(zip(order, pool.map(verdict, order)))


def latest(limit=24, page=1):
    """Newest uploads. One feed page holds 22 items, so a page is one request."""
    def fetch():
        items, more = _feed_page(page)
        items = items[:limit]
        return page_payload(items, page, limit,
                            total=None,
                            total_pages=(page + 1) if more else page)

    return _latest_cache.get_or_set((limit, page), fetch)


def _category_url(slug, page):
    path = f"/category/videodownload/{urllib.parse.quote(slug)}"
    if page > 1:
        path += f"/page/{page}"
    return BASE + path + "/"


def browse(slug="", limit=24, page=1):
    """One page of a category, or the newest uploads when no category given."""
    if not slug:
        return latest(limit, page)

    def fetch():
        try:
            text, _ = _get(_category_url(slug, page))
        except NkiriError:
            # the nested taxonomy path is the site's own menu link; a flat
            # /category/<slug>/ is what older permalinks still use
            try:
                text, _ = _get(f"{BASE}/category/{urllib.parse.quote(slug)}/"
                               + (f"page/{page}/" if page > 1 else ""))
            except NkiriError as e:
                logger.warning("9ja browse failed %s p%d: %s", slug, page, e)
                return page_payload([], page, limit)
        items = _cards(text)[:limit]
        more = len(items) >= min(limit, 20)
        return page_payload(items, page, limit, total=None,
                            total_pages=(page + 1) if more else page)

    return _browse_cache.get_or_set((slug, limit, page), fetch)


def search(query, limit=24, page=1):
    """Search. REST decides *which* posts match and in what order; the search
    page supplies the posters for those ids, because the REST search result
    carries no media. Neither of those states a category, so each hit's own
    record is asked (`_listed_flags`).

    Filtering after REST means a page can come back short of `limit`. That is
    left alone on purpose: over-fetching to refill it would shift the offset
    REST pages by, and results would fall down the gap between two pages.
    """
    query = (query or "").strip()
    if not query:
        return page_payload([], page, limit)

    def fetch():
        q = urllib.parse.quote(query)
        try:
            rows = _api(f"/search?search={q}&per_page={limit}"
                        f"&subtype=post&page={page}")
        except NkiriError as e:
            logger.warning("9ja search failed %r: %s", query, e)
            return page_payload([], page, limit)
        order = [r["id"] for r in rows if r.get("subtype", "post") == "post"]

        try:
            text, _ = _get(f"{BASE}/?s={q}&paged={page}")
            cards = {c["id"]: c for c in _cards(text)}
        except NkiriError:
            cards = {}

        listed = _listed_flags(order, cards)
        # a hit REST matched but the page rendered no card for used to become a
        # blank row: no title, no poster, and now no category to judge either,
        # so it is left out rather than drawn as a titleless tile
        items = [cards[pid] for pid in order
                 if listed.get(pid) and pid in cards]
        return page_payload(items, page, limit, total=None,
                            total_pages=(page + 1) if len(rows) >= limit else page)

    return _search_cache.get_or_set((query.lower(), limit, page), fetch)


# --------------------------------------------------------------------- post

_ID_RE = re.compile(r"-id(\d+)\.html", re.I)


def _id_from_url(url):
    m = _ID_RE.search(url or "")
    return int(m.group(1)) if m else None


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


def find_links(content_html):
    """Download targets as [{label, text, url}].

    This site marks each row with <em>EPISODE n</em> inside the same <p> as
    its anchor, and the anchor text is always just "DOWNLOAD", so the label
    has to be read from the paragraph, not from a heading.
    """
    items, seen = [], set()
    for para in _PARA_RE.findall(content_html):
        em = _EM_RE.search(para) or _STRONG_RE.search(para)
        label = _clean_label(em.group(1)) if em else ""
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
            items.append({"label": label,
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

    return _post_cache.get_or_set(int(pid), fetch)


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


def size_info(url):
    """Per-link size. This site prints it on the post page instead, so the
    detail view already carries it and there is nothing to look up here."""
    return {"size": None, "bytes": None}


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


def clear_cache():
    for c in (_menu_cache, _latest_cache, _search_cache,
              _post_cache, _browse_cache):
        c.clear()
