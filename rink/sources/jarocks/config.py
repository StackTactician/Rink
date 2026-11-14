"""Fixed facts about this site: where it lives, and what is a film."""

import re

BASE = "https://9jarocks.net"
API = BASE + "/wp-json/wp/v2"


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

#: a post URL ends -id<number>.html
_ID_RE = re.compile(r"-id(\d+)\.html", re.I)


def _id_from_url(url):
    m = _ID_RE.search(url or "")
    return int(m.group(1)) if m else None
