#!/usr/bin/env python3
"""Search bocpages.org (the Boards of Canada fan wiki) via MediaWiki API.

MediaWiki (and Wikimedia's policy in particular) rejects requests with generic
or missing User-Agents with 403. Format: '<client>/<ver> (<contact>) <lib>/<ver>'.
Override via BOC_USER_AGENT or --user-agent. Falls back to OpenSearch and to
scraping Special:Search if api.php is blocked.
"""

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


API_URL = "https://bocpages.org/w/api.php"
SEARCH_URL = "https://bocpages.org/w/index.php"
PAGE_URL = "https://bocpages.org/wiki/"

DEFAULT_USER_AGENT = (
    "bocpages_search.py/1.1 "
    "(+https://github.com/7ochen/Q_DEV; contact: user@example.com) "
    "python-urllib/3"
)


def build_headers(user_agent):
    return {
        "User-Agent": user_agent,
        "Api-User-Agent": user_agent,
        "Accept": "application/json, text/html;q=0.9, */*;q=0.1",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
    }


def fetch(url, headers, retries=4):
    delay = 2
    last_err = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(delay); delay *= 2; continue
            raise
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(delay); delay *= 2
    raise last_err


def strip_html(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text or ""))


def page_url(title):
    return PAGE_URL + urllib.parse.quote(title.replace(" ", "_"))


def search_api(query, limit, offset, what, headers):
    params = {
        "action": "query", "list": "search", "srsearch": query,
        "srlimit": limit, "sroffset": offset, "srwhat": what,
        "srprop": "snippet|size|wordcount|timestamp",
        "format": "json", "formatversion": "2",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    data = json.loads(fetch(url, headers))
    if "error" in data:
        raise RuntimeError(data["error"].get("info", "MediaWiki API error"))
    return data.get("query", {}).get("search", [])


def search_opensearch(query, limit, headers):
    params = {"action": "opensearch", "search": query, "limit": limit, "format": "json"}
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    data = json.loads(fetch(url, headers))
    # [query, [titles], [descs], [urls]]
    titles, descs, urls = data[1], data[2], data[3]
    return [{"title": t, "snippet": d, "url": u}
            for t, d, u in zip(titles, descs, urls)]


def search_scrape(query, limit, headers):
    """Fallback: scrape Special:Search HTML when api.php is unavailable."""
    params = {"title": "Special:Search", "search": query,
              "fulltext": "Search", "limit": limit}
    url = f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"
    body = fetch(url, headers).decode("utf-8", errors="replace")

    # bocpages uses single quotes in its rendered HTML; accept either quote style.
    pattern = re.compile(
        r'''class=['"]mw-search-result-heading['"]>\s*'''
        r'''<a\s+href=['"]([^'"]+)['"][^>]*title=['"]([^'"]+)['"][^>]*>''',
        re.IGNORECASE,
    )
    snippet_re = re.compile(
        r'''class=['"]searchresult['"][^>]*>(.*?)</div>''',
        re.IGNORECASE | re.DOTALL,
    )
    data_re = re.compile(
        r'''class=['"]mw-search-result-data['"][^>]*>(.*?)</div>''',
        re.IGNORECASE | re.DOTALL,
    )
    snippets = snippet_re.findall(body)
    data_lines = data_re.findall(body)

    hits = []
    for i, m in enumerate(pattern.finditer(body)):
        href, title = m.group(1), m.group(2)
        snip = strip_html(snippets[i]).strip() if i < len(snippets) else ""
        meta = strip_html(data_lines[i]).strip() if i < len(data_lines) else ""
        full = urllib.parse.urljoin("https://bocpages.org", href)
        hits.append({"title": title, "snippet": snip, "url": full, "meta": meta})
        if len(hits) >= limit:
            break
    return hits


def format_hit(hit):
    title = hit.get("title", "")
    snippet = strip_html(hit.get("snippet", "")).strip()
    url = hit.get("url") or page_url(title)
    words = hit.get("wordcount")
    ts = hit.get("timestamp", "")
    if words is not None:
        meta = f"  ({words} words, {ts})"
    elif hit.get("meta"):
        meta = f"  ({hit['meta']})"
    else:
        meta = ""
    return f"{title}{meta}\n  {url}\n  {snippet}"


def main():
    parser = argparse.ArgumentParser(description="Search bocpages.org.")
    parser.add_argument("query")
    parser.add_argument("-n", "--limit", type=int, default=25)
    parser.add_argument("-o", "--offset", type=int, default=0)
    parser.add_argument("-w", "--what",
                        choices=["text", "title", "nearmatch"], default="text")
    parser.add_argument("--user-agent",
                        default=os.environ.get("BOC_USER_AGENT", DEFAULT_USER_AGENT))
    parser.add_argument("--mode",
                        choices=["auto", "api", "opensearch", "scrape"],
                        default="auto")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    headers = build_headers(args.user_agent)
    limit = max(1, min(50, args.limit))
    offset = max(0, args.offset)

    def try_mode(mode):
        if mode == "api":
            return search_api(args.query, limit, offset, args.what, headers)
        if mode == "opensearch":
            return search_opensearch(args.query, limit, headers)
        if mode == "scrape":
            return search_scrape(args.query, limit, headers)

    order = [args.mode] if args.mode != "auto" else ["api", "opensearch", "scrape"]

    hits = None
    for mode in order:
        try:
            hits = try_mode(mode)
            break
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as e:
            print(f"[{mode}] failed: {e}", file=sys.stderr)
            continue

    if hits is None:
        print("All modes failed.", file=sys.stderr)
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
