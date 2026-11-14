"""Fixed facts about thenkiri: where it lives, and what counts as itself."""

BASE = "https://thenkiri.com"
API = BASE + "/wp-json/wp/v2"

#: hosts that are the site itself, never a download target
OWN_HOSTS = frozenset({"", "thenkiri.com", "nkiri.ink", "dramakey.com"})
