"""Fixed facts about this site: where it lives, and what it serves."""

import re

BASE = "https://movibox.net"
API = "https://h5-api.aoneroom.com/wefeed-h5api-bff"

#: the player route. The API checks this exact prefix, so it is not a nicety.
PLAY_ROUTE = BASE + "/movies/"


#: subjectType 1 is a film, 2 is a series. The same feed also carries 6, which
#: is music compilations and stage shows — not what this app is for.
_FILM_TYPES = frozenset({1, 2})

#: the CDN the signed MP4s live on
_FILE_HOST_RE = re.compile(r"(^|\.)hakunaymatata\.com$", re.I)

#: what the CDN answers a movibox file request with if no movibox referer came
_FILE_REFERER = BASE + "/"

#: the API caps a page at 30 whatever perPage asks for, and its own
#: `totalCount` is not the number of rows it will hand over (a query that
#: reports 67 returns 31), so a real count means reading every page. Pages are
#: fetched in waves of three and the whole answer is cached, which makes the
#: count exact and every later page of the same search free.
_PAGE_SIZE = 30
_WAVE = 3
_MAX_PAGES = 9
