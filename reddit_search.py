#!/usr/bin/env python3
"""Search Reddit using the public JSON endpoint."""

import argparse
import json
import sys
import urllib.parse
import urllib.request


USER_AGENT = "reddit_search.py/1.0"


def search_reddit(query, subreddit=None, sort="relevance", time="all", limit=25):
    if subreddit:
        base = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {"q": query, "restrict_sr": "on", "sort": sort, "t": time, "limit": limit}
    else:
        base = "https://www.reddit.com/search.json"
        params = {"q": query, "sort": sort, "t": time, "limit": limit}

    url = f"{base}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    return [child["data"] for child in data.get("data", {}).get("children", [])]


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
    parser.add_argument("query", help="Search query")
    parser.add_argument("-r", "--subreddit", help="Limit to a subreddit")
    parser.add_argument(
        "-s", "--sort",
        choices=["relevance", "hot", "top", "new", "comments"],
        default="relevance",
    )
    parser.add_argument(
        "-t", "--time",
        choices=["hour", "day", "week", "month", "year", "all"],
        default="all",
    )
    parser.add_argument("-n", "--limit", type=int, default=25, help="Max results (1-100)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    try:
        posts = search_reddit(
            args.query,
            subreddit=args.subreddit,
            sort=args.sort,
            time=args.time,
            limit=max(1, min(100, args.limit)),
        )
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
