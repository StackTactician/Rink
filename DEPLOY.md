# Deploying

Two pieces: the Python server (API + download streaming) and the static page.
They can run together or apart.

## Server

Any host that runs a Python process on `$PORT`. `render.yaml` covers Render:

- Runtime `python`, build `pip install -r requirements.txt` (no packages needed),
  start `python -m nkiri.web`.
- The port comes from `$PORT`; a CLI argument still overrides it locally.
- Free instances sleep when idle. First request after a sleep takes ~30-60s
  while the process boots and warms its caches.
- Nothing is persisted between restarts: caches, posters, search state all sit
  in memory. That is by design, not an oversight.

## Static page

`nkiri/web/static` is the whole frontend: `index.html`, `app.js`, `style.css`,
`config.js`, `fonts/`. No build step.

Cloudflare Pages: root directory `nkiri/web/static`, no build command.

Then point the page at the server, in `config.js`:

```js
window.RINK_API = "https://<your-service>.onrender.com";
```

Empty string means "same origin", which is what you want when the Python
process serves the page itself. One-off override without committing:
`https://<pages-site>/?api=https://<service>.onrender.com`.

## What crosses the wire

- JSON endpoints send `Access-Control-Allow-Origin: *`, so a page on one host
  can read the API on another.
- Posters are fetched by the server once and re-served at `/api/img`, so the
  browser only ever talks to the API host.
- Downloads are resolved server-side and streamed through `/api/file`. Files
  therefore pass through the host: on a free plan they count against egress,
  and a slow transfer can outlive the request timeout. Resolve-then-link is not
  offered because the file hosts reject direct requests from browsers.

## Without the split

`python -m nkiri.web` serves the page and the API on one origin. Fewer moving
parts, no CORS, no cold start between the two halves - the only thing you lose
is static hosting's CDN, which matters little for a LAN or single-user tool.
