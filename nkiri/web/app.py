"""Rink web server: routes, JSON API, static files, download streaming.

Run:  python3 -m nkiri.web [port]      (default 8321)
"""

import gzip
import json
import logging
import os
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..catalog import browse, formats, genres, public
from ..config import BASE
from ..content import parse_post_view
from ..download import resolve_info
from ..media import fetch_image, image_allowed, proxy_url
from ..net import open_stream
from ..posts import get_post, latest, page_payload, search_results
from ..refs import parse_ref
from ..text import human_size

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(STATIC_DIR)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "rink.log")

logger = logging.getLogger("nkiri.web")


def setup_logging(level=logging.INFO):
    """File + stdout logging for the server (never configures the CLI)."""
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    root = logging.getLogger("nkiri")
    root.setLevel(level)
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    if not any(type(h) is logging.StreamHandler for h in root.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    return root


class Handler(BaseHTTPRequestHandler):
    server_version = "rink/2.0"
    protocol_version = "HTTP/1.1"   # keep-alive: one socket per phone page load

    def log_message(self, fmt, *a):
        try:
            request_line = a[0] if a else ""
            status = a[1] if len(a) > 1 else "?"
        except Exception:
            request_line, status = "", "?"
        logger.info("REQ %s %s -> %s", self.command, self.path, status)

    # ------------------------------------------------------------ responses

    def _send(self, code, body, ctype="application/json; charset=utf-8",
              cache="no-store"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        gzipped = None
        if len(data) >= 512 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            gzipped = gzip.compress(data, 6)
            if len(gzipped) >= len(data):
                gzipped = None
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if gzipped is not None:
            self.send_header("Content-Encoding", "gzip")
            data = gzipped
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj))

    def _static(self, name, ctype):
        path = os.path.join(STATIC_DIR, name)
        if not os.path.exists(path):
            self._send(404, "not found", "text/plain")
            return
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype, cache="public, max-age=3600")

    # ------------------------------------------------------------- download

    def _stream_file(self, direct, name):
        """Proxy a direct file URL so the browser fetch stays same-origin."""
        try:
            with open_stream(direct) as r:
                ctype = r.headers.get("Content-Type") or "application/octet-stream"
                clen = r.headers.get("Content-Length")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                if clen:
                    self.send_header("Content-Length", clen)
                self.send_header("Content-Disposition",
                                 _disposition(name))
                self.send_header("Access-Control-Allow-Origin", "*")
                if not clen:
                    # unknown length: HTTP/1.1 cannot delimit it, so close after
                    self.send_header("Connection", "close")
                    self.close_connection = True
                self.end_headers()
                sent = 0
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    sent += len(chunk)
                logger.info("STREAM OK %s (%s)", name, human_size(sent))
        except (BrokenPipeError, ConnectionResetError):
            logger.warning("STREAM aborted (client closed) %s", name)
        except Exception as e:
            logger.warning("STREAM error %s: %s", name, e)
            try:
                self.send_response(502)
                self.end_headers()
            except Exception:
                pass

    # ---------------------------------------------------------------- routes

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path
        q = urllib.parse.parse_qs(u.query)

        try:
            route = ROUTES.get(path)
            if route is not None:
                return route(self, q)
            if path.startswith("/fonts/") and path.count("/") == 2:
                return self._static(os.path.join("fonts", path[7:]), "font/woff")
            self._send(404, "not found", "text/plain")
        except Exception as e:
            logger.exception("GET %s failed", self.path)
            return self._json({"error": str(e)}, 500)

    # ----------------------------------------------------------- endpoints

    def _ep_latest(self, q):
        self._json(latest(_int_param(q, "limit", 24), _int_param(q, "page", 1)))

    def _ep_search(self, q):
        query = _str_param(q, "q")
        limit = _int_param(q, "limit", 24)
        page = _int_param(q, "page", 1)
        if not query.strip():
            return self._json(page_payload([], page, limit, 0, 0))
        self._json(search_results(query, limit, page))

    def _ep_genres(self, q):
        self._json({"genres": public(genres())})

    def _ep_formats(self, q):
        self._json({"formats": public(formats())})

    def _ep_browse(self, q):
        self._json(browse(_str_param(q, "tag"), _str_param(q, "cat"),
                          _int_param(q, "limit", 24), _int_param(q, "page", 1)))

    def _ep_post(self, q):
        pid = parse_ref(_str_param(q, "id"))
        if not pid:
            return self._json({"error": "not found"}, 404)
        post = parse_post_view(get_post(pid))
        post["poster"] = proxy_url(post.get("poster"))
        return self._json(post)

    def _ep_resolve(self, q):
        url = _str_param(q, "url")
        referer = _str_param(q, "referer", BASE + "/")
        if not url:
            return self._json({"error": "missing url"}, 400)
        return self._json(resolve_info(url, referer))

    def _ep_file(self, q):
        direct = _str_param(q, "url")
        name = _str_param(q, "name", "download")
        if not direct:
            return self._json({"error": "missing url"}, 400)
        logger.info("STREAM request name=%s", name)
        return self._stream_file(direct, name)

    def _ep_img(self, q):
        """Same-origin poster proxy: the phone never talks to the CDN itself."""
        url = _str_param(q, "u")
        if not image_allowed(url):
            return self._send(404, "not found", "text/plain")
        hit = fetch_image(url)
        if not hit:
            return self._send(404, "not found", "text/plain")
        data, ctype = hit
        self._send(200, data, ctype, cache="public, max-age=604800, immutable")

    # ------------------------------------------------------------- static

    def _ep_index(self, q):
        self._static("index.html", "text/html; charset=utf-8")

    def _ep_js(self, q):
        self._static("app.js", "application/javascript; charset=utf-8")

    def _ep_css(self, q):
        self._static("style.css", "text/css; charset=utf-8")

def _disposition(name):
    """attachment header, ASCII-safe for old clients + RFC 5987 for the rest."""
    ascii_name = name.encode("ascii", "replace").decode("ascii").replace('"', "'")
    quoted = urllib.parse.quote(name, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"


def _str_param(q, key, default=""):
    return (q.get(key) or [default])[0]


def _int_param(q, key, default):
    try:
        return int(_str_param(q, key, str(default)))
    except ValueError:
        return default


ROUTES = {
    "/": Handler._ep_index,
    "/index.html": Handler._ep_index,
    "/app.js": Handler._ep_js,
    "/style.css": Handler._ep_css,
    "/api/latest": Handler._ep_latest,
    "/api/search": Handler._ep_search,
    "/api/genres": Handler._ep_genres,
    "/api/formats": Handler._ep_formats,
    "/api/browse": Handler._ep_browse,
    "/api/post": Handler._ep_post,
    "/api/resolve": Handler._ep_resolve,
    "/api/file": Handler._ep_file,
    "/api/img": Handler._ep_img,
}


def warm_cache(limit=24):
    """Prefetch the landing page so the first browser hit is already cached."""
    try:
        latest(limit)
        # the chip row needs these before the first paint, not after it
        logger.info("WARM catalog: %d genres, %d formats",
                    len(genres()), len(formats()))
    except Exception as e:
        logger.warning("WARM failed: %s", e)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    port = int(argv[0]) if argv else 8321
    setup_logging()
    threading.Thread(target=warm_cache, daemon=True).start()

    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    logger.info("=" * 60)
    logger.info("SESSION START  port=%d  pid=%d  log=%s", port, os.getpid(), LOG_FILE)
    print(f"rink web running:   http://localhost:{port}")
    print(f"logging to          {LOG_FILE}")
    print("(open on your phone via http://<this-computer-ip>:%d)" % port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
