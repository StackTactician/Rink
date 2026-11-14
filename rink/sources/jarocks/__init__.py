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

The work is split by what it is about:

  config    where the site lives, and what counts as a film
  state     the caches
  http      the two ways it answers: an HTML page, a REST body
  listing   cards, the feed, categories, and their pages
  filters   films and shows only, and the per-post category lookup
  search    REST for the matches, the search page for the posters
  post      one post: its links, its labels, and the rows they become
  resolve   the three-hop token chain, and the size on the landing page

Everything the rest of the app uses is re-exported here, so `sources` and the
tests keep talking to `jarocks.<name>` and never to a submodule.
"""

from . import config, filters, http, listing, post, resolve, search, state
from .config import (API, BASE, _CDN_HOST_RE, _FILE_HOST_RE, _FILM_SHOW_RE,
                     _FILM_SHOW_SLUGS, _SKIP_RE, _id_from_url,
                     _is_film_or_show)
from .filters import _cat_slugs, _listed_flags, _looks_like_film, _post_cats
from .http import _api, _get, _unescape_js
from .listing import (_cards, _category_url, _dedupe, _feed_page, _full_poster,
                      _rfc822, _strip_feed_junk, browse, latest, menu)
from .post import (_category_chips, _clean_label, _label_for, _poster,
                   _raw_post, _synopsis, find_links, parse_ref, post_view)
from .resolve import (_SIZE_AFTER_FILE_RE, _filename, _open, _opener,
                      _total_from_range, file_host_allowed, resolve_direct,
                      resolve_host_allowed, resolve_info, size_info)
from .search import search
from .state import _post_cat_cache, clear_cache

__all__ = [
    "menu", "latest", "browse", "search", "post_view", "parse_ref",
    "find_links", "resolve_direct", "resolve_info", "size_info",
    "file_host_allowed", "resolve_host_allowed", "clear_cache",
]


#: What this source is, and what it can do. See `sources.META` docs.
META = {
    "id": "9ja",
    "label": "9jarocks",
    "site": BASE,
    "kind": "category",
    "aliases": ("jarocks", "9jarocks", "9jarocks.net"),
    #: the size is on the file host's landing page, one GET per episode
    "can_size": True,
    #: one axis only: the site's own categories
    "has_formats": False,
    #: browsing a category serves 390x220 stills, newest-uploads serves posters,
    #: so no single ratio is right and the box takes whatever arrives
    "poster_aspect": None,
    "file_tags": ("9jarocks.net", "9jarocks"),
    "image_hosts": ("9jarocks.net", "www.9jarocks.net"),
}


def chips():
    """The chip row: the site's own film/show categories, biggest first."""
    return [{k: c[k] for k in ("slug", "name", "count")} for c in menu()]


def formats():
    """No second axis on this site."""
    return []


def file_referer(url):
    """loadedfiles wants no referer."""
    return None
