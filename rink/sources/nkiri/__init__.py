"""thenkiri.com: the original source, and the one the app is named after.

It is WordPress, and its REST collection *is* open, so listing is a plain
`/posts?per_page=N` rather than a parsed archive. Two things are specific to
it:

  * **A genre table of its own.** The site files posts under WordPress
    categories, but the chips Rink shows are its own canonical genre list with
    an alias table per genre, because the site's own names drift.
  * **A two-step resolve on downloadwella.** A post links to an intermediate
    page, which carries a form; posting it returns the CDN link. The CDN
    honours Range, so a file can be resumed.

The work is split by what it is about:

  config    where the site lives, and what counts as the site itself
  state     the caches
  http      the REST side: a pooled connection to one WordPress install
  listing   the genre and format tables, and a category's page
  posts     the collection, search ranking, and one post's raw record
  post      a post's links and labels, and the rows they become
  media     the media batch that fills a page of posters
  resolve   the downloadwella chain, and the size on the landing page

Everything the rest of the app uses is re-exported here, so `sources` and the
tests keep talking to `nkiri.<name>` and never to a submodule.
"""

from . import config, http, listing, media, post, posts, refs, resolve, state
from .config import API, BASE, OWN_HOSTS
from .listing import (browse, find, format_names, formats, genre_names, genres,
                      public)
from .media import LARGE, media_url, media_urls
from .post import (clean_label, clean_text, display_label, extract_synopsis,
                   find_download_links, parse_post_view)
from .posts import (get_post, latest, page_payload, raw_posts, raw_search,
                    search_results)
from .refs import parse_ref
from .resolve import (direct_url_allowed, landing_size, resolve_direct,
                      resolve_info, resolve_target_allowed)
from .state import clear_cache

__all__ = [
    "menu", "browse", "latest", "search", "post_view", "parse_ref",
    "resolve_direct", "resolve_info", "landing_size", "clear_cache",
]


#: What this source is, and what it can do. The registry reads this instead of
#: keeping its own copy, so a new source is one module and no edits elsewhere.
META = {
    "id": "nkiri",
    "label": "Nkiri",
    "site": BASE,
    "kind": "genre",
    "aliases": ("thenkiri", "thenkiri.com"),
    #: the landing page states the size, for one GET we were making anyway
    "can_size": True,
    #: genres *and* formats are both chips here; the others have one axis
    "has_formats": True,
    #: detail posters are 700 tall at 600-1000 wide: a wide box, not a 2:3 one
    "poster_aspect": "10/7",
    "file_tags": ("thenkiri", "nkiri.ink", "nkiri.com", "nkiri", "dramakey.com", "dramakey"),
    "image_hosts": ("thenkiri.com", "www.thenkiri.com"),
}


#: the registry asks every source for `search`; this one calls it search_results
search = search_results


def chips():
    """The chip row: this source's own genres."""
    return public(genres())


def post_view(ref):
    """Detail view, with the tag/category ids resolved to names."""
    view = parse_post_view(get_post(int(ref)))
    view["genres"] = genre_names(view.pop("tag_ids", []))
    view["formats"] = format_names(view.pop("cat_ids", []))
    return view


def size_info(url):
    """Size from the landing page: it prints one and costs a single GET."""
    return landing_size(url)


def file_referer(url):
    """downloadwella wants no referer, so there is nothing to carry."""
    return None


#: the names the registry uses are this source's own names for the same thing
file_host_allowed = direct_url_allowed
resolve_host_allowed = resolve_target_allowed
