#!/usr/bin/env python3
"""WeChat (Weixin) article search via Sogou Weixin Search.

Uses scrapling StealthyFetcher (primary) or requests (fallback) to fetch
results from weixin.sogou.com, then parses structured JSON output.

Usage:
  py scripts/weixin_search.py search "AI Agent" --limit 10
  py scripts/weixin_search.py search "开发者技术博客" --type account --limit 5
  py scripts/weixin_search.py health
  py scripts/weixin_search.py search "OpenClaw" --fallback
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

logger = logging.getLogger("weixin-search")

# ---------- Dependency check ----------
HAS_SCRAPLING = False
HAS_LXML = False

try:
    from scrapling import StealthyFetcher
    HAS_SCRAPLING = True
except ImportError:
    pass

try:
    from lxml import etree
    HAS_LXML = True
except ImportError:
    pass

try:
    import requests
except ImportError:
    print(
        json.dumps({"error": "Missing dependency: pip install requests"}, ensure_ascii=False)
    )
    sys.exit(1)


# ---------- Constants ----------
BASE_URL = "https://weixin.sogou.com/weixin?query={query}&type={type}&page={page}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
TS_RE = re.compile(r"(\d{10})")


# ---------- Fetching ----------

def _fetch(url: str, fallback: bool = False) -> str:
    """Fetch page. Scrapling first, requests fallback."""
    if not fallback and HAS_SCRAPLING:
        try:
            fetcher = StealthyFetcher()
            page = fetcher.fetch(
                url,
                stealthy=True,
                disable_resources=True,
                wait_until="domcontentloaded",
                timeout=15,
            )
            text = page.text or ""
            if text:
                return text
        except Exception as e:
            logger.debug(f"scrapling fetch failed: {e}")

    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=10
        )
        resp.encoding = "utf-8"
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        logger.debug(f"requests fetch failed: {e}")

    return ""


# ---------- Parsing ----------

def _ts_to_str(ts: str) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _parse_articles(html: str) -> list[dict[str, Any]]:
    """Parse article search results (type=2)."""
    if not HAS_LXML:
        return []
    try:
        tree = etree.HTML(html)
        items = tree.xpath('//ul[@class="news-list"]/li')
        results = []
        for item in items:
            # Title / URL: <h3>/<a>
            title_nodes = item.xpath('.//h3/a')
            title = (
                title_nodes[0].xpath("string(.)").strip().replace("\n", "")
                if title_nodes
                else ""
            )
            url = title_nodes[0].get("href", "") if title_nodes else ""

            # Summary: <p class="txt-info">
            summary_nodes = item.xpath('.//p[@class="txt-info"]')
            summary = (
                summary_nodes[0].xpath("string(.)").strip()[:300]
                if summary_nodes
                else ""
            )

            # Author: <span class="all-time-*">
            author_nodes = item.xpath('.//span[contains(@class, "all-time")]')
            author = ""
            if author_nodes and author_nodes[0].text:
                author = author_nodes[0].text.strip()

            # Date: extract timestamp from <span class="s2"><script>
            pub_date = ""
            script_texts = item.xpath('.//span[contains(@class, "s2")]//script/text()')
            for t in script_texts:
                m = TS_RE.search(t)
                if m:
                    pub_date = _ts_to_str(m.group(1))
                    break

            if title or url:
                results.append({
                    "title": title,
                    "url": url,
                    "summary": summary,
                    "author": author,
                    "published": pub_date,
                    "source": "sogou-weixin",
                })
        return results
    except Exception as e:
        logger.debug(f"Article parse error: {e}")
        return []


def _parse_accounts(html: str) -> list[dict[str, Any]]:
    """Parse account search results (type=1)."""
    if not HAS_LXML:
        return []
    try:
        tree = etree.HTML(html)
        items = tree.xpath('//ul[@class="news-list2"]/li')
        results = []
        for item in items:
            name_nodes = item.xpath('.//div[@class="tit"]//a')
            name = (
                name_nodes[0].xpath("string(.)").strip()
                if name_nodes
                else ""
            )
            url = name_nodes[0].get("href", "") if name_nodes else ""

            wid_nodes = item.xpath('.//label[@name="em_weixinhao"]/text()')
            weixin_id = wid_nodes[0].strip() if wid_nodes else ""

            desc_nodes = item.xpath('.//p[@class="info"]//text()')
            desc = "".join(desc_nodes).strip()[:300] if desc_nodes else ""

            if name or url:
                results.append({
                    "name": name,
                    "url": url,
                    "weixin_id": weixin_id,
                    "description": desc,
                    "source": "sogou-weixin",
                })
        return results
    except Exception as e:
        logger.debug(f"Account parse error: {e}")
        return []


# ---------- Core ----------

def search_weixin(
    query: str,
    search_type: str = "article",
    limit: int = 10,
    fallback: bool = False,
) -> dict[str, Any]:
    """Search WeChat articles or accounts via Sogou Weixin Search."""
    encoded = quote(query)
    type_num = 1 if search_type == "account" else 2
    pages = max(1, (limit + 9) // 10)

    all_items: list[dict[str, Any]] = []
    fetch_modes = []
    errors = []

    for page in range(1, pages + 1):
        url = BASE_URL.format(query=encoded, type=type_num, page=page)
        html = _fetch(url, fallback=fallback)
        mode = ""
        ok = False

        if html and len(html) > 200:  # sanity check
            ok = True
            mode = f"{'fallback' if fallback else 'scrapling'}-p{page}"

        if not ok:
            errors.append(f"page {page}: fetch failed or empty")
            continue

        if search_type == "account":
            results = _parse_accounts(html)
        else:
            results = _parse_articles(html)

        all_items.extend(results)
        fetch_modes.append(mode)

    key = "accounts" if search_type == "account" else "articles"

    if not all_items and not errors:
        errors.append(
            "Empty results — Sogou may have served a CAPTCHA page "
            "or changed its HTML structure."
        )

    return {
        "query": query,
        "search_type": search_type,
        key: all_items[:limit],
        "total": min(len(all_items), limit),
        "pages_fetched": len(fetch_modes),
        "fetch_modes": ", ".join(fetch_modes),
        "warnings": errors,
    }


def health_check() -> dict[str, Any]:
    """Quick health check."""
    result = search_weixin("测试", limit=1)
    has_any = bool(result.get("articles") or result.get("accounts"))
    warnings = result.get("warnings", [])

    if has_any:
        status, reason = "healthy", f'OK — {len(result["articles"] + result.get("accounts", []))} result(s)'
    elif warnings:
        status, reason = "error", warnings[0]
    else:
        status, reason = "warning", "No results (structure may have changed)"

    return {
        "service": "sogou-weixin-search",
        "status": status,
        "reason": reason,
        "scrapling": HAS_SCRAPLING,
        "lxml": HAS_LXML,
        "warnings": warnings,
    }


# ---------- CLI ----------

def cmd_search(args: argparse.Namespace):
    result = search_weixin(
        args.query, args.type, args.limit, getattr(args, "fallback", False)
    )
    print(json.dumps(result, ensure_ascii=False, indent=None))


def cmd_health(_: argparse.Namespace):
    print(json.dumps(health_check(), ensure_ascii=False, indent=None))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weixin_search",
        description="WeChat (Weixin) article/account search via Sogou",
    )
    sub = parser.add_subparsers(dest="action")

    p1 = sub.add_parser("search", help="Search WeChat articles or accounts")
    p1.add_argument("query", help="Search keyword")
    p1.add_argument(
        "--type", choices=["article", "account"], default="article"
    )
    p1.add_argument("--limit", type=int, default=10)
    p1.add_argument(
        "--fallback",
        action="store_true",
        help="Skip scrapling, use requests only",
    )
    p1.set_defaults(func=cmd_search)

    p2 = sub.add_parser("health", help="Check service health")
    p2.set_defaults(func=cmd_health)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.action:
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except Exception as e:
        print(json.dumps({"error": str(e)[:300]}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
