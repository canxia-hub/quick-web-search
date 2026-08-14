#!/usr/bin/env python3
"""RSS/Atom Feed Reader CLI — RSS sub-command for quick-web-search skill.

Supports: fetch, add, remove, list, monitor, health.

Usage:
  # Fetch latest entries from a Feed URL
  py scripts/rss_fetch.py fetch "https://hnrss.org/newest" --limit 10

  # Add to subscription list
  py scripts/rss_fetch.py add "阮一峰" --url "https://www.ruanyifeng.com/blog/atom.xml"

  # List subscriptions
  py scripts/rss_fetch.py list

  # Monitor all subscribed feeds for new entries (incremental)
  py scripts/rss_fetch.py monitor

  # Health check a Feed
  py scripts/rss_fetch.py health "https://hnrss.org/newest"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

# ---------- Dependency check ----------
try:
    import feedparser
except ImportError:
    print(
        json.dumps({"error": "Missing dependency: pip install feedparser"}, ensure_ascii=False)
    )
    sys.exit(1)

try:
    import requests
except ImportError:
    print(
        json.dumps({"error": "Missing dependency: pip install requests"}, ensure_ascii=False)
    )
    sys.exit(1)

logger = logging.getLogger("rss-fetch")

# ---------- Paths ----------
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
FEEDS_DIR = Path.home() / ".openclaw" / "rss-subscribe"
DEFAULT_FEEDS_FILE = FEEDS_DIR / "feeds.json"
DEFAULT_STATE_FILE = FEEDS_DIR / "feeds.state.json"


# ---------- Helpers ----------

def _parse_date(date_str: str) -> Optional[float]:
    """Parse a date string to epoch seconds. Supports ISO 8601 and common formats."""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    # Try feedparser's date parser
    parsed = feedparser._parse_date(date_str)
    if parsed:
        try:
            return time.mktime(parsed[:9])
        except Exception:
            pass
    return None


def _entry_to_dict(entry: Any, feed_title: str = "") -> dict[str, Any]:
    """Convert a feedparser entry to a clean dict."""
    return {
        "title": entry.get("title", "").strip(),
        "link": entry.get("link", "").strip(),
        "summary": entry.get("summary", "")[:500].strip() if entry.get("summary") else "",
        "published": entry.get("published", entry.get("updated", "")),
        "authors": [a.get("name", "") for a in entry.get("authors", [])] if entry.get("authors") else [],
        "tags": [t.get("term", "") for t in entry.get("tags", [])][:5] if entry.get("tags") else [],
        "feed": feed_title,
    }


def _fetch_feed(url: str, limit: int = 20, since: Optional[str] = None) -> dict[str, Any]:
    """Fetch entries from a single RSS/Atom feed."""
    since_epoch = _parse_date(since) if since else 0

    user_agent = "OpenClaw/rss-fetch/1.0 (https://github.com/openclaw/openclaw)"

    try:
        feed = feedparser.parse(url, agent=user_agent, request_headers={"User-Agent": user_agent})
    except Exception as e:
        return {"error": f"Feed parse error: {str(e)}", "entries": [], "total": 0}

    error_messages = []
    if feed.bozo and feed.bozo_exception:
        error_messages.append(f"Feed warning: {str(feed.bozo_exception)[:200]}")

    feed_title = feed.feed.get("title", urlparse(url).netloc)

    entries = []
    for e in feed.entries[:limit * 3]:  # extra buffer for since filter
        entry_epoch = None
        pub_date = e.get("published_parsed") or e.get("updated_parsed")
        if pub_date:
            try:
                entry_epoch = time.mktime(pub_date[:9])
            except Exception:
                pass

        if since_epoch and entry_epoch and entry_epoch < since_epoch:
            continue

        entries.append(_entry_to_dict(e, feed_title))
        if len(entries) >= limit:
            break

    return {
        "feed_url": url,
        "feed_title": feed_title,
        "entries": entries,
        "total": len(entries),
        "bozo": len(error_messages) > 0,
        "warnings": error_messages,
    }


def _load_feeds(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_feeds(feeds: list[dict[str, str]], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(feeds, f, ensure_ascii=False, indent=2)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict[str, Any], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------- Actions ----------

def cmd_fetch(args: argparse.Namespace):
    """Fetch entries from a URL."""
    result = _fetch_feed(args.url, limit=args.limit, since=args.since)
    print(json.dumps(result, ensure_ascii=False))


def cmd_monitor(args: argparse.Namespace):
    """Monitor feeds and output only new entries since cutoff."""
    feeds_path = Path(args.feeds_file) if args.feeds_file else DEFAULT_FEEDS_FILE
    feeds = _load_feeds(feeds_path)

    # Read state file (tracks last checked timestamp per feed)
    state_path = feeds_path.with_suffix(".state.json")
    state = _load_state(state_path)

    feed_urls = [f["url"] for f in feeds] if feeds else ([args.url] if args.url else [])

    results = []
    for url in feed_urls:
        last_check = state.get(url, {}).get("last_check")
        result = _fetch_feed(url, limit=args.limit, since=last_check)
        if result.get("entries"):
            results.append(result)
        # Update state timestamp
        state[url] = {
            "last_check": datetime.now(timezone.utc).isoformat(),
            "count": len(result.get("entries", [])),
        }

    # Save state
    _save_state(state, state_path)

    print(json.dumps({"feeds_checked": len(feed_urls), "new_results": results}, ensure_ascii=False))


def cmd_list(args: argparse.Namespace):
    """List all subscribed feeds."""
    feeds_path = Path(args.feeds_file) if args.feeds_file else DEFAULT_FEEDS_FILE
    feeds = _load_feeds(feeds_path)
    if not feeds:
        print(json.dumps({"feeds": [], "file": str(feeds_path)}, ensure_ascii=False))
        return
    print(json.dumps({"feeds": feeds, "total": len(feeds), "file": str(feeds_path)}, ensure_ascii=False))


def cmd_add(args: argparse.Namespace):
    """Add a feed subscription."""
    feeds_path = Path(args.feeds_file) if args.feeds_file else DEFAULT_FEEDS_FILE
    feeds = _load_feeds(feeds_path)

    # Check duplicate
    for f in feeds:
        if f["url"] == args.url:
            print(json.dumps({"error": f"Feed already exists: {args.url}"}, ensure_ascii=False))
            sys.exit(1)

    feeds.append({
        "name": args.name or urlparse(args.url).netloc,
        "url": args.url,
        "added_at": datetime.now(timezone.utc).isoformat(),
    })
    _save_feeds(feeds, feeds_path)
    print(json.dumps({"ok": True, "feed": feeds[-1], "total": len(feeds)}, ensure_ascii=False))


def cmd_remove(args: argparse.Namespace):
    """Remove a feed subscription."""
    feeds_path = Path(args.feeds_file) if args.feeds_file else DEFAULT_FEEDS_FILE
    feeds = _load_feeds(feeds_path)

    before = len(feeds)
    feeds = [f for f in feeds if f["url"] != args.url and f.get("name") != args.url]

    if len(feeds) == before:
        print(json.dumps({"error": f"Feed not found: {args.url}"}, ensure_ascii=False))
        sys.exit(1)

    _save_feeds(feeds, feeds_path)
    print(json.dumps({"ok": True, "remaining": len(feeds), "removed": args.url}, ensure_ascii=False))


def cmd_health(args: argparse.Namespace):
    """Check feed health (reachable, parseable, entry count)."""
    url = args.url
    try:
        response = requests.head(url, timeout=10, allow_redirects=True, headers={
            "User-Agent": "OpenClaw/rss-fetch/1.0"
        })
        feed = feedparser.parse(url, agent="OpenClaw/rss-fetch/1.0")
        entry_count = len(feed.entries)

        if response.status_code >= 400:
            status = "error"
            reason = f"HTTP {response.status_code}"
        elif feed.bozo:
            status = "warning"
            reason = f"Bozo: {str(feed.bozo_exception)[:100]}"
        elif entry_count == 0:
            status = "warning"
            reason = "No entries found"
        else:
            status = "healthy"
            reason = f"OK — {entry_count} entries"

        print(json.dumps({
            "url": url,
            "status": status,
            "reason": reason,
            "http_status": response.status_code,
            "entry_count": entry_count,
            "feed_title": feed.feed.get("title", ""),
        }, ensure_ascii=False))

    except requests.exceptions.Timeout:
        print(json.dumps({"url": url, "status": "error", "reason": "Timeout (10s)"}, ensure_ascii=False))
    except requests.exceptions.RequestException as e:
        print(json.dumps({"url": url, "status": "error", "reason": str(e)[:200]}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"url": url, "status": "error", "reason": str(e)[:200]}, ensure_ascii=False))


# ---------- Argument Parser ----------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rss-fetch",
        description="RSS/Atom Feed Reader CLI — sub-command for quick-web-search skill",
    )
    subparsers = parser.add_subparsers(dest="action", help="Available actions")

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch latest entries from an RSS URL")
    p_fetch.add_argument("url", help="Feed URL")
    p_fetch.add_argument("--limit", type=int, default=10, help="Max entries (default: 10)")
    p_fetch.add_argument("--since", type=str, default=None, help="Only entries after date (ISO 8601)")
    p_fetch.set_defaults(func=cmd_fetch)

    # monitor
    p_monitor = subparsers.add_parser("monitor", help="Monitor subscribed feeds for updates")
    p_monitor.add_argument("--feeds-file", type=str, default=None)
    p_monitor.add_argument("--url", type=str, default=None, help="Single URL if no feeds file")
    p_monitor.add_argument("--limit", type=int, default=20)
    p_monitor.set_defaults(func=cmd_monitor)

    # list
    p_list = subparsers.add_parser("list", help="List subscribed feeds")
    p_list.add_argument("--feeds-file", type=str, default=None)
    p_list.set_defaults(func=cmd_list)

    # add
    p_add = subparsers.add_parser("add", help="Add a feed subscription")
    p_add.add_argument("name", nargs="?", help="Feed name (defaults to domain)")
    p_add.add_argument("--url", required=True, help="Feed URL")
    p_add.add_argument("--feeds-file", type=str, default=None)
    p_add.set_defaults(func=cmd_add)

    # remove
    p_remove = subparsers.add_parser("remove", help="Remove a feed subscription")
    p_remove.add_argument("url", help="Feed URL or name to remove")
    p_remove.add_argument("--feeds-file", type=str, default=None)
    p_remove.set_defaults(func=cmd_remove)

    # health
    p_health = subparsers.add_parser("health", help="Check feed health")
    p_health.add_argument("url", help="Feed URL")
    p_health.set_defaults(func=cmd_health)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except FileNotFoundError as e:
        print(json.dumps({"error": f"File not found: {str(e)}"}, ensure_ascii=False))
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid feeds file: {str(e)}"}, ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"Unexpected error: {str(e)[:200]}"}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
