"""Constants no single source owns: the user agent the sites expect, and
the timeouts. Anything about one site belongs in that source's config."""

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Network timeouts (seconds)
TIMEOUT = 30
FORM_TIMEOUT = 30
HEAD_TIMEOUT = 20
STREAM_TIMEOUT = 60

