"""Command-line interface: search, list, show, download, open."""

import argparse
import os
import re
import sys
import time

from .content import display_label, find_download_links
from .download import download_file, filename_for, resolve_direct
from .errors import NkiriError
from .posts import get_post, raw_posts, raw_search
from .refs import parse_ref
from .text import clean_title, human_size, strip_tags


def _prog():
    """Name shown in the usage hints (stable across invocation styles)."""
    return "nkiri.py"

def _require_ref(ref):
    """parse_ref, but exit(2) when the reference cannot be resolved."""
    post_id = parse_ref(ref)
    if post_id is None:
        print(f"Could not resolve '{ref}' to a post id.", file=sys.stderr)
        sys.exit(2)
    return post_id


def _require_post(post_id):
    """get_post, but exit(2) with the CLI message on failure."""
    try:
        return get_post(post_id)
    except Exception as e:
        print(f"Failed to fetch post {post_id}: {e}", file=sys.stderr)
        sys.exit(2)


# ------------------------------------------------------------------ search

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


def cmd_search(args):
    try:
        res = raw_search(args.query, args.limit, args.page)
    except Exception as e:
        print(f"Search failed: {e}", file=sys.stderr)
        sys.exit(1)
    results = res["items"]
    if not results:
        where = f" on page {args.page}" if args.page > 1 else ""
        print(f"No results for '{args.query}'{where}.")
        return
    print(f"\nResults for '{args.query}' ({len(results)}):\n")
    for i, r in enumerate(results, 1):
        kind = "page" if r.get("type") == "page" else "post"
        print(f"  {i:>3}. {clean_title(r.get('title', ''))}")
        print(f"       id={r['id']}  [{kind}]")
    _page_line(res, f'python3 {_prog()} search "{args.query}" '
                    f'--limit {args.limit} --page {args.page + 1}')
    print(f"\nUse: python3 {_prog()} show <id>   |   download <id>\n")


def cmd_list(args):
    try:
        res = raw_posts(args.limit, args.page)
    except Exception as e:
        print(f"List failed: {e}", file=sys.stderr)
        sys.exit(1)
    rows = []
    for r in res["items"]:
        rows.append((r["id"], clean_title(r["title"]["rendered"]), r["date"][:10]))
    if args.type:
        t = args.type.lower()
        rows = [x for x in rows if t in x[1].lower()]
    print(f"\nLatest uploads ({len(rows)}):\n")
    for pid, title, date in rows:
        print(f"  {date}  {pid:>7}  {title}")
    _page_line(res, f"python3 {_prog()} list "
                    f"--limit {args.limit} --page {args.page + 1}")
    print(f"\nUse: python3 {_prog()} show <id>   |   download <id>\n")


# --------------------------------------------------------------- show page

_INFO_RE = re.compile(
    r"(quality|size|format|resolution|audio|language|year|genre|cast|"
    r"director|duration|story|about)", re.I)


def cmd_show(args):
    post = _require_post(_require_ref(args.ref))
    content = post["content"]["rendered"]

    text = strip_tags(re.sub(r"<br\s*/?>", "\n", content))
    text = re.sub(r"\n{3,}", "\n\n", text)

    print(f"\n{'=' * 62}")
    print(f"  {post['title']}")
    print(f"  Page: {post['link']}")
    print(f"{'=' * 62}\n")

    links = find_download_links(content)
    if links:
        print("  Download links:")
        for item in links:
            print(f"    - {item['text']}: {item['url']}")
    else:
        print("  (no external download links found on this page)")

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    info = [l for l in lines if _INFO_RE.search(l)]
    if info:
        print("\n  Info:")
        for l in info[:25]:
            print(f"    {l[:120]}")
    print()


# --------------------------------------------------------- download engine

def _choose_links(links, args):
    if args.all:
        return links
    if args.link:
        for i, item in enumerate(links, 1):
            if str(i) == str(args.link):
                return [item]
    return [links[0]]


def cmd_download(args):
    post = _require_post(_require_ref(args.ref))
    links = find_download_links(post["content"]["rendered"])
    if not links:
        print("No external download links found on this page.")
        sys.exit(1)

    if args.list:
        print(f"Download options for: {post['title']}\n")
        for i, item in enumerate(links, 1):
            print(f"  {i}. {item['text']}")
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
        label = display_label(item)
        print(f"\n{prefix}Resolving: {label}")
        try:
            direct = resolve_direct(item["url"], referer=post["link"])
        except NkiriError as e:
            print(f"{prefix}Resolve failed: {e}", file=sys.stderr)
            failures.append(label)
            continue

        dest = os.path.join(outdir, filename_for(direct))
        print(f"{prefix}Direct URL : {direct}")
        print(f"{prefix}Saving to  : {dest}")

        try:
            size = download_file(direct, dest, post["link"], quiet=args.quiet)
        except NkiriError as e:
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
    print(_require_post(_require_ref(args.ref))["link"])


# ------------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="nkiri",
        description="Clean custom client for thenkiri.com — search & download with no pop-up ads.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="search the site")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=15)
    sp.add_argument("--page", type=int, default=1, help="result page (default 1)")
    sp.set_defaults(fn=cmd_search)

    sp = sub.add_parser("list", help="list latest uploads")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--page", type=int, default=1, help="result page (default 1)")
    sp.add_argument("--type", choices=["movie", "series", "drama", "anime", "indian",
                                       "korean", "bollywood", "nollywood"],
                    help="filter titles by keyword")
    sp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("show", help="show a post's info + download links")
    sp.add_argument("ref", help="post id or thenkiri.com URL")
    sp.set_defaults(fn=cmd_show)

    sp = sub.add_parser("download", help="resolve + download a file")
    sp.add_argument("ref", help="post id or thenkiri.com URL")
    sp.add_argument("--out", help="output directory (default ~/Downloads)")
    sp.add_argument("--link", help="which download link to use (number, default 1)")
    sp.add_argument("--list", action="store_true", help="just list available links")
    sp.add_argument("--all", action="store_true",
                    help="download ALL links on the page (e.g. every episode)")
    sp.add_argument("--quiet", action="store_true", help="hide per-file progress bars")
    sp.set_defaults(fn=cmd_download)

    sp = sub.add_parser("open", help="print the page URL for a post id")
    sp.add_argument("ref")
    sp.set_defaults(fn=cmd_open)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
