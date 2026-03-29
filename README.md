# searxng-web-search

A lightweight OpenClaw skill for fast web search through a self-hosted SearXNG instance, aligned with the same query-understanding and local ranking style used by `deep-search-research`.

## Positioning

Use this project for **quick search-and-scan tasks**:
- current web lookups
- recent news
- broad internet context gathering
- fast shortlist generation

Use `deep-search-research` instead when a task needs:
- an explicit research plan
- multi-source synthesis
- citations and evidence tracking
- a structured research report

## What changed

This public version keeps SearXNG as the retrieval backend, but aligns the search stack with `deep-search-research` by reusing the same style of:
- query understanding
- result normalization
- local quality-layer reranking

That makes quick search and deep research feel like two depths of one system instead of two unrelated systems.

## Repository layout

- `SKILL.md` — skill entrypoint
- `scripts/` — deterministic helpers and the main `searxng_search.py`
- `docs/PUBLIC-RELEASE-AUDIT.md` — release audit for public publication

## Quick start

```bash
py scripts/searxng_search.py "OpenClaw" --text
py scripts/searxng_search.py "latest browser automation agent news" --categories news --time-range day --max-results 5
py scripts/searxng_search.py --health
```

## Requirements

- Python 3.9+
- `requests`
- A reachable SearXNG instance with JSON output enabled

## Notes

- The script defaults to `http://localhost:8888` for local SearXNG.
- Auto-start looks for a local OpenClaw-style SearXNG installation under `~/.openclaw/searxng/`.
- No API key is required for this skill itself.
