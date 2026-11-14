"""movibox.net: a streaming source behind an undocumented JSON API.

Not WordPress. The site is a Nuxt 3 shell over a private API at
``h5-api.aoneroom.com/wefeed-h5api-bff``, and three things about it are not
obvious:

  * **The token is handed out, not signed up for.** ``GET /home`` answers with
    ``x-user: {"token": "<JWT>"}`` and a matching ``set-cookie``. That JWT is
    anonymous (``atp: 3``) and lives 90 days; as ``Authorization: Bearer`` it
    opens search, detail, play and download. No account, no login.
  * **The client token is a clock.** Requests without a user token carry
    ``X-Client-Token: <unix>,<md5(reversed unix)>``. It is only needed to mint
    the JWT, but the API rejects a request that has neither.
  * **Playback is gated on the Referer.** ``/subject/play`` and
    ``/subject/download`` answer ``hasResource: false`` with an empty stream
    list unless ``Referer`` is the *player route* — ``/movies/<detailPath>``.
    The ``type`` query parameter the site appends is decorative; the referer
    is the whole gate. This is why every probe without it looked like the
    catalogue had no files.

  * **Play and download disagree about quality.** ``/subject/download`` marks
    the 1080p row ``vipLocked`` and withholds its URL; ``/subject/play``, the
    endpoint the site's own player calls, returns every resolution with a
    working link to an anonymous client. The file is the same, so play is
    asked first and download is only the fallback.

Files are plain MP4 on ``*.hakunaymatata.com`` behind a signed query string.
The CDN honours Range, so a file can be streamed or resumed, but it answers
429 to a request that arrives without a movibox referer — hence
``file_referer()`` and the proxy in the web layer.

Sizes are integers in the JSON, so nothing here has to read a page to learn
how big a file is.
"""

import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .cache import TTLCache
from .config import TIMEOUT, UA
from .errors import FetchError, NkiriError
from .posts import page_payload
from .text import clean_title, human_size

BASE = "https://movibox.net"
API = "https://h5-api.aoneroom.com/wefeed-h5api-bff"

#: the player route. The API checks this exact prefix, so it is not a nicety.
PLAY_ROUTE = BASE + "/movies/"

logger = logging.getLogger(__name__)

_home_cache = TTLCache(ttl=300)
_menu_cache = TTLCache(ttl=3600)
_search_cache = TTLCache(ttl=300)
_enum_cache = TTLCache(ttl=300)
_detail_cache = TTLCache(ttl=600)
_files_cache = TTLCache(ttl=300)

#: subjectType 1 is a film, 2 is a series. The same feed also carries 6, which
#: is music compilations and stage shows — not what this app is for.
_FILM_TYPES = frozenset({1, 2})

#: the CDN the signed MP4s live on
_FILE_HOST_RE = re.compile(r"(^|\.)hakunaymatata\.com$", re.I)

#: the API's own host, for the referer the CDN wants
_FILE_REFERER = BASE + "/"

_token = {"value": None, "at": 0.0}
_TOKEN_TTL = 3600


# ------------------------------------------------------------------ plumbing

def _client_token():
    """`<unix>,<md5 of the reversed unix>` — the API's clock-based client id."""
    ts = int(time.time())
    return f"{ts}," + hashlib.md5(str(ts)[::-1].encode()).hexdigest()


def _headers(token=None, referer=None):
    h = {
        "Accept": "application/json",
        "X-Client-Info": json.dumps({"timezone": "Africa/Lagos"}),
        "X-Request-Lang": "en",
        "User-Agent": UA,
        "Referer": referer or (BASE + "/"),
        "Origin": BASE,
    }
    if token:
        h["Authorization"] = "Bearer " + token
        h["Cookie"] = "token=" + token
    else:
        h["X-Client-Token"] = _client_token()
    return h


def _raw(path, token=None, referer=None, body=None, timeout=TIMEOUT):
    """One request. Returns (status, headers, bytes)."""
    data = json.dumps(body).encode() if body is not None else None
    headers = _headers(token, referer)
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except Exception as e:
        raise FetchError(str(e)) from e


def _token_value(force=False):
    """The anonymous JWT, minted from /home and kept for an hour."""
    now = time.time()
    if not force and _token["value"] and now - _token["at"] < _TOKEN_TTL:
        return _token["value"]
    status, headers, _ = _raw("/home")
    if status != 200:
        raise FetchError(f"movibox token: HTTP {status}")
    try:
        token = json.loads(headers.get("x-user") or "{}").get("token")
    except ValueError:
        token = None
    if not token:
        raise FetchError("movibox token: no x-user header")
    _token["value"], _token["at"] = token, now
    return token


def _api(path, referer=None, body=None):
    """GET/POST a JSON path, re-minting the token once if it is refused."""
    for attempt in (1, 2):
        token = _token_value(force=attempt == 2)
        status, _headers_, raw = _raw(path, token, referer, body)
        if status == 200:
            try:
                payload = json.loads(raw)
            except ValueError as e:
                raise FetchError(f"invalid JSON from {path}: {e}") from e
            if payload.get("code") in (0, None):
                return payload.get("data") or {}
            raise FetchError(f"{path}: {payload.get('message')}")
        if status in (400, 401) and attempt == 1:
            continue                      # stale token: mint a new one
        raise FetchError(f"HTTP {status} from {path}")
    raise FetchError(f"unreachable: {path}")


# ------------------------------------------------------------------ mapping

def _poster(cover):
    """The full-size cover. The API also serves resized copies; the original
    is what keeps a portrait poster from being cropped to a landscape box."""
    if isinstance(cover, dict):
        return cover.get("url") or ""
    return cover or ""


def _item(subject):
    """One card, in the shape every other source produces."""
    path = subject.get("detailPath") or ""
    return {
        "id": path,
        "title": clean_title(subject.get("title") or ""),
        "url": f"{BASE}/movies/{path}" if path else BASE,
        "date": (subject.get("releaseDate") or "")[:10],
        "poster": _poster(subject.get("cover")),
    }


def _wanted(subject):
    """Films and series only: the feed also carries music and stage shows."""
    if subject.get("subjectType") not in _FILM_TYPES:
        return False
    if subject.get("isPornographic"):
        return False
    return bool(subject.get("detailPath"))


def _home():
    return _home_cache.get_or_set("home", lambda: _api("/home"))


def _sections():
    """The site's own home rows, in the order it shows them.

    This is the taxonomy: movibox has no genre endpoint, and its filter
    endpoint ignores every field it is given, so the rows it publishes are the
    only real categorisation it exposes.
    """
    out, seen = [], set()
    for row in _home().get("operatingList") or ():
        if row.get("type") != "SUBJECTS_MOVIE":
            continue
        subjects = [s for s in (row.get("subjects") or ()) if _wanted(s)]
        if not subjects:
            continue
        name = (row.get("title") or "").strip()
        slug = str(row.get("opId") or "")
        if not name or not slug or name in seen:
            continue
        seen.add(name)
        out.append({"slug": slug, "name": name, "count": len(subjects),
                    "subjects": subjects})
    return out


# ------------------------------------------------------------------ listing

def menu():
    """Chip row: the home rows, as the site itself orders them."""
    def fetch():
        return [{"slug": s["slug"], "name": s["name"], "count": s["count"]}
                for s in _sections()]

    return _menu_cache.get_or_set("all", fetch)


def _flatten():
    """Every section's subjects, deduped, in home order."""
    seen, out = set(), []
    for section in _sections():
        for subject in section["subjects"]:
            item = _item(subject)
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            out.append(item)
    return out


def latest(limit=24, page=1):
    """The home feed: the site's rows flattened, paged locally."""
    def fetch():
        items = _flatten()
        start = max(0, (page - 1) * limit)
        window = items[start:start + limit]
        pages = max(1, (len(items) + limit - 1) // limit)
        return page_payload(window, page, limit, total=len(items),
                            total_pages=pages)

    return _home_cache.get_or_set(("latest", limit, page), fetch)


def browse(slug="", limit=24, page=1):
    """One home row. Rows are fixed-length, so there is only ever one page."""
    if not slug:
        return latest(limit, page)

    def fetch():
        for section in _sections():
            if section["slug"] == str(slug):
                items = [_item(s) for s in section["subjects"]][:limit]
                return page_payload(items, 1, limit, total=len(items),
                                    total_pages=1)
        return page_payload([], page, limit, total=0, total_pages=1)

    return _menu_cache.get_or_set(("browse", str(slug), limit), fetch)


#: the API caps a page at 30 whatever perPage asks for, and its own
#: `totalCount` is not the number of rows it will hand over (a query that
#: reports 67 returns 31), so a real count means reading every page. Pages are
#: fetched in waves of three and the whole answer is cached, which makes the
#: count exact and every later page of the same search free.
_PAGE_SIZE = 30
_WAVE = 3
_MAX_PAGES = 9


def _search_page(query, page):
    """One page of hits, as cards. Returns (items, has_more, total_hint)."""
    try:
        data = _api("/subject/search",
                    body={"keyword": query, "page": page,
                          "perPage": _PAGE_SIZE})
    except NkiriError as e:
        logger.warning("movibox search failed %r p%d: %s", query, page, e)
        return [], False, 0
    items = []
    for subject in data.get("items") or ():
        if _wanted(subject):
            items.append(_item(subject))
    pager = data.get("pager") or {}
    try:
        hint = int(pager.get("totalCount") or 0)
    except (TypeError, ValueError):
        hint = 0
    return items, bool(pager.get("hasMore")), hint


def _enumerate(query):
    """Every hit for a query, deduped, in the API's order.

    Returns (items, complete). `complete` is False when the cap was reached,
    which is the only case where the count is a lower bound rather than a
    number.
    """
    return _enum_cache.get_or_set(query.lower(),
                                  lambda: _enumerate_uncached(query))


def _enumerate_uncached(query):
    items, seen = [], set()

    def absorb(found):
        for item in found:
            # a series comes back once per season, all sharing one detailPath,
            # so the card is the same card: keep the first
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            items.append(item)

    first, more, hint = _search_page(query, 1)
    absorb(first)
    if not more:
        return items, True

    # The API caps a page at 30 but usually returns fewer, so its totalCount
    # overstates how many pages there are. What one page actually held is the
    # better divisor, and it turns the whole read into a single parallel wave
    # for a typical query instead of one round trip per page.
    per_page = max(1, len(first))
    estimate = min(_MAX_PAGES, max(2, -(-hint // per_page) if hint else _WAVE))
    page = 2
    while page <= _MAX_PAGES:
        wave = list(range(page, min(page + estimate, _MAX_PAGES + 1)))
        if not wave:
            break
        with ThreadPoolExecutor(max_workers=len(wave)) as pool:
            results = list(pool.map(lambda p: _search_page(query, p), wave))
        for found, _has_more, _hint in results:
            absorb(found)
        # only the last page of the wave says whether there is more: an
        # earlier page's hasMore is about pages already fetched
        more = results[-1][1]
        if not more:
            return items, True
        page += len(wave)
    return items, False


def search(query, limit=24, page=1):
    """Search, paged from one cached enumeration.

    The API's own paging is not trustworthy — it reports more pages than it
    will serve, and its total is not the number of rows — so the whole result
    set is read once and sliced here. That is what makes the count exact and
    the page numbers honest.
    """
    query = (query or "").strip()
    if not query:
        return page_payload([], page, limit)

    def fetch():
        items, complete = _enumerate(query)
        start = max(0, (page - 1) * limit)
        window = items[start:start + limit]
        if complete:
            pages = max(1, (len(items) + limit - 1) // limit)
            return page_payload(window, page, limit, total=len(items),
                                total_pages=pages)
        # the cap was hit: say how many pages are known, not how many exist
        return page_payload(window, page, limit, total=None,
                            total_pages=page + 1)

    return _search_cache.get_or_set((query.lower(), limit, page), fetch)


# --------------------------------------------------------------------- post

def parse_ref(ref):
    """A detailPath, or a movibox URL. None when neither."""
    ref = (ref or "").strip()
    if not ref:
        return None
    if "movibox.net" in ref:
        path = urllib.parse.urlparse(ref).path.rstrip("/")
        return path.rsplit("/", 1)[-1] or None
    return ref


def _detail(path):
    return _detail_cache.get_or_set(path, lambda: _api(
        "/detail?detailPath=" + urllib.parse.quote(path)))


def _safe_name(text):
    return re.sub(r"[^A-Za-z0-9._ -]+", "", text or "").strip() or "movibox"


def _files(subject_id, path, se, ep):
    """One episode's files: [{resolution, url, size, codec}].

    Asked of `/subject/play`, not `/subject/download`. The two endpoints
    disagree: download marks the 1080p row `vipLocked` and withholds its URL,
    while play — the endpoint the site's own player uses — returns every
    resolution with a working link, to an anonymous client. The file is the
    same either way, so the play answer is the complete one, and it is what
    makes a quality choice possible at all.

    `/subject/download` is still asked when play comes back empty, so a title
    that only publishes downloads is not lost.
    """
    key = (subject_id, path, se, ep)

    def fetch():
        quoted = urllib.parse.quote(path)
        referer = PLAY_ROUTE + quoted
        rows = []
        for endpoint, field in (("play", "streams"), ("download", "downloads")):
            try:
                data = _api(f"/subject/{endpoint}?subjectId={subject_id}"
                            f"&se={se}&ep={ep}&detailPath={quoted}",
                            referer=referer)
            except NkiriError as e:
                logger.warning("movibox %s failed %s s%s e%s: %s",
                               endpoint, path, se, ep, e)
                continue
            rows = data.get(field) or []
            if any(r.get("url") for r in rows):
                break
        out = []
        for row in rows:
            url = row.get("url")
            if not url:
                continue
            try:
                size = int(row.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            try:
                resolution = int(row.get("resolutions") or row.get("resolution") or 0)
            except (TypeError, ValueError):
                resolution = 0
            out.append({"resolution": resolution, "url": url, "bytes": size,
                        "codec": row.get("codecName") or ""})
        out.sort(key=lambda f: -f["resolution"])
        return out

    return _files_cache.get_or_set(key, fetch)


def _episodes(seasons):
    """(season, episode) pairs to ask for.

    A film answers only to ``se=0&ep=0``; the season number is a real value
    here, so it is passed through as given rather than defaulted to one.
    """
    pairs = []
    for season in seasons:
        se = season.get("se")
        se = 0 if se is None else int(se)
        try:
            max_ep = int(season.get("maxEp") or 0)
        except (TypeError, ValueError):
            max_ep = 0
        for ep in range(1, max_ep + 1) if max_ep else [0]:
            pairs.append((se, ep))
    return pairs or [(0, 0)]


def post_view(path):
    """Detail view model, same keys the other sources produce."""
    data = _detail(path)
    subject = data.get("subject") or {}
    resource = data.get("resource") or {}
    seasons = resource.get("seasons") or []
    subject_id = subject.get("subjectId") or ""
    title = clean_title(subject.get("title") or "")
    pairs = _episodes(seasons)
    multi = len(pairs) > 1

    # one request per episode, so a ten-episode season is ten calls: they run
    # together rather than one after another, and each is cached
    with ThreadPoolExecutor(max_workers=min(8, len(pairs))) as pool:
        found = list(pool.map(
            lambda p: (p, _files(subject_id, path, p[0], p[1])), pairs))

    links = []
    for (se, ep), files in found:
        for f in files:
            res = f["resolution"]
            label = f"Episode {ep}" if multi else "Movie"
            if res:
                label += f" · {res}p"
            name = _safe_name(
                f"{title} S{se:02d}E{ep:02d} {res}p" if multi
                else f"{title} {res}p")
            links.append({
                "label": label,
                "text": "Download",
                "url": f["url"],
                "size": human_size(f["bytes"]) if f["bytes"] else None,
                "bytes": f["bytes"] or None,
                "name": name + ".mp4",
                "play": True,
                # the client groups these into one row per episode and offers
                # the qualities as a choice, so the number travels separately
                "resolution": res or None,
                "season": se if multi else None,
                "episode": ep if multi else None,
            })

    return {
        "id": path,
        "title": title,
        "url": f"{BASE}/movies/{path}",
        "date": (subject.get("releaseDate") or "")[:10],
        "poster": _poster(subject.get("cover")),
        "synopsis": subject.get("description") or "",
        "links": links,
        "genres": [],
        "formats": [],
    }


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


def clear_cache():
    for cache in (_home_cache, _menu_cache, _search_cache, _enum_cache,
                  _detail_cache, _files_cache):
        cache.clear()
    _token["value"], _token["at"] = None, 0.0
