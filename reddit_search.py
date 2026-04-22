#!/usr/bin/env python3
"""Search Reddit using the public JSON endpoint.

Reddit requires a unique, descriptive User-Agent. Set REDDIT_USER_AGENT or
--user-agent to something like "myscript/1.0 (by /u/yourname)" per their API
rules; generic UAs get 403-ed. Falls back to old.reddit.com and .rss when the
primary host rate-limits.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


DEFAULT_USER_AGENT = (
    "reddit_search.py/1.1 "
    "(+https://github.com/7ochen/Q_DEV; contact: user@example.com)"
)

HOSTS = ["www.reddit.com", "old.reddit.com"]


def build_headers(user_agent):
    return {
        "User-Agent": user_agent,
        "Accept": "application/json, text/html;q=0.9, */*;q=0.1",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
    }


def fetch(url, headers, retries=4):
    delay = 2
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(delay)
            delay *= 2
    raise last_err


def search_json(query, subreddit, sort, time_range, limit, headers):
    for host in HOSTS:
        if subreddit:
            base = f"https://{host}/r/{subreddit}/search.json"
            params = {"q": query, "restrict_sr": "on", "sort": sort,
                      "t": time_range, "limit": limit, "raw_json": 1}
        else:
            base = f"https://{host}/search.json"
            params = {"q": query, "sort": sort, "t": time_range,
                      "limit": limit, "raw_json": 1}
        url = f"{base}?{urllib.parse.urlencode(params)}"
        try:
            data = json.loads(fetch(url, headers))
            return [c["data"] for c in data.get("data", {}).get("children", [])]
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                continue
            raise
    raise RuntimeError("All Reddit JSON hosts returned 403/429.")


def search_rss(query, subreddit, sort, time_range, limit, headers):
    """Last-resort fallback: Reddit's RSS feeds are less aggressively filtered."""
    if subreddit:
        base = f"https://www.reddit.com/r/{subreddit}/search.rss"
        params = {"q": query, "restrict_sr": "on", "sort": sort,
                  "t": time_range, "limit": limit}
    else:
        base = "https://www.reddit.com/search.rss"
        params = {"q": query, "sort": sort, "t": time_range, "limit": limit}
    url = f"{base}?{urllib.parse.urlencode(params)}"
    body = fetch(url, headers).decode("utf-8", errors="replace")
    root = ET.fromstring(body)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    posts = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link_el = entry.find("a:link", ns)
        link = link_el.get("href") if link_el is not None else ""
        author = (entry.findtext("a:author/a:name", default="", namespaces=ns) or "").strip()
        updated = entry.findtext("a:updated", default="", namespaces=ns) or ""
        posts.append({
            "title": title, "author": author.lstrip("/u/"),
            "permalink": urllib.parse.urlparse(link).path,
            "url": link, "score": 0, "num_comments": 0,
            "subreddit_name_prefixed": "", "created_utc": updated,
        })
    return posts


def format_post(post):
    title = post.get("title", "")
    author = post.get("author", "")
    sub = post.get("subreddit_name_prefixed", "")
    score = post.get("score", 0)
    comments = post.get("num_comments", 0)
    permalink = post.get("permalink", "")
    url = f"https://www.reddit.com{permalink}" if permalink else post.get("url", "")
    return f"[{score:>5} | {comments:>4}c] {sub} — {title}\n  by u/{author}\n  {url}"


def main():
    parser = argparse.ArgumentParser(description="Search Reddit.")
    parser.add_argument("query")
    parser.add_argument("-r", "--subreddit")
    parser.add_argument("-s", "--sort",
                        choices=["relevance", "hot", "top", "new", "comments"],
                        default="relevance")
    parser.add_argument("-t", "--time",
                        choices=["hour", "day", "week", "month", "year", "all"],
                        default="all")
    parser.add_argument("-n", "--limit", type=int, default=25)
    parser.add_argument("--user-agent",
                        default=os.environ.get("REDDIT_USER_AGENT", DEFAULT_USER_AGENT))
    parser.add_argument("--rss", action="store_true",
                        help="Force RSS fallback (less rate-limited)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    headers = build_headers(args.user_agent)
    limit = max(1, min(100, args.limit))

    try:
        if args.rss:
            posts = search_rss(args.query, args.subreddit, args.sort, args.time, limit, headers)
        else:
            try:
                posts = search_json(args.query, args.subreddit, args.sort,
                                    args.time, limit, headers)
            except (urllib.error.HTTPError, RuntimeError) as e:
                print(f"JSON endpoint failed ({e}); falling back to RSS.", file=sys.stderr)
                posts = search_rss(args.query, args.subreddit, args.sort,
                                   args.time, limit, headers)
    except urllib.error.HTTPError as e:
        print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        json.dump(posts, sys.stdout, indent=2)
        print()
        return

    if not posts:
        print("No results.")
        return

    for post in posts:
        print(format_post(post))
        print()


if __name__ == "__main__":
    main()
