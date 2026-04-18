#!/usr/bin/env python3
"""Search bocpages.org (the Boards of Canada fan wiki) via the MediaWiki API."""

import argparse
import json
import sys
import urllib.parse
import urllib.request


API_URL = "https://bocpages.org/api.php"
PAGE_URL = "https://bocpages.org/wiki/"
USER_AGENT = "bocpages_search.py/1.0 (contact: user@example.com)"


def search_bocpages(query, limit=25, offset=0, what="text"):
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "sroffset": offset,
        "srwhat": what,
        "srprop": "snippet|size|wordcount|timestamp",
        "format": "json",
        "formatversion": "2",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    if "error" in data:
        raise RuntimeError(data["error"].get("info", "MediaWiki API error"))

    return data.get("query", {}).get("search", [])


def strip_html(text):
    import re
    return re.sub(r"<[^>]+>", "", text or "")


def format_hit(hit):
    title = hit.get("title", "")
    snippet = strip_html(hit.get("snippet", "")).strip()
    words = hit.get("wordcount", 0)
    ts = hit.get("timestamp", "")
    url = PAGE_URL + urllib.parse.quote(title.replace(" ", "_"))
    return f"{title}  ({words} words, {ts})\n  {url}\n  {snippet}"


def main():
    parser = argparse.ArgumentParser(description="Search bocpages.org.")
    parser.add_argument("query", help="Search query")
    parser.add_argument("-n", "--limit", type=int, default=25, help="Max results (1-50)")
    parser.add_argument("-o", "--offset", type=int, default=0, help="Result offset")
    parser.add_argument(
        "-w", "--what",
        choices=["text", "title", "nearmatch"],
        default="text",
        help="Search scope",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    try:
        hits = search_bocpages(
            args.query,
            limit=max(1, min(50, args.limit)),
            offset=max(0, args.offset),
            what=args.what,
        )
    except urllib.error.HTTPError as e:
        print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"API error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        json.dump(hits, sys.stdout, indent=2)
        print()
        return

    if not hits:
        print("No results.")
        return

    for hit in hits:
        print(format_hit(hit))
        print()


if __name__ == "__main__":
    main()
