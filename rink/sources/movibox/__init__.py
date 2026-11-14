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

The work is split by what it is about:

  config    where the site lives, and what it serves
  state     the caches, and the token
  api       the clock token, the JWT, and one request
  listing   the home rows, their pages, and search
  files     one episode's files, from the endpoint that lists every quality
  post      one title: its seasons, its episodes, and the rows they become
  resolve   a movibox link is already the file

Everything the rest of the app uses is re-exported here, so `sources` and the
tests keep talking to `movibox.<name>` and never to a submodule.
"""

from . import api, config, files, listing, post, resolve, state
from .api import _api, _client_token, _headers, _raw, _token_value
from .config import (API, BASE, PLAY_ROUTE, _FILE_HOST_RE, _FILE_REFERER,
                     _FILM_TYPES, _MAX_PAGES, _PAGE_SIZE, _WAVE)
from .files import _files
from .listing import (_enumerate, _flatten, _home, _item, _poster, _search_page,
                      _sections, _wanted, browse, latest, menu, search)
from .post import _detail, _episodes, _safe_name, parse_ref, post_view
from .resolve import (file_host_allowed, file_referer, resolve_host_allowed,
                      resolve_info, size_info)
from .state import _enum_cache, _files_cache, clear_cache

__all__ = [
    "menu", "latest", "browse", "search", "post_view", "parse_ref",
    "file_host_allowed", "file_referer", "resolve_host_allowed",
    "resolve_info", "size_info", "clear_cache",
]


#: What this source is, and what it can do. See `sources.META` docs.
META = {
    "id": "movibox",
    "label": "MoviBox",
    "site": BASE,
    "kind": "category",
    "aliases": ("movi", "movibox.net"),
    #: the API states every file's size inline, so there is nothing to ask for
    #: and a per-episode round trip would only repeat what we were told
    "can_size": False,
    #: one axis: its own home rows
    "has_formats": False,
    #: covers are 2:3 posters
    "poster_aspect": "2/3",
    "file_tags": ("movibox.net", "movibox"),
    "image_hosts": (".aoneroom.com",),
}


def chips():
    """The chip row: the site's own home rows."""
    return menu()


def formats():
    """No second axis on this site."""
    return []
