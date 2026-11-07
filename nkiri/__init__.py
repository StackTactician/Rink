"""nkiri — clean client and web UI for thenkiri.com.

Package layout:
  config    site constants
  errors    exception types
  net       HTTP primitives (GET, form POST, HEAD size)
  text      HTML/text helpers
  refs      post-id resolution from ids and URLs
  media     WP media -> image URL, with cache
  posts     post/search/latest service layer
  content   post-content scraping (links, synopsis, view model)
  download  2-step downloadwella resolver + file transfer
  cli       argparse CLI
  web       HTTP server + static UI
"""

import logging

# No handlers configured in the CLI: keep library warnings silent unless the
# host (web) configures logging.
logging.getLogger("nkiri").addHandler(logging.NullHandler())

__version__ = "2.0"
