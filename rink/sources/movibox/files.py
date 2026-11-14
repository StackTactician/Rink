"""One episode's files, asked of the endpoint that lists every quality."""

import logging
import urllib.parse

from ...errors import RinkError
from . import api, config, state

logger = logging.getLogger(__name__)

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
        referer = config.PLAY_ROUTE + quoted
        rows = []
        for endpoint, field in (("play", "streams"), ("download", "downloads")):
            try:
                data = api._api(f"/subject/{endpoint}?subjectId={subject_id}"
                            f"&se={se}&ep={ep}&detailPath={quoted}",
                            referer=referer)
            except RinkError as e:
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

    return state._files_cache.get_or_set(key, fetch)
