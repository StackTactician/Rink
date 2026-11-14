"""Command-line interface: search, list, show, download, open.

This is a client of the engine, not a part of it. Everything it needs comes
from `sources`, the same registry the web UI talks to, so every source the
web page can show is available here too — and a new source needs no change
in this file.
"""

import argparse
import os
import sys
import time

from . import sources
from .files import download_file, filename_for
from .errors import RinkError
from .text import human_size


def _prog():
    """Name shown in the usage hints (stable across invocation styles)."""
    return "rink.py"


def _src(args):
    return sources.norm(getattr(args, "source", None))


def _require_ref(src, ref):
    """parse_ref, but exit(2) when the reference cannot be resolved."""
    parsed = sources.parse_ref(src, ref)
    if not parsed:
        print(f"Could not resolve '{ref}' on {src}.", file=sys.stderr)
        sys.exit(2)
    return parsed


def _require_post(src, ref):
    """sources.post, but exit(2) with the CLI message on failure."""
    try:
        return sources.post(src, _require_ref(src, ref))
    except Exception as e:
        print(f"Failed to fetch {ref} on {src}: {e}", file=sys.stderr)
        sys.exit(2)


def _page_line(res, next_hint):
    """'Page 1 of 307 · 7367 total' plus a copy-paste next command."""
    pages = res.get("total_pages")
    total = res.get("total")
    if not pages:
        return
    print(f"\n  Page {res['page']} of {pages}"
          + (f" · {total} total" if total else ""))
    if res["page"] < pages:
        print(f"  Next: {next_hint}")


def _rows(res):
    """(id, title, date) for a page of cards."""
    return [(i.get("id"), i.get("title") or "", i.get("date") or "")
            for i in res.get("items") or ()]


# ------------------------------------------------------------------ listing

def cmd_sources(args):
    for s in sources.source_list():
        meta = sources.meta(s["id"])
        print(f"  {s['id']:<10} {s['label']:<12} {meta.get('site', '')}")
    print(f"\n  default: {sources.DEFAULT}")


def cmd_menu(args):
    src = _src(args)
    menu = sources.menu(src)
    print(f"\n{src} — {menu['kind']} chips:\n")
    for chip in menu["chips"]:
        count = chip.get("count")
        print(f"  {chip['slug']:<28} {chip['name']}"
              + (f"  ({count})" if count else ""))
    if menu.get("formats"):
        print("\n  formats:")
        for f in menu["formats"]:
            print(f"    {f['slug']:<28} {f['name']}")
    print()


def cmd_browse(args):
    src = _src(args)
    try:
        res = sources.browse(src, args.slug, args.cat, args.limit, args.page)
    except Exception as e:
        print(f"Browse failed: {e}", file=sys.stderr)
        sys.exit(1)
    rows = _rows(res)
    if not rows:
        print(f"Nothing under '{args.slug}' on {src}.")
        return
    print(f"\n{args.slug or 'latest'} on {src} ({len(rows)}):\n")
    for pid, title, date in rows:
        print(f"  {date}  {pid}  {title}")
    _page_line(res, f"python3 {_prog()} browse {args.slug} --source {src} "
                    f"--limit {args.limit} --page {args.page + 1}")
    print()


def cmd_list(args):
    src = _src(args)
    try:
        res = sources.latest(src, args.limit, args.page)
    except Exception as e:
        print(f"List failed: {e}", file=sys.stderr)
        sys.exit(1)
    rows = _rows(res)
    if args.type:
        t = args.type.lower()
        rows = [r for r in rows if t in r[1].lower()]
    print(f"\nLatest on {src} ({len(rows)}):\n")
    for pid, title, date in rows:
        print(f"  {date}  {pid}  {title}")
    _page_line(res, f"python3 {_prog()} list --source {src} "
                    f"--limit {args.limit} --page {args.page + 1}")
    print()


def cmd_search(args):
    src = _src(args)
    try:
        res = sources.search(src, args.query, args.limit, args.page)
    except Exception as e:
        print(f"Search failed: {e}", file=sys.stderr)
        sys.exit(1)
    rows = _rows(res)
    if not rows:
        where = f" on page {args.page}" if args.page > 1 else ""
        print(f"No results for '{args.query}'{where} on {src}.")
        return
    print(f"\nResults for '{args.query}' on {src} ({len(rows)}):\n")
    for pid, title, date in rows:
        print(f"  {date}  {pid}  {title}")
    _page_line(res, f'python3 {_prog()} search "{args.query}" '
                    f'--source {src} --limit {args.limit} --page {args.page + 1}')
    print(f"\nUse: python3 {_prog()} show <id> --source {src}"
          f"   |   download <id> --source {src}\n")


# --------------------------------------------------------------------- post

def cmd_show(args):
    src = _src(args)
    post = _require_post(src, args.ref)
    print(f"\n{'=' * 62}")
    print(f"  {post.get('title')}")
    print(f"  Page: {post.get('url')}")
    print(f"{'=' * 62}\n")
    if post.get("date"):
        print(f"  Added: {post['date']}")
    if post.get("synopsis"):
        print(f"\n  {post['synopsis'][:400]}\n")

    links = post.get("links") or []
    if links:
        print("  Download links:")
        for i, item in enumerate(links, 1):
            label = item.get("label") or item.get("text") or "File"
            size = f"  [{item['size']}]" if item.get("size") else ""
            print(f"    {i:>3}. {label}{size}")
            print(f"         {item['url']}")
    else:
        print("  (no download links found on this page)")
    print()


def _choose_links(links, args):
    if args.all:
        return links
    if args.link:
        for i, item in enumerate(links, 1):
            if str(i) == str(args.link):
                return [item]
    return [links[0]]


def cmd_download(args):
    src = _src(args)
    post = _require_post(src, args.ref)
    links = post.get("links") or []
    if not links:
        print("No download links found on this page.")
        sys.exit(1)

    if args.list:
        print(f"Download options for: {post.get('title')}\n")
        for i, item in enumerate(links, 1):
            label = item.get("label") or item.get("text") or "File"
            size = f"  [{item['size']}]" if item.get("size") else ""
            print(f"  {i}. {label}{size}")
            print(f"     {item['url']}\n")
        return

    chosen = _choose_links(links, args)
    outdir = os.path.expanduser(
        args.out or os.path.join(os.path.expanduser("~"), "Downloads"))
    os.makedirs(outdir, exist_ok=True)

    t0 = time.time()
    failures = []
    for n, item in enumerate(chosen, 1):
        prefix = f"[{n}/{len(chosen)}] " if len(chosen) > 1 else ""
        label = item.get("label") or item.get("text") or "File"
        print(f"\n{prefix}Resolving: {label}")
        try:
            # the host decides which chain to walk, so the tab the link came
            # from does not have to be passed along
            resolved = sources.resolve(item["url"], post.get("url"))
        except (RinkError, ValueError) as e:
            print(f"{prefix}Resolve failed: {e}", file=sys.stderr)
            failures.append(label)
            continue

        direct = resolved["direct"]
        name = item.get("name") or resolved.get("name") or filename_for(direct)
        dest = os.path.join(outdir, name)
        print(f"{prefix}Direct URL : {direct}")
        print(f"{prefix}Saving to  : {dest}")

        try:
            # a CDN that wants a referer gets one; the rest keep the page URL
            referer = sources.file_referer(direct, post.get("url"))
            size = download_file(direct, dest, referer, quiet=args.quiet)
        except RinkError as e:
            print(f"{prefix}Failed ({e})", file=sys.stderr)
            failures.append(label)
            continue
        print(f"{prefix}Done — {human_size(size)}")

    print(f"\n{'=' * 50}")
    print(f"Finished in {time.time() - t0:.0f}s. "
          f"{len(chosen) - len(failures)}/{len(chosen)} succeeded.")
    if failures:
        print("Failed:", *failures, sep="\n  - ")
        sys.exit(1)


def cmd_open(args):
    src = _src(args)
    print(_require_post(src, args.ref).get("url"))


# --------------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="rink",
        description="Clean client for the configured sources — search, browse "
                    "and download with no pop-up ads.")
    ids = [s["id"] for s in sources.source_list()]
    p.add_argument("--source", "-s", default=sources.DEFAULT, choices=ids,
                   help=f"which site to talk to (default {sources.DEFAULT})")
    sub = p.add_subparsers(dest="cmd", required=True)

    def _sub(name, help):
        """A subcommand, with the source flag in front of or behind it."""
        sp = sub.add_parser(name, help=help)
        sp.add_argument("--source", "-s", default=argparse.SUPPRESS,
                        choices=ids,
                        help="which site to talk to (default: the one above)")
        return sp

    sp = _sub("sources", "list the available sources")
    sp.set_defaults(fn=cmd_sources)

    sp = _sub("menu", "show a source's chip row")
    sp.set_defaults(fn=cmd_menu)

    sp = _sub("browse", "list one chip's titles")
    sp.add_argument("slug", nargs="?", default="", help="chip slug (see menu)")
    sp.add_argument("--cat", default="", help="format filter, where the source has one")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--page", type=int, default=1)
    sp.set_defaults(fn=cmd_browse)

    sp = _sub("list", "list latest uploads")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--page", type=int, default=1, help="result page (default 1)")
    sp.add_argument("--type", help="filter titles by keyword")
    sp.set_defaults(fn=cmd_list)

    sp = _sub("search", "search the site")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=15)
    sp.add_argument("--page", type=int, default=1, help="result page (default 1)")
    sp.set_defaults(fn=cmd_search)

    sp = _sub("show", "show a post's info + download links")
    sp.add_argument("ref", help="post id or a URL from that site")
    sp.set_defaults(fn=cmd_show)

    sp = _sub("download", "resolve + download a file")
    sp.add_argument("ref", help="post id or a URL from that site")
    sp.add_argument("--out", help="output directory (default ~/Downloads)")
    sp.add_argument("--link", help="which download link to use (number, default 1)")
    sp.add_argument("--list", action="store_true", help="just list available links")
    sp.add_argument("--all", action="store_true",
                    help="download ALL links on the page (e.g. every episode)")
    sp.add_argument("--quiet", action="store_true", help="hide per-file progress bars")
    sp.set_defaults(fn=cmd_download)

    sp = _sub("open", "print the page URL for a post id")
    sp.add_argument("ref")
    sp.set_defaults(fn=cmd_open)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
