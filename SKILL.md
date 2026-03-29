---
name: quick-web-search
description: Search the web through a self-hosted SearXNG instance with a lightweight but quality-aware pipeline. Use when the user needs a quick web lookup, current information, recent news, or broad internet context without a full research report. Prefer this skill for fast search-and-scan tasks; use a heavier research workflow only when the task needs planning, multi-source synthesis, citations, or a structured report.
---

# Quick Web Search

Use this skill as a **quality-aware quick-search layer** over SearXNG.

It keeps the retrieval path lightweight while improving output quality in three ways:
- normalize results into a stable document shape
- expand or compress queries with focused query-understanding logic
- re-rank results with a local quality-layer instead of trusting raw engine order

## Use this workflow

1. Use `scripts/searxng_search.py` for quick web lookups.
2. Keep the task lightweight: find, scan, shortlist, or gather current context.
3. If the user needs a report, research plan, claim tracing, or multi-platform synthesis, switch to a heavier research workflow.

## Command patterns

Basic search:
```bash
py scripts/searxng_search.py "your query"
```

Tech or news search:
```bash
py scripts/searxng_search.py "latest browser automation agent news" --categories news --time-range day --max-results 5
py scripts/searxng_search.py "open source coding assistant" --categories it --max-results 8
```

Human-readable output:
```bash
py scripts/searxng_search.py "OpenClaw" --text
```

Health check:
```bash
py scripts/searxng_search.py --health
```

## Output contract

The script returns JSON with:
- `query`
- `results`
- `suggestions`
- `answers`
- `total_results`
- `error`
- `meta`

`meta` contains execution details such as:
- `executed_queries`
- `query_profile`
- `ranking_backend`
- `backend`
- `unresponsive_engines`
- `base_url`

Each result includes:
- title
- url
- snippet
- engines
- score
- category
- source_type
- query_variant
- quality

## Guardrails

- Treat this as **fast search**, not deep research.
- Prefer the original query plus one focused variant; do not turn quick search into a large retrieval job.
- Preserve error transparency. If SearXNG is unreachable or rate-limited, surface it clearly.
- Use the returned `quality` block to guide filtering; do not assume raw engine order is trustworthy.

## Notes

- Auto-start is supported for the local SearXNG deployment.
- The quick-search path intentionally stays cheaper and shallower than a full research workflow.
- This skill is meant to keep fast lookup behavior stable and quality-aware without turning every search into a large research task.
