#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

try:
    import requests
except ImportError:
    print(
        json.dumps(
            {
                "query": "",
                "results": [],
                "suggestions": [],
                "answers": [],
                "total_results": 0,
                "error": "Missing dependency: pip install requests",
            },
            ensure_ascii=False,
        )
    )
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from http_utils import canonicalize_url, sanitize_extracted_text, stable_hash
from quality_layer import annotate_documents
from query_understanding import build_platform_query, build_query_profile
from source_adapter import NormalizedDocument

logger = logging.getLogger(__name__)

OPENCLAW_HOME = Path.home() / ".openclaw"
SEARXNG_STARTUP_SCRIPTS = [
    str(OPENCLAW_HOME / "searxng" / "start_searxng.cmd"),
    str(OPENCLAW_HOME / "searxng" / "manage"),
]
SEARXNG_STARTUP_TIMEOUT = 10
ACADEMIC_DOMAINS = {
    "arxiv.org",
    "semanticscholar.org",
    "scholar.google.com",
    "acm.org",
    "dl.acm.org",
    "ieeexplore.ieee.org",
    "nature.com",
    "sciencedirect.com",
    "springer.com",
    "paperswithcode.com",
}
COMMUNITY_DOMAINS = {
    "github.com",
    "news.ycombinator.com",
    "reddit.com",
    "www.reddit.com",
    "stackoverflow.com",
    "lobste.rs",
    "quora.com",
    "zhihu.com",
    "www.zhihu.com",
}
AGGREGATOR_DOMAINS = {
    "wikipedia.org",
    "en.wikipedia.org",
    "github.com/topics",
    "paperswithcode.com",
}


def dedupe_jsonable(items: list[Any]) -> list[Any]:
    seen: set[str] = set()
    deduped: list[Any] = []
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


class SearXNGSearchTool:
    def __init__(
        self,
        base_url: Optional[str] = None,
        max_results: int = 0,
        language: Optional[str] = None,
        safesearch: Optional[int] = None,
        timeout: Optional[int] = None,
        categories: Optional[str] = None,
    ):
        self.base_url = (base_url or os.environ.get("SEARXNG_BASE_URL", "http://localhost:8888")).rstrip("/")
        self.max_results = max_results or int(os.environ.get("SEARXNG_MAX_RESULTS", "10"))
        self.language = language or os.environ.get("SEARXNG_LANGUAGE", "all")
        self.safesearch = safesearch if safesearch is not None else int(os.environ.get("SEARXNG_SAFESEARCH", "0"))
        self.timeout = timeout or int(os.environ.get("SEARXNG_TIMEOUT", "15"))
        self.categories = categories or os.environ.get("SEARXNG_CATEGORIES", "general")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "OpenClaw-BasicSearch/1.0 (+https://docs.openclaw.ai)",
            }
        )

    def _is_port_in_use(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            return sock.connect_ex(("localhost", port)) == 0

    def _extract_port_from_url(self, url: str) -> Optional[int]:
        try:
            parsed = urlparse(url)
            if parsed.port:
                return parsed.port
            if parsed.scheme == "https":
                return 443
            if parsed.scheme == "http":
                return 80
        except Exception:
            return None
        return None

    def _start_searxng(self) -> bool:
        port = self._extract_port_from_url(self.base_url)
        if not port:
            logger.warning("Cannot extract port from URL: %s", self.base_url)
            return False

        for script_path in SEARXNG_STARTUP_SCRIPTS:
            if not os.path.exists(script_path):
                continue
            try:
                logger.info("Starting SearXNG from %s", script_path)
                if script_path.endswith((".cmd", ".bat")):
                    subprocess.Popen(
                        [script_path],
                        shell=True,
                        cwd=os.path.dirname(script_path),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    subprocess.Popen(
                        [script_path],
                        cwd=os.path.dirname(script_path),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                for _ in range(SEARXNG_STARTUP_TIMEOUT):
                    if self._is_port_in_use(port):
                        time.sleep(2)
                        return True
                    time.sleep(1)
                return self._is_port_in_use(port)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to start SearXNG from %s: %s", script_path, exc)
        return False

    def ensure_searxng_running(self) -> bool:
        try:
            response = self._session.get(urljoin(self.base_url + "/", "healthz"), timeout=3)
            if response.status_code == 200:
                return True
        except Exception:
            pass

        port = self._extract_port_from_url(self.base_url)
        if port and self._is_port_in_use(port):
            return True
        return self._start_searxng()

    def _build_query_variants(self, query: str) -> list[str]:
        original = query.strip()
        variants = [original]
        focused = build_platform_query(original, "github")
        if focused and focused.lower() != original.lower():
            variants.append(focused)
        return list(dict.fromkeys(variant for variant in variants if variant))

    def _request_search(self, params: dict[str, Any], query: str) -> dict[str, Any]:
        search_url = urljoin(self.base_url + "/", "search")
        try:
            response = self._session.get(search_url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return {"ok": True, "data": response.json()}
        except requests.exceptions.ConnectionError:
            if self.ensure_searxng_running():
                time.sleep(2)
                try:
                    response = self._session.get(search_url, params=params, timeout=self.timeout)
                    response.raise_for_status()
                    return {"ok": True, "data": response.json()}
                except Exception as exc:  # noqa: BLE001
                    return {"ok": False, "error": f"Cannot connect to SearXNG after auto-start: {exc}"}
            return {
                "ok": False,
                "error": (
                    f"Cannot connect to SearXNG at {self.base_url}. Auto-start failed; "
                    "please ensure the local service is installed and running."
                ),
            }
        except requests.exceptions.Timeout:
            return {"ok": False, "error": f"Request to SearXNG timed out after {self.timeout}s."}
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            if status == 403:
                return {
                    "ok": False,
                    "error": "SearXNG returned 403 Forbidden. Ensure JSON format is enabled in settings.yml.",
                }
            if status == 429:
                return {
                    "ok": False,
                    "error": "Rate limited by SearXNG. Try again later or use a self-hosted instance with limiter disabled.",
                }
            return {"ok": False, "error": f"SearXNG HTTP error {status}: {exc}"}
        except (requests.exceptions.RequestException, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"Search request failed: {exc}"}

    def _infer_source_type(self, url: str, category: str) -> str:
        domain = (urlparse(url).netloc or "").lower()
        if domain in ACADEMIC_DOMAINS or domain.endswith((".edu", ".ac.uk")):
            return "academic"
        if category == "news" or any(marker in domain for marker in ["news", "press", "media", "blog"]):
            return "newsroom"
        if domain in COMMUNITY_DOMAINS:
            return "community"
        if domain in AGGREGATOR_DOMAINS:
            return "aggregator"
        if domain.startswith(("docs.", "developer.", "developers.", "support.", "help.", "api.", "platform.")):
            return "official"
        if domain.endswith((".gov",)):
            return "official"
        return "official"

    def _credibility_hints(self, url: str, category: str) -> list[str]:
        domain = (urlparse(url).netloc or "").lower()
        hints: list[str] = []
        if domain.startswith(("docs.", "developer.", "developers.", "support.", "help.", "api.", "platform.")):
            hints.append("official_docs")
        if domain in ACADEMIC_DOMAINS or domain.endswith((".edu", ".ac.uk")):
            hints.append("academic_paper")
        if domain == "github.com":
            hints.append("github_repo")
        if domain == "news.ycombinator.com":
            hints.append("hn_discussion")
        if domain in {"paperswithcode.com", "semanticscholar.org"}:
            hints.append("citation_indexed")
        if category in {"news", "general", "it", "science"} and domain not in COMMUNITY_DOMAINS:
            hints.append("primary_source")
        if category in {"general", "it"} and domain not in ACADEMIC_DOMAINS and domain not in COMMUNITY_DOMAINS:
            hints.append("product_page")
        return list(dict.fromkeys(hints))

    def _normalize_results(self, raw_results: list[dict[str, Any]], query_variant: str) -> list[NormalizedDocument]:
        normalized: list[NormalizedDocument] = []
        for item in raw_results:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            title = sanitize_extracted_text(str(item.get("title") or ""), max_length=240)
            snippet = sanitize_extracted_text(str(item.get("content") or ""), max_length=420)
            canonical_url = canonicalize_url(url)
            category = str(item.get("category") or "")
            normalized.append(
                NormalizedDocument(
                    doc_id=f"searxng:{stable_hash(canonical_url)}",
                    platform="searxng",
                    source_type=self._infer_source_type(canonical_url, category),
                    title=title,
                    url=url,
                    canonical_url=canonical_url,
                    snippet=snippet,
                    published_at=str(item.get("publishedDate") or ""),
                    language="en" if any(ord(ch) < 128 for ch in (title + snippet)) else "",
                    engagement={"score": float(item.get("score") or 0.0)},
                    credibility_hints=self._credibility_hints(canonical_url, category),
                    content_hash=stable_hash(f"{title}\n{snippet}\n{canonical_url}"),
                    metadata={
                        "engines": list(item.get("engines") or []),
                        "category": category,
                        "thumbnail": item.get("thumbnail"),
                        "image_url": item.get("img_src"),
                        "query_variant": query_variant,
                    },
                )
            )
        return normalized

    def search(
        self,
        query: str,
        categories: Optional[str] = None,
        engines: Optional[str] = None,
        language: Optional[str] = None,
        pageno: int = 1,
        time_range: Optional[str] = None,
        safesearch: Optional[int] = None,
        max_results: Optional[int] = None,
    ) -> dict[str, Any]:
        if not query or not query.strip():
            return self._make_response(query="", error="Empty search query")

        effective_max = max_results or self.max_results
        query_variants = self._build_query_variants(query)
        all_documents: list[NormalizedDocument] = []
        suggestions: list[str] = []
        answers: list[str] = []
        unresponsive_engines: list[Any] = []
        errors: list[str] = []

        for variant in query_variants:
            params = {
                "q": variant,
                "format": "json",
                "categories": categories or self.categories,
                "language": language or self.language,
                "safesearch": safesearch if safesearch is not None else self.safesearch,
                "pageno": pageno,
            }
            if engines:
                params["engines"] = engines
            if time_range and time_range in {"day", "month", "year"}:
                params["time_range"] = time_range

            payload = self._request_search(params, query=variant)
            if not payload.get("ok"):
                errors.append(str(payload.get("error") or "unknown error"))
                continue

            data = payload["data"]
            suggestions.extend(list(data.get("suggestions") or []))
            answers.extend(list(data.get("answers") or []))
            unresponsive_engines.extend(list(data.get("unresponsive_engines") or []))
            raw_results = list(data.get("results") or [])
            per_query_limit = max(effective_max * 2, 8)
            all_documents.extend(self._normalize_results(raw_results[:per_query_limit], query_variant=variant))

        if not all_documents:
            return self._make_response(
                query=query,
                suggestions=dedupe_jsonable(suggestions),
                answers=dedupe_jsonable(answers),
                error="; ".join(dict.fromkeys(errors)) if errors else "No results found.",
            )

        deduped_by_url: dict[str, NormalizedDocument] = {}
        for document in all_documents:
            key = document.canonical_url or document.content_hash or document.doc_id
            if key not in deduped_by_url:
                deduped_by_url[key] = document
        deduped_documents = list(deduped_by_url.values())
        ranked_documents = annotate_documents(query, deduped_documents)

        results = []
        for item in ranked_documents[:effective_max]:
            metadata = dict(item.get("metadata") or {})
            result = {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", ""),
                "engines": metadata.get("engines", []),
                "score": (item.get("quality") or {}).get("combined", 0.0),
                "category": metadata.get("category", ""),
                "source_type": item.get("source_type", ""),
                "query_variant": metadata.get("query_variant", ""),
                "quality": item.get("quality", {}),
            }
            if item.get("published_at"):
                result["published_date"] = item["published_at"]
            if metadata.get("thumbnail"):
                result["thumbnail"] = metadata["thumbnail"]
            if metadata.get("image_url"):
                result["image_url"] = metadata["image_url"]
            results.append(result)

        return self._make_response(
            query=query,
            results=results,
            suggestions=dedupe_jsonable(suggestions),
            answers=dedupe_jsonable(answers),
            total_results=len(results),
            extra={
                "executed_queries": query_variants,
                "query_profile": build_query_profile(query).to_dict(),
                "ranking_backend": "local-quality-layer",
                "backend": "searxng + deep-search-style normalization",
                "unresponsive_engines": unresponsive_engines,
                "base_url": self.base_url,
                "errors": list(dict.fromkeys(errors)),
            },
        )

    def check_health(self) -> dict[str, Any]:
        config_url = urljoin(self.base_url + "/", "config")
        try:
            response = self._session.get(config_url, timeout=5)
            response.raise_for_status()
            config = response.json()
            return {
                "healthy": True,
                "base_url": self.base_url,
                "version": config.get("version", "unknown"),
                "engines_count": len(config.get("engines", [])),
                "categories": config.get("categories", []),
                "backend": "searxng + deep-search-style normalization",
                "error": None,
            }
        except requests.exceptions.ConnectionError:
            return {
                "healthy": False,
                "base_url": self.base_url,
                "backend": "searxng + deep-search-style normalization",
                "error": f"Cannot connect to {self.base_url}",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "healthy": False,
                "base_url": self.base_url,
                "backend": "searxng + deep-search-style normalization",
                "error": str(exc),
            }

    def format_results_as_text(self, response: dict[str, Any]) -> str:
        if response.get("error"):
            return f"Search error: {response['error']}"

        results = response.get("results", [])
        if not results:
            return f"No results found for: {response.get('query', '')}"

        meta = response.get("meta") or {}
        lines = [f"Search results for: {response['query']}"]
        if meta.get("executed_queries"):
            lines.append(f"Executed queries: {', '.join(meta['executed_queries'])}")
        if response.get("answers"):
            first_answer = response["answers"][0]
            if isinstance(first_answer, dict):
                answer_text = str(first_answer.get("answer") or first_answer.get("url") or first_answer)
            else:
                answer_text = str(first_answer)
            lines.append(f"Direct answer: {answer_text}")
        lines.append("")

        for index, item in enumerate(results, 1):
            lines.append(f"{index}. {item['title']}")
            lines.append(f"   URL: {item['url']}")
            if item.get("snippet"):
                lines.append(f"   {item['snippet']}")
            lines.append(
                f"   Score: {item.get('score', 0)} | Source: {item.get('source_type', 'unknown')} | Category: {item.get('category', '')}"
            )
            if item.get("published_date"):
                lines.append(f"   Published: {item['published_date']}")
            engines_str = ", ".join(item.get("engines", []))
            if engines_str:
                lines.append(f"   Engines: {engines_str}")
            lines.append("")

        suggestions = response.get("suggestions", [])
        if suggestions:
            lines.append(f"Related searches: {', '.join(suggestions[:5])}")
        return "\n".join(lines)

    @staticmethod
    def _make_response(
        query: str = "",
        results: Optional[list] = None,
        suggestions: Optional[list] = None,
        answers: Optional[list] = None,
        total_results: int = 0,
        error: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload = {
            "query": query,
            "results": results or [],
            "suggestions": suggestions or [],
            "answers": answers or [],
            "total_results": total_results,
            "error": error,
        }
        if extra:
            payload["meta"] = extra
        return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search the web using SearXNG with deep-search-style normalization and ranking.",
        epilog=(
            "Environment variables: SEARXNG_BASE_URL, SEARXNG_MAX_RESULTS, "
            "SEARXNG_LANGUAGE, SEARXNG_SAFESEARCH, SEARXNG_TIMEOUT, SEARXNG_CATEGORIES"
        ),
    )
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--base-url", default=None, help="SearXNG instance URL")
    parser.add_argument("--categories", default=None, help="Search categories: general, images, videos, news, map, music, it, science, files, social media")
    parser.add_argument("--engines", default=None, help="Comma-separated engine names")
    parser.add_argument("--language", default=None, help="Search language (e.g. en, zh, all)")
    parser.add_argument("--time-range", choices=["day", "month", "year"], default=None, help="Time range filter")
    parser.add_argument("--safesearch", type=int, choices=[0, 1, 2], default=None, help="Safe search level")
    parser.add_argument("--max-results", type=int, default=None, help="Maximum number of results to return")
    parser.add_argument("--page", type=int, default=1, help="Page number for pagination")
    parser.add_argument("--text", action="store_true", help="Output as human-readable text instead of JSON")
    parser.add_argument("--health", action="store_true", help="Check SearXNG instance health and exit")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--auto-start", action="store_true", default=True, help="Automatically start SearXNG if not running (default: True)")
    parser.add_argument("--no-auto-start", action="store_false", dest="auto_start", help="Disable automatic SearXNG startup")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s: %(message)s")

    tool = SearXNGSearchTool(
        base_url=args.base_url,
        categories=args.categories,
        language=args.language,
        safesearch=args.safesearch,
    )

    if args.auto_start and not args.health:
        if tool.ensure_searxng_running():
            logger.info("SearXNG is running")
        else:
            logger.warning("SearXNG auto-start failed, search may fail")

    if args.health:
        health = tool.check_health()
        print(json.dumps(health, indent=2, ensure_ascii=False))
        return 0 if health["healthy"] else 1

    if not args.query:
        parser.error("Search query is required (or use --health)")

    result = tool.search(
        query=args.query,
        categories=args.categories,
        engines=args.engines,
        language=args.language,
        pageno=args.page,
        time_range=args.time_range,
        safesearch=args.safesearch,
        max_results=args.max_results,
    )

    if args.text:
        print(tool.format_results_as_text(result))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))

    return 1 if result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
