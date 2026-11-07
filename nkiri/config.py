"""Site constants shared by the CLI and the web server."""

BASE = "https://thenkiri.com"
API = BASE + "/wp-json/wp/v2"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Network timeouts (seconds)
TIMEOUT = 30
FORM_TIMEOUT = 30
HEAD_TIMEOUT = 20
STREAM_TIMEOUT = 60

# Hosts that are the site itself, never a download target
OWN_HOSTS = frozenset({"", "thenkiri.com", "nkiri.ink", "dramakey.com"})
