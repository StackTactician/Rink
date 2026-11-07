# Rink

A small command-line tool and local web UI for browsing thenkiri.com: search
posts, list new uploads, read a post, and download its files.

It is a scraper. It talks to that site's public WordPress API and its download
hosts, so it is as stable as the site's markup and as legal as your use of it.

## Requirements

Python 3.9 or newer. No third-party packages.

## Web UI

```
python3 -m nkiri.web          # serves http://localhost:8321
python3 -m nkiri.web 9000     # other port
```

Open it in a browser, or from another device on the same network via
`http://<this-machine-ip>:8321`.

The page is plain HTML/CSS/JS served by the same process. Posters are fetched
from the site once and cached in memory, then served locally at `/api/img`.
Downloads are resolved server-side and streamed through `/api/file`, so the
browser saves them with its own download manager.

## CLI

```
python3 -m nkiri search "resident evil"
python3 -m nkiri list --limit 20
python3 -m nkiri show 143755
python3 -m nkiri download 143755 --link 2 --out ~/Downloads
```

`ref` is a post id or a full thenkiri.com URL. `python3 nkiri.py` works the
same way.

## How search works

WordPress returns search hits newest-first and scores body text, so plain
`?search=` gives poor ordering. Rink asks for relevance order, then ranks posts
whose title contains every query word first, then posts matching any word, and
pages that list itself. One upstream request per query; up to 100 posts are
pulled, so a search tops out at four pages of 30.

## Limits

- No authentication, no accounts, no database. State is in-memory and lost on
  restart.
- Search is capped at the 100 posts it fetches.
- Mislabelled or missing posters and download links come from the source site;
  Rink cleans what it can but does not invent data.
- The image and file proxies only accept hosts on an allowlist, but they do
  make this machine the middleman for whatever you download.

## Tests

```
python3 -m unittest discover -s tests
```

## Licence

None granted. This is a personal tool, published as-is.
