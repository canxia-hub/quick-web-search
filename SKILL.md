---
name: searxng-web-search
description: Search the web through a self-hosted SearXNG instance with a lightweight pipeline aligned to deep-search-research. Use when the user needs a quick web lookup, current information, recent news, or broad internet context without a full research report. Prefer this skill for fast search-and-scan tasks; prefer deep-search-research when the task needs a plan, multi-source synthesis, citations, or a structured research deliverable.
---

# SearXNG Web Search

Use this skill as the **quick-search companion** to `deep-search-research`.

It keeps the retrieval path lightweight, but aligns with the deep-search stack in three ways:
- normalize results into a stable document shape
- expand or compress queries with the same query-understanding logic
- re-rank results with the same local quality-layer style instead of trusting raw engine order

## Use this workflow

1. Use `scripts/searxng_search.py` for quick web lookups.
2. Keep the task lightweight: find, scan, shortlist, or gather current context.
3. If the user needs a report, research plan, claim tracing, or multi-platform synthesis, switch to `deep-search-research`.

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
- The quick-search path intentionally stays cheaper and shallower than `deep-search-research`.
- This skill is meant to reduce search-system drift: quick lookup and deep research should feel like two depths of the same stack, not two unrelated systems.
