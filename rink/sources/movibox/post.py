"""One title: its seasons, its episodes, and the rows they become."""

import logging
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from ...text import clean_title, human_size
from . import api, config, state
from .files import _files
from .listing import _poster

logger = logging.getLogger(__name__)

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
    return state._detail_cache.get_or_set(path, lambda: api._api(
        "/detail?detailPath=" + urllib.parse.quote(path)))


def _safe_name(text):
    return re.sub(r"[^A-Za-z0-9._ -]+", "", text or "").strip() or "movibox"


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
        "url": f"{config.BASE}/movies/{path}",
        "date": (subject.get("releaseDate") or "")[:10],
        "poster": _poster(subject.get("cover")),
        "synopsis": subject.get("description") or "",
        "links": links,
        "genres": [],
        "formats": [],
    }
