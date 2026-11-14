# Rink

Browse and download movies, series and dramas from a browser on your own
machine or from a terminal. Three sources behind one interface: thenkiri.com,
9jarocks.net and movibox.net.

## Browser

```
python3 -m rink.web
```

Open `http://localhost:8321`, or that address with this machine's IP from a
phone on the same network. Search, open a title, pick a file, download. The
toggle in the header switches source.

## Terminal

```
python3 -m rink sources
python3 -m rink search "resident evil"
python3 -m rink list --src 9ja
python3 -m rink show 143755
python3 -m rink download 143755
```

`143755` stands for any post id or full link, and `--src` picks the source
(default: `nkiri`).

## Adding a source

A source is one package under `rink/sources/`, laid out like the others:

```
rink/sources/<name>/
  __init__.py   re-exports, and the META dict that describes the source
  config.py     where the site lives, and what counts as itself
  state.py      the caches
  http.py       how the site answers (or api.py, if it is a JSON API)
  listing.py    cards, menu, latest, browse, search
  post.py       one post's links, labels, and the view model
  resolve.py    a link -> a file, and the size
```

`META` is what the app reads to show the source: `id`, `label`, `site`,
`kind`, `aliases`, `can_size`, `has_formats`, `poster_aspect`, `image_hosts`,
`file_tags`. Then add the package to `_MODULES` in `rink/sources/__init__.py`
— that line is the only edit outside the package. The toggle, the size
policy, the image proxy and the download naming all follow from `META`.

`tests/test_source_contract.py` enforces the interface and adds a fake fourth
source to prove it needs nothing else.

## Notes

A personal tool, published as-is. No accounts, nothing stored beyond the
running process. It reads sites it does not own, so it works for as long as
those sites do.
