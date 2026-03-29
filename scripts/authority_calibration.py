from __future__ import annotations

from typing import Any

DOMAIN_EXACT_RULES = {
    "github.com": {"tier": "high", "label": "open-source-code-host"},
    "arxiv.org": {"tier": "high", "label": "preprint-archive"},
    "semanticscholar.org": {"tier": "high", "label": "citation-index"},
    "news.ycombinator.com": {"tier": "medium", "label": "community-discussion"},
    "docs.github.com": {"tier": "very-high", "label": "official-docs"},
    "openai.com": {"tier": "high", "label": "vendor-site"},
    "platform.openai.com": {"tier": "very-high", "label": "official-api-docs"},
    "anthropic.com": {"tier": "high", "label": "vendor-site"},
    "docs.anthropic.com": {"tier": "very-high", "label": "official-api-docs"},
    "ai.google.dev": {"tier": "very-high", "label": "official-api-docs"},
    "developers.google.com": {"tier": "very-high", "label": "official-docs"},
    "acm.org": {"tier": "high", "label": "academic-publisher"},
    "dl.acm.org": {"tier": "very-high", "label": "academic-publisher"},
    "ieeexplore.ieee.org": {"tier": "very-high", "label": "academic-publisher"},
    "nature.com": {"tier": "very-high", "label": "academic-publisher"},
    "sciencedirect.com": {"tier": "high", "label": "academic-publisher"},
    "paperswithcode.com": {"tier": "high", "label": "research-index"},
}

DOMAIN_SUFFIX_RULES = {
    ".gov": {"tier": "very-high", "label": "government"},
    ".edu": {"tier": "high", "label": "education"},
    ".ac.uk": {"tier": "high", "label": "academic-institution"},
}

TIER_SCORES = {
    "very-high": 0.95,
    "high": 0.82,
    "medium": 0.64,
    "low": 0.45,
    "unknown": 0.52,
}

SOURCE_TYPE_FLOORS = {
    "official": 0.88,
    "academic": 0.84,
    "newsroom": 0.68,
    "community": 0.54,
    "aggregator": 0.38,
}

HINT_WEIGHTS = {
    "official_repo": 0.08,
    "official_docs": 0.10,
    "primary_source": 0.07,
    "academic_paper": 0.07,
    "peer_reviewed": 0.08,
    "citation_indexed": 0.04,
    "benchmark": 0.03,
    "product_page": 0.03,
    "vendor_blog": 0.01,
}

NEGATIVE_HINTS = {
    "mirror": -0.06,
    "repost": -0.08,
    "aggregated_summary": -0.08,
    "low_signal_discussion": -0.05,
}


def authority_rule(domain: str) -> dict[str, str]:
    normalized = (domain or "").lower()
    if normalized in DOMAIN_EXACT_RULES:
        return DOMAIN_EXACT_RULES[normalized]
    for suffix, payload in DOMAIN_SUFFIX_RULES.items():
        if normalized.endswith(suffix):
            return payload
    return {"tier": "unknown", "label": "unclassified"}


def authority_breakdown(domain: str, source_type: str, hints: list[str] | None = None) -> dict[str, Any]:
    hints = hints or []
    rule = authority_rule(domain)
    tier = rule.get("tier", "unknown")
    tier_score = TIER_SCORES.get(tier, 0.52)
    type_floor = SOURCE_TYPE_FLOORS.get(source_type, 0.5)
    positive = sum(HINT_WEIGHTS.get(hint, 0.0) for hint in hints)
    negative = sum(NEGATIVE_HINTS.get(hint, 0.0) for hint in hints)
    base = max(tier_score, type_floor)
    score = min(max(base + positive + negative, 0.0), 0.99)
    return {
        "domain": (domain or "").lower(),
        "tier": tier,
        "ruleLabel": rule.get("label", "unclassified"),
        "tierScore": tier_score,
        "typeFloor": type_floor,
        "positiveHintBoost": round(positive, 4),
        "negativeHintPenalty": round(negative, 4),
        "score": round(score, 4),
    }


def authority_score(domain: str, source_type: str, hints: list[str] | None = None) -> float:
    return float(authority_breakdown(domain, source_type, hints).get("score") or 0.0)
