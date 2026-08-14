# quick-web-search

A lightweight OpenClaw skill for fast web search through a self-hosted SearXNG instance, RSS/Atom feed monitoring, and optional WeChat article/account search through Sogou Weixin.

## Positioning

Use this project for **quick search-and-scan tasks**:
- current web lookups
- recent news
- broad internet context gathering
- fast shortlist generation
- RSS/Atom feed fetching and incremental monitoring
- WeChat article/account discovery through Sogou Weixin

Use a heavier research workflow instead when a task needs:
- an explicit research plan
- multi-source synthesis
- citations and evidence tracking
- a structured research report

## What changed

This public version keeps SearXNG as the retrieval backend, while strengthening the search stack with:
- query understanding
- result normalization
- local quality-layer reranking
- RSS/Atom feed subscriptions and incremental monitoring
- an optional Sogou Weixin adapter with a requests fallback

That makes quick search feel more stable, selective, and consistent than raw metasearch output alone.

## Repository layout

- `SKILL.md` — skill entrypoint
- `scripts/searxng_search.py` — SearXNG search entrypoint
- `scripts/rss_fetch.py` — RSS/Atom fetch, subscription, and monitor entrypoint
- `scripts/weixin_search.py` — optional WeChat article/account search entrypoint
- `scripts/` — deterministic search helpers
- `docs/PUBLIC-RELEASE-AUDIT.md` — release audit for public publication

## Quick start

```bash
py scripts/searxng_search.py "OpenClaw" --text
py scripts/searxng_search.py "latest browser automation agent news" --categories news --time-range day --max-results 5
py scripts/searxng_search.py --health
py scripts/rss_fetch.py fetch "https://hnrss.org/newest" --limit 10
py scripts/rss_fetch.py monitor
py scripts/weixin_search.py search "OpenClaw" --limit 5 --fallback
```

## Requirements

- Python 3.9+
- `requests`
- `feedparser` for RSS/Atom support
- `lxml` for WeChat result parsing
- Optional: `scrapling` for the primary stealthy WeChat fetch path; `requests` remains available as a fallback
- A reachable SearXNG instance with JSON output enabled

## Notes

- The script defaults to `http://localhost:8888` for local SearXNG.
- Auto-start looks for a local OpenClaw-style SearXNG installation under `~/.openclaw/searxng/`.
- No API key is required for this skill itself.
- RSS subscription state is stored under `~/.openclaw/rss-subscribe/`.
- Sogou Weixin may serve CAPTCHAs or change its HTML; the adapter reports empty/failed retrievals transparently.
